#!/usr/bin/env python3
"""Isolated disposable Podman lab. No dependencies outside Python + Podman."""

import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
VERSION = os.environ.get("NETBOX_RW_TEST_VERSION", "4.7.1")
PORTS = {"4.6.10": 18860, "4.7.0": 18870, "4.7.1": 18871}
if VERSION not in PORTS:
    raise ValueError("NETBOX_RW_TEST_VERSION must select a pinned lab version: " + ", ".join(PORTS))
PORT = PORTS[VERSION]
URL = f"http://127.0.0.1:{PORT}"
STATE = ROOT / ".lab" / VERSION
PREFIX = "nbrw-audit-" + VERSION.replace(".", "-")
LABEL = "io.netbox-readwrite-mcp.project=" + PREFIX


def cmd(*args, **kw):
    return subprocess.run(list(args), check=True, **kw)


def pod(*args, **kw):
    return cmd("podman", *args, **kw)


def config():
    return json.loads((STATE / "secrets.json").read_text())


def setup():
    (ROOT / ".lab").mkdir(mode=0o700, exist_ok=True)
    STATE.mkdir(mode=0o700, exist_ok=True)
    if not (STATE / "secrets.json").exists():
        data = {k: secrets.token_hex(32) for k in ["db_password", "secret_key", "pepper"]}
        data["token"] = secrets.token_hex(20)
        (STATE / "secrets.json").write_text(json.dumps(data))
        (STATE / "secrets.json").chmod(0o600)
    c = config()
    env = {
        "DB_HOST": PREFIX + "-postgres",
        "DB_NAME": "netbox",
        "DB_USER": "netbox",
        "DB_PASSWORD": c["db_password"],
        "SECRET_KEY": c["secret_key"],
        "API_TOKEN_PEPPER_1": c["pepper"],
        "REDIS_HOST": PREFIX + "-valkey",
        "REDIS_CACHE_HOST": PREFIX + "-valkey",
        "REDIS_DATABASE": "0",
        "REDIS_CACHE_DATABASE": "1",
        "SKIP_SUPERUSER": "true",
        "CHANGELOG_RETENTION": "0",
        "COPILOT_ENABLED": "false",
        "ISOLATED_DEPLOYMENT": "true",
        "ALLOWED_HOSTS": "*",
    }
    (STATE / "netbox.env").write_text("".join(f"{k}={v}\n" for k, v in env.items()))
    (STATE / "netbox.env").chmod(0o600)
    (STATE / "postgres.env").write_text(
        f"POSTGRES_DB=netbox\nPOSTGRES_USER=netbox\nPOSTGRES_PASSWORD={c['db_password']}\n"
    )
    (STATE / "postgres.env").chmod(0o600)
    lock = json.loads((ROOT / "scripts/images.lock.json").read_text())
    selected = {key: lock[key] for key in ("postgres", "valkey")}
    selected["netbox"] = lock["netbox"][VERSION]
    manifest = {}
    for key, spec in selected.items():
        image = spec["digest"]
        if subprocess.run(["podman", "image", "exists", image]).returncode:
            pod("pull", image)
        info = json.loads(pod("image", "inspect", image, capture_output=True, text=True).stdout)[0]
        manifest[key] = {**spec, "id": info["Id"]}
    (STATE / "runtime-images.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def start():
    images = setup()
    if subprocess.run(["podman", "network", "exists", PREFIX]).returncode:
        pod("network", "create", "--label", LABEL, PREFIX)

    def run(name, key, args, command=()):
        name = PREFIX + "-" + name
        if subprocess.run(["podman", "container", "exists", name]).returncode == 0:
            pod("start", name)
            return
        pod(
            "run",
            "-d",
            "--name",
            name,
            "--label",
            LABEL,
            "--network",
            PREFIX,
            *args,
            images[key]["digest"],
            *command,
        )

    pod("volume", "create", "--label", LABEL, PREFIX + "-db", capture_output=True)
    run(
        "postgres",
        "postgres",
        ["--env-file", str(STATE / "postgres.env"), "-v", PREFIX + "-db:/var/lib/postgresql"],
    )
    run("valkey", "valkey", [], ["valkey-server", "--appendonly", "yes"])
    run(
        "netbox",
        "netbox",
        ["--env-file", str(STATE / "netbox.env"), "-p", f"127.0.0.1:{PORT}:8080", "--memory", "2g"],
    )
    print("Started. Run python3 scripts/lab.py ready, then bootstrap.", flush=True)


def ready():
    for _ in range(180):
        try:
            with urllib.request.urlopen(URL + "/login/", timeout=3) as r:
                if r.status == 200:
                    print("NetBox ready")
                    return
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError("NetBox did not become ready; inspect project logs")


def bootstrap():
    c = config()
    if "admin_password" not in c:
        c["admin_password"] = secrets.token_urlsafe(24)
        (STATE / "secrets.json").write_text(json.dumps(c))
    source = """
from django.contrib.auth import get_user_model
from users.models import Token
u,_ = get_user_model().objects.get_or_create(username='audit-admin', defaults={'is_superuser':True})
u.set_password(PASSWORD)
u.save()
Token.objects.get_or_create(plaintext=TOKEN, defaults={'token':TOKEN, 'version':1, 'user':u, 'write_enabled':True, 'description':'Disposable lab bootstrap'})
print('Lab API identity ready')
""".replace("TOKEN", repr(c["token"])).replace("PASSWORD", repr(c["admin_password"]))
    pod(
        "exec",
        "-i",
        PREFIX + "-netbox",
        "/opt/netbox/venv/bin/python",
        "/opt/netbox/netbox/manage.py",
        "shell",
        input=source,
        text=True,
    )
    image = json.loads((ROOT / "scripts/images.lock.json").read_text())["netbox"][VERSION]["digest"]
    if subprocess.run(["podman", "container", "exists", PREFIX + "-worker"]).returncode:
        pod(
            "run",
            "-d",
            "--name",
            PREFIX + "-worker",
            "--label",
            LABEL,
            "--network",
            PREFIX,
            "--env-file",
            str(STATE / "netbox.env"),
            "--memory",
            "1g",
            image,
            "/opt/netbox/venv/bin/python",
            "/opt/netbox/netbox/manage.py",
            "rqworker",
        )


def stop():
    # Exact names only; preserve data and evidence.
    for suffix in ["worker", "netbox", "valkey", "postgres"]:
        name = PREFIX + "-" + suffix
        if subprocess.run(["podman", "container", "exists", name]).returncode == 0:
            pod("stop", name)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["up", "ready", "bootstrap", "stop"])
    a = p.parse_args()
    {"up": start, "ready": ready, "bootstrap": bootstrap, "stop": stop}[a.action]()
