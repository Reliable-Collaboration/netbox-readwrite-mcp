"""Native Community import semantics through the companion and MCP journal."""

import json
import os
import uuid

import pytest

from netbox_readwrite_mcp.server import build_service
from scripts.lab import STATE, URL
from tests.integration.test_administration import queue_admin  # noqa: F401
from tests.integration.test_configuration import shell
from tests.integration.test_personal import people  # noqa: F401

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("NETBOX_RW_LIVE") != "1", reason="Disposable lab opt-in required"),
]
PATH = "plugins/agent-support/imports/"


@pytest.fixture
def importer(tmp_path):
    cfg = json.loads((STATE / "broad-config.json").read_text())
    assert cfg["netbox_url"] == URL
    cfg["journal"] = str(tmp_path / "import.sqlite")
    service = build_service(cfg)
    prefix = "import-" + uuid.uuid4().hex[:12]
    try:
        yield service, prefix
    finally:
        service.store.close()
        shell(f"""
from dcim.models import Site
Site.objects.filter(slug__startswith={prefix!r}).delete()
""")


@pytest.mark.parametrize("format", ["csv", "json", "yaml"])
def test_native_import_create_update_and_journal(importer, format):
    service, prefix = importer
    task = service.begin_task("Qualify native imports")["task_id"]
    schema = service.query(PATH + "dcim.site/")
    assert schema["status"] == 200, schema
    assert schema["body"]["fields"]["name"]["required"]
    if format == "csv":
        data = f"name,slug,status\n{prefix},{prefix},active\n"
    elif format == "yaml":
        data = f"- name: {prefix}\n  slug: {prefix}\n  status: active\n"
    else:
        data = json.dumps([{"name": prefix, "slug": prefix, "status": "active"}])
    body = {"format": format, "data": data}
    result = service.execute_action(task, "import-create", "POST", PATH + "dcim.site/", body)
    assert result["last_receipt"]["status"] == 200, result
    assert result["state"] == "applied" and len(result["native_changes"]) == 1, result
    pk = result["last_receipt"]["body"]["ids"][0]
    assert service.query(f"dcim/sites/{pk}/")["body"]["name"] == prefix
    assert (
        service.execute_action(task, "import-create", "POST", PATH + "dcim.site/", body)["id"] == result["id"]
    )
    update = service.execute_action(
        task,
        "import-update",
        "POST",
        PATH + "dcim.site/",
        {
            "format": "json",
            "data": json.dumps([{"id": pk, "description": "Imported update"}]),
        },
    )
    assert update["last_receipt"]["status"] == 200, update
    assert update["state"] == "applied"
    actual = service.query(f"dcim/sites/{pk}/")["body"]
    assert actual["description"] == "Imported update" and actual["name"] == prefix


def test_import_atomic_rollback_and_malformed_input(importer):
    service, prefix = importer
    before = service.query("dcim/sites/", {"slug": prefix})["body"]["count"]
    records = [
        [{"name": prefix, "slug": prefix}, {"name": prefix, "slug": prefix}],
        [{"name": prefix, "slug": prefix}, {"name": "", "slug": prefix + "-invalid"}],
        [{"name": prefix, "slug": prefix, "typo_field": True}],
        [{"id": True}],
        [{"id": "invalid"}],
        [{"id": -1}],
        ["not a record"],
        [],
    ]
    for rows in records:
        response = service.api.request(
            "POST", PATH + "dcim.site/", {"data": json.dumps(rows), "format": "json"}
        )
        assert response["status"] == 400, response
        assert service.query("dcim/sites/", {"slug": prefix})["body"]["count"] == before
    for data, format in [("[", "json"), ("- [", "yaml"), ("", "auto")]:
        assert (
            service.api.request("POST", PATH + "dcim.site/", {"data": data, "format": format})["status"]
            == 400
        )


def test_import_discovery_and_model_permission_denial(importer, people):  # noqa: F811
    service, _ = importer
    catalog = service.query(PATH)
    assert catalog["status"] == 200, catalog
    models = {row["model"] for row in catalog["body"]["results"]}
    assert {"dcim.device", "dcim.site", "ipam.ipaddress", "virtualization.virtualmachine"} <= models
    actor, readonly = people[0]
    assert {row["model"] for row in actor.query(PATH)["body"]["results"]} == {"users.token"}
    for method in ["GET", "POST"]:
        assert (
            actor.api.request(method, PATH + "dcim.site/", {"data": "[]"} if method == "POST" else None)[
                "status"
            ]
            == 403
        )
    assert service.api.request("GET", PATH + "commercial.something/")["status"] == 404


