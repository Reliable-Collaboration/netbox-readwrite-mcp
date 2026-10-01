"""Real NetBox greenfield lifecycle through the public MCP surface."""

import json
import os
import sys
import uuid

import pytest

from netbox_readwrite_mcp.server import build_service
from tests.integration.mcp_client import Client
from scripts.lab import STATE, URL, VERSION

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("NETBOX_RW_LIVE") != "1", reason="Requires explicit disposable lab opt-in"
    ),
]


@pytest.fixture
def service(tmp_path):
    cfg = json.loads((STATE / "broad-config.json").read_text())
    assert cfg["netbox_url"] == URL
    cfg["journal"] = str(tmp_path / "journal.sqlite")
    svc = build_service(cfg)
    assert svc.api.get("status/")["body"]["netbox-version"] == VERSION
    yield svc
    svc.store.close()


@pytest.fixture
def client(tmp_path):
    cfg = json.loads((STATE / "broad-config.json").read_text())
    assert cfg["netbox_url"] == URL
    cfg["journal"] = str(tmp_path / "mcp.sqlite")
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg))
    obj = Client([sys.executable, "-m", "netbox_readwrite_mcp", "--config", str(path)])
    yield obj
    evidence = STATE / "evidence" / "greenfield"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / (uuid.uuid4().hex + ".json")).write_text(json.dumps(obj.transcript))
    obj.close()


def key():
    return str(uuid.uuid4())


def create(client, task, resource, data):
    result = client.tool("create_object", task_id=task, operation_key=key(), object_type=resource, data=data)
    assert result.get("state") == "applied", result
    return result["last_receipt"]["body"]


def test_companion_preserves_cold_openapi_generation(service):
    # NetBox caches schema responses for a day. A unique URL must exercise actual
    # generation, even when an old schema was cached before a plugin was installed.
    response = service.api.request("GET", "schema/?format=json&qualification=" + uuid.uuid4().hex)
    assert response["status"] == 200, response["body"]
    paths = response["body"]["paths"]
    assert "/api/dcim/devices/" in paths
    metadata = paths["/api/plugins/agent-support/filter-schema/"]["get"]
    assert any(p["name"] == "resource" and p["required"] for p in metadata["parameters"])


