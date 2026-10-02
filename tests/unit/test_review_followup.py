"""Adversarial recovery, replay, shared-key and asynchronous-job regressions."""

from contextlib import contextmanager
import fcntl
import json

import pytest

from netbox_readwrite_mcp.workspace import WorkspaceService
from netbox_readwrite_mcp.feedback import Feedback
from tests.unit.test_workspace import API


@pytest.fixture
def workspace(tmp_path):
    service = WorkspaceService(API(), tmp_path / "review.sqlite", "review", "agent", None)
    service.task = service.begin_task("review")["task_id"]
    yield service
    service.store.close()


def original_edit(s):
    return s.update_object(s.task, "original-key", "dcim/devices/", 1, s.api.etag(1), {"description": "B"})


def test_general_undo_detects_aba_during_current_read(workspace, monkeypatch):
    s = workspace
    op = original_edit(s)
    get = s.api.get
    armed = True

    def racing_get(path):
        nonlocal armed
        if armed and path == "dcim/devices/1/":
            armed = False
            s.api.change(1, {"description": "C"})
            s.api.change(1, {"description": "B"})
        return get(path)

    monkeypatch.setattr(s.api, "get", racing_get)
    result = s.undo_operation(op["id"], "undo-key-001")
    assert result["status"] == "conflicted"
    assert s.api.devices[1]["description"] == "B"
    assert s.api.patches == 1


def test_failed_undo_replay_retains_original_task_and_receipt(workspace, monkeypatch):
    s = workspace
    op = original_edit(s)
    request = s.api.request
    monkeypatch.setattr(
        s.api,
        "request",
        lambda method, path, *a, **kw: (
            {"status": 412, "body": {}, "headers": {}}
            if method == "PATCH"
            else request(method, path, *a, **kw)
        ),
    )
    first = s.undo_operation(op["id"], "undo-key-001")
    task_count = s.store.db.execute("SELECT count(*) FROM tasks").fetchone()[0]
    second = s.undo_operation(op["id"], "undo-key-001")
    assert first["status"] == second["status"] == "failed"
    assert second["replayed"] and first["correction"]["id"] == second["correction"]["id"]
    assert s.store.db.execute("SELECT count(*) FROM tasks").fetchone()[0] == task_count


def test_cross_tool_key_check_is_inside_lock(workspace, monkeypatch):
    s = workspace
    other = WorkspaceService(s.api, s.store.path, "review", "agent", None)
    task = other.begin_task("second client")["task_id"]
    original_lock = s.store.lock
    armed = True

    @contextmanager
    def interleaved_lock():
        nonlocal armed
        if armed:
            armed = False
            other.create_object(task, "shared-key-001", "dcim/devices/", {"name": "other"})
        with original_lock():
            yield

    monkeypatch.setattr(s.store, "lock", interleaved_lock)
    try:
        with pytest.raises(ValueError, match="Idempotency"):
            s.update_device(s.task, "shared-key-001", 1, s.api.etag(1), {"description": "B"})
        assert s.api.patches == 0
        assert s.store.db.execute("SELECT count(*) FROM operations").fetchone()[0] == 0
    finally:
        other.store.close()


def test_nested_store_lock_retains_outer_process_lock(workspace):
    with workspace.store.lock():
        with workspace.store.lock():
            pass
        with open(str(workspace.store.path) + ".lock") as independent:
            with pytest.raises(BlockingIOError):
                fcntl.flock(independent, fcntl.LOCK_EX | fcntl.LOCK_NB)


