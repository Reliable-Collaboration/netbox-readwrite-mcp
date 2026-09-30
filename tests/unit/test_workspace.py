from copy import deepcopy
import json
import uuid

import pytest

from netbox_readwrite_mcp.workspace import WorkspaceService
from netbox_readwrite_mcp.server import call
from tests.unit.fakes import NetBoxModel


class API(NetBoxModel):
    def get(self, path):
        if path == "":
            return {"body": {"dcim": self.url + "/api/dcim/", "status": self.url + "/api/status/"}}
        if path == "dcim/":
            return {"body": {"devices": self.url + "/api/dcim/devices/"}, "status": 200, "headers": {}}
        if path.split("?")[0] == "dcim/devices/":
            return {
                "status": 200,
                "headers": {},
                "body": {
                    "count": len(self.devices),
                    "results": deepcopy(list(self.devices.values())),
                    "next": None,
                },
            }
        return super().get(path.split("?")[0])

    def request(self, method, path, data=None, headers=None, files=None):
        if method == "GET":
            return self.get(path)
        if method == "OPTIONS":
            return {"status": 200, "body": {"actions": {}}, "headers": {}}
        if method == "PATCH":
            return super().request(method, path, data, headers)
        if method == "POST":
            pk = max(self.devices) + 1
            self.devices[pk] = {"id": pk, "name": "new", "description": "", "status": "active", "serial": ""}
            self.revisions[pk] = 1
            rid = self.change(pk, data, actor="agent")
            self.rows[-1]["action"] = {"value": "create"}
            self.rows[-1]["prechange_data"] = {}
            return {"status": 201, "body": deepcopy(self.devices[pk]), "headers": {"x-request-id": rid}}
        if method == "DELETE":
            pk = int(path.strip("/").split("/")[-1])
            rid = self.change(pk, {}, actor="agent")
            self.rows[-1]["action"] = {"value": "delete"}
            self.rows[-1]["postchange_data"] = {}
            del self.devices[pk]
            return {"status": 204, "body": None, "headers": {"x-request-id": rid}}
        raise AssertionError(method)

    def graphql(self, query, variables):
        return {"status": 200, "body": {"data": variables}}


@pytest.fixture
def broad(tmp_path):
    service = WorkspaceService(API(), tmp_path / "journal.sqlite", "instance", "agent", None)
    service.task = service.begin_task("Broad tests")["task_id"]
    yield service
    service.store.close()


def key():
    return str(uuid.uuid4())


def test_crud_discovery_reads_schema_aliases_and_recovery(broad):
    assert broad.discover_models()["models"][0]["resource"] == "dcim/devices/"
    assert broad.discover_models(True)["models"]
    assert broad.catalog.resolve("dcim.devices") == "dcim/devices/"
    assert broad.get_objects("devices", {"q": "new"}, ["name"])["data"]["count"] == 2
    opkey = key()
    op = broad.create_object(broad.task, opkey, "devices", {"name": "new"})
    assert op["state"] == "applied"
    assert broad.create_object(broad.task, opkey, "devices", {"name": "new"})["id"] == op["id"]
    with pytest.raises(ValueError, match="Idempotency"):
        broad.create_object(broad.task, opkey, "devices", {"name": "different"})
    obj = broad.get_object_by_id("devices", 3, ["name"])
    update = broad.update_object(broad.task, key(), "devices", 3, obj["etag"], {"description": "B"})
    assert broad.preview_undo(update["id"])["status"] == "ready"
    result = broad.undo_operation(update["id"], key())
    assert result["status"] == "applied"
    assert broad.preview_undo(update["id"])["status"] == "already_undone"
    assert broad.preview_undo(result["correction"]["id"])["status"] == "unsupported"
    assert broad.preview_undo(op["id"])["status"] == "conflicted"
    assert broad.undo_task(broad.task)["status"] == "partial_or_blocked"
    assert broad.find_operation(opkey)["operation"]["id"] == op["id"]
    assert len(broad.get_task(broad.task)["operations"]) == 2
    assert broad.observability()["unresolved"] == []
    bundle = broad.recovery_bundle(op["id"])
    assert bundle["operation"]["native_ids"]
    assert broad.diagnostic_report(op["id"])["operation"]["state"] == "applied"
    assert broad.query("dcim/devices/")["status"] == 200
    assert broad.graphql("{a}", {"a": 1})["body"]["data"] == {"a": 1}
    current = broad.get_object_by_id("devices", 3)
    assert broad.delete_object(broad.task, key(), "devices", 3, current["etag"])["state"] == "applied"