def test_greenfield_physical_and_virtual_inventory(client):
    """No existing object IDs: discover, create dependencies, cable/IP/VM, find by name, edit."""
    suffix = uuid.uuid4().hex[:10]
    resources = client.tool("discover_models")["models"]
    assert "dcim/devices/" in [r["resource"] for r in resources]
    task = client.tool("begin_task", purpose="Greenfield home lab " + suffix)["task_id"]
    site = create(client, task, "dcim/sites/", {"name": suffix, "slug": suffix})
    role = create(client, task, "dcim/device-roles/", {"name": suffix, "slug": suffix})
    vendor = create(client, task, "dcim/manufacturers/", {"name": suffix, "slug": suffix})
    dtype = create(
        client, task, "dcim/device-types/", {"manufacturer": vendor["id"], "model": suffix, "slug": suffix}
    )
    rack = create(client, task, "dcim/racks/", {"name": suffix, "site": site["id"], "u_height": 12})
    devices = []
    interfaces = []
    for n in range(2):
        device = create(
            client,
            task,
            "dcim/devices/",
            {
                "name": suffix + str(n),
                "site": site["id"],
                "role": role["id"],
                "device_type": dtype["id"],
                "rack": rack["id"],
                "position": n + 1,
                "face": "front",
            },
        )
        devices.append(device)
        interfaces.append(
            create(
                client,
                task,
                "dcim/interfaces/",
                {"device": device["id"], "name": "eth0", "type": "1000base-t"},
            )
        )
    cable = create(
        client,
        task,
        "dcim/cables/",
        {
            "a_terminations": [{"object_type": "dcim.interface", "object_id": interfaces[0]["id"]}],
            "b_terminations": [{"object_type": "dcim.interface", "object_id": interfaces[1]["id"]}],
            "status": "connected",
        },
    )
    assert cable["id"]
    trace = client.tool("query", path=f"dcim/interfaces/{interfaces[0]['id']}/trace/")
    assert trace["status"] == 200
    vrf = create(client, task, "ipam/vrfs/", {"name": suffix})
    prefix = create(
        client, task, "ipam/prefixes/", {"prefix": "192.0.2.0/24", "vrf": vrf["id"], "description": suffix}
    )
    allocation = client.tool(
        "execute_action",
        task_id=task,
        operation_key=key(),
        method="POST",
        path=f"ipam/prefixes/{prefix['id']}/available-ips/",
        data={"assigned_object_type": "dcim.interface", "assigned_object_id": interfaces[0]["id"]},
    )
    assert allocation["state"] == "applied", allocation
    vlan = create(client, task, "ipam/vlans/", {"name": suffix, "vid": 123})
    iface = client.tool("get_object_by_id", object_type="dcim/interfaces/", object_id=interfaces[0]["id"])
    result = client.tool(
        "update_object",
        task_id=task,
        operation_key=key(),
        object_type="dcim/interfaces/",
        object_id=interfaces[0]["id"],
        expected_etag=iface["etag"],
        data={"mode": "access", "untagged_vlan": vlan["id"]},
    )
    assert result["state"] == "applied", result
    ctype = create(client, task, "virtualization/cluster-types/", {"name": suffix, "slug": suffix})
    cluster = create(client, task, "virtualization/clusters/", {"name": suffix, "type": ctype["id"]})
    vm = create(
        client,
        task,
        "virtualization/virtual-machines/",
        {"name": suffix, "cluster": cluster["id"], "vcpus": 2, "memory": 1024},
    )
    create(client, task, "virtualization/interfaces/", {"name": "eth0", "virtual_machine": vm["id"]})
    found = client.tool(
        "get_objects",
        object_type="dcim/devices/",
        filters={"site_id": site["id"]},
        fields=["id", "name"],
        limit=1,
    )
    assert found["data"]["count"] == 2 and len(found["data"]["results"]) == 1
    assert client.tool("get_changelogs", filters={"changed_object_id": devices[0]["id"]})["data"]["count"] > 0
    assert client.tool("observability")["unresolved"] == []
    summary = client.tool("get_task", task_id=task)
    assert len(summary["operations"]) >= 15
    assert summary["full"] is False and summary["state_counts"]["applied"] >= 15
    assert len(json.dumps(summary)) < 25000
    assert all("native_changes" not in operation for operation in summary["operations"])
    detail = client.tool("get_task", task_id=task, full=True, limit=1)
    assert len(detail["operations"]) == 1 and detail["next_offset"] == 1
    assert "native_changes" in detail["operations"][0]


@pytest.mark.parametrize(
    "resource,data",
    [
        ("dcim/regions/", {}),
        ("dcim/site-groups/", {}),
        ("dcim/sites/", {}),
        ("dcim/manufacturers/", {}),
        ("dcim/device-roles/", {}),
        ("dcim/platforms/", {}),
        ("tenancy/tenant-groups/", {}),
        ("tenancy/tenants/", {}),
        ("ipam/roles/", {}),
        ("ipam/rirs/", {}),
        ("ipam/vlan-groups/", {}),
        ("ipam/route-targets/", {"name": "65000:123"}),
        ("ipam/vrfs/", {}),
        ("ipam/vlans/", {"vid": 234}),
        ("virtualization/cluster-types/", {}),
        ("virtualization/cluster-groups/", {}),
        ("circuits/providers/", {}),
        ("circuits/circuit-types/", {}),
        ("extras/tags/", {}),
    ],
)
def test_real_crud_lifecycle(service, resource, data):
    suffix = uuid.uuid4().hex[:12]
    task = service.begin_task("CRUD lifecycle")["task_id"]
    payload = {"name": suffix, "slug": suffix, **data}
    if resource == "ipam/route-targets/":
        payload["name"] = f"65000:{int(suffix[:6], 16)}"
    operation_key = key()
    op = service.create_object(task, operation_key, resource, payload)
    assert op["state"] == "applied", op
    assert service.create_object(task, operation_key, resource, payload)["id"] == op["id"]
    object_id = op["last_receipt"]["body"]["id"]
    current = service.get_object_by_id(resource, object_id)
    update = service.update_object(
        task, key(), resource, object_id, current["etag"], {"description": "Updated by live test"}
    )
    assert update["state"] == "applied", update
    with pytest.raises(ValueError, match="Stale"):
        service.delete_object(task, key(), resource, object_id, current["etag"])
    current = service.get_object_by_id(resource, object_id)
    deletion = service.delete_object(task, key(), resource, object_id, current["etag"])
    assert deletion["state"] == "applied", deletion
    assert service.api.request("GET", resource + str(object_id) + "/")["status"] == 404
    assert service.store.verify()["integrity"] == "verified"


