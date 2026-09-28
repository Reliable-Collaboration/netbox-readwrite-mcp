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
