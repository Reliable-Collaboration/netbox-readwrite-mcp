"""Live contract tests on this spike's allowlisted synthetic devices only."""

import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import unittest
import uuid

from netbox_readwrite_mcp.api import NetBox
from netbox_readwrite_mcp.server import build_service
from netbox_readwrite_mcp.store import encode
from tests.integration.mcp_client import Client

HERE = Path(__file__).resolve().parents[2]


class Contract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("NETBOX_RW_LIVE") != "1":
            raise unittest.SkipTest(
                "Run scripts/lab.py and seed.py; set NETBOX_RW_LIVE=1 to test the disposable lab"
            )
        cls.config = json.loads((HERE / ".lab/config.json").read_text())
        if cls.config["netbox_url"] != "http://127.0.0.1:18790":
            raise RuntimeError("Integration tests only run against the disposable loopback lab")
        cls.device = cls.config["allowed_device_ids"][0]
        cls.other = cls.config["allowed_device_ids"][1]
        root = HERE
        cls.admin = NetBox(
            cls.config["netbox_url"], json.loads((root / ".lab/secrets.json").read_text())["token"]
        )
        cls.run_label = "run-" + time.strftime("%Y%m%dT%H%M%S")
        cls.evidence = HERE / ".lab" / "evidence" / cls.run_label
        cls.evidence.mkdir(parents=True)
        cls.state_dir = HERE / ".lab" / cls.run_label
        cls.state_dir.mkdir(mode=0o700)

    def setUp(self):
        # Different devices from the first spike; never touches a user inventory.
        for device in (self.device, self.other):
            response = self.admin.request(
                "PATCH", f"dcim/devices/{device}/", {"description": "A", "serial": "", "status": "active"}
            )
            self.assertEqual(response["status"], 200)
        self.cfg = {**self.config, "journal": str(self.state_dir / (self._testMethodName + ".sqlite"))}
        self.cfg_path = self.state_dir / (self._testMethodName + ".json")
        self.cfg_path.write_text(json.dumps(self.cfg))
        self.service = build_service(self.cfg)
        self.task = self.service.begin_task(self._testMethodName)["task_id"]

    def tearDown(self):
        try:
            with self.service.store.lock():
                raw = encode(self.service.store.export()).encode()
            (self.evidence / (self._testMethodName + ".json")).write_bytes(raw)
            (self.evidence / (self._testMethodName + ".sha256")).write_text(hashlib.sha256(raw).hexdigest())
        finally:
            self.service.store.close()

    def update(self, changes=None, device=None, key=None, task=None):
        current = self.service.read_device(device or self.device)
        result = self.service.update_device(
            task or self.task,
            key or str(uuid.uuid4()),
            current["device_id"],
            current["etag"],
            changes or {"description": "B"},
        )
        self.assertEqual(result["state"], "applied")
        return result

    def external(self, changes, device=None):
        result = self.admin.request("PATCH", f"dcim/devices/{device or self.device}/", changes)
        self.assertEqual(result["status"], 200)

    def test_01_mcp_write_undo_and_evidence(self):
        client = Client([sys.executable, "-m", "netbox_readwrite_mcp", "--config", str(self.cfg_path)])
        try:
            tools = client.rpc("tools/list")["result"]["tools"]
            self.assertIn("update_device", [x["name"] for x in tools])
            self.assertNotIn("delete", [x["name"] for x in tools])
            task = client.tool("begin_task", purpose="Agent edits through direct REST")["task_id"]
            current = client.tool("read_device", device_id=self.device)
            op = client.tool(
                "update_device",
                task_id=task,
                operation_key="mcp-write-0001",
                device_id=self.device,
                expected_etag=current["etag"],
                changes={"description": "MCP B"},
            )
            self.assertEqual(op["state"], "applied")
            self.assertEqual(op["before_values"], {"description": "A"})
            self.assertIsNotNone(op["native_id"])
            result = client.tool("undo_operation", operation_id=op["id"], operation_key="mcp-undo-0001")
            self.assertEqual(result["status"], "applied")
            self.assertEqual(self.service.read_device(self.device)["values"]["description"], "A")
            self.assertEqual(client.tool("observability")["unresolved"], [])
            (self.evidence / "mcp-transcript.json").write_text(json.dumps(client.transcript, indent=2))
        finally:
            client.close()

    def test_02_replay_same_key_and_reject_changed_payload(self):
        current = self.service.read_device(self.device)
        args = dict(
            task_id=self.task,
            operation_key="stable-key-0001",
            device_id=self.device,
            expected_etag=current["etag"],
            changes={"description": "B"},
        )
        first = self.service.update_device(**args)
        self.external({"description": "C"})
        self.service.store.close()
        self.service = build_service(self.cfg)
        second = self.service.update_device(**args)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(self.service.read_device(self.device)["values"]["description"], "C")
        with self.assertRaisesRegex(ValueError, "Idempotency"):
            self.service.update_device(**{**args, "changes": {"description": "D"}})

    def test_03_noop_is_observable_without_http_patch(self):
        current = self.service.read_device(self.device)
        api = self.service.api
        original = api.request

        def guard(method, *args, **kwargs):
            self.assertNotEqual(method, "PATCH")
            return original(method, *args, **kwargs)

        api.request = guard
        op = self.service.update_device(
            self.task, "noop-key-0001", self.device, current["etag"], {"description": "A"}
        )
        self.assertEqual(op["state"], "no_change")
        self.assertEqual(self.service.preview_undo(op["id"])["status"], "no_change")
        self.assertEqual(self.service.observability()["states"], {"no_change": 1})

    def test_04_preserve_unrelated_newer_edit(self):
        op = self.update()
        self.external({"serial": "external-serial"})
        result = self.service.undo_operation(op["id"], "undo-unrelated-0001")
        self.assertEqual(result["status"], "applied")
        current = self.service.read_device(self.device)["values"]
        self.assertEqual(current["description"], "A")
        self.assertEqual(current["serial"], "external-serial")

    def test_05_same_field_warns_person(self):
        op = self.update()
        self.external({"description": "C"})
        result = self.service.undo_operation(op["id"], "undo-conflict-0001")
        self.assertEqual(result["status"], "conflicted")
        self.assertTrue(result["warning"])
        self.assertEqual(result["conflicts"][0]["field"], "description")
        self.assertEqual(self.service.read_device(self.device)["values"]["description"], "C")
        (self.evidence / "conflict-warning.json").write_text(json.dumps(result, indent=2))

    def test_06_ABA_warns_even_when_current_value_matches(self):
        op = self.update()
        self.external({"description": "C"})
        self.external({"description": "B"})
        self.assertEqual(self.service.preview_undo(op["id"])["status"], "conflicted")

    def test_07_stale_initial_write_refused(self):
        current = self.service.read_device(self.device)
        self.external({"description": "C"})
        with self.assertRaisesRegex(ValueError, "Stale"):
            self.service.update_device(
                self.task, "stale-write-0001", self.device, current["etag"], {"description": "B"}
            )
        self.assertEqual(self.service.read_device(self.device)["values"]["description"], "C")
        self.assertEqual(self.service.observability()["states"], {})

    def test_08_change_during_undo_warns_person(self):
        op = self.update()
        self.service.fault = lambda point: (
            self.external({"description": "race"}) if point == "before_undo_apply" else None
        )
        result = self.service.undo_operation(op["id"], "undo-race-0001")
        self.assertEqual(result["status"], "conflicted")
        self.assertTrue(result["warning"])
        self.assertEqual(self.service.read_device(self.device)["values"]["description"], "race")

    def test_09_server_rejects_last_moment_race_with_412(self):
        current = self.service.read_device(self.device)
        self.service.fault = lambda point: (
            self.external({"description": "raced"}) if point == "after_dispatch_record" else None
        )
        op = self.service.update_device(
            self.task, "server-race-0001", self.device, current["etag"], {"description": "B"}
        )
        self.assertEqual(op["state"], "failed")
        self.assertEqual(self.service.read_device(self.device)["values"]["description"], "raced")
        bundle = self.service.recovery_bundle(op["id"])
        receipts = [json.loads(e["payload"])["receipt"] for e in bundle["events"] if e["kind"] == "state"]
        self.assertIn(412, [r["status"] for r in receipts if isinstance(r, dict) and "status" in r])

    def test_10_archive_down_blocks_write(self):
        original = self.service.api.history
        self.service.api.history = lambda: (_ for _ in ()).throw(ConnectionError("Archive unavailable"))
        current = self.service.read_device(self.device)
        with self.assertRaises(ConnectionError):
            self.service.update_device(
                self.task, "archive-down-0001", self.device, current["etag"], {"description": "B"}
            )
        self.assertEqual(self.service.read_device(self.device)["values"]["description"], "A")
        self.assertGreater(self.service.observability()["event_counts"]["archive_failed"], 0)
        self.service.api.history = original

    def test_11_failed_journal_commit_prevents_write(self):
        original = self.service.store.event

        def fail(kind, *args, **kwargs):
            if kind == "prepared":
                raise sqlite3.OperationalError("Injected disk-full condition")
            return original(kind, *args, **kwargs)

        self.service.store.event = fail
        current = self.service.read_device(self.device)
        with self.assertRaises(sqlite3.OperationalError):
            self.service.update_device(
                self.task, "disk-full-0001", self.device, current["etag"], {"description": "B"}
            )
        self.service.store.event = original
        self.assertEqual(self.service.read_device(self.device)["values"]["description"], "A")
        self.assertEqual(self.service.observability()["states"], {})

    def test_12_commit_then_response_loss_reconciles(self):
        request = self.service.api.request

        def drop(method, *args, **kwargs):
            result = request(method, *args, **kwargs)
            if method == "PATCH":
                self.assertEqual(result["status"], 200)
                raise ConnectionResetError("Injected loss of committed response")
            return result

        self.service.api.request = drop
        current = self.service.read_device(self.device)
        op = self.service.update_device(
            self.task, "lost-response-0001", self.device, current["etag"], {"description": "B"}
        )
        self.assertEqual(op["state"], "uncertain")
        self.assertEqual(op["before_values"], {"description": "A"})
        self.service.api.request = request
        self.service.reconcile()
        self.assertEqual(self.service.get_operation(op["id"])["state"], "applied")
        self.assertEqual(self.service.undo_operation(op["id"], "lost-response-undo")["status"], "applied")

    def test_13_hard_crash_before_dispatch_and_after_commit(self):
        code = """import json,os,sys
from netbox_readwrite_mcp.server import build_service
s=build_service(json.load(open(sys.argv[1])))
s.fault=lambda point: os._exit(93) if point==sys.argv[3] else None
r=s.read_device(int(sys.argv[4]))
s.update_device(sys.argv[2],sys.argv[3],r['device_id'],r['etag'],{'description':'B'})
"""
        for point in ["after_prepare", "after_response"]:
            result = subprocess.run(
                [sys.executable, "-c", code, str(self.cfg_path), self.task, point, str(self.device)], cwd=HERE
            )
            self.assertEqual(result.returncode, 93)
            self.service.reconcile()
        operations = self.service.get_task(self.task)["operations"]
        self.assertEqual([x["state"] for x in operations], ["failed", "applied"])
        self.assertEqual(operations[1]["before_values"], {"description": "A"})
        self.assertEqual(
            self.service.undo_operation(operations[1]["id"], "crash-undo-0001")["status"], "applied"
        )

    def test_14_unprovable_outcome_blocks_further_device_writes(self):
        self.service.fault = lambda point: (
            (_ for _ in ()).throw(SystemExit(94)) if point == "after_dispatch_record" else None
        )
        current = self.service.read_device(self.device)
        with self.assertRaises(SystemExit):
            self.service.update_device(
                self.task, "unknown-outcome-0001", self.device, current["etag"], {"description": "B"}
            )
        self.service.fault = lambda point: None
        self.service.reconcile()
        with self.assertRaisesRegex(RuntimeError, "unresolved"):
            self.service.update_device(
                self.task, "unknown-outcome-0002", self.device, current["etag"], {"description": "C"}
            )
        self.assertEqual(self.service.read_device(self.device)["values"]["description"], "A")
        self.assertEqual(len(self.service.observability()["unresolved"]), 1)

    def test_15_task_undo_repeated_fields_reverse_order(self):
        self.update({"description": "B"})
        self.update({"description": "C"})
        result = self.service.undo_task(self.task)
        self.assertEqual(result["status"], "undone")
        self.assertFalse(result["atomic"])
        self.assertEqual(self.service.read_device(self.device)["values"]["description"], "A")
        self.assertEqual(self.service.undo_task(self.task)["status"], "undone")
        self.assertEqual(len(self.service.get_task(result["correction_task_id"])["operations"]), 2)
        (self.evidence / "task-undo.json").write_text(json.dumps(result, indent=2))

    def test_16_task_undo_partial_stops_on_conflict(self):
        self.update({"description": "B"})
        self.update({"serial": "serial-B"}, device=self.other)
        self.external({"description": "C"})
        result = self.service.undo_task(self.task)
        self.assertEqual(result["status"], "partial_or_blocked")
        self.assertEqual(result["results"][0]["status"], "applied")
        self.assertEqual(result["results"][1]["status"], "conflicted")
        self.assertEqual(self.service.read_device(self.other)["values"]["serial"], "")
        self.assertEqual(self.service.read_device(self.device)["values"]["description"], "C")

    def test_17_task_undo_resume_after_process_loss(self):
        self.update({"description": "B"})
        self.update({"description": "C"})
        code = """import json,os,sys
from netbox_readwrite_mcp.server import build_service
s=build_service(json.load(open(sys.argv[1])))
s.fault=lambda point: os._exit(95) if point=='after_response' else None
s.undo_task(sys.argv[2])
"""
        result = subprocess.run([sys.executable, "-c", code, str(self.cfg_path), self.task], cwd=HERE)
        self.assertEqual(result.returncode, 95)
        self.service.reconcile()
        result = self.service.undo_task(self.task)
        self.assertEqual(result["status"], "undone")
        self.assertEqual(self.service.read_device(self.device)["values"]["description"], "A")

    def test_18_unsupported_fields_and_outside_scope_rejected(self):
        current = self.service.read_device(self.device)
        for changes in [{"asset_tag": "unique"}, {"tags": []}, {"site": 1}]:
            with self.assertRaises(ValueError):
                self.service.update_device(
                    self.task, str(uuid.uuid4()), self.device, current["etag"], changes
                )
        with self.assertRaises(ValueError):
            self.service.update_device(
                self.task, "outside-scope-0001", 999999, current["etag"], {"description": "B"}
            )
        self.assertEqual(self.service.read_device(self.device)["values"]["description"], "A")

    def test_19_invalid_status_recorded_as_failed(self):
        current = self.service.read_device(self.device)
        op = self.service.update_device(
            self.task, "invalid-status-0001", self.device, current["etag"], {"status": "invented-status"}
        )
        self.assertEqual(op["state"], "failed")
        self.assertEqual(self.service.read_device(self.device)["values"]["status"], "active")

    def test_20_backup_restores_history_and_recovery(self):
        op = self.update()
        backup = self.state_dir / "restored.sqlite"
        receipt = self.service.store.backup(backup)
        self.assertEqual(receipt["sha256"], hashlib.sha256(backup.read_bytes()).hexdigest())
        restored = build_service({**self.cfg, "journal": str(backup)})
        try:
            self.assertEqual(restored.recovery_bundle(op["id"])["inverse"], {"description": "A"})
            self.assertEqual(restored.undo_operation(op["id"], "restored-undo-0001")["status"], "applied")
            (self.evidence / "restored-journal.json").write_text(encode(restored.store.export()))
        finally:
            restored.store.close()

    def test_21_immutable_evidence_and_projection_integrity(self):
        op = self.update()
        with self.assertRaises(sqlite3.IntegrityError):
            self.service.store.db.execute("UPDATE events SET payload='{}'")
        original = self.service.store.db.execute(
            "SELECT before_values FROM operations WHERE id=?", (op["id"],)
        ).fetchone()[0]
        self.service.store.db.execute("UPDATE operations SET before_values='{}' WHERE id=?", (op["id"],))
        try:
            with self.assertRaisesRegex(RuntimeError, "projection"):
                self.service.preview_undo(op["id"])
        finally:
            self.service.store.db.execute(
                "UPDATE operations SET before_values=? WHERE id=?", (original, op["id"])
            )
        self.service.store.verify()

    def test_22_two_processes_share_idempotency_boundary(self):
        current = self.service.read_device(self.device)
        code = """import json,sys
from netbox_readwrite_mcp.server import build_service
s=build_service(json.load(open(sys.argv[1])))
r=s.update_device(sys.argv[2],'concurrent-key-0001',int(sys.argv[3]),sys.argv[4],{'description':'B'})
print(json.dumps({'id':r['id'],'state':r['state']}))
"""
        args = [sys.executable, "-c", code, str(self.cfg_path), self.task, str(self.device), current["etag"]]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            outputs = list(pool.map(lambda _: subprocess.check_output(args, cwd=HERE, text=True), range(2)))
        rows = [json.loads(x) for x in outputs]
        self.assertEqual(rows[0]["id"], rows[1]["id"])
        self.assertEqual([r["state"] for r in rows], ["applied", "applied"])
        self.assertEqual(len(self.service.get_task(self.task)["operations"]), 1)

    def test_23_native_permissions_restrict_scope_and_deletion(self):
        outside = int((HERE / ".lab/outside-id").read_text())
        self.assertNotIn(outside, self.service.allowed)
        response = self.service.api.request("PATCH", f"dcim/devices/{outside}/", {"description": "forbidden"})
        self.assertIn(response["status"], (403, 404))
        response = self.service.api.request("DELETE", f"dcim/devices/{self.device}/")
        self.assertEqual(response["status"], 403)
        self.assertEqual(self.service.read_device(self.device)["values"]["description"], "A")

    def test_24_evidence_loss_blocks_and_keeps_archive(self):
        op = self.update()
        history = self.service.api.history
        self.service.api.history = lambda: [r for r in history() if r["id"] != op["native_id"]]
        try:
            with self.assertRaisesRegex(RuntimeError, "missing"):
                self.service.preview_undo(op["id"])
            self.assertIn(op["native_id"], self.service.observability()["archive"]["missing_native_ids"])
            self.assertEqual(
                self.service.recovery_bundle(op["id"])["native_evidence"][0]["id"], op["native_id"]
            )
        finally:
            self.service.api.history = history
        self.service.reconcile()

    def test_25_archive_loss_after_commit_stays_explicit(self):
        history = self.service.api.history

        def fault(point):
            if point == "after_response":
                self.service.api.history = lambda: (_ for _ in ()).throw(
                    ConnectionError("Archive lost after commit")
                )

        self.service.fault = fault
        current = self.service.read_device(self.device)
        op = self.service.update_device(
            self.task, "postcommit-outage-0001", self.device, current["etag"], {"description": "B"}
        )
        self.assertEqual(op["state"], "applied_unverified")
        self.assertEqual(op["before_values"], {"description": "A"})
        self.assertEqual(len(self.service.observability()["unresolved"]), 1)
        self.service.api.history = history
        self.service.fault = lambda point: None
        self.service.reconcile()
        self.assertEqual(self.service.get_operation(op["id"])["state"], "applied")

    def test_26_wrong_actor_marker_cannot_resolve_uncertainty(self):
        request = self.service.api.request

        def drop(method, *args, **kwargs):
            response = request(method, *args, **kwargs)
            if method == "PATCH":
                raise ConnectionResetError("Lost response")
            return response

        self.service.api.request = drop
        current = self.service.read_device(self.device)
        op = self.service.update_device(
            self.task, "actor-check-0001", self.device, current["etag"], {"description": "B"}
        )
        self.service.api.request = request
        # Simulate a different actor during reconciliation; restore the configured
        # identity afterward. The genuine server evidence remains unchanged.
        actor = self.service.actor
        self.service.actor = "wrong-actor"
        self.service.reconcile()
        self.assertEqual(self.service.get_operation(op["id"])["state"], "uncertain")
        self.service.actor = actor
        self.service.reconcile()
        self.assertEqual(self.service.get_operation(op["id"])["state"], "applied")

    def test_27_status_and_serial_restore(self):
        op = self.update({"status": "planned", "serial": "serial-B"})
        self.assertEqual(self.service.undo_operation(op["id"], "status-undo-0001")["status"], "applied")
        fields = self.service.read_device(self.device)["values"]
        self.assertEqual(fields["status"], "active")
        self.assertEqual(fields["serial"], "")

    def test_28_journal_rejects_wrong_instance_lineage(self):
        with self.assertRaisesRegex(ValueError, "different instance"):
            build_service({**self.cfg, "instance_id": "different-restore-lineage"})

    def test_29_failed_undo_key_returns_same_receipt(self):
        op = self.update()
        request = self.service.api.request
        self.service.api.request = lambda method, *args, **kwargs: (
            {"status": 403, "headers": {}, "body": {"detail": "Injected permission rejection"}}
            if method == "PATCH"
            else request(method, *args, **kwargs)
        )
        first = self.service.undo_operation(op["id"], "failed-undo-key-0001")
        self.assertEqual(first["status"], "failed")
        self.service.api.request = request
        second = self.service.undo_operation(op["id"], "failed-undo-key-0001")
        self.assertEqual(second["status"], "failed")
        self.assertEqual(first["correction"]["id"], second["correction"]["id"])
        self.assertEqual(self.service.read_device(self.device)["values"]["description"], "B")
        self.assertEqual(self.service.undo_operation(op["id"], "failed-undo-key-0002")["status"], "applied")

    def test_30_task_undo_resumes_pre_dispatch_crash(self):
        self.update({"description": "B"})
        code = """import json,os,sys
from netbox_readwrite_mcp.server import build_service
s=build_service(json.load(open(sys.argv[1])))
s.fault=lambda point: os._exit(96) if point=='after_prepare' else None
s.undo_task(sys.argv[2])
"""
        result = subprocess.run([sys.executable, "-c", code, str(self.cfg_path), self.task], cwd=HERE)
        self.assertEqual(result.returncode, 96)
        self.service.reconcile()
        result = self.service.undo_task(self.task)
        self.assertEqual(result["status"], "undone")
        self.assertEqual(self.service.read_device(self.device)["values"]["description"], "A")
        corrections = self.service.get_task(result["correction_task_id"])["operations"]
        self.assertEqual([r["state"] for r in corrections], ["failed", "applied"])

    def test_31_normalized_lost_responses_reconcile(self):
        original = self.service.api.request
        for field in ["description", "serial"]:
            with self.subTest(field=field):

                def dropped(method, *args, **kwargs):
                    result = original(method, *args, **kwargs)
                    if method == "PATCH":
                        self.assertEqual(result["status"], 200)
                        raise ConnectionResetError("Lost normalized response")
                    return result

                self.service.api.request = dropped
                key = str(uuid.uuid4())
                try:
                    op = self.service.update_device(
                        self.task,
                        key,
                        self.device,
                        self.service.read_device(self.device)["etag"],
                        {field: "  normalized  "},
                    )
                finally:
                    self.service.api.request = original
                self.assertEqual(op["state"], "uncertain")
                self.service.reconcile()
                op = self.service.get_operation(op["id"])
                self.assertEqual(op["state"], "applied")
                self.assertEqual(op["requested"], {field: "  normalized  "})
                self.assertEqual(op["after_values"], {field: "normalized"})
                self.assertEqual(
                    self.service.undo_operation(op["id"], str(uuid.uuid4()))["status"], "applied"
                )

    def test_32_normalized_hard_crash_reconciles(self):
        code = """import json,os,sys
from netbox_readwrite_mcp.server import build_service
s=build_service(json.load(open(sys.argv[1])))
s.fault=lambda point: os._exit(93) if point=='after_response' else None
r=s.read_device(int(sys.argv[3]))
s.update_device(sys.argv[2],'normalized-crash-key',r['device_id'],r['etag'],{'description':'  B  '})
"""
        result = subprocess.run(
            [sys.executable, "-c", code, str(self.cfg_path), self.task, str(self.device)], cwd=HERE
        )
        self.assertEqual(result.returncode, 93)
        self.service.reconcile()
        op = self.service.find_operation("normalized-crash-key")["operation"]
        self.assertEqual(op["state"], "applied")
        self.assertEqual(op["after_values"], {"description": "B"})
        self.assertEqual(self.service.undo_operation(op["id"], "normalized-crash-undo")["status"], "applied")

    def test_33_normalization_to_noop_avoids_patch(self):
        original = self.service.api.request

        def guarded(method, *args, **kwargs):
            self.assertNotEqual(method, "PATCH")
            return original(method, *args, **kwargs)

        self.service.api.request = guarded
        result = self.service.update_device(
            self.task,
            "normalized-noop-key",
            self.device,
            self.service.read_device(self.device)["etag"],
            {"description": "  A  ", "serial": "   "},
        )
        self.assertEqual(result["state"], "no_change")
        self.assertIsNone(result["native_id"])

    def test_34_unrestorable_existing_values_block_before_write(self):
        script = (
            "from dcim.models import Device\n"
            f"Device.objects.filter(pk={self.device}).update(description='  prior  ',serial='  prior  ')\n"
        )
        subprocess.run(
            [
                "podman",
                "exec",
                "-i",
                "nbrw-audit-netbox",
                "/opt/netbox/venv/bin/python",
                "/opt/netbox/netbox/manage.py",
                "shell",
            ],
            input=script,
            text=True,
            check=True,
            capture_output=True,
        )
        original = self.service.api.request

        def guarded(method, *args, **kwargs):
            self.assertNotEqual(method, "PATCH")
            return original(method, *args, **kwargs)

        self.service.api.request = guarded
        try:
            for field in ["description", "serial"]:
                with (
                    self.subTest(field=field),
                    self.assertRaisesRegex(ValueError, "Unrestorable previous value"),
                ):
                    self.service.update_device(
                        self.task,
                        str(uuid.uuid4()),
                        self.device,
                        self.service.read_device(self.device)["etag"],
                        {field: "replacement"},
                    )
            self.assertEqual(self.service.read_device(self.device)["values"]["description"], "  prior  ")
        finally:
            self.service.api.request = original
            self.external({"description": "A", "serial": ""})

    def test_35_real_response_requery_preserves_original_effect(self):
        from tests.integration.response_race import patch_with_intervening_writer

        original = self.service.api.request
        for newer in ["A", "C"]:
            with self.subTest(newer=newer):
                self.external({"description": "A"})

                def raced(method, path, data=None, headers=None):
                    if method != "PATCH":
                        return original(method, path, data, headers)
                    return patch_with_intervening_writer(
                        path, data, headers["If-Match"], self.service.api.token, self.admin.token, newer
                    )

                self.service.api.request = raced
                try:
                    op = self.update({"description": "B"})
                finally:
                    self.service.api.request = original
                self.assertEqual(op["after_values"], {"description": "B"})
                self.assertIsNotNone(op["native_id"])
                self.assertEqual(op["last_receipt"]["body"]["description"], newer)
                self.assertEqual(self.service.preview_undo(op["id"])["status"], "conflicted")
                self.assertEqual(
                    self.service.undo_operation(op["id"], str(uuid.uuid4()))["status"], "conflicted"
                )
                self.assertEqual(self.service.read_device(self.device)["values"]["description"], newer)

    def test_36_normalization_adapter_matches_real_serializer(self):
        from netbox_readwrite_mcp.normalization import canonical_changes

        for value in ["  B  ", "\tB\n", "\u00a0B\u2003", "   "]:
            changes = {"description": value, "serial": value}
            response = self.admin.request("PATCH", f"dcim/devices/{self.device}/", changes)
            self.assertEqual(response["status"], 200)
            self.assertEqual({key: response["body"][key] for key in changes}, canonical_changes(changes))
        response = self.admin.request("PATCH", f"dcim/devices/{self.device}/", {"status": " active "})
        self.assertEqual(response["status"], 400)


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(Contract)
    )
    report = {
        "tests": result.testsRun,
        "success": result.wasSuccessful(),
        "failures": [(str(t), text) for t, text in result.failures],
        "errors": [(str(t), text) for t, text in result.errors],
    }
    (Contract.evidence / "results.json").write_text(json.dumps(report, indent=2))
    print(Contract.evidence)
    raise SystemExit(not result.wasSuccessful())