def test_discovery_schema_graphql_and_native_errors(service):
    models = service.discover_models()["models"]
    assert len(models) > 100
    schema = service.get_schema("dcim/devices/")
    assert schema["paths"] and schema["schemas"]
    response = service.graphql("{ device_list { id name } }")
    assert response["status"] == 200 and "data" in response["body"], response
    task = service.begin_task("Validation")["task_id"]
    failure = service.create_object(task, key(), "dcim/devices/", {"name": "missing-required-fields"})
    assert failure["state"] == "failed"
    assert failure["last_receipt"]["status"] == 400
    report = service.diagnostic_report(failure["id"])
    assert "missing-required-fields" not in json.dumps(report)
    assert service.actor not in json.dumps(report)


def test_website_native_form_create_and_validation(service):
    page = service.web_read("/dcim/sites/add/")
    assert page["status"] == 200, page
    assert any(f.get("name") == "name" for form in page["body"]["forms"] for f in form["fields"])
    assert "csrfmiddlewaretoken" not in json.dumps(page["body"].get("text"))
    task = service.begin_task("Website native form")["task_id"]
    suffix = uuid.uuid4().hex[:12]
    op = service.web_submit(
        task, key(), "/dcim/sites/add/", {"name": suffix, "slug": suffix, "status": "active", "_create": ""}
    )
    assert op["state"] == "applied", op
    assert op["guarantee_limits"]["conditional_write"] is False
    assert op["guarantee_limits"]["automatic_undo"] is False
    assert service.get_operation(op["id"])["guarantee_limits"] == op["guarantee_limits"]
    assert service.get_objects("dcim/sites/", {"name": suffix})["data"]["count"] == 1
    invalid = service.web_submit(
        task, key(), "/dcim/sites/add/", {"name": "", "slug": "", "status": "active"}
    )
    assert invalid["last_receipt"]["status"] == 200
    assert invalid["state"] == "completed"  # HTTP 200 is not reported as a verified mutation.
    assert "required" in invalid["last_receipt"]["body"]["text"].lower()


def test_response_loss_reconcile_and_restart(service):
    task = service.begin_task("Lost create response")["task_id"]
    suffix = uuid.uuid4().hex[:12]
    service.fault = lambda point: (
        (_ for _ in ()).throw(OSError("lost response")) if point == "after_response" else None
    )
    op = service.create_object(task, key(), "dcim/sites/", {"name": suffix, "slug": suffix})
    assert op["state"] == "uncertain"
    service.fault = lambda _: None
    service.reconcile()
    assert service.get_operation(op["id"])["state"] == "applied"
    assert service.get_objects("dcim/sites/", {"name": suffix})["data"]["count"] == 1


def test_bulk_partial_and_resume(service):
    task = service.begin_task("Bulk operations")["task_id"]
    suffix = uuid.uuid4().hex[:12]
    steps = [
        {
            "action": "create_object",
            "arguments": {"object_type": "dcim/sites/", "data": {"name": suffix, "slug": suffix}},
        },
        {"action": "create_object", "arguments": {"object_type": "dcim/devices/", "data": {}}},
    ]
    operation_key = key()
    result = service.bulk(task, operation_key, steps)
    assert result["status"] == "partial_or_blocked"
    assert service.bulk(task, operation_key, steps)["results"][0]["id"] == result["results"][0]["id"]
    assert service.get_objects("dcim/sites/", {"name": suffix})["data"]["count"] == 1


def test_all_discovered_resources_have_real_read_and_options(service):
    coverage = []
    for entry in service.discover_models()["models"]:
        path = entry["resource"]
        read = service.api.request("GET", path + "?limit=1")
        options = service.api.request("OPTIONS", path)
        assert read["status"] in {200, 400, 403, 405}, (path, read)
        assert options["status"] in {200, 403}, (path, options)
        coverage.append({"resource": path, "GET": read["status"], "OPTIONS": options["status"]})
    (STATE / "resource-coverage.json").write_text(json.dumps(coverage, indent=2))


