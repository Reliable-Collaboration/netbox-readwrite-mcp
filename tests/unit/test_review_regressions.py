"""Regression contracts for the bed414e review; assertions describe correct behavior."""

from unittest.mock import patch
import pytest
from netbox_readwrite_mcp.service import Service


@pytest.mark.parametrize("timestamps", [(200.0, 100.0), (100.0, 100.0)])
def test_task_undo_uses_durable_execution_order(service, tmp_path, timestamps):
    task = service.begin_task("Clock-independent task")["task_id"]
    ids = []
    for index, (timestamp, value) in enumerate(zip(timestamps, ["B", "C"])):
        with patch("netbox_readwrite_mcp.service.time.time", return_value=timestamp):
            op = service.update_device(
                task, f"clock-key-{index}", 1, service.read_device(1)["etag"], {"description": value}
            )
            ids.append(op["id"])
    # A new connection proves ordering survives process lifetime.
    reopened = Service(service.api, tmp_path / "journal.sqlite", "lineage", "agent", [1, 2])
    try:
        assert [r["id"] for r in reopened.get_task(task)["operations"]] == ids
        assert reopened.undo_task(task)["status"] == "undone"
        assert reopened.read_device(1)["values"]["description"] == "A"
    finally:
        reopened.store.close()


@pytest.mark.parametrize("report", ["observability", "recovery_bundle", "export"])
@pytest.mark.parametrize("mutation", ["insert", "state"])
def test_evidence_reads_use_one_snapshot(service, edit, tmp_path, report, mutation):
    op = edit()
    writer = Service(service.api, tmp_path / "journal.sqlite", "lineage", "agent", [1, 2])
    connection = service.store.db

    class CommitBetweenReads:
        fired = False

        def execute(self, sql, *args):
            if sql == "SELECT * FROM operations" and not self.fired:
                self.fired = True
                with writer.store.lock():
                    if mutation == "state":
                        writer.store.set_state(op["id"], "applied", receipt={"review": "concurrent receipt"})
                    else:
                        writer.update_device(
                            op["task_id"],
                            "concurrent-new-key",
                            1,
                            writer.read_device(1)["etag"],
                            {"serial": "new"},
                        )
            return connection.execute(sql, *args)

        def __getattr__(self, name):
            return getattr(connection, name)

    proxy = CommitBetweenReads()
    service.store.db = proxy
    try:
        if report == "observability":
            result = service.observability()
            assert result["states"] == {"applied": 1}
            assert result["integrity"]["integrity"] == "verified"
        elif report == "recovery_bundle":
            result = service.recovery_bundle(op["id"])
            assert result["operation"]["last_receipt"]["status"] == 200
        else:
            result = service.store.export()
            assert len(result["operations"]) == 1
            assert not any("concurrent receipt" in row["payload"] for row in result["events"])
        assert proxy.fired
        assert not connection.in_transaction
        assert service.store.verify()["integrity"] == "verified"
    finally:
        service.store.db = connection
        writer.store.close()


def test_nested_snapshot_does_not_commit_enclosing_transaction(service):
    with pytest.raises(RuntimeError, match="rollback"):
        with service.store.transaction():
            service.store.event("temporary", {})
            with service.store.snapshot():
                assert service.store.verify()["integrity"] == "verified"
                assert service.store.db.in_transaction
            raise RuntimeError("rollback")
    assert service.store.db.execute("SELECT count(*) FROM events").fetchone()[0] == 0


@pytest.mark.parametrize("field", ["description", "serial"])
@pytest.mark.parametrize("failure", ["response_loss", "hard_exit"])
def test_normalized_intent_reconciles_after_lost_response(service, field, failure):
    task = service.begin_task("Normalized write")["task_id"]

    def lose(point):
        if point == "after_response":
            if failure == "hard_exit":
                raise SystemExit(93)
            raise ConnectionResetError("Lost committed response")

    service.fault = lose
    args = (task, "normalized-key", 1, service.read_device(1)["etag"], {field: "  B \n"})
    if failure == "hard_exit":
        with pytest.raises(SystemExit):
            service.update_device(*args)
    else:
        assert service.update_device(*args)["state"] == "uncertain"
    service.fault = lambda _: None
    service.reconcile()
    op = service.find_operation("normalized-key")["operation"]
    assert op["state"] == "applied"
    assert op["requested"] == {field: "  B \n"}
    assert op["normalized_requested"] == {field: "B"}
    assert op["after_values"] == {field: "B"}
    assert service.update_device(*args)["id"] == op["id"]
    assert service.undo_operation(op["id"], "normalized-undo")["status"] == "applied"


@pytest.mark.parametrize("field,raw", [("description", " A \n"), ("serial", " \t")])
def test_normalization_to_noop_never_dispatches(service, edit, field, raw):
    assert edit({field: raw})["state"] == "no_change"
    assert service.api.patches == 0


@pytest.mark.parametrize("field", ["description", "serial"])
def test_unrestorable_previous_values_refused_before_dispatch(service, edit, field):
    service.api.devices[1][field] = "  old  "
    with pytest.raises(ValueError, match="Unrestorable previous value"):
        edit({field: "new"})
    assert service.api.patches == 0
    assert service.api.devices[1][field] == "  old  "


@pytest.mark.parametrize("newer", ["A", "C"])
def test_response_requery_does_not_rewrite_committed_effect(service, edit, newer):
    request = service.api.request

    def raced(*args, **kwargs):
        receipt = request(*args, **kwargs)
        service.api.change(1, {"description": newer})
        receipt["body"] = service.api.get("dcim/devices/1/")["body"]
        return receipt

    service.api.request = raced
    op = edit()
    assert op["state"] == "applied"
    assert op["after_values"] == {"description": "B"}
    assert op["last_receipt"]["body"]["description"] == newer
    assert op["native_id"] == 1
    assert service.preview_undo(op["id"])["status"] == "conflicted"


