"""Enable the companion in an explicitly selected NetBox configuration file."""

import argparse
import os
from pathlib import Path
import stat
import tempfile

MARKER = "# netbox-agent-api: managed enablement"
SNIPPET = """
# netbox-agent-api: managed enablement
PLUGINS = list(globals().get("PLUGINS", []))
if "netbox_agent_api" not in PLUGINS:
    PLUGINS.append("netbox_agent_api")
"""


def enable(path):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Select the real configuration file, not a symbolic link")
    old = path.read_bytes() if path.exists() else b""
    if MARKER.encode() in old:
        return False
    updated = old.rstrip() + b"\n" + SNIPPET.encode()
    compile(updated, str(path), "exec")  # Never execute operator configuration here.
    metadata = path.stat() if path.exists() else None
    if metadata and (metadata.st_uid != os.geteuid()):
        raise ValueError("Run as the configuration file owner to preserve ownership")
    if old:
        backup = path.with_name(path.name + ".before-agent-api")
        with backup.open("xb") as dest:
            os.chmod(backup, 0o600)
            dest.write(old)
    fd, temporary = tempfile.mkstemp(prefix=".agent-api-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as dest:
            os.fchmod(dest.fileno(), stat.S_IMODE(metadata.st_mode) if metadata else 0o600)
            if metadata:
                os.fchown(dest.fileno(), metadata.st_uid, metadata.st_gid)
            dest.write(updated)
            dest.flush()
            os.fsync(dest.fileno())
        if (path.read_bytes() if path.exists() else b"") != old:
            raise ValueError("Configuration changed during enablement; retry after inspection")
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, required=True, help="Existing configuration.py or the deployment's plugins.py"
    )
    args = parser.parse_args()
    try:
        changed = enable(args.config)
    except (OSError, ValueError, SyntaxError) as exc:
        parser.exit(
            1, "Enablement failed (" + type(exc).__name__ + "); inspect the selected configuration file.\n"
        )
    print("Companion enabled." if changed else "Companion already enabled.")
    print("Restart NetBox web and worker processes using your deployment manager.")


if __name__ == "__main__":
    main()