def test_workflow_code_with_discovery_and_idempotent_mutations(service):
    suffix = uuid.uuid4().hex[:12]
    task = service.begin_task("Workflow integration")["task_id"]
    code = f'''
results = []
for n in range(2):
    name = "{suffix}" + str(n)
    created = tool("create_object", object_type="dcim/sites/", data={{"name": name, "slug": name}})
    results.append(created["last_receipt"]["body"]["id"])
result = results
'''
    operation_key = key()
    result = service.run_workflow(task, operation_key, code)
    assert result["status"] == "completed", result
    assert len(result["result"]) == 2
    assert service.run_workflow(task, operation_key, code)["result"] == result["result"]
    with pytest.raises(ValueError, match="Idempotency"):
        service.run_workflow(task, operation_key, code + "\nresult = 0")


def test_custom_fields_tags_and_native_bulk(service):
    task = service.begin_task("Custom fields and bulk")["task_id"]
    suffix = "cf" + uuid.uuid4().hex[:12]
    cf = service.create_object(
        task, key(), "extras/custom-fields/", {"name": suffix, "type": "text", "object_types": ["dcim.site"]}
    )
    assert cf["state"] == "applied", cf
    tag = service.create_object(task, key(), "extras/tags/", {"name": suffix, "slug": suffix})[
        "last_receipt"
    ]["body"]
    result = service.execute_action(
        task,
        key(),
        "POST",
        "dcim/sites/",
        [
            {
                "name": suffix + str(n),
                "slug": suffix + str(n),
                "custom_fields": {suffix: "inventoried"},
                "tags": [{"id": tag["id"]}],
            }
            for n in range(2)
        ],
    )
    assert result["state"] == "applied", result
    assert len(result["native_changes"]) == 2
    assert len(result["last_receipt"]["body"]) == 2


def test_rendering_and_allocation_actions(service):
    task = service.begin_task("Allocation and rendering")["task_id"]
    suffix = uuid.uuid4().hex[:12]
    template = service.create_object(
        task, key(), "extras/config-templates/", {"name": suffix, "template_code": "hostname {{ hostname }}"}
    )
    assert template["state"] == "applied", template
    template_id = template["last_receipt"]["body"]["id"]
    render = service.execute_action(
        task,
        key(),
        "POST",
        f"extras/config-templates/{template_id}/render/",
        {"hostname": "lab-router"},
    )
    assert render["last_receipt"]["status"] == 200, render
    assert "lab-router" in json.dumps(render["last_receipt"])
    group = service.create_object(task, key(), "ipam/vlan-groups/", {"name": suffix, "slug": suffix})[
        "last_receipt"
    ]["body"]
    available = service.query(f"ipam/vlan-groups/{group['id']}/available-vlans/")
    assert available["status"] == 200
    allocated = service.execute_action(
        task, key(), "POST", f"ipam/vlan-groups/{group['id']}/available-vlans/", {"name": suffix}
    )
    assert allocated["state"] == "applied", allocated


def test_multipart_script_upload_run_and_job_completion(service):
    import base64
    import time

    task = service.begin_task("Script upload and execution")["task_id"]
    suffix = "audit_" + uuid.uuid4().hex[:12]
    source = 'from extras.scripts import Script\nclass AuditScript(Script):\n    class Meta:\n        name = "Audit script"\n    def run(self, data, commit):\n        self.log_success("Live MCP test completed")\n        return "ok"\n'
    uploaded = service.execute_action(
        task,
        key(),
        "POST",
        "extras/scripts/upload/",
        {},
        files=[
            {
                "field": "file",
                "filename": suffix + ".py",
                "base64": base64.b64encode(source.encode()).decode(),
            }
        ],
    )
    assert uploaded["last_receipt"]["status"] == 201, uploaded
    op = service.execute_action(
        task, key(), "POST", f"extras/scripts/{suffix}.AuditScript/", {"data": {}, "commit": True}
    )
    assert op["state"] == "accepted", op
    for _ in range(30):
        service.reconcile()
        op = service.get_operation(op["id"])
        if op["state"] != "accepted":
            break
        time.sleep(1)
    assert op["state"] == "job_completed", op
    assert op["job_result"]["status"]["value"] == "completed"