@pytest.mark.parametrize("legacy_state", ["no_change", "applied_unverified", "uncertain"])
def test_legacy_response_derived_expectations_are_repaired(service, edit, legacy_state):
    from netbox_readwrite_mcp.store import encode

    op = edit({"description": " B "})
    service.store.set_state(
        op["id"],
        legacy_state,
        native_id=None,
        request_id=None,
        after_values=encode({"description": "A" if legacy_state == "no_change" else " B "}),
    )
    service.reconcile()
    repaired = service.get_operation(op["id"])
    assert repaired["state"] == "applied"
    assert repaired["after_values"] == {"description": "B"}
    assert repaired["native_id"] == 1
    assert service.undo_operation(op["id"], "repaired-undo-key")["status"] == "applied"


def legacy_edit(service, before, requested, after, reverses=None):
    """Build the old durable record format, without using current write guards."""
    import time
    import uuid
    from netbox_readwrite_mcp.store import encode

    task = service.begin_task("Legacy fixture")["task_id"]
    op_id = str(uuid.uuid4())
    service.api.devices[1]["description"] = before
    service.api.change(1, {"description": after, "changelog_message": "netbox-rw:" + op_id}, actor="agent")
    record = service.api.rows[-1]
    row = {
        "id": op_id,
        "operation_key": op_id,
        "fingerprint": "legacy-fixture",
        "task_id": task,
        "device_id": 1,
        "requested": encode({"description": requested}),
        "before_values": encode({"description": before}),
        "after_values": encode({"description": requested}),
        "before_etag": "legacy-etag",
        "state": "prepared",
        "request_id": None,
        "native_id": None,
        "reverses": reverses,
        "created": time.time(),
        "updated": time.time(),
    }
    with service.store.lock(), service.store.transaction():
        service.store.db.execute(
            "INSERT INTO operations VALUES(" + ",".join("?" for _ in row) + ")", tuple(row.values())
        )
        service.store.event("prepared", row, op_id)
    service.store.set_state(
        op_id,
        "applied",
        request_id=record["request_id"],
        native_id=record["id"],
        after_values=encode({"description": after}),
    )
    return service.get_operation(op_id)


def test_legacy_inverse_that_cannot_roundtrip_is_not_dispatched(service):
    op = legacy_edit(service, " old ", "B", "B")
    result = service.undo_operation(op["id"], "legacy-undo-key")
    assert result["status"] == "unsupported"
    assert result["inverse"] == {"description": " old "}
    assert result["warning"]
    assert service.api.patches == 0


def test_legacy_inexact_correction_never_counts_as_undone(service):
    original = legacy_edit(service, " old ", "B", "B")
    correction = legacy_edit(service, "B", " old ", "old", reverses=original["id"])
    assert service.preview_undo(original["id"])["status"] == "incomplete_restore"
    assert (
        service.undo_operation(original["id"], correction["operation_key"])["status"] == "incomplete_restore"
    )
    assert service.undo_task(original["task_id"])["status"] == "partial_or_blocked"
    assert service.api.patches == 0


def test_inexact_pairs_do_not_hide_intervening_conflicts(service):
    original = legacy_edit(service, "A", "B", "B")
    later = legacy_edit(service, " B ", "C", "C")
    legacy_edit(service, "C", " B ", "B", reverses=later["id"])
    # Current value matches original's after-value, but this pair was not net-zero.
    result = service.preview_undo(original["id"])
    assert result["status"] == "conflicted"
    assert result["conflicts"]


def test_legacy_false_noop_preview_reconciles_before_returning(service, edit):
    from netbox_readwrite_mcp.store import encode

    op = edit()
    service.store.set_state(op["id"], "no_change", native_id=None, after_values=encode({"description": "A"}))
    service.api.change(1, {"description": "A"})
    assert service.preview_undo(op["id"])["status"] == "conflicted"
    assert service.get_operation(op["id"])["state"] == "applied"


def test_legacy_false_noop_without_evidence_is_not_trusted(service, edit):
    from netbox_readwrite_mcp.store import encode

    # Simulate a dispatched legacy receipt whose native history was never observed.
    task = service.begin_task("legacy unknown")["task_id"]
    service.api.request = lambda *a, **kw: {"status": 200, "headers": {}, "body": {}}
    op = service.update_device(
        task, "legacy-no-evidence", 1, service.read_device(1)["etag"], {"description": "B"}
    )
    service.store.set_state(op["id"], "no_change", after_values=encode({"description": "A"}))
    with pytest.raises(RuntimeError, match="unresolved"):
        service.preview_undo(op["id"])
    assert service.get_operation(op["id"])["state"] == "uncertain"


def test_task_undo_does_not_skip_legacy_dispatched_noop(service, edit):
    from netbox_readwrite_mcp.store import encode

    op = edit()
    service.store.set_state(op["id"], "no_change", native_id=None, after_values=encode({"description": "A"}))
    assert service.undo_task(op["task_id"])["status"] == "undone"
    assert service.read_device(1)["values"]["description"] == "A"
    assert service.get_operation(op["id"])["state"] == "applied"
    assert service.api.patches == 2


def test_normalized_intent_is_durable_not_recomputed(service, edit):
    op = edit({"description": " B ", "serial": "  "})
    with patch("netbox_readwrite_mcp.service.canonical_changes", side_effect=AssertionError("recomputed")):
        read = service.get_operation(op["id"])
        assert read["normalized_requested"] == {"description": "B", "serial": ""}
    events = service.recovery_bundle(op["id"])["events"]
    assert any(row["kind"] == "normalized_intent" for row in events)
