"""Seed ONLY the isolated nbrw-audit lab; never accepts a production URL."""

import json
import os
from pathlib import Path
import secrets
import subprocess
import uuid
from netbox_readwrite_mcp.api import NetBox

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".lab"
os.umask(0o077)
STATE.mkdir(mode=0o700, exist_ok=True)
admin = json.loads((ROOT / ".lab/secrets.json").read_text())["token"]
api = NetBox("http://127.0.0.1:18790", admin)


def ensure(path, name, data):
    rows = api.get(path + "?name=" + name)["body"]["results"]
    if rows:
        return rows[0]["id"]
    response = api.request("POST", path, {"name": name, **data})
    if response["status"] != 201:
        raise RuntimeError(response)
    return response["body"]["id"]


site = ensure("dcim/sites/", "audit-site", {"slug": "audit-site"})
manufacturer = ensure("dcim/manufacturers/", "audit-vendor", {"slug": "audit-vendor"})
rows = api.get("dcim/device-types/?slug=audit-type")["body"]["results"]
if rows:
    device_type = rows[0]["id"]
else:
    result = api.request(
        "POST",
        "dcim/device-types/",
        {"model": "audit-type", "slug": "audit-type", "manufacturer": manufacturer},
    )
    assert result["status"] == 201, result
    device_type = result["body"]["id"]
role = ensure("dcim/device-roles/", "audit-role", {"slug": "audit-role", "color": "607d8b"})
fixtures = {"site": site, "type": device_type, "role": role}
outside = ensure(
    "dcim/devices/",
    "audit-outside-scope",
    {"site": site, "device_type": device_type, "role": role, "status": "active"},
)
(STATE / "outside-id").write_text(str(outside))

ids = []
for name in ["audit-target", "audit-secondary"]:
    found = api.get("dcim/devices/?name=" + name)["body"]["results"]
    if found:
        ids.append(found[0]["id"])
    else:
        response = api.request(
            "POST",
            "dcim/devices/",
            {
                "name": name,
                "site": fixtures["site"],
                "device_type": fixtures["type"],
                "role": fixtures["role"],
                "status": "active",
                "description": "A",
            },
        )
        assert response["status"] == 201, response
        ids.append(response["body"]["id"])
token_path = STATE / "token"
if not token_path.exists():
    token_path.write_text(secrets.token_hex(20))
script = """
from django.contrib.auth import get_user_model
from users.models import Token,ObjectPermission
from core.models import ObjectType
u,_=get_user_model().objects.get_or_create(username='audit-agent',defaults={'is_superuser':False})
Token.objects.get_or_create(plaintext=TOKEN,defaults={'token':TOKEN,'version':1,'user':u,'write_enabled':True})
p,_=ObjectPermission.objects.update_or_create(name='audit-device-edits',defaults={'actions':['view','change'],'constraints':{'id__in':IDS}})
p.users.add(u);p.object_types.add(ObjectType.objects.get(app_label='dcim',model='device'))
p,_=ObjectPermission.objects.get_or_create(name='audit-history',defaults={'actions':['view']})
p.users.add(u);p.object_types.add(ObjectType.objects.get(app_label='core',model='objectchange'))
print('Restricted direct-write lab identity ready')
""".replace("TOKEN", repr(token_path.read_text().strip())).replace("IDS", repr(ids))
subprocess.run(
    [
        "podman",
        "exec",
        "-i",
        "nbrw-audit-netbox",
        "/opt/netbox/venv/bin/python",
        "/opt/netbox/netbox/manage.py",
        "shell",
    ],
    input=script,
    text=True,
    check=True,
)
config_path = STATE / "config.json"
config = {
    "netbox_url": api.url,
    "token_file": str(token_path),
    "journal": str(STATE / "journal.sqlite"),
    "instance_id": str(uuid.uuid4()),
    "actor": "audit-agent",
    "allowed_device_ids": ids,
}
if config_path.exists():
    config["instance_id"] = json.loads(config_path.read_text())["instance_id"]
config_path.write_text(json.dumps(config, indent=2) + "\n")
print("Config:", config_path)
print("Synthetic device IDs:", ids)