def test_native_permission_denial_and_read_only(service):
    task = service.begin_task("Permission denial")["task_id"]
    denied = service.create_object(task, key(), "users/users/", {"username": "should-not-create"})
    assert denied["state"] == "failed" and denied["last_receipt"]["status"] == 403
    service.read_only = True
    assert service.get_objects("dcim/sites/")["data"]["count"] > 0
    with pytest.raises(ValueError, match="read_only"):
        service.create_object(task, key(), "dcim/sites/", {"name": "denied", "slug": "denied"})
    with pytest.raises(ValueError, match="read_only"):
        service.web_submit(task, key(), "/dcim/sites/add/", {})


def test_native_cascade_evidence(service):
    task = service.begin_task("Cascade evidence")["task_id"]
    suffix = uuid.uuid4().hex[:12]
    site = service.create_object(task, key(), "dcim/sites/", {"name": suffix, "slug": suffix})[
        "last_receipt"
    ]["body"]
    location = service.create_object(
        task, key(), "dcim/locations/", {"name": suffix, "slug": suffix, "site": site["id"]}
    )
    assert location["state"] == "applied"
    current = service.get_object_by_id("dcim/sites/", site["id"])
    result = service.delete_object(task, key(), "dcim/sites/", site["id"], current["etag"])
    assert result["state"] == "applied", result
    assert {x["changed_object_type"] for x in result["native_changes"]} >= {"dcim.site", "dcim.location"}
    assert len(service.recovery_bundle(result["id"])["operation"]["native_changes"]) >= 2


def test_general_update_undo_preserves_other_fields_and_detects_aba(service):
    task = service.begin_task("General compensation")["task_id"]
    suffix = uuid.uuid4().hex[:12]
    created = service.create_object(task, key(), "dcim/sites/", {"name": suffix, "slug": suffix})
    object_id = created["last_receipt"]["body"]["id"]
    current = service.get_object_by_id("dcim/sites/", object_id)
    edit = service.update_object(task, key(), "dcim/sites/", object_id, current["etag"], {"description": "B"})
    service.api.request("PATCH", f"dcim/sites/{object_id}/", {"comments": "Preserve this"})
    assert service.preview_undo(edit["id"])["status"] == "ready"
    assert service.undo_operation(edit["id"], key())["status"] == "applied"
    now = service.get_object_by_id("dcim/sites/", object_id)
    assert now["data"]["description"] == "" and now["data"]["comments"] == "Preserve this"
    edit = service.update_object(task, key(), "dcim/sites/", object_id, now["etag"], {"description": "B"})
    service.api.request("PATCH", f"dcim/sites/{object_id}/", {"description": "C"})
    service.api.request("PATCH", f"dcim/sites/{object_id}/", {"description": "B"})
    assert service.preview_undo(edit["id"])["status"] == "conflicted"
    assert service.undo_operation(edit["id"], key())["status"] == "conflicted"


def test_relationship_and_json_recovery(service):
    task = service.begin_task("Relationship compensation")["task_id"]
    suffix = uuid.uuid4().hex[:12]
    regions = [
        service.create_object(
            task, key(), "dcim/regions/", {"name": suffix + str(n), "slug": suffix + str(n)}
        )["last_receipt"]["body"]
        for n in range(2)
    ]
    obj = service.create_object(
        task, key(), "dcim/sites/", {"name": suffix, "slug": suffix, "region": regions[0]["id"]}
    )["last_receipt"]["body"]
    current = service.get_object_by_id("dcim/sites/", obj["id"])
    op = service.update_object(
        task, key(), "dcim/sites/", obj["id"], current["etag"], {"region": regions[1]["id"]}
    )
    assert service.preview_undo(op["id"])["status"] == "ready"
    assert service.undo_operation(op["id"], key())["status"] == "applied"
    assert service.get_object_by_id("dcim/sites/", obj["id"])["data"]["region"]["id"] == regions[0]["id"]


def test_loss_before_dispatch_after_dispatch_and_integrity(service):
    task = service.begin_task("Crash boundaries")["task_id"]
    suffix = uuid.uuid4().hex[:12]
    operation_key = key()

    def kill(point):
        if point == "after_prepare":
            raise SystemExit(9)

    service.fault = kill
    with pytest.raises(SystemExit):
        service.create_object(task, operation_key, "dcim/sites/", {"name": suffix, "slug": suffix})
    service.fault = lambda _: None
    assert service.find_operation(operation_key)["operation"]["state"] == "prepared"
    service.reconcile()
    assert service.find_operation(operation_key)["operation"]["state"] == "failed"
    assert service.get_objects("dcim/sites/", {"name": suffix})["data"]["count"] == 0
    op = service.create_object(task, key(), "dcim/sites/", {"name": suffix, "slug": suffix})
    service.store.db.execute("UPDATE resource_operations SET state='failed' WHERE id=?", (op["id"],))
    with pytest.raises(RuntimeError, match="integrity"):
        service.store.verify()


