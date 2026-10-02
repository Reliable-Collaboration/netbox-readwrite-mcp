"""Receipts must distinguish absent audit evidence from absence of a mutation."""

import pytest

from netbox_readwrite_mcp.reporting import journal_summary_text, operation_outcome, with_reporting
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


def test_ready_to_quote_summary_counts_journal_receipts_not_tool_errors():
    operations = [
        {"state": "applied"},
        {"state": "failed"},
        {"state": "completed", "last_receipt": {"status": 201}},
        {"state": "completed", "last_receipt": {"status": 200}},
    ]
    summary = journal_summary_text(operations)
    assert summary.startswith("Journal records 4 operations (applied=1, completed=2, failed=1).")
    assert "does NOT mean read-only or no mutation" in summary
    assert "remains recorded after a successful correction" in summary
    assert "Completed receipts reporting HTTP 201 creation: 1." in summary
    assert "rejected calls before journaling are not included" in summary
    assert journal_summary_text([]).startswith("Journal records 0 operations.")


@pytest.mark.parametrize("state", ["accepted", "job_failed", "job_missing", "uncertain", "dispatched"])
def test_unresolved_or_job_states_do_not_become_creation_proof(state):
    assert (
        operation_outcome({"state": state, "last_receipt": {"status": 201}})["effect_evidence"]
        == "effects_require_verification"
    )


def test_reporting_does_not_rewrite_original_receipt():
    op = {"id": "a", "operation_key": "key", "state": "completed", "last_receipt": {"status": 201}}
    annotated = with_reporting({"found": True, "operation": op})
    assert "outcome_details" not in op
    assert annotated["operation"]["last_receipt"] == op["last_receipt"]
    assert annotated["operation"]["outcome_details"]["effect_evidence"] == "server_reported_creation"


def test_legacy_outcome_string_survives_public_receipt_enrichment(broad):  # noqa: F811
    before = broad.read_device(1)
    created = call(
        broad,
        "update_device",
        {
            "task_id": broad.task,
            "operation_key": "legacy-reporting",
            "device_id": 1,
            "expected_etag": before["etag"],
            "changes": {"description": "receipt compatibility"},
        },
    )
    operation = call(broad, "get_operation", {"operation_id": created["id"]})
    full = call(broad, "get_task", {"task_id": broad.task, "full": True})
    compact = call(broad, "get_task", {"task_id": broad.task})
    assert compact["operations"][0]["native_change_count"] == 1
    for receipt in (created, operation, full["operations"][0]):
        assert receipt["outcome"] == receipt["state"] == "applied"
        assert receipt["outcome_details"]["effect_evidence"] == "native_changes_correlated"
    assert "outcome_details" not in broad.get_operation(created["id"])


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
    assert summary["operations"][0]["outcome_details"]["effect_evidence"] == "server_reported_creation"
    assert "NOT mean read-only" in summary["state_meanings"]["completed"]
    assert summary["summary_text"].startswith("Journal records 3 operations (completed=2, failed=1).")
    assert "outcome_details" not in broad.get_task(broad.task)["operations"][1]


def test_escaped_etag_error_teaches_exact_copy_without_rewriting_value(broad):  # noqa: F811
    value = 'W/\\"version\\"'
    params = {"name": "update_object", "arguments": {"expected_etag": value}}
    error = error_result(broad, params, ValueError("Stale expected_etag"))["structuredContent"]
    assert "literal backslashes" in error["action"]
    assert params["arguments"]["expected_etag"] == value
    assert error["code"] == "STALE_STATE"
