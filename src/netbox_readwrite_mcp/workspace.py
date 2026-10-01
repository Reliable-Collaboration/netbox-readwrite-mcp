"""General NetBox operations with durable, inspectable execution receipts."""

import json
import re
import time
import uuid

from .catalog import Catalog, api_path, query_string
from .compatibility import NETBOX_VERSION, normalization_profile
from .service import Service
from .store import digest, encode, consistent_read

PENDING = {"prepared", "dispatched", "uncertain", "accepted"}


class WorkspaceService(Service):
    def __init__(self, *args, read_only=False, web_password_file=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.catalog = Catalog(self.api)
        self.read_only = read_only
        self.web_password_file = web_password_file
        self.web = None
        self.store.db.execute(
            "CREATE TABLE IF NOT EXISTS resource_operations(id TEXT PRIMARY KEY, operation_key TEXT UNIQUE NOT NULL, task_id TEXT NOT NULL REFERENCES tasks(id), state TEXT NOT NULL, document TEXT NOT NULL)"
        )

    def _broad(self, write=False):
        if self.allowed is not None:
            raise ValueError(
                "Legacy device allowlist journal: general operations require an explicitly migrated broad-scope journal"
            )
        if write and self.read_only:
            raise ValueError("This connection is read_only")
        normalization_profile(self.api.get("status/")["body"]["netbox-version"])

    def discover_models(self, refresh=False):
        self._broad()
        return {
            "netbox_version": NETBOX_VERSION,
            "models": self.catalog.discover(refresh),
            "scope": "NetBox token permissions",
            "content_is_untrusted_data": True,
        }

    def get_schema(self, object_type, full=False, action=None):
        self._broad()
        return self.catalog.describe(object_type, full=full, action=action)

    def get_objects(self, object_type, filters=None, fields=None, limit=100, offset=0):
        self._broad()
        if type(limit) is not int or not 1 <= limit <= 1000 or type(offset) is not int or offset < 0:
            raise ValueError("limit must be 1–1000 and offset must be nonnegative")
        resource = self.catalog.resolve(object_type)
        self.catalog.validate_filters(resource, filters)
        params = {**(filters or {}), "limit": limit, "offset": offset}
        if fields:
            if not isinstance(fields, list) or any(not isinstance(x, str) for x in fields):
                raise ValueError("fields must be a list of strings")
            params["fields"] = ",".join(fields)
        result = self.api.get(resource + "?" + query_string(params))
        return {"resource": resource, "data": result["body"], "content_is_untrusted_data": True}

    def get_object_by_id(self, object_type, object_id, fields=None):
        self._broad()
        if type(object_id) is not int or object_id < 1:
            raise ValueError("object_id must be a positive integer")
        path = self.catalog.resolve(object_type) + str(object_id) + "/"
        if fields:
            if not isinstance(fields, list) or any(not isinstance(x, str) for x in fields):
                raise ValueError("fields must be a list of strings")
            path += "?" + query_string({"fields": ",".join(fields)})
        result = self.api.get(path)
        return {
            "data": result["body"],
            "etag": result["headers"].get("etag"),
            "content_is_untrusted_data": True,
        }

    def get_changelogs(self, filters=None, limit=100, offset=0):
        return self.get_objects("core/object-changes/", filters, None, limit, offset)

    def query(self, path, filters=None):
        self._broad()
        path = api_path(path)
        self.catalog.validate_filters(path, filters)
        result = self.api.get(path + ("?" + query_string(filters) if filters else ""))
        return {**result, "content_is_untrusted_data": True}

    def graphql(self, query, variables=None):
        self._broad()
        # NetBox exposes a query-only GraphQL schema. Reject explicit mutation operations too.
        if not isinstance(query, str) or re.search(r"\bmutation\b", query):
            raise ValueError("graphql accepts queries only")
        return {**self.api.graphql(query, variables or {}), "content_is_untrusted_data": True}

    def _resource_operation(self, operation_id):
        row = self.store.db.execute(
            "SELECT document FROM resource_operations WHERE id=?", (operation_id,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    @consistent_read
    def get_operation(self, operation_id):
        return self._resource_operation(operation_id) or super().get_operation(operation_id)

    @consistent_read
    def find_operation(self, operation_key):
        row = self.store.db.execute(
            "SELECT document FROM resource_operations WHERE operation_key=?", (operation_key,)
        ).fetchone()
        if row:
            return {
                "found": True,
                "operation": json.loads(row[0]),
                "guidance": "Preserve the original key; reconcile uncertain outcomes. Never blindly replay.",
            }
        return super().find_operation(operation_key)

    @consistent_read
    def get_task(self, task_id):
        out = super().get_task(task_id)
        out["operations"].extend(
            json.loads(r[0])
            for r in self.store.db.execute(
                "SELECT document FROM resource_operations WHERE task_id=? ORDER BY rowid", (task_id,)
            )
        )
        sequence = {
            r[0]: r[1]
            for r in self.store.db.execute(
                "SELECT operation_id,seq FROM events WHERE kind IN ('prepared','resource_prepared')"
            )
        }
        out["operations"].sort(key=lambda x: sequence[x["id"]])
        return out

    def _save(self, op, initial=False):
        with self.store.transaction():
            if initial:
                self.store.db.execute(
                    "INSERT INTO resource_operations VALUES(?,?,?,?,?)",
                    (op["id"], op["operation_key"], op["task_id"], op["state"], encode(op)),
                )
            else:
                self.store.db.execute(
                    "UPDATE resource_operations SET state=?,document=? WHERE id=?",
                    (op["state"], encode(op), op["id"]),
                )
            self.store.event("resource_prepared" if initial else "resource_state", op, op["id"])

    def _evidence(self, op):
        receipt = op.get("last_receipt") or {}
        request_id = receipt.get("headers", {}).get("x-request-id")
        marker = "netbox-rw:" + op["id"]
        records = [
            r
            for r in self._records()
            if r["id"] > op["history_floor"]
            and r["user_name"] == self.actor
            and (r["message"] == marker or (request_id and r["request_id"] == request_id))
        ]
        if records:
            op["native_changes"] = records
            op["native_ids"] = [r["id"] for r in records]
            if op["state"] != "accepted":
                op["state"] = "applied"
            op["guidance"] = "Inspect all affected objects. Use preview_undo for recovery classification."
        return bool(records)

    def _execute(
        self,
        task_id,
        operation_key,
        method,
        path,
        data,
        expected_etag=None,
        files=None,
        sender=None,
        transport="rest",
        reverses=None,
    ):
        self._broad(write=True)
        if files:
            from .api import multipart

            multipart(data or {}, files)
        if not isinstance(operation_key, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{8,160}", operation_key):
            raise ValueError(
                "operation_key must be 8–160 ASCII letters, digits, dots, underscores, colons, or hyphens"
            )
        if not self.store.db.execute("SELECT 1 FROM tasks WHERE id=?", (task_id,)).fetchone():
            raise ValueError("Unknown task")
        fingerprint = digest(
            {
                "task_id": task_id,
                "method": method,
                "path": path,
                "data": data,
                "expected_etag": expected_etag,
                "files": files,
                "transport": transport,
                "reverses": reverses,
            }
        )
        with self.store.lock():
            existing = self.find_operation(operation_key)
            if existing["found"]:
                op = existing["operation"]
                if op["fingerprint"] != fingerprint:
                    raise ValueError("Idempotency key was already used for different arguments")
                return op
            self.store.verify()
            self._sync()
            self._reconcile_resources()
            # An unresolved action may affect dependencies anywhere in a small estate.
            pending = self.store.db.execute(
                "SELECT id FROM resource_operations WHERE state IN ('prepared','dispatched','uncertain','accepted')"
            ).fetchall()
            legacy = self.store.db.execute(
                "SELECT id FROM operations WHERE state IN ('prepared','dispatched','uncertain','applied_unverified')"
            ).fetchall()
            if pending or legacy:
                raise RuntimeError("There are unresolved operations; reconcile before a new mutation")
            before = None
            if transport == "rest" and method in {"PATCH", "PUT", "DELETE"} and re.search(r"/\d+/$", path):
                before_response = self.api.get(path)
                before = before_response["body"]
                if not expected_etag or before_response["headers"].get("etag") != expected_etag:
                    raise ValueError("Stale or absent expected_etag: read the object before editing/deleting")
            op_id = str(uuid.uuid4())
            op = {
                "id": op_id,
                "operation_key": operation_key,
                "task_id": task_id,
                "fingerprint": fingerprint,
                "method": method,
                "path": path,
                "transport": transport,
                "reverses": reverses,
                "requested": data,
                "files": files,
                "before": before,
                "expected_etag": expected_etag,
                "created": time.time(),
                "history_floor": max((r["id"] for r in self._records()), default=0),
                "state": "prepared",
                "last_receipt": None,
                "native_changes": [],
                "native_ids": [],
                "guidance": "Not dispatched",
            }
            if transport == "website":
                op["guarantee_limits"] = {
                    "conditional_write": False,
                    "pre_write_snapshot": False,
                    "automatic_undo": False,
                    "validation": "Inspect returned HTML text and verify authoritative state. HTTP 200 is not proof of success.",
                }
            self._save(op, initial=True)
            self.fault("after_prepare")
            op["state"] = "dispatched"
            op["guidance"] = "Dispatch may have committed. Never retry with a new key."
            self._save(op)
            self.fault("after_dispatch_record")
            payload = data
            if (
                transport == "rest"
                and method in {"POST", "PATCH", "PUT"}
                and isinstance(data, dict)
                and not files
            ):
                payload = {**data, "changelog_message": "netbox-rw:" + op_id}
            headers = {"If-Match": expected_etag} if expected_etag else {}
            try:
                receipt = (
                    sender() if sender else self.api.request(method, path, payload, headers, files=files)
                )
                self.fault("after_response")
                op["last_receipt"] = receipt
                code = receipt["status"]
                body = receipt.get("body")
                job = (
                    body.get("result")
                    if isinstance(body, dict) and path.startswith("extras/scripts/")
                    else None
                )
                if isinstance(body, dict) and code == 202:
                    job = body.get("job", body)
                if (
                    isinstance(job, dict)
                    and isinstance(job.get("url"), str)
                    and job["url"].startswith(self.api.url + "/api/core/jobs/")
                ):
                    op["job_path"] = job["url"][len(self.api.url + "/api/") :]
                if code == 202 or "job_path" in op:
                    op["state"] = "accepted"
                    op["guidance"] = (
                        "Asynchronous job accepted, not completed. Inspect the job with query and retain its result."
                    )
                elif 200 <= code < 400:
                    op["state"] = "completed"
                    op["guidance"] = (
                        "HTTP exchange completed; inspect the result for validation errors or job state. No verified native mutation evidence yet."
                    )
                elif code in {400, 401, 403, 404, 405, 409, 412, 422}:
                    op["state"] = "failed"
                    op["guidance"] = (
                        "Definite rejection. Inspect native errors before a deliberate new attempt."
                    )
                else:
                    op["state"] = "uncertain"
                self._save(op)
            except Exception as exc:
                op["state"] = "uncertain"
                op["guidance"] = "Response lost or unreadable. Reconcile; never replay under a new key."
                op["error_type"] = type(exc).__name__
                self._save(op)
                return op
            try:
                self._sync()
                self._evidence(op)
                self._save(op)
            except Exception as exc:
                op["evidence_warning"] = type(exc).__name__
                self._save(op)
            return op

    def create_object(self, task_id, operation_key, object_type, data):
        if not isinstance(data, dict):
            raise ValueError("data must be an object")
        return self._execute(task_id, operation_key, "POST", self.catalog.resolve(object_type), data)

    def update_object(self, task_id, operation_key, object_type, object_id, expected_etag, data):
        if type(object_id) is not int or object_id < 1 or not isinstance(data, dict):
            raise ValueError("object_id must be positive and data must be an object")
        return self._execute(
            task_id,
            operation_key,
            "PATCH",
            self.catalog.resolve(object_type) + str(object_id) + "/",
            data,
            expected_etag,
        )

    def delete_object(self, task_id, operation_key, object_type, object_id, expected_etag):
        if type(object_id) is not int or object_id < 1:
            raise ValueError("object_id must be positive")
        return self._execute(
            task_id,
            operation_key,
            "DELETE",
            self.catalog.resolve(object_type) + str(object_id) + "/",
            None,
            expected_etag,
        )

    def execute_action(self, task_id, operation_key, method, path, data=None, expected_etag=None, files=None):
        if method not in {"POST", "PUT", "PATCH", "DELETE"}:
            raise ValueError("Use query for GET; mutation methods are POST, PUT, PATCH, DELETE")
        if data is not None and not isinstance(data, (dict, list)):
            raise ValueError(
                "data must be a JSON object or array, not a JSON-encoded string or scalar. "
                "Pass structured data directly; this request was not sent to NetBox."
            )
        return self._execute(task_id, operation_key, method, api_path(path), data, expected_etag, files)

    def bulk(self, task_id, operation_key, operations):
        if not isinstance(operations, list) or not 1 <= len(operations) <= 1000:
            raise ValueError("operations must contain 1–1000 steps")
        for item in operations:
            if (
                not isinstance(item, dict)
                or set(item) != {"action", "arguments"}
                or item.get("action")
                not in {
                    "create_object",
                    "update_object",
                    "delete_object",
                    "execute_action",
                }
            ):
                raise ValueError(
                    "Each bulk step requires action and arguments. action must be create_object, update_object, delete_object or execute_action (not create/update/delete). No steps were executed."
                )
            args = item.get("arguments")
            if not isinstance(args, dict) or {"task_id", "operation_key"} & args.keys():
                raise ValueError(
                    "Step arguments must be an object excluding task_id and operation_key. No steps were executed."
                )
        results = []
        for index, item in enumerate(operations):
            args = item["arguments"]
            try:
                result = getattr(self, item["action"])(
                    task_id=task_id, operation_key=f"{operation_key}.{index}", **args
                )
            except Exception as exc:
                results.append({"index": index, "error": str(exc)})
                return {"status": "partial_or_blocked", "atomic": False, "results": results}
            results.append(result)
            if result["state"] not in {"applied", "completed"}:
                return {"status": "partial_or_blocked", "atomic": False, "results": results}
        return {"status": "completed", "atomic": False, "results": results}

    def _reconcile_resources(self):
        for row in self.store.db.execute(
            "SELECT document FROM resource_operations WHERE state IN ('prepared','dispatched','uncertain','accepted','completed')"
        ).fetchall():
            op = json.loads(row[0])
            if op["state"] == "prepared":
                op["state"] = "failed"
                op["guidance"] = "Abandoned before dispatch; no request sent."
                self._save(op)
            else:
                changed = self._evidence(op)
                if op["state"] == "accepted" and op.get("job_path"):
                    job = self.api.get(op["job_path"])["body"]
                    status = job.get("status")
                    status = status.get("value") if isinstance(status, dict) else status
                    op["job_result"] = job
                    if status in {"completed", "errored", "failed", "stopped"}:
                        op["state"] = "job_completed" if status == "completed" else "job_failed"
                        op["guidance"] = (
                            "Inspect job_result and native_changes. Failed jobs may have partial effects; never assume rollback."
                        )
                    changed = True
                if changed:
                    self._save(op)

    def reconcile(self):
        with self.store.lock():
            self.store.verify()
            self._sync()
            self._reconcile()
            self._reconcile_resources()
            return self.observability()

    @consistent_read
    def observability(self):
        out = super().observability()
        rows = self.store.db.execute("SELECT id,state FROM resource_operations").fetchall()
        for row in rows:
            out["states"][row["state"]] = out["states"].get(row["state"], 0) + 1
            if row["state"] in PENDING:
                out["unresolved"].append(dict(row))
        out["read_only"] = self.read_only
        return out

    def preview_undo(self, operation_id):
        from .recovery import assess

        op = self._resource_operation(operation_id)
        if not op:
            return super().preview_undo(operation_id)
        with self.store.lock():
            if op.get("reverses"):
                return {"status": "unsupported", "warning": "Undo of a correction is not supported"}
            corrections = [
                json.loads(r[0])
                for r in self.store.db.execute("SELECT document FROM resource_operations")
                if json.loads(r[0]).get("reverses") == operation_id and json.loads(r[0])["state"] != "failed"
            ]
            if corrections:
                correction = corrections[-1]
                original = op["native_changes"][0]
                fields = {
                    k
                    for k in op["requested"]
                    if k != "changelog_message"
                    and original["prechange_data"].get(k) != original["postchange_data"].get(k)
                }
                restored = correction["native_changes"]
                exact = len(restored) == 1 and all(
                    restored[0]["postchange_data"].get(k) == original["prechange_data"].get(k) for k in fields
                )
                return {
                    "status": "already_undone"
                    if correction["state"] == "applied" and exact
                    else "incomplete_restore"
                    if correction["state"] == "applied"
                    else "correction_pending",
                    "correction": correction,
                }
            return assess(self, op)

    def undo_operation(self, operation_id, operation_key):
        if self.read_only:
            raise ValueError("This connection is read_only")
        op = self._resource_operation(operation_id)
        if not op:
            if self.store.db.execute(
                "SELECT 1 FROM resource_operations WHERE operation_key=?", (operation_key,)
            ).fetchone():
                raise ValueError("Idempotency key belongs to a general operation")
            return super().undo_operation(operation_id, operation_key)
        plan = self.preview_undo(operation_id)
        if plan["status"] != "ready":
            return plan
        task = self.begin_task("Correct operation " + operation_id)["task_id"]
        result = self._execute(
            task, operation_key, "PATCH", plan["path"], plan["inverse"], plan["etag"], reverses=operation_id
        )
        if result["state"] != "applied":
            return {"status": result["state"], "correction": result}
        verified = self.preview_undo(operation_id)
        return {
            "status": "applied" if verified["status"] == "already_undone" else verified["status"],
            "correction": result,
        }

    def undo_task(self, task_id):
        if self.read_only:
            raise ValueError("This connection is read_only")
        if self.store.db.execute("SELECT 1 FROM resource_operations WHERE task_id=?", (task_id,)).fetchone():
            results = []
            for op in reversed(self.get_task(task_id)["operations"]):
                result = self.undo_operation(op["id"], "task-undo-" + op["id"])
                results.append(result)
                if result["status"] not in {"applied", "already_undone", "no_change"}:
                    return {"status": "partial_or_blocked", "atomic": False, "results": results}
            return {"status": "undone", "atomic": False, "results": results}
        return super().undo_task(task_id)

    def _preflight(self, device_id):
        if self.store.db.execute(
            "SELECT 1 FROM resource_operations WHERE state IN ('prepared','dispatched','uncertain','accepted')"
        ).fetchone():
            raise RuntimeError("There are unresolved general operations; reconcile before editing a device")
        return super()._preflight(device_id)

    def update_device(self, *args, **kwargs):
        operation_key = kwargs.get("operation_key", args[1] if len(args) > 1 else None)
        if (
            operation_key
            and self.store.db.execute(
                "SELECT 1 FROM resource_operations WHERE operation_key=?", (operation_key,)
            ).fetchone()
        ):
            raise ValueError("Idempotency key belongs to a general operation")
        if self.read_only:
            raise ValueError("This connection is read_only")
        return super().update_device(*args, **kwargs)

    def recovery_bundle(self, operation_id):
        op = self._resource_operation(operation_id)
        if not op:
            return super().recovery_bundle(operation_id)
        self.store.verify()
        return {
            "schema_version": 2,
            "operation": op,
            "recovery": self.preview_undo(operation_id),
            "events": [
                dict(r)
                for r in self.store.db.execute(
                    "SELECT * FROM events WHERE operation_id=? ORDER BY seq", (operation_id,)
                )
            ],
        }

    def diagnostic_report(self, operation_id=None):
        """Safe-by-construction issue attachment: no inventory, URLs, purposes, or receipt bodies."""
        from . import __version__

        report = {
            "schema_version": 1,
            "server_version": __version__,
            "netbox_target": NETBOX_VERSION,
            "operation": None,
        }
        if operation_id:
            op = self.get_operation(operation_id)
            receipt = op.get("last_receipt") or {}
            report["operation"] = {
                "id": op["id"],
                "state": op["state"],
                "http_status": receipt.get("status"),
                "native_ids": op.get("native_ids", [op.get("native_id")]),
                "error_type": op.get("error_type"),
            }
        report["issue_repository"] = "Reliable-Collaboration/netbox-readwrite-mcp"
        report["guidance"] = (
            "Attach this report to a GitHub issue using the consuming agent's GitHub connection. Keep recovery_bundle and raw inventory private."
        )
        return report

    def _website(self):
        from .web import Website

        if self.web is None:
            self.web = Website(self.api, self.actor, self.web_password_file)
        self.web.login()
        return self.web

    def web_read(self, path):
        self._broad()
        return self._website().request(path)

    def web_submit(self, task_id, operation_key, path, data, files=None):
        self._broad(write=True)
        web = self._website()
        web.url(path)
        # Do not issue a preflight GET here: some views have action-like GETs.
        return self._execute(
            task_id,
            operation_key,
            "POST",
            path,
            data,
            files=files,
            sender=lambda: web.request(path, data, files),
            transport="website",
        )

    def run_workflow(self, task_id, operation_key, code):
        from .workflow import Workflow
        from .server import call

        self._broad()
        if not re.fullmatch(r"[A-Za-z0-9._:-]{8,120}", operation_key):
            raise ValueError("Workflow operation_key must be 8–120 safe ASCII characters")
        if not self.store.db.execute("SELECT 1 FROM tasks WHERE id=?", (task_id,)).fetchone():
            raise ValueError("Unknown task")
        identity = {"task_id": task_id, "operation_key": operation_key, "code_hash": digest(code)}
        with self.store.lock():
            previous = [
                json.loads(r[0])
                for r in self.store.db.execute("SELECT payload FROM events WHERE kind='workflow_started'")
            ]
            if any(x["operation_key"] == operation_key and x != identity for x in previous):
                raise ValueError("Idempotency key reused for different workflow")
            if identity not in previous:
                self.store.event("workflow_started", identity)
        calls = []
        writes = {"create_object", "update_object", "delete_object", "execute_action", "web_submit"}
        reads = {
            "get_objects",
            "get_object_by_id",
            "get_changelogs",
            "query",
            "graphql",
            "get_schema",
            "discover_models",
            "web_read",
        }

        def invoke(name, **arguments):
            if name not in writes | reads:
                raise ValueError("Tool unavailable inside workflow")
            if name in writes:
                if {"task_id", "operation_key"} & arguments.keys():
                    raise ValueError("Workflow owns task_id and operation_key")
                arguments = {
                    **arguments,
                    "task_id": task_id,
                    "operation_key": f"{operation_key}.{len(calls)}",
                }
            step_key = f"{operation_key}.{len(calls)}"
            step_fingerprint = digest({"name": name, "arguments": arguments})

            def cached_step():
                for row in self.store.db.execute(
                    "SELECT payload FROM events WHERE kind='workflow_step' ORDER BY seq DESC"
                ):
                    entry = json.loads(row[0])
                    if entry["key"] == step_key:
                        if entry["fingerprint"] != step_fingerprint:
                            raise ValueError("Idempotency workflow step changed arguments")
                        return entry["result"]
                return None

            with self.store.lock():
                self.store.verify()
                result = cached_step()
            if result is None:
                fresh = call(self, name, arguments)
                with self.store.lock():
                    result = cached_step()
                    if result is None:
                        result = fresh
                        self.store.event(
                            "workflow_step",
                            {"key": step_key, "fingerprint": step_fingerprint, "result": result},
                        )
            if name in writes:
                # An originally uncertain/accepted result may since have been reconciled.
                result = self.get_operation(result["id"])
            calls.append({"tool": name, "operation_id": result.get("id"), "state": result.get("state")})
            if name in writes and result.get("state") not in {"applied", "completed", "job_completed"}:
                raise RuntimeError(
                    "Workflow stopped at failed, accepted or uncertain operation; inspect receipt"
                )
            return result

        try:
            result = Workflow(invoke).run(code)
            return {"status": "completed", "result": result, "calls": calls, "atomic": False}
        except Exception as exc:
            return {"status": "partial_or_blocked", "error": str(exc), "calls": calls, "atomic": False}
