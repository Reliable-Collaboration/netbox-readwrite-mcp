"""Verify the release plugin bundle in an unmodified upstream NetBox lab image."""

import json
from pathlib import Path
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    image = json.loads((ROOT / "scripts/images.lock.json").read_text())["netbox"]["4.7.2"]["digest"]
    with tempfile.TemporaryDirectory() as stage:
        with tarfile.open(ROOT / "release/netbox-agent-api-container.tar.gz") as archive:
            archive.extractall(stage, filter="data")
        plugin = Path(stage) / "netbox-agent-api/plugin"
        subprocess.run(
            [
                "podman",
                "run",
                "--rm",
                "--network",
                "nbrw-audit-4-7-2",
                "--env-file",
                str(ROOT / ".lab/4.7.2/netbox.env"),
                "--volume",
                str(plugin) + ":/opt/netbox/agent-api:ro,z",
                "--env",
                "PYTHONPATH=/opt/netbox/agent-api",
                "--env",
                "NETBOX_CONFIGURATION=netbox_agent_api_configuration",
                "--entrypoint",
                "/opt/netbox/venv/bin/python",
                image,
                "/opt/netbox/netbox/manage.py",
                "shell",
                "-c",
                'from django.conf import settings; from django.urls import resolve; from importlib.metadata import version; import netbox_agent_api; assert "netbox_agent_api" in settings.PLUGINS; assert version("netbox-agent-api") == "0.4.0"; assert netbox_agent_api.__file__.startswith("/opt/netbox/agent-api/"); resolve("/api/plugins/agent-support/"); print("Upstream image plus release companion bundle: PASS")',
            ],
            check=True,
        )


if __name__ == "__main__":
    main()