def test_acknowledged_jobs_allow_scheduled_work_and_guarded_cancellation(workspace, monkeypatch):
    s = workspace
    request = s.api.request
    state = {"status": "scheduled", "exists": True}
    job_path = "core/jobs/123/"

    def job_request(method, path, data=None, *a, **kw):
        if method == "GET" and path == job_path:
            return {
                "status": 200 if state["exists"] else 404,
                "body": {"status": {"value": state["status"]}},
                "headers": {},
            }
        if method == "POST" and path == "extras/scripts/1/":
            return {"status": 202, "body": {"url": s.api.url + "/api/" + job_path}, "headers": {}}
        if method == "POST" and path == "plugins/agent-support/native-delete/core.job/":
            state["exists"] = False
            return {"status": 200, "body": {"applied": True}, "headers": {}}
        return request(method, path, data, *a, **kw)

    monkeypatch.setattr(s.api, "request", job_request)
    op = s.execute_action(s.task, "schedule-key", "POST", "extras/scripts/1/", {})
    changed = s.update_device(s.task, "scheduled-edit", 1, s.api.etag(1), {"description": "B"})
    assert changed["state"] == "applied"
    assert s.get_operation(op["id"])["state"] == "job_scheduled"
    state["status"] = "running"
    with pytest.raises(RuntimeError, match="unresolved"):
        s.create_object(s.task, "blocked-create", "dcim/devices/", {})
    with pytest.raises(RuntimeError, match="unresolved"):
        s.execute_action(
            s.task, "wrong-cancel", "POST", "plugins/agent-support/native-delete/core.job/", {"id": 124}
        )
    # A known cancellation cannot bypass another unknown dispatch.
    unknown = s._resource_operation(op["id"]).copy()
    unknown.update(
        id="unrelated-unknown", operation_key="unrelated-unknown", state="uncertain", native_changes=[]
    )
    s._save(unknown, initial=True)
    with pytest.raises(RuntimeError, match="unresolved"):
        s.execute_action(
            s.task,
            "unsafe-cancel",
            "POST",
            "plugins/agent-support/native-delete/core.job/",
            {"id": 123, "apply": True},
        )
    unknown["state"] = "failed"
    s._save(unknown)
    cancelled = s.execute_action(
        s.task,
        "cancel-job-key",
        "POST",
        "plugins/agent-support/native-delete/core.job/",
        {"id": 123, "apply": True},
    )
    assert cancelled["state"] == "completed"
    s.reconcile()
    assert s.get_operation(op["id"])["state"] == "job_missing"
    assert s.create_object(s.task, "after-cancel-key", "dcim/devices/", {})["state"] == "applied"


def test_feedback_supports_device_receipts_and_safe_read_diagnostics(workspace, tmp_path):
    s = workspace
    op = s.update_device(s.task, "legacy-write-key", 1, s.api.etag(1), {"description": "PRIVATE_INVENTORY"})
    feedback = Feedback(s.store.path, tmp_path / "outbox.sqlite")
    result = feedback.submit("report-key-001", op["id"], "receipt-mismatch", "reconciled-receipt")
    assert result["diagnostic"]["operation"]["http_status"] == 200
    with s.store.lock():
        seq = s.store.event(
            "tool_call",
            {"tool": "get_schema", "is_error": True, "error": "PRIVATE_ERROR", "path": "PRIVATE_PATH"},
        )
    result = feedback.submit("report-read-001", f"event:{seq}", "discovery-gap", "discoverable-schema")
    assert result["diagnostic"]["tool"] == "get_schema"
    assert "PRIVATE" not in json.dumps(result)
    with pytest.raises(ValueError):
        feedback.submit("report-read-002", "event:99999999", "discovery-gap", "discoverable-schema")


def test_legacy_task_undo_cannot_reuse_general_operation_key(workspace):
    s = workspace
    original = s.update_device(s.task, "legacy-task-edit", 1, s.api.etag(1), {"description": "B"})
    other_task = s.begin_task("unrelated resource write")["task_id"]
    key = "task-undo:" + original["id"] + ":0"
    s.create_object(other_task, key, "dcim/devices/", {"name": "other"})
    with pytest.raises(ValueError, match="Idempotency"):
        s.undo_task(s.task)
    assert s.api.patches == 1
    assert s.api.devices[1]["description"] == "B"
