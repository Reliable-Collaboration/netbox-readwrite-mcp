"""Fixed-repository publication, privacy and durable lost-response reconciliation."""

import asyncio
import json
import sqlite3
import subprocess
import sys
import uuid
from types import SimpleNamespace

import pytest

from netbox_readwrite_mcp.feedback import Feedback, REPOSITORY


@pytest.fixture
def journal(tmp_path):
    path = tmp_path / "netbox.sqlite"
    operation = str(uuid.uuid4())
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE resource_operations(id TEXT PRIMARY KEY, document TEXT)")
        db.execute(
            "INSERT INTO resource_operations VALUES (?,?)",
            (
                operation,
                json.dumps(
                    {
                        "state": "failed",
                        "requested": {"password": "PRIVATE_SECRET", "name": "PRIVATE_ASSET"},
                        "last_receipt": {"status": 400, "body": "PRIVATE_RESPONSE"},
                        "actor": "PRIVATE_ACTOR",
                    }
                ),
            ),
        )
    return path, operation


def test_feedback_publication_is_fixed_scoped_private_and_replayable(journal, tmp_path):
    path, operation = journal
    calls = []

    def gh(command, **kwargs):
        calls.append((command, kwargs))
        assert command[-2:] == ["--repo", REPOSITORY]
        assert command[:3] == ["gh", "issue", "create"]
        assert command[-4:-2] == ["--body-file", "-"]
        assert "PRIVATE" not in kwargs["input"]
        assert operation in kwargs["input"]
        return SimpleNamespace(returncode=0, stdout=f"https://github.com/{REPOSITORY}/issues/123\n")

    feedback = Feedback(path, tmp_path / "outbox", True, gh)
    result = feedback.submit("report-first", operation, "unexpected-rejection", "successful-operation")
    assert result["state"] == "published" and result["number"] == 123
    assert (
        Feedback(path, tmp_path / "outbox", True, gh).submit(
            "report-first", operation, "unexpected-rejection", "successful-operation"
        )
        == result
    )
    assert len(calls) == 1
    with pytest.raises(ValueError, match="different report"):
        feedback.submit("report-first", operation, "qualification", "feedback-roundtrip")
    with pytest.raises(ValueError):
        feedback.submit("report-wrong", operation, "PRIVATE_SECRET", "successful-operation")
    with pytest.raises(ValueError):
        feedback.submit("report-wrong", str(uuid.uuid4()), "qualification", "feedback-roundtrip")
    assert len(calls) == 1
    assert (tmp_path / "outbox").stat().st_mode & 0o777 == 0o600


def test_lost_github_response_never_republishes_and_marker_reconciles(journal, tmp_path):
    path, operation = journal
    creates = []

    def gh(command, **kwargs):
        if command[2] == "create":
            creates.append(kwargs["input"])
            raise subprocess.TimeoutExpired(command, 45)
        if command[2] == "list":
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(
                    [
                        {
                            "number": 321,
                            "url": f"https://github.com/{REPOSITORY}/issues/321",
                            "body": creates[0],
                        }
                    ]
                ),
            )
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"number": 321, "state": "OPEN", "comments": [{"body": "Maintainer reply"}]}),
        )

    feedback = Feedback(path, tmp_path / "outbox", True, gh)
    result = feedback.submit("report-lost", operation, "qualification", "feedback-roundtrip")
    assert result["state"] == "uncertain"
    assert feedback.submit("report-lost", operation, "qualification", "feedback-roundtrip") == result
    result = feedback.get("report-lost", reconcile=True)
    assert result["state"] == "published" and result["number"] == 321
    assert feedback.read("report-lost")["issue"]["comments"][0]["body"] == "Maintainer reply"
    assert len(creates) == 1


def test_publication_requires_operator_enable_and_does_not_read_arbitrary_paths(journal, tmp_path):
    path, operation = journal
    feedback = Feedback(path, tmp_path / "outbox", runner=lambda *a, **kw: pytest.fail("Must not invoke gh"))
    assert (
        feedback.submit("report-draft", operation, "qualification", "feedback-roundtrip")["state"] == "draft"
    )
    with pytest.raises(ValueError):
        feedback.submit("report-path", "/etc/passwd", "qualification", "feedback-roundtrip")
    with pytest.raises(ValueError, match="separate"):
        Feedback(path, path)


def test_feedback_stdio_official_sdk_schema_and_draft(journal, tmp_path):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    path, operation = journal

    async def check():
        params = StdioServerParameters(
            command=sys.executable,
            args=[
                "-m",
                "netbox_readwrite_mcp.feedback",
                "--journal",
                str(path),
                "--outbox",
                str(tmp_path / "outbox"),
            ],
        )
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert {t.name for t in tools.tools} == {"report_issue", "reconcile_report", "read_report"}
            result = await session.call_tool(
                "report_issue",
                {
                    "operation_key": "sdk-report",
                    "operation_id": operation,
                    "category": "qualification",
                    "expected": "feedback-roundtrip",
                },
            )
            assert not result.isError
            assert json.loads(result.content[0].text)["state"] == "draft"
            invalid = await session.call_tool(
                "report_issue",
                {
                    "operation_key": "sdk-report",
                    "operation_id": operation,
                    "category": "arbitrary body",
                    "expected": "feedback-roundtrip",
                },
            )
            assert invalid.isError

    asyncio.run(check())
