"""Native CSV, YAML and saved-template export contracts without browser HTML."""

import base64
import csv
import io
import os

import pytest

from tests.integration.test_administration import queue_admin  # noqa: F401

from tests.integration.test_rename import sites  # noqa: F401
from tests.integration.test_imports import importer  # noqa: F401
from tests.integration.test_patterns import parents  # noqa: F401
from tests.integration.test_personal import people  # noqa: F401
from tests.integration.test_configuration import shell

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("NETBOX_RW_LIVE") != "1", reason="Disposable lab opt-in required"),
]
ROOT = "plugins/agent-support/exports/"


def test_native_csv_selected_columns_chunks_and_content_guard(sites):  # noqa: F811
    service, prefix, ids = sites
    path = ROOT + "dcim.site/"
    schema = service.query(path)["body"]
    assert "name" in {row["name"] for row in schema["columns"]}
    body = {"ids": ids, "format": "csv", "columns": ["name", "slug"], "length": 20}
    first = service.api.request("POST", path, body)
    assert first["status"] == 200, first
    result = base64.b64decode(first["body"]["base64"])
    offset = first["body"]["next_offset"]
    while offset is not None:
        row = service.api.request(
            "POST", path, {**body, "offset": offset, "expected_sha256": first["body"]["sha256"]}
        )
        assert row["status"] == 200, row
        result += base64.b64decode(row["body"]["base64"])
        offset = row["body"]["next_offset"]
    rows = list(csv.reader(io.StringIO(result.decode())))
    assert len(rows) == 3 and all(len(row) == 2 for row in rows)
    assert {tuple(row) for row in rows[1:]} == {
        (prefix + "-old-1", prefix + "-1"),
        (prefix + "-old-2", prefix + "-2"),
    }
    service.api.request("PATCH", f"dcim/sites/{ids[0]}/", {"name": prefix + "-changed"})
    assert (
        service.api.request("POST", path, {**body, "expected_sha256": first["body"]["sha256"]})["status"]
        == 412
    )
    assert service.api.request("POST", path, {**body, "columns": ["password"]})["status"] == 400
    assert service.api.request("POST", path, {**body, "format": "yaml"})["status"] == 400


def test_export_get_supports_readonly_mcp_and_native_permission_denial(sites, people):  # noqa: F811
    service, _, ids = sites
    service.catalog.schema = service.api.get("schema/?format=json&export-cold=qualification")["body"]
    service.read_only = True
    result = service.query(ROOT + "dcim.site/", {"export": "csv", "ids": ids, "columns": ["name"]})
    assert result["status"] == 200 and result["body"]["size"] > 0, result
    assert people[0][0].api.request("POST", ROOT + "dcim.site/", {"ids": ids})["status"] == 403


def test_native_yaml_device_type_export(parents):  # noqa: F811
    service, prefix, ids = parents
    result = service.api.request(
        "POST", ROOT + "dcim.devicetype/", {"format": "yaml", "ids": [ids["device_type"]]}
    )
    assert result["status"] == 200, result
    rendered = base64.b64decode(result["body"]["base64"]).decode()
    assert "manufacturer: " + prefix in rendered and "model: " + prefix in rendered
    assert "slug: " + prefix in rendered


def test_native_saved_export_template_and_invalid_template(sites):  # noqa: F811
    service, prefix, ids = sites
    created = service.api.request(
        "POST",
        "extras/export-templates/",
        {
            "name": prefix,
            "object_types": ["dcim.site"],
            "template_code": "{% for object in queryset %}{{ object.slug }}\n{% endfor %}",
        },
    )
    assert created["status"] == 201, created
    pk = created["body"]["id"]
    try:
        body = {"format": "template", "template_id": pk, "ids": ids}
        result = service.api.request("POST", ROOT + "dcim.site/", body)
        assert result["status"] == 200, result
        assert set(result["body"]["text"].splitlines()) == {prefix + "-1", prefix + "-2"}
        assert service.api.request("POST", ROOT + "ipam.vlan/", {**body, "ids": []})["status"] == 404
        assert (
            service.api.request("POST", ROOT + "dcim.site/", {"format": "template", "ids": ids})["status"]
            == 400
        )
    finally:
        shell(f"""
from extras.models import ExportTemplate
ExportTemplate.objects.filter(pk={pk}).delete()
""")


def test_every_stock_export_schema_and_empty_export(queue_admin):  # noqa: F811
    catalog = queue_admin.api.get(ROOT)["body"]
    models = {row["model"] for row in catalog["results"]}
    assert {"core.objectchange", "extras.bookmark", "extras.notification", "extras.subscription"} <= models
    assert len(models) > 100
    for model in sorted(models):
        path = ROOT + model + "/"
        schema = queue_admin.api.request("GET", path)
        assert schema["status"] == 200, (model, schema)
        result = queue_admin.api.request("POST", path, {"ids": [], "format": "csv"})
        assert result["status"] == 200, (model, result)
        assert result["body"]["sha256"]
