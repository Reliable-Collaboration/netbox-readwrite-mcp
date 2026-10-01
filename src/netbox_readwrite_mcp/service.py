"""Direct REST writes with durable recovery evidence and bounded compensation."""

import json
import re
import time
import uuid
from .api import HISTORY_FIELDS
from .store import Store, encode, digest, consistent_read
from .compatibility import normalization_profile
from .normalization import canonical_changes, exact_inverse, exact_correction

FIELDS = {"description", "serial", "status"}
PENDING = {"prepared", "dispatched", "uncertain", "applied_unverified"}


def values(device):
    return {
        k: (device[k]["value"] if k == "status" and isinstance(device[k], dict) else device[k])
        for k in FIELDS
    }


def native_record(row):
    # Exclude live expanded references, which change after a rename/delete.
    return {k: row[k] for k in HISTORY_FIELDS}


class Service:
    def __init__(self, api, journal, instance_id, actor, allowed_device_ids, fault=None):
        self.api = api
        self.actor = actor
        self.allowed = None if allowed_device_ids is None else frozenset(allowed_device_ids)
        if self.allowed is not None and (
            not self.allowed or any(type(x) is not int or x <= 0 for x in self.allowed)
        ):
            raise ValueError("A non-empty positive device ID allowlist is required")
        self.store = Store(
            journal,
            {
                "url": api.url,
                "instance_id": instance_id,
                "actor": actor,
                "allowed_device_ids": None if self.allowed is None else sorted(self.allowed),
                "policy": 1,
            },
        )
        self.fault = fault or (lambda point: None)
        self.version = None

    def _device(self, device_id):
        if type(device_id) is not int or (self.allowed is not None and device_id not in self.allowed):
            raise ValueError("Device is outside the configured allowlist")
        return self.api.get(f"dcim/devices/{device_id}/")

    def read_device(self, device_id):
        row = self._device(device_id)
        return {
            "device_id": device_id,
            "name": row["body"]["name"],
            "values": values(row["body"]),
            "etag": row["headers"].get("etag"),
            "content_is_untrusted_data": True,
        }

    def begin_task(self, purpose):
        if not isinstance(purpose, str) or not 1 <= len(purpose) <= 1000:
            raise ValueError("Purpose must contain 1–1000 characters")
        with self.store.lock(), self.store.transaction():
            task = str(uuid.uuid4())
            self.store.db.execute("INSERT INTO tasks VALUES(?,?,?,NULL)", (task, purpose, time.time()))
            self.store.event("task_started", {"task_id": task, "purpose": purpose})
        return {"task_id": task}

    @consistent_read
    def get_operation(self, operation_id):
        row = self.store.db.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
        if not row:
            raise ValueError("Unknown operation")
        result = dict(row)
        for name in ["requested", "before_values", "after_values"]:
            result[name] = json.loads(result[name])
        normalized = self.store.db.execute(
            "SELECT payload FROM events WHERE operation_id=? AND kind='normalized_intent' ORDER BY seq LIMIT 1",
            (operation_id,),
        ).fetchone()
        result["normalized_requested"] = (
            json.loads(normalized[0])["values"] if normalized else canonical_changes(result["requested"])
        )
        result["outcome"] = result["state"]
        result["guidance"] = {
            "uncertain": "Reconcile; never blindly repeat the write under a new key.",
            "applied_unverified": "HTTP receipt exists; native evidence has not been verified. Reconcile.",
            "prepared": "Dispatch was not durably entered; do not retry automatically.",
            "dispatched": "Dispatch may have committed. Reconcile before taking further action.",
            "applied": "Committed evidence verified; preview undo before correction.",
            "no_change": "No effective field change; no correction is needed.",
            "failed": "No mutation is expected: the request was rejected or abandoned before dispatch. Inspect the receipt before a deliberate new attempt.",
        }.get(result["state"], "Inspect operation evidence.")
        receipt = self.store.db.execute(
            "SELECT payload FROM events WHERE operation_id=? AND kind='state' ORDER BY seq DESC",
            (operation_id,),
        ).fetchall()
        result["last_receipt"] = next(
            (json.loads(r[0])["receipt"] for r in receipt if json.loads(r[0])["receipt"] is not None), None
        )
        return result

    @consistent_read
    def find_operation(self, operation_key):
        """Recover the authoritative receipt even if the MCP response was lost."""
        row = self.store.db.execute(
            "SELECT id FROM operations WHERE operation_key=?", (operation_key,)
        ).fetchone()
        return {
            "found": bool(row),
            "operation": self.get_operation(row[0]) if row else None,
            "guidance": "Keep the original key and arguments. Absence is not permission to bypass a failed journal.",
        }

    @consistent_read
    def get_task(self, task_id):
        task = self.store.db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not task:
            raise ValueError("Unknown task")
        return {
            "task": dict(task),
            "operations": [
                self.get_operation(r[0])
                for r in self.store.db.execute(
                    "SELECT o.id FROM operations o JOIN events e ON e.operation_id=o.id "
                    "WHERE o.task_id=? AND e.kind='prepared' ORDER BY e.seq",
                    (task_id,),
                )
            ],
        }

    def _sync(self):
        """Replayable full scan, transactional export; never deletes archived data."""
        try:
            rows = self.api.history()
            with self.store.transaction():
                for row in rows:
                    payload = native_record(row)
                    hashed = digest(payload)
                    existing = self.store.db.execute(
                        "SELECT hash FROM native_changes WHERE id=?", (row["id"],)
                    ).fetchone()
                    if existing and existing[0] != hashed:
                        raise RuntimeError(
                            "Native history changed: inspect schema/restore lineage before writing"
                        )
                    self.store.db.execute(
                        "INSERT OR IGNORE INTO native_changes VALUES(?,?,?)",
                        (row["id"], encode(payload), hashed),
                    )
                seen = {r["id"] for r in rows}
                missing = [
                    r[0] for r in self.store.db.execute("SELECT id FROM native_changes") if r[0] not in seen
                ]
                self.store.db.execute(
                    "INSERT OR REPLACE INTO metadata VALUES('archive_health',?)",
                    (encode({"at": time.time(), "missing_native_ids": missing, "native_rows": len(seen)}),),
                )
                self.store.event("archive_synced", {"native_rows": len(seen), "missing_native_ids": missing})
            if missing:
                raise RuntimeError(
                    "Native history is missing; writes and undo are blocked until investigated"
                )
        except Exception as exc:
            self.store.event("archive_failed", {"error": str(exc)})
            raise

    def _records(self):
        return [
            json.loads(r[0]) for r in self.store.db.execute("SELECT payload FROM native_changes ORDER BY id")
        ]

    def _reconcile(self):
        records = self._records()
        # Called while holding the process lock: no writer can still own a
        # prepared row. A crash before the dispatch record never sent a request.
        for row in self.store.db.execute("SELECT id FROM operations WHERE state='prepared'").fetchall():
            self.store.set_state(
                row[0], "failed", receipt={"reason": "Abandoned before dispatch; no request sent"}
            )
        ids = [
            r[0]
            for r in self.store.db.execute(
                "SELECT id FROM operations WHERE state IN ('dispatched','uncertain','applied_unverified') "
                "OR (state='no_change' AND native_id IS NULL AND before_values != '{}')"
            )
        ]
        for op_id in ids:
            op = self.get_operation(op_id)
            if op["state"] == "no_change":
                # Older versions trusted response bodies after dispatch. Preserve
                # that receipt, but require native evidence before trusting it.
                self.store.set_state(
                    op_id,
                    "uncertain",
                    receipt={"reason": "Legacy dispatched no_change requires native verification"},
                )
            expected = {key: op["normalized_requested"][key] for key in op["before_values"]}
            matches = [r for r in records if r["message"] == "netbox-rw:" + op_id]
            if not matches:
                continue
            if len(matches) != 1:
                self.store.event("correlation_conflict", {"reason": "Marker is not unique"}, op_id)
                continue
            change = matches[0]
            valid = (
                change["user_name"] == self.actor
                and change["changed_object_type"] == "dcim.device"
                and change["changed_object_id"] == op["device_id"]
                and change["action"]["value"] == "update"
                and (not op["request_id"] or op["request_id"] == change["request_id"])
                and all(
                    k in change["prechange_data"] and change["prechange_data"][k] == v
                    for k, v in op["before_values"].items()
                )
                and all(
                    k in change["postchange_data"] and change["postchange_data"][k] == v
                    for k, v in expected.items()
                )
            )
            if not valid:
                self.store.event(
                    "correlation_conflict",
                    {"reason": "Actor, receipt, or snapshots do not match intent", "native_id": change["id"]},
                    op_id,
                )
                continue
            after = {key: change["postchange_data"][key] for key in expected}
            self.store.set_state(
                op_id,
                "no_change" if after == op["before_values"] else "applied",
                request_id=change["request_id"],
                native_id=change["id"],
                after_values=encode(after),
            )

    def _preflight(self, device_id):
        self.store.verify()
        status = self.api.get("status/")["body"]
        self.version = status["netbox-version"]
        self.profile = normalization_profile(self.version)
        self._sync()
        self._reconcile()
        outstanding = self.store.db.execute(
            "SELECT id FROM operations WHERE device_id=? AND state IN ('prepared','dispatched','uncertain','applied_unverified')",
            (device_id,),
        ).fetchall()
        if outstanding:
            raise RuntimeError("Device has unresolved operations: " + ", ".join(r[0] for r in outstanding))

    def _write(self, task_id, operation_key, device_id, expected_etag, changes, reverses=None):
        if not isinstance(operation_key, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{8,160}", operation_key):
            raise ValueError(
                "operation_key must be 8–160 letters, digits, dots, underscores, colons, or hyphens"
            )
        if not isinstance(changes, dict) or not changes or not set(changes) <= FIELDS:
            raise ValueError(
                "Unsupported edit: only description, serial, and status are supported. Read capabilities; relationship, create, delete, and bulk edits require a separate recovery contract."
            )
        if any(not isinstance(v, str) or len(v) > 10000 for v in changes.values()):
            raise ValueError(
                "Supported field values must be strings of at most 10000 characters; use an empty string to clear text"
            )
        if not isinstance(expected_etag, str) or not expected_etag:
            raise ValueError("Read the device and supply its expected_etag")
        if not self.store.db.execute("SELECT 1 FROM tasks WHERE id=?", (task_id,)).fetchone():
            raise ValueError("Unknown task")
        fingerprint = digest(
            {
                "task": task_id,
                "device": device_id,
                "etag": expected_etag,
                "changes": changes,
                "reverses": reverses,
            }
        )
        existing = self.store.db.execute(
            "SELECT id,fingerprint FROM operations WHERE operation_key=?", (operation_key,)
        ).fetchone()
        if existing:
            if existing["fingerprint"] != fingerprint:
                raise ValueError("Idempotency key was already used for different arguments")
            return self.get_operation(existing["id"])
        self._preflight(device_id)
        current = self._device(device_id)
        if current["headers"].get("etag") != expected_etag:
            raise ValueError("Stale expected_etag: read current state; no write was dispatched")
        prior = values(current["body"])
        normalized = canonical_changes(changes)
        actual = {k: v for k, v in normalized.items() if prior[k] != v}
        before = {k: prior[k] for k in actual}
        if canonical_changes(before) != before:
            raise ValueError(
                "Unrestorable previous value: NetBox REST normalizes the existing text. "
                "No write was dispatched; ask an operator to review the original values."
            )
        now = time.time()
        op_id = str(uuid.uuid4())
        state = "prepared" if actual else "no_change"
        row = {
            "id": op_id,
            "operation_key": operation_key,
            "fingerprint": fingerprint,
            "task_id": task_id,
            "device_id": device_id,
            "requested": encode(changes),
            "before_values": encode(before),
            "after_values": encode(actual),
            "before_etag": expected_etag,
            "state": state,
            "request_id": None,
            "native_id": None,
            "reverses": reverses,
            "created": now,
            "updated": now,
        }
        with self.store.transaction():
            self.store.db.execute(
                "INSERT INTO operations VALUES(" + ",".join("?" for _ in row) + ")", tuple(row.values())
            )
            self.store.event("prepared", row, op_id)
            self.store.event(
                "normalized_intent",
                {"profile": self.profile, "netbox_version": self.version, "values": normalized},
                op_id,
            )
        if not actual:
            return self.get_operation(op_id)
        self.fault("after_prepare")
        self.store.set_state(op_id, "dispatched")
        self.fault("after_dispatch_record")
        try:
            response = self.api.request(
                "PATCH",
                f"dcim/devices/{device_id}/",
                {**actual, "changelog_message": "netbox-rw:" + op_id},
                {"If-Match": expected_etag},
            )
            self.fault("after_response")
        except Exception as exc:
            self.store.set_state(op_id, "uncertain", receipt={"error_type": type(exc).__name__})
            return self.get_operation(op_id)
        if response["status"] == 200:
            # NetBox re-queries after committing. The response representation can
            # already contain another writer's edit: retain it as a receipt, not
            # as our committed effect. Only correlated native history proves that.
            self.store.set_state(
                op_id, "applied_unverified", response, request_id=response["headers"].get("x-request-id")
            )
        elif response["status"] in {400, 401, 403, 404, 405, 409, 412, 422}:
            # Timeouts/rate limits can originate in a proxy after forwarding.
            # A 408/429 is not sufficient evidence of non-commit.
            self.store.set_state(
                op_id, "failed", response, request_id=response["headers"].get("x-request-id")
            )
        else:
            self.store.set_state(
                op_id, "uncertain", response, request_id=response["headers"].get("x-request-id")
            )
        try:
            self._sync()
            self._reconcile()
        except Exception:
            # State + archive_failed evidence already recorded. Do not turn a
            # committed-but-unverified write into a misleading generic failure.
            pass
        return self.get_operation(op_id)

    def update_device(self, task_id, operation_key, device_id, expected_etag, changes):
        with self.store.lock():
            try:
                return self._write(task_id, operation_key, device_id, expected_etag, changes)
            except Exception as exc:
                self.store.event(
                    "write_blocked_or_interrupted",
                    {
                        "task_id": task_id,
                        "operation_key": operation_key,
                        "device_id": device_id,
                        "reason": str(exc),
                    },
                )
                raise

    def reconcile(self):
        with self.store.lock():
            self.store.verify()
            self._sync()
            self._reconcile()
            return self.observability()

    def _correction(self, op_id):
        row = self.store.db.execute(
            "SELECT id FROM operations WHERE reverses=? AND state NOT IN ('failed','rejected')", (op_id,)
        ).fetchone()
        return self.get_operation(row[0]) if row else None

    def _preview(self, operation_id):
        op = self.get_operation(operation_id)
        if op["reverses"]:
            return {
                "status": "unsupported",
                "reason": "Undo of a correction (redo) is not supported",
                "operation_id": operation_id,
            }
        if op["state"] == "no_change" and op["before_values"] and op["native_id"] is None:
            self._preflight(op["device_id"])
            op = self.get_operation(operation_id)
        correction = self._correction(operation_id)
        if correction:
            if correction["state"] in {"applied", "no_change"} and not exact_correction(op, correction):
                return {
                    "status": "incomplete_restore",
                    "operation_id": operation_id,
                    "correction": correction,
                    "inverse": exact_inverse(op),
                    "warning": "The recorded correction did not restore the exact previous values. "
                    "Operator review is required; it is not a completed undo.",
                }
            return {
                "status": "already_undone"
                if correction["state"] in {"applied", "no_change"}
                else "correction_pending",
                "operation_id": operation_id,
                "correction": correction,
            }
        if op["state"] == "no_change":
            return {"status": "no_change", "operation_id": operation_id}
        if op["state"] != "applied":
            return {
                "status": "blocked",
                "operation_id": operation_id,
                "reason": "Original operation is not verified as applied",
                "state": op["state"],
            }
        inverse = exact_inverse(op)
        if canonical_changes(inverse) != inverse:
            return {
                "status": "unsupported",
                "operation_id": operation_id,
                "inverse": inverse,
                "warning": "The previous values cannot be restored exactly through NetBox REST "
                "because it normalizes text. No correction was dispatched; ask an operator.",
            }
        self._preflight(op["device_id"])
        current = self._device(op["device_id"])
        self._sync()  # Complete the read/history window; ETag protects subsequent changes.
        fields = {k for k in op["before_values"] if op["before_values"][k] != op["after_values"][k]}
        conflicts = []
        now = values(current["body"])
        for field in fields:
            if now[field] != op["after_values"][field]:
                conflicts.append(
                    {
                        "field": field,
                        "reason": "Current value differs",
                        "expected": op["after_values"][field],
                        "current": now[field],
                    }
                )
        # A fully evidenced write+inverse pair is net-zero. This permits repeated
        # same-field updates within a task to be undone in reverse order.
        ignored = set()
        for row in self.store.db.execute(
            "SELECT a.id,b.id FROM operations a JOIN operations b ON b.reverses=a.id "
            "WHERE b.state='applied' AND a.device_id=?",
            (op["device_id"],),
        ):
            original, correction = self.get_operation(row[0]), self.get_operation(row[1])
            if exact_correction(original, correction):
                ignored.update((original["native_id"], correction["native_id"]))
        for record in self._records():
            if (
                record["changed_object_type"] != "dcim.device"
                or record["changed_object_id"] != op["device_id"]
            ):
                continue
            if record["id"] <= op["native_id"] or record["id"] in ignored:
                continue
            for field in fields:
                if record["prechange_data"].get(field) != record["postchange_data"].get(field):
                    conflicts.append(
                        {
                            "field": field,
                            "reason": "Intervening field change (including ABA)",
                            "native_id": record["id"],
                        }
                    )
        etag = current["headers"].get("etag")
        if not etag:
            raise RuntimeError("Server did not supply a concurrency precondition")
        return {
            "status": "conflicted" if conflicts else "ready",
            "operation_id": operation_id,
            "device_id": op["device_id"],
            "native_id": op["native_id"],
            "etag": etag,
            "inverse": {k: op["before_values"][k] for k in sorted(fields)},
            "conflicts": conflicts,
            "warning": (
                "Newer edits affect the fields being undone. Review the conflicts; no write will be made."
                if conflicts
                else None
            ),
            "external_effects": "Webhooks and downstream actions are not reversed.",
        }

    def preview_undo(self, operation_id):
        with self.store.lock():
            return self._preview(operation_id)

    def _undo(self, operation_id, operation_key, task_id=None):
        previous = self.store.db.execute(
            "SELECT id,reverses FROM operations WHERE operation_key=?", (operation_key,)
        ).fetchone()
        if previous:
            if previous["reverses"] != operation_id:
                raise ValueError("Idempotency key belongs to another operation")
            receipt = self.get_operation(previous["id"])
            original = self.get_operation(operation_id)
            if receipt["state"] in {"applied", "no_change"} and not exact_correction(original, receipt):
                return self._preview(operation_id)
            return {
                "status": receipt["state"],
                "original_operation_id": operation_id,
                "correction": receipt,
                "replayed": True,
                "warning": (
                    "Previous correction did not complete; inspect its receipt before trying a new key."
                    if receipt["state"] != "applied"
                    else None
                ),
            }
        preview = self._preview(operation_id)
        if preview["status"] != "ready":
            self.store.event("undo_assessed", preview, operation_id)
            return preview
        if task_id is None:
            task_id = str(uuid.uuid4())
            with self.store.transaction():
                self.store.db.execute(
                    "INSERT INTO tasks VALUES(?,?,?,NULL)", (task_id, "Undo " + operation_id, time.time())
                )
                self.store.event("task_started", {"task_id": task_id, "purpose": "Undo " + operation_id})
        self.fault("before_undo_apply")
        try:
            result = self._write(
                task_id,
                operation_key,
                preview["device_id"],
                preview["etag"],
                preview["inverse"],
                reverses=operation_id,
            )
        except ValueError as exc:
            if "Stale expected_etag" not in str(exc):
                raise
            warning = {
                "status": "conflicted",
                "operation_id": operation_id,
                "warning": "The object changed during undo. No correction was dispatched; review current values.",
            }
            self.store.event("undo_conflict", warning, operation_id)
            return warning
        if result["state"] in {"applied", "no_change"} and not exact_correction(
            self.get_operation(operation_id), result
        ):
            return self._preview(operation_id)
        return {
            "status": result["state"],
            "original_operation_id": operation_id,
            "correction": result,
            "warning": (
                "Correction was not verified as applied. Review the receipt and current state; do not force an overwrite."
                if result["state"] != "applied"
                else None
            ),
            "external_effects": preview["external_effects"],
        }

    def undo_operation(self, operation_id, operation_key):
        with self.store.lock():
            return self._undo(operation_id, operation_key)

    def undo_task(self, task_id):
        with self.store.lock():
            task = self.get_task(task_id)
            if task["task"]["reverses_task"]:
                raise ValueError("Undo of a corrective task is unsupported")
            existing = self.store.db.execute(
                "SELECT id FROM tasks WHERE reverses_task=?", (task_id,)
            ).fetchone()
            if existing:
                correction_task = existing[0]
            else:
                correction_task = str(uuid.uuid4())
                with self.store.transaction():
                    self.store.db.execute(
                        "INSERT INTO tasks VALUES(?,?,?,?)",
                        (correction_task, "Undo task " + task_id, time.time(), task_id),
                    )
                    self.store.event("task_started", {"task_id": correction_task, "reverses_task": task_id})
            results = []
            for op in reversed(task["operations"]):
                if op["state"] in {"failed", "rejected"} or (
                    op["state"] == "no_change" and (not op["before_values"] or op["native_id"] is not None)
                ):
                    continue
                failed_attempts = self.store.db.execute(
                    "SELECT count(*) FROM operations WHERE reverses=? AND state='failed'", (op["id"],)
                ).fetchone()[0]
                result = self._undo(
                    op["id"], "task-undo:" + op["id"] + ":" + str(failed_attempts), correction_task
                )
                results.append(result)
                if result["status"] not in {"applied", "already_undone", "no_change"}:
                    return {
                        "status": "partial_or_blocked",
                        "task_id": task_id,
                        "correction_task_id": correction_task,
                        "results": results,
                        "atomic": False,
                    }
            return {
                "status": "undone",
                "task_id": task_id,
                "correction_task_id": correction_task,
                "results": results,
                "atomic": False,
            }

    @consistent_read
    def get_device_history(self, device_id):
        if self.allowed is not None and device_id not in self.allowed:
            raise ValueError("Device is outside the configured allowlist")
        return {
            "device_id": device_id,
            "archived_changes": [
                r
                for r in self._records()
                if r["changed_object_type"] == "dcim.device" and r["changed_object_id"] == device_id
            ],
            "freshness": self.observability()["archive"],
        }

    @consistent_read
    def observability(self):
        row = self.store.db.execute("SELECT value FROM metadata WHERE key='archive_health'").fetchone()
        health = json.loads(row[0]) if row else {"at": None, "missing_native_ids": []}
        health["age_seconds"] = None if health["at"] is None else time.time() - health["at"]
        health["stale"] = health["age_seconds"] is None or health["age_seconds"] > 60
        states = {
            r[0]: r[1] for r in self.store.db.execute("SELECT state,count(*) FROM operations GROUP BY state")
        }
        unresolved = [
            dict(r)
            for r in self.store.db.execute(
                "SELECT id,device_id,state,created FROM operations WHERE state IN ('prepared','dispatched','uncertain','applied_unverified')"
            )
        ]
        return {
            "states": states,
            "unresolved": unresolved,
            "archive": health,
            "native_records": self.store.db.execute("SELECT count(*) FROM native_changes").fetchone()[0],
            "integrity": self.store.verify(),
            "event_counts": {
                r[0]: r[1] for r in self.store.db.execute("SELECT kind,count(*) FROM events GROUP BY kind")
            },
        }

    @consistent_read
    def recovery_bundle(self, operation_id):
        self.store.verify()
        op = self.get_operation(operation_id)
        return {
            "schema_version": 1,
            "identity": json.loads(
                self.store.db.execute("SELECT value FROM metadata WHERE key='identity'").fetchone()[0]
            ),
            "operation": op,
            "inverse": op["before_values"],
            "native_evidence": [r for r in self._records() if r["id"] == op["native_id"]],
            "events": [
                dict(r)
                for r in self.store.db.execute(
                    "SELECT * FROM events WHERE operation_id=? ORDER BY seq", (operation_id,)
                )
            ],
            "guidance": "Offline evidence only. Never apply this inverse blindly: preview undo against live state and current ETag.",
        }