def test_general_repeated_field_task_undo(service):
    suffix = uuid.uuid4().hex[:12]
    setup = service.begin_task("Setup compensation fixture")["task_id"]
    obj = service.create_object(setup, key(), "dcim/sites/", {"name": suffix, "slug": suffix})[
        "last_receipt"
    ]["body"]
    task = service.begin_task("Repeated field edits")["task_id"]
    for description in ["B", "C"]:
        current = service.get_object_by_id("dcim/sites/", obj["id"])
        assert (
            service.update_object(
                task, key(), "dcim/sites/", obj["id"], current["etag"], {"description": description}
            )["state"]
            == "applied"
        )
    result = service.undo_task(task)
    assert result["status"] == "undone", result
    assert service.undo_task(task)["status"] == "undone"
    assert service.get_object_by_id("dcim/sites/", obj["id"])["data"]["description"] == ""


def test_available_prefixes_and_asns(service):
    task = service.begin_task("Remaining IPAM allocation classes")["task_id"]
    suffix = uuid.uuid4().hex[:12]
    vrf = service.create_object(task, key(), "ipam/vrfs/", {"name": suffix})["last_receipt"]["body"]
    parent = service.create_object(
        task, key(), "ipam/prefixes/", {"prefix": "198.51.100.0/24", "vrf": vrf["id"]}
    )["last_receipt"]["body"]
    available = service.query(f"ipam/prefixes/{parent['id']}/available-prefixes/")
    assert available["status"] == 200
    allocated = service.execute_action(
        task, key(), "POST", f"ipam/prefixes/{parent['id']}/available-prefixes/", {"prefix_length": 28}
    )
    assert allocated["state"] == "applied", allocated
    rir = service.create_object(task, key(), "ipam/rirs/", {"name": suffix, "slug": suffix})["last_receipt"][
        "body"
    ]
    start = 4200000000 + int(suffix[:6], 16)
    asn_range = service.create_object(
        task,
        key(),
        "ipam/asn-ranges/",
        {"name": suffix, "slug": suffix, "rir": rir["id"], "start": start, "end": start + 5},
    )
    assert asn_range["state"] == "applied", asn_range
    range_id = asn_range["last_receipt"]["body"]["id"]
    assert service.query(f"ipam/asn-ranges/{range_id}/available-asns/")["status"] == 200
    allocated = service.execute_action(task, key(), "POST", f"ipam/asn-ranges/{range_id}/available-asns/", {})
    assert allocated["state"] == "applied", allocated


def test_website_edit_delete_and_rack_elevation(service):
    task = service.begin_task("Website edit/delete and rack elevation")["task_id"]
    suffix = uuid.uuid4().hex[:12]
    site = service.create_object(task, key(), "dcim/sites/", {"name": suffix, "slug": suffix})[
        "last_receipt"
    ]["body"]
    rack = service.create_object(
        task, key(), "dcim/racks/", {"name": suffix, "site": site["id"], "u_height": 12}
    )["last_receipt"]["body"]
    elevation = service.query(f"dcim/racks/{rack['id']}/elevation/", {"face": "front"})
    assert elevation["status"] == 200
    assert service.web_read(f"/dcim/sites/{site['id']}/edit/")["body"]["forms"]
    update = service.web_submit(
        task,
        key(),
        f"/dcim/sites/{site['id']}/edit/",
        {"name": suffix, "slug": suffix, "status": "active", "description": "Website edit", "_update": ""},
    )
    assert update["state"] == "applied", update
    assert service.get_object_by_id("dcim/sites/", site["id"])["data"]["description"] == "Website edit"
    assert service.web_read(f"/dcim/racks/{rack['id']}/delete/")["status"] == 200
    deletion = service.web_submit(
        task, key(), f"/dcim/racks/{rack['id']}/delete/", {"confirm": "True", "_confirm": ""}
    )
    assert deletion["state"] == "applied", deletion
    assert service.api.request("GET", f"dcim/racks/{rack['id']}/")["status"] == 404