@pytest.mark.parametrize(
    "status,state",
    [
        (200, "completed"),
        (202, "accepted"),
        (204, "completed"),
        (400, "failed"),
        (401, "failed"),
        (403, "failed"),
        (404, "failed"),
        (409, "failed"),
        (412, "failed"),
        (422, "failed"),
        (429, "uncertain"),
        (500, "uncertain"),
    ],
)
def test_receipt_states_without_native_changes(broad, status, state):
    broad.api.request = lambda *a, **kw: {"status": status, "headers": {}, "body": {}}
    op = broad.execute_action(broad.task, key(), "POST", "extras/action/", {})
    assert op["state"] == state
    assert broad.get_operation(op["id"])["state"] == state
    assert broad.preview_undo(op["id"])["status"] in {"blocked", "no_change"}


def test_uncertainty_blocks_other_paths_and_reconciles(broad):
    broad.fault = lambda p: (_ for _ in ()).throw(OSError()) if p == "after_response" else None
    op = broad.create_object(broad.task, key(), "dcim/devices/", {"name": "uncertain"})
    assert op["state"] == "uncertain"
    with pytest.raises(RuntimeError, match="unresolved"):
        broad.update_device(broad.task, key(), 1, broad.read_device(1)["etag"], {"description": "B"})
    broad.fault = lambda p: None
    broad.reconcile()
    assert broad.get_operation(op["id"])["state"] == "applied"


def test_prepared_and_unknown_dispatch_recovery(broad):
    def kill(point):
        if point == "after_dispatch_record":
            raise SystemExit()

    broad.fault = kill
    opkey = key()
    with pytest.raises(SystemExit):
        broad.create_object(broad.task, opkey, "dcim/devices/", {"name": "missing"})
    broad.fault = lambda p: None
    broad.reconcile()
    assert broad.find_operation(opkey)["operation"]["state"] == "dispatched"
    with pytest.raises(RuntimeError, match="unresolved"):
        broad.create_object(broad.task, key(), "dcim/devices/", {})


def test_resource_integrity_projection_and_export(broad, tmp_path):
    op = broad.create_object(broad.task, key(), "dcim/devices/", {})
    assert len(broad.store.export()["resource_operations"]) == 1
    backup = broad.store.backup(tmp_path / "backup.sqlite")
    assert backup["sha256"]
    document = broad.get_operation(op["id"])
    document["path"] = "changed/"
    broad.store.db.execute(
        "UPDATE resource_operations SET document=? WHERE id=?", (json.dumps(document), op["id"])
    )
    with pytest.raises(RuntimeError, match="integrity"):
        broad.store.verify()


@pytest.mark.parametrize(
    "name,args",
    [
        ("create_object", {"object_type": "dcim/devices/", "data": []}),
        (
            "update_object",
            {"object_type": "dcim/devices/", "object_id": False, "expected_etag": "x", "data": {}},
        ),
        ("delete_object", {"object_type": "dcim/devices/", "object_id": 0, "expected_etag": "x"}),
        ("execute_action", {"method": "GET", "path": "dcim/devices/"}),
        ("bulk", {"operations": []}),
        ("bulk", {"operations": [{"action": "shell", "arguments": {}}]}),
        ("bulk", {"operations": [{"action": "create_object", "arguments": {"task_id": "fake"}}]}),
    ],
)
def test_invalid_mutation_arguments(broad, name, args):
    with pytest.raises(ValueError):
        getattr(broad, name)(task_id=broad.task, operation_key=key(), **args)