def test_import_related_lookup_uses_native_names(importer):
    service, prefix = importer
    body = {
        "format": "json",
        "data": json.dumps({"name": prefix, "slug": prefix, "region": "missing-" + prefix}),
    }
    response = service.api.request("POST", PATH + "dcim.site/", body)
    assert response["status"] == 400 and "region" in str(response["body"]), response


def test_every_stock_import_schema_serializes(queue_admin):  # noqa: F811
    service = queue_admin
    catalog = service.query(PATH)["body"]
    assert catalog["count"] >= 100
    for row in catalog["results"]:
        response = service.query(PATH + row["model"] + "/")
        assert response["status"] == 200 and response["body"]["fields"], row["model"]
        assert len(json.dumps(response["body"])) < 30000, row["model"]


def test_import_add_change_constraints_and_readonly_token(importer, people):  # noqa: F811
    from netbox_readwrite_mcp.api import NetBox

    service, prefix = importer
    actor, readonly = people[0]
    shell(f"""
from users.models import ObjectPermission
from core.models import ObjectType
p = ObjectPermission.objects.get(name={actor.actor!r})
p.actions = ['view', 'add']
p.constraints = {{'slug__startswith': {prefix!r}}}
p.save()
p.object_types.set([ObjectType.objects.get(app_label='dcim', model='site')])
""")
    payload = {"format": "json", "data": json.dumps({"name": prefix, "slug": prefix, "status": "active"})}
    assert NetBox(URL, readonly).request("POST", PATH + "dcim.site/", payload)["status"] == 403
    created = actor.api.request("POST", PATH + "dcim.site/", payload)
    assert created["status"] == 200, created
    pk = created["body"]["ids"][0]
    update = {"format": "json", "data": json.dumps({"id": pk, "description": "not allowed"})}
    denied = actor.api.request("POST", PATH + "dcim.site/", update)
    assert denied["status"] == 400 and "change" in str(denied["body"]), denied
    assert service.query(f"dcim/sites/{pk}/")["body"]["description"] == ""
    shell(f"""
from users.models import ObjectPermission
p = ObjectPermission.objects.get(name={actor.actor!r})
p.actions = ['view', 'add', 'change']
p.save()
""")
    assert actor.api.request("POST", PATH + "dcim.site/", update)["status"] == 200
    escape = {"format": "json", "data": json.dumps({"id": pk, "slug": "outside-" + prefix})}
    assert actor.api.request("POST", PATH + "dcim.site/", escape)["status"] == 403
    assert service.query(f"dcim/sites/{pk}/")["body"]["slug"] == prefix


def test_import_response_loss_reconciles_native_history_without_replay(importer, monkeypatch):
    service, prefix = importer
    task = service.begin_task("Lost native import receipt")["task_id"]
    original = service.api.request
    calls = []

    def lose(method, path, *args, **kwargs):
        result = original(method, path, *args, **kwargs)
        if method == "POST" and path == PATH + "dcim.site/":
            calls.append(path)
            assert result["status"] == 200
            raise OSError("Lost receipt after commit")
        return result

    monkeypatch.setattr(service.api, "request", lose)
    body = {"format": "json", "data": json.dumps({"name": prefix, "slug": prefix, "status": "active"})}
    operation = service.execute_action(task, "lost-import", "POST", PATH + "dcim.site/", body)
    assert operation["state"] == "uncertain"
    assert service.query("dcim/sites/", {"slug": prefix})["body"]["count"] == 1
    assert (
        service.execute_action(task, "lost-import", "POST", PATH + "dcim.site/", body)["id"]
        == operation["id"]
    )
    assert len(calls) == 1


def test_cold_bulk_schemas_and_concrete_mcp_discovery(importer):
    service, _ = importer
    response = service.api.get("schema/?format=json&bulk-qualification=" + uuid.uuid4().hex)
    service.catalog.schema = response["body"]
    for family in ["imports", "bulk-rename", "bulk-edit", "pattern-create"]:
        model = "ipam.vlan" if family == "pattern-create" else "dcim.site"
        path = f"plugins/agent-support/{family}/{model}/"
        schema = service.get_schema(path, method="POST")
        assert schema["schemas"] and schema["paths"], path
        assert len(json.dumps(schema)) < 30000
    choices = service.query(PATH + "dcim.site/", {"field": "time_zone"})["body"]["fields"]
    assert set(choices) == {"time_zone"} and len(choices["time_zone"]["choices"]) > 50
