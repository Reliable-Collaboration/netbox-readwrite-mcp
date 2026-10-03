#!/usr/bin/env python3
"""Submit and triage integration issues with the operator's existing gh login.

Never reads NetBox credentials or journal files. A diagnostic_report JSON file
is validated by an exact allowlist before attaching. No raw recovery bundles.
"""

import argparse
import json
from pathlib import Path
import subprocess

REPOSITORY = "Reliable-Collaboration/netbox-readwrite-mcp"


def diagnostic(path):
    data = json.loads(Path(path).read_text())
    if set(data) != {
        "schema_version",
        "server_version",
        "netbox_target",
        "operation",
        "issue_repository",
        "guidance",
    }:
        raise ValueError("Expected diagnostic_report output, not a journal or recovery bundle")
    if data["operation"] is not None and set(data["operation"]) != {
        "id",
        "state",
        "http_status",
        "native_ids",
        "error_type",
    }:
        raise ValueError("Unexpected diagnostic fields")
    # Rebuild rather than forwarding user-controlled metadata/guidance.
    return {k: data[k] for k in ("schema_version", "server_version", "netbox_target", "operation")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    report = commands.add_parser("submit")
    report.add_argument("--title", required=True)
    report.add_argument("--body-file", required=True, help="Reviewed, sanitized reproduction text")
    report.add_argument("--diagnostic", required=True)
    commands.add_parser("list")
    for action in ("view", "comment"):
        command = commands.add_parser(action)
        command.add_argument("number", type=int)
        if action == "comment":
            command.add_argument("--body-file", required=True)
    args = parser.parse_args()
    command = ["gh", "issue", "create" if args.action == "submit" else args.action, "--repo", REPOSITORY]
    body = None
    if args.action == "submit":
        body = (
            Path(args.body_file).read_text()
            + "\n\nDiagnostic report:\n```json\n"
            + json.dumps(diagnostic(args.diagnostic), indent=2)
            + "\n```\n"
        )
        command += ["--title", args.title, "--body-file", "-"]
    elif args.action in {"view", "comment"}:
        command.append(str(args.number))
        if args.action == "comment":
            command += ["--body-file", args.body_file]
        else:
            command += ["--comments"]
    subprocess.run(command, input=body, text=True, check=True)


if __name__ == "__main__":
    main()