@pytest.mark.parametrize(
    "name,args",
    [
        ("get_objects", {"object_type": "devices", "limit": 0}),
        ("get_objects", {"object_type": "devices", "offset": -1}),
        ("get_objects", {"object_type": "devices", "fields": "bad"}),
        ("get_object_by_id", {"object_type": "devices", "object_id": 0}),
        ("get_object_by_id", {"object_type": "devices", "object_id": 1, "fields": [1]}),
        ("graphql", {"query": "mutation { unsafe }"}),
    ],
)
def test_invalid_reads(broad, name, args):
    with pytest.raises(ValueError):
        getattr(broad, name)(**args)


def test_read_only_blocks_all_mutations(broad):
    broad.read_only = True
    assert broad.get_objects("dcim/devices/")
    for name, args in [
        (
            "create_object",
            {"task_id": broad.task, "operation_key": key(), "object_type": "dcim/devices/", "data": {}},
        ),
        ("undo_operation", {"operation_id": "unknown", "operation_key": key()}),
        ("undo_task", {"task_id": broad.task}),
        ("update_device", {}),
        ("web_submit", {"task_id": broad.task, "operation_key": key(), "path": "/", "data": {}}),
    ]:
        with pytest.raises(ValueError, match="read_only"):
            getattr(broad, name)(**args)


def test_legacy_scope_cannot_escape_through_general_tools(tmp_path):
    svc = WorkspaceService(API(), tmp_path / "old.sqlite", "instance", "agent", [1])
    try:
        with pytest.raises(ValueError, match="allowlist"):
            svc.discover_models()
    finally:
        svc.store.close()


def test_bulk_workflow_failures_are_explicit(broad):
    steps = [{"action": "create_object", "arguments": {"object_type": "dcim/devices/", "data": {}}}]
    assert broad.bulk(broad.task, key(), steps)["status"] == "completed"
    assert (
        broad.bulk(broad.task, key(), [{"action": "create_object", "arguments": {}}])["status"]
        == "partial_or_blocked"
    )
    assert broad.run_workflow(broad.task, key(), "import os")["status"] == "partial_or_blocked"
    assert (
        broad.run_workflow(broad.task, key(), 'result = tool("diagnostic_report")')["status"]
        == "partial_or_blocked"
    )
    assert call(broad, "get_objects", {"object_type": "dcim/devices/", "offset": 0})["data"]["count"] == 3


def test_live_schema_resolves_recursive_references_and_refreshes(broad):
    original = broad.api.request
    schema = {
        "paths": {
            "/api/dcim/devices/": {
                "post": {"requestBody": {"schema": {"$ref": "#/components/schemas/Device"}}}
            }
        },
        "components": {
            "schemas": {
                "Device": {
                    "type": "object",
                    "properties": {"related": {"$ref": "#/components/schemas/Device"}},
                }
            }
        },
    }
    broad.api.request = lambda method, path, *args, **kw: (
        {"status": 200, "body": schema} if path.startswith("schema/") else original(method, path, *args, **kw)
    )
    described = broad.get_schema("dcim/devices/")
    assert described["schemas"]["Device"]["type"] == "object"
    assert broad.get_schema("dcim/devices/")["paths"]
    broad.discover_models(True)
    assert broad.catalog.schema is None
    broad.api.request = lambda method, path, *args, **kw: (
        {"status": 403, "body": None} if path.startswith("schema/") else original(method, path, *args, **kw)
    )
    with pytest.raises(RuntimeError, match="schema unavailable"):
        broad.get_schema("dcim/devices/")
    with pytest.raises(ValueError, match="ambiguous"):
        broad.catalog.resolve("does-not-exist")


def test_all_entrypoints_share_operation_key_namespace(broad):
    opkey = key()
    broad.create_object(broad.task, opkey, "dcim/devices/", {})
    with pytest.raises(ValueError, match="Idempotency"):
        broad.update_device(broad.task, opkey, 1, broad.read_device(1)["etag"], {"description": "B"})


