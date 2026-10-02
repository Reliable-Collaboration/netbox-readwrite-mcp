"""Receipts must distinguish absent audit evidence from absence of a mutation."""

import pytest

from netbox_readwrite_mcp.reporting import operation_outcome, with_reporting
from netbox_readwrite_mcp.server import call, error_result
from tests.unit.test_workspace import broad  # noqa: F401


@pytest.mark.parametrize("status", [200, 201, 204, 302])
def test_completed_never_proves_no_mutation(status):
    op = {"state": "completed", "method": "POST", "last_receipt": {"status": status}, "native_ids": []}
    result = operation_outcome(op)
    assert result["effect_evidence"] != "guarded_no_change"
    assert "read-only" in result["explanation"]
    if status == 201:
        assert result["effect_evidence"] == "server_reported_creation"
        assert "verify" in result["explanation"]


@pytest.mark.parametrize("state", ["accepted", "job_failed", "job_missing", "uncertain", "dispatched"])
def test_unresolved_or_job_states_do_not_become_creation_proof(state):
    assert (
        operation_outcome({"state": state, "last_receipt": {"status": 201}})["effect_evidence"]
        == "effects_require_verification"
    )


def test_reporting_does_not_rewrite_original_receipt():
    op = {"id": "a", "operation_key": "key", "state": "completed", "last_receipt": {"status": 201}}
    annotated = with_reporting({"found": True, "operation": op})
    assert "outcome" not in op
    assert annotated["operation"]["last_receipt"] == op["last_receipt"]
    assert annotated["operation"]["outcome"]["effect_evidence"] == "server_reported_creation"


def test_task_reports_unlogged_creation_and_retains_rejection_counts(broad):  # noqa: F811
    statuses = iter([400, 201, 200])
    original = broad.api.request
    broad.api.request = lambda method, path, *args, **kwargs: (
        {"status": next(statuses), "body": {"id": 91}, "headers": {}}
        if method == "POST"
        else original(method, path, *args, **kwargs)
    )
    for i in range(3):
        call(
            broad,
            "create_object",
            {
                "task_id": broad.task,
                "operation_key": f"report-{i}",
                "object_type": "devices",
                "data": {"name": "example"},
            },
        )
    summary = call(broad, "get_task", {"task_id": broad.task, "offset": 1, "limit": 1})
    assert summary["state_counts"] == {"failed": 1, "completed": 2}
    assert summary["effect_evidence_counts"] == {
        "attempt_rejected_or_abandoned": 1,
        "server_reported_creation": 1,
        "effects_require_verification": 1,
    }
    assert summary["operations"][0]["outcome"]["effect_evidence"] == "server_reported_creation"
    assert "NOT mean read-only" in summary["state_meanings"]["completed"]
    assert "outcome" not in broad.get_task(broad.task)["operations"][1]


def test_escaped_etag_error_teaches_exact_copy_without_rewriting_value(broad):  # noqa: F811
    value = 'W/\\"version\\"'
    params = {"name": "update_object", "arguments": {"expected_etag": value}}
    error = error_result(broad, params, ValueError("Stale expected_etag"))["structuredContent"]
    assert "literal backslashes" in error["action"]
    assert params["arguments"]["expected_etag"] == value
    assert error["code"] == "STALE_STATE"