@pytest.mark.parametrize("method", ["POST", "PATCH", "DELETE"])
def test_general_lost_response_for_each_crud_class(service, method):
    task = service.begin_task("Response loss " + method)["task_id"]
    suffix = uuid.uuid4().hex[:12]
    if method != "POST":
        obj = service.create_object(task, key(), "dcim/sites/", {"name": suffix, "slug": suffix})[
            "last_receipt"
        ]["body"]
        current = service.get_object_by_id("dcim/sites/", obj["id"])
    service.fault = lambda point: (
        (_ for _ in ()).throw(OSError("response lost")) if point == "after_response" else None
    )
    if method == "POST":
        op = service.create_object(task, key(), "dcim/sites/", {"name": suffix, "slug": suffix})
    elif method == "PATCH":
        op = service.update_object(
            task, key(), "dcim/sites/", obj["id"], current["etag"], {"description": "updated"}
        )
    else:
        op = service.delete_object(task, key(), "dcim/sites/", obj["id"], current["etag"])
    assert op["state"] == "uncertain"
    service.fault = lambda _: None
    service.reconcile()
    # DELETE has no body marker or retained HTTP request-ID after response loss.
    expected = "uncertain" if method == "DELETE" else "applied"
    assert service.get_operation(op["id"])["state"] == expected
    if method == "DELETE":
        with pytest.raises(RuntimeError, match="unresolved"):
            service.create_object(task, key(), "dcim/sites/", {"name": "blocked", "slug": "blocked"})


@pytest.mark.parametrize("method", ["PATCH", "DELETE"])
def test_native_last_moment_conditional_mutation(service, method):
    task = service.begin_task("Race " + method)["task_id"]
    suffix = uuid.uuid4().hex[:12]
    obj = service.create_object(task, key(), "dcim/sites/", {"name": suffix, "slug": suffix})["last_receipt"][
        "body"
    ]
    current = service.get_object_by_id("dcim/sites/", obj["id"])

    def race(point):
        if point == "after_dispatch_record":
            service.api.request("PATCH", f"dcim/sites/{obj['id']}/", {"description": "other writer"})

    service.fault = race
    if method == "PATCH":
        result = service.update_object(
            task, key(), "dcim/sites/", obj["id"], current["etag"], {"description": "should not overwrite"}
        )
    else:
        result = service.delete_object(task, key(), "dcim/sites/", obj["id"], current["etag"])
    assert result["state"] == "failed" and result["last_receipt"]["status"] == 412, result
    assert service.get_object_by_id("dcim/sites/", obj["id"])["data"]["description"] == "other writer"


def test_workflow_branch_replay_after_real_create(service):
    suffix = uuid.uuid4().hex[:12]
    task = service.begin_task("Durable workflow decisions")["task_id"]
    code = f'''
sites = tool("get_objects", object_type="dcim/sites/", filters={{"slug": "{suffix}"}})
if sites["data"]["count"] == 0:
    site = tool("create_object", object_type="dcim/sites/", data={{"name": "{suffix}", "slug": "{suffix}"}})
    result = site["id"]
else:
    result = "wrong replay branch"
'''
    operation_key = key()
    first = service.run_workflow(task, operation_key, code)
    assert first["status"] == "completed", first
    assert service.run_workflow(task, operation_key, code)["result"] == first["result"]
    assert service.get_objects("dcim/sites/", {"slug": suffix})["data"]["count"] == 1


@pytest.mark.parametrize("resource", ["dcim/sites/", "dcim/devices/", "dcim/interfaces/", "dcim/cables/"])
def test_agent_schema_response_fits_client_context(service, resource):
    compact = service.get_schema(resource)
    full = service.get_schema(resource, full=True)
    assert len(json.dumps(compact).encode()) < 30000
    assert len(json.dumps(compact)) < len(json.dumps(full))
    assert compact["schemas"]
    assert (
        compact["paths"]["/api/" + resource]["post"]["request"]
        == (full["paths"]["/api/" + resource]["post"]["requestBody"]["content"]["application/json"]["schema"])
    )
    focused = service.get_schema(resource, method="PATCH")
    assert len(json.dumps(focused).encode()) < 30000
    assert focused["filters"] == {}
    request = focused["paths"]["/api/" + resource]["patch"]["request"]
    assert request["items"]["$ref"].rsplit("/", 1)[1] in focused["schemas"]
    assert all(set(methods) == {"patch"} for methods in focused["paths"].values())