def test_pending_jobs_reconcile_to_terminal_state(broad):
    old_get = broad.api.get
    broad.api.request = lambda *a, **kw: {
        "status": 202,
        "headers": {},
        "body": {"url": broad.api.url + "/api/core/jobs/1/"},
    }
    op = broad.execute_action(broad.task, key(), "POST", "extras/action/", {})
    assert op["state"] == "accepted"
    broad.api.get = lambda p: (
        {"body": {"status": {"value": "completed"}}} if p == "core/jobs/1/" else old_get(p)
    )
    broad.reconcile()
    assert broad.get_operation(op["id"])["state"] == "job_completed"


def test_workflow_replay_retains_original_read_decisions(broad):
    code = """
items = tool("get_objects", object_type="dcim/devices/")
if items["data"]["count"] == 2:
    first = tool("create_object", object_type="dcim/devices/", data={"name": "first"})
second = tool("create_object", object_type="dcim/devices/", data={"name": "second"})
result = second["id"]
"""
    operation_key = key()
    first = broad.run_workflow(broad.task, operation_key, code)
    assert first["status"] == "completed"
    assert len(broad.api.devices) == 4
    second = broad.run_workflow(broad.task, operation_key, code)
    assert second["status"] == "completed" and second["result"] == first["result"]
    assert len(broad.api.devices) == 4


def test_invalid_upload_never_enters_dispatch_or_blocks_future_work(broad):
    with pytest.raises(ValueError):
        broad.execute_action(
            broad.task,
            key(),
            "POST",
            "extras/scripts/upload/",
            {},
            files=[{"field": "file", "filename": "test.py", "base64": "not base64!"}],
        )
    assert broad.observability()["unresolved"] == []
    assert broad.store.db.execute("SELECT count(*) FROM resource_operations").fetchone()[0] == 0
    assert broad.create_object(broad.task, key(), "dcim/devices/", {})["state"] == "applied"


def test_general_observers_use_one_snapshot(broad):
    op = broad.create_object(broad.task, key(), "dcim/devices/", {})
    original = broad.store.verify
    seen = []

    def verify():
        seen.append(broad.store.db.in_transaction)
        return original()

    broad.store.verify = verify
    assert broad.observability()["integrity"]["integrity"] == "verified"
    assert seen == [True]
    assert not broad.store.db.in_transaction
    assert broad.get_task(broad.task)["operations"][0]["id"] == op["id"]


def test_schema_default_excludes_response_graph_and_preserves_write_contract(broad):
    write = {
        "type": "object",
        "required": ["name"],
        "properties": {
            "name": {"type": "string", "maxLength": 100, "description": "A name"},
            "status": {"type": "string", "enum": ["active", "planned"]},
        },
    }
    schema = {
        "paths": {
            "/api/dcim/devices/": {
                "get": {
                    "parameters": [{"in": "query", "name": "name", "schema": {"type": "string"}}],
                    "responses": {"200": {"schema": {"$ref": "#/components/schemas/LargeResponse"}}},
                },
                "post": {
                    "requestBody": {
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Write"}}}
                    }
                },
            }
        },
        "components": {"schemas": {"Write": write, "LargeResponse": {"description": "x" * 100000}}},
    }
    original = broad.api.request
    broad.api.request = lambda method, path, *args, **kw: (
        {"status": 200, "body": schema} if path.startswith("schema/") else original(method, path, *args, **kw)
    )
    compact = call(broad, "get_schema", {"object_type": "dcim/devices/"})
    assert len(json.dumps(compact)) < 2000
    assert compact["schemas"]["Write"]["required"] == ["name"]
    assert compact["schemas"]["Write"]["properties"]["status"]["enum"] == ["active", "planned"]
    assert compact["filters"] == {"name": "string"}
    assert "LargeResponse" not in compact["schemas"]
    full = call(broad, "get_schema", {"object_type": "dcim/devices/", "full": True})
    assert len(full["schemas"]["LargeResponse"]["description"]) == 100000
