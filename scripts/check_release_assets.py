"""Exercise downloaded-format MCP assets without a checkout on their import path."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    release = ROOT / "release"
    manifest = json.loads((release / "release.json").read_text())
    for line in (release / "SHA256SUMS").read_text().splitlines():
        expected, name = line.split("  ", 1)
        assert hashlib.sha256((release / name).read_bytes()).hexdigest() == expected
    with zipfile.ZipFile(release / f"netbox_readwrite_mcp-{manifest['version']}-py3-none-any.whl") as wheel:
        assert (
            wheel.read("netbox_readwrite_mcp/agent-guide.md")
            == (ROOT / "src/netbox_readwrite_mcp/agent-guide.md").read_bytes()
        )
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)
        (path / "token").write_text("synthetic-offline-token")
        config = {
            "netbox_url": "https://netbox.invalid",
            "actor": "packaging-test",
            "token_file": "token",
            "journal": "journal.sqlite",
            "instance_id": "packaging-test",
        }
        (path / "config.json").write_text(json.dumps(config))
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}},
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "get_guidance", "arguments": {"topic": "native-imports-and-bulk-forms"}},
            },
        ]
        run = subprocess.run(
            [
                sys.executable,
                str(release / "netbox-readwrite-mcp.pyz"),
                "--config",
                str(path / "config.json"),
            ],
            input="".join(json.dumps(row) + "\n" for row in requests),
            capture_output=True,
            text=True,
            cwd=path,
            check=True,
        )
        rows = [json.loads(line) for line in run.stdout.splitlines()]
        assert rows[0]["result"]["serverInfo"]["version"] == manifest["version"]
        assert "get_guidance" in rows[0]["result"]["instructions"]
        assert "related_objects" in rows[1]["result"]["structuredContent"]["instructions"]
    print("Release checksums, wheel guidance and standalone MCP initialization/guidance: PASS")


if __name__ == "__main__":
    main()