def test_agent_can_inspect_allocation_action_without_full_schema(service):
    compact = service.get_schema("ipam/prefixes/", action="available-ips")
    assert len(json.dumps(compact)) < 15000
    assert compact["schemas"]
    assert all(path.endswith("/available-ips/") for path in compact["paths"])
    fields = {key for schema in compact["schemas"].values() for key in schema.get("properties", {})}
    # NetBox documents allocation inputs separately from the full IP write schema.
    assert "prefix_length" in fields
    ip_schema = service.get_schema("ipam/ip-addresses/")
    ip_fields = {key for schema in ip_schema["schemas"].values() for key in schema.get("properties", {})}
    assert {"assigned_object_type", "assigned_object_id"} <= ip_fields
    with pytest.raises(ValueError, match="not found"):
        service.get_schema("ipam/prefixes/", action="not-an-action")


@pytest.mark.parametrize(
    "resource", ["dcim/devices/", "ipam/vrfs/", "ipam/prefixes/", "virtualization/clusters/"]
)
def test_unknown_slug_filter_cannot_select_unrelated_live_objects(service, resource):
    with pytest.raises(ValueError, match="Unknown filters.*slug"):
        service.get_objects(resource, {"slug": "agent-must-never-match-this"})
    with pytest.raises(ValueError, match="Unknown filters"):
        service.query(resource, {"slug": "agent-must-never-match-this"})


def test_companion_uses_native_filters_and_target_permissions(service):
    path = "plugins/agent-support/filter-schema/"
    assert path in {entry["resource"] for entry in service.discover_models(refresh=True)["models"]}
    metadata = service.api.get(path + "?resource=dcim/devices/")["body"]
    assert metadata["schema_version"] == 1
    assert "name" in metadata["filters"] and "slug" not in metadata["filters"]
    restricted = build_service(json.loads((STATE / "config.json").read_text()))
    try:
        assert restricted.api.request("GET", path + "?resource=dcim/devices/")["status"] == 200
        for resource in ["dcim/sites/", "users/users/"]:
            assert restricted.api.request("GET", resource)["status"] == 403
            assert restricted.api.request("GET", path + "?resource=" + resource)["status"] == 403
    finally:
        restricted.store.close()
    for resource in ["../users/users/", "https://example.com/api/", "api/dcim/devices/"]:
        from urllib.parse import urlencode

        assert (
            service.api._send(
                "GET", service.api.url + "/api/" + path + "?" + urlencode({"resource": resource})
            )["status"]
            == 400
        )
    assert service.api.request("POST", path, {"resource": "dcim/devices/"})["status"] == 405
    assert service.api.request("GET", path + "?resource=missing/resources/")["status"] == 404


def test_custom_field_filters_are_discovered_validated_and_refreshed(service):
    suffix = "cf" + uuid.uuid4().hex[:12]
    filter_name = "cf_" + suffix
    assert filter_name not in service.get_schema("dcim/sites/")["filters"]
    task = service.begin_task("Native dynamic filter metadata")["task_id"]
    cf = service.create_object(
        task,
        key(),
        "extras/custom-fields/",
        {"name": suffix, "type": "text", "object_types": ["dcim.site"], "filter_logic": "exact"},
    )["last_receipt"]["body"]
    for color in ["red", "blue"]:
        assert (
            service.create_object(
                task,
                key(),
                "dcim/sites/",
                {"name": suffix + color, "slug": suffix + color, "custom_fields": {suffix: color}},
            )["state"]
            == "applied"
        )
    assert filter_name in service.get_schema("dcim/sites/")["filters"]
    rows = service.get_objects("dcim/sites/", {filter_name: "red"})["data"]["results"]
    assert [row["name"] for row in rows] == [suffix + "red"]
    with pytest.raises(ValueError, match="Unknown filters"):
        service.get_objects("dcim/devices/", {filter_name: "red"})
    current = service.get_object_by_id("extras/custom-fields/", cf["id"])
    assert (
        service.update_object(
            task, key(), "extras/custom-fields/", cf["id"], current["etag"], {"filter_logic": "disabled"}
        )["state"]
        == "applied"
    )
    assert filter_name not in service.get_schema("dcim/sites/")["filters"]
    with pytest.raises(ValueError, match="Unknown filters"):
        service.get_objects("dcim/sites/", {filter_name: "red"})
