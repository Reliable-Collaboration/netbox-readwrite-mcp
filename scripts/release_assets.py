"""Assemble reproducible release filenames and a checksum manifest from CI builds."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import zipapp

ROOT = Path(__file__).resolve().parents[1]


def main():
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    companion = tomllib.loads((ROOT / "companion/pyproject.toml").read_text())["project"]["version"]
    if companion != version:
        raise ValueError("MCP and companion versions must match")
    output = ROOT / "release"
    output.mkdir(exist_ok=True)
    for package, directory in [
        ("netbox_readwrite_mcp", ROOT / "dist"),
        ("netbox_agent_api", ROOT / "companion/dist"),
    ]:
        for suffix in ["-py3-none-any.whl", ".tar.gz"]:
            filename = package + "-" + version + suffix
            shutil.copyfile(directory / filename, output / filename)
    with tempfile.TemporaryDirectory() as stage:
        shutil.copytree(
            ROOT / "src/netbox_readwrite_mcp",
            Path(stage) / "netbox_readwrite_mcp",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        zipapp.create_archive(
            stage,
            output / "netbox-readwrite-mcp.pyz",
            interpreter="/usr/bin/env python3",
            main="netbox_readwrite_mcp.server:main",
            compressed=True,
        )
    shutil.copyfile(ROOT / "packaging/compose.agent-api.yaml", output / "compose.agent-api.yaml")
    manifest = {
        "version": version,
        "netbox_version": "4.7.2",
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "image": "ghcr.io/reliable-collaboration/netbox-agent-api:" + version + "-netbox4.7.2",
    }
    (output / "release.json").write_text(json.dumps(manifest, indent=2) + "\n")
    assets = sorted(p for p in output.iterdir() if p.name != "SHA256SUMS")
    (output / "SHA256SUMS").write_text(
        "".join(hashlib.sha256(p.read_bytes()).hexdigest() + "  " + p.name + "\n" for p in assets)
    )
    print("Built release", version)


if __name__ == "__main__":
    main()
