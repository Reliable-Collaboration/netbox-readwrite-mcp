"""Interactive first-run configuration; credentials never enter command arguments."""

import argparse
import getpass
import json
import os
from pathlib import Path
import sys
import uuid

from .config import load_config, validate_config


def default_config():
    return (
        Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
        / "netbox-readwrite-mcp/config.json"
    )


def client_entry(config, client="generic"):
    command = str(Path(sys.executable).parent / "netbox-readwrite-mcp")
    args = ["--config", str(Path(config).resolve())]
    if sys.argv[0].endswith(".pyz"):
        command = sys.executable
        args.insert(0, str(Path(sys.argv[0]).resolve()))
    if client == "opencode":
        return {"mcp": {"netbox": {"type": "local", "command": [command, *args], "enabled": True}}}
    return {"mcpServers": {"netbox": {"command": command, "args": args}}}


def configure(path, url, actor, token, read_only=False):
    path = Path(path).expanduser().resolve()
    cfg = validate_config(
        {
            "netbox_url": url,
            "actor": actor,
            "token_file": "token",
            "journal": "state/journal.sqlite",
            "instance_id": str(uuid.uuid4()),
            "read_only": read_only,
        }
    )
    token = token.strip()
    if not token or "\n" in token or "\r" in token:
        raise ValueError("Supply one non-empty API token")
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if path.parent.stat().st_mode & 0o077:
        raise ValueError("Configuration directory must be private (chmod 700)")
    # Track ownership only after exclusive creation; include flush/close failures.
    created = []
    try:
        with path.open("x") as output:
            created.append(path)
            os.chmod(path, 0o600)
            secret_path = path.parent / "token"
            with secret_path.open("x") as secret:
                created.append(secret_path)
                os.chmod(secret_path, 0o600)
                secret.write(token + "\n")
            output.write(json.dumps(cfg, indent=2) + "\n")
    except BaseException:
        for owned in reversed(created):
            owned.unlink(missing_ok=True)
        raise
    return path


def doctor(path):
    from .api import NetBox
    from .compatibility import QUALIFIED_VERSIONS, normalization_profile

    cfg = load_config(path)
    api = NetBox(cfg["netbox_url"], Path(cfg["token_file"]).read_text())
    version = api.get("status/")["body"]["netbox-version"]
    normalization_profile(version)
    api.get("plugins/agent-support/")
    api.get("core/object-changes/?limit=1&fields=id")
    return {
        "netbox_version": version,
        "qualified": version in QUALIFIED_VERSIONS,
        "tested_versions": list(QUALIFIED_VERSIONS),
        "companion": "available",
        "history": "readable",
        "read_only": cfg.get("read_only", False),
    }


def main(argv=None):
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["configure", "doctor", "client-config"])
    parser.add_argument("--config", type=Path, default=default_config())
    parser.add_argument("--netbox-url")
    parser.add_argument("--actor")
    parser.add_argument(
        "--token-file", type=Path, help="Read an existing private token file instead of prompting"
    )
    parser.add_argument("--read-only", action="store_true")
    parser.add_argument("--client", choices=["generic", "opencode"], default="generic")
    args = parser.parse_args(argv)
    try:
        if args.action == "configure":
            if args.config.expanduser().exists():
                raise ValueError(
                    "Configuration already exists; use client-config or doctor. Existing identity was preserved."
                )
            path = configure(
                args.config,
                args.netbox_url or input("NetBox base URL: "),
                args.actor or input("NetBox username: "),
                args.token_file.read_text()
                if args.token_file
                else getpass.getpass("NetBox API token (hidden): "),
                args.read_only,
            )
            print("Configuration saved. Add this entry to your MCP client:", file=sys.stderr)
            print(json.dumps(client_entry(path, args.client), indent=2))
            print(
                "Check the connection with: netbox-readwrite-mcp doctor --config " + str(path),
                file=sys.stderr,
            )
        elif args.action == "client-config":
            load_config(args.config)
            print(json.dumps(client_entry(args.config, args.client), indent=2))
        else:
            print(json.dumps(doctor(args.config), indent=2))
    except Exception as exc:
        # HTTP errors and file contents can contain private deployment data.
        if isinstance(exc, (ValueError, FileExistsError)):
            parser.exit(1, str(exc) + "\n")
        parser.exit(
            1,
            "Setup/check failed ("
            + type(exc).__name__
            + "). Check paths, token, NetBox permissions and companion installation.\n",
        )
