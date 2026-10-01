"""Native bulk field updates and clear semantics through structured API."""

import os

import pytest

from tests.integration.test_rename import sites  # noqa: F401
from tests.integration.test_imports import importer  # noqa: F401
from tests.integration.test_administration import queue_admin  # noqa: F401

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("NETBOX_RW_LIVE") != "1", reason="Disposable lab opt-in required"),
]
PATH = "plugins/agent-support/bulk-edit/dcim.site/"


def test_native_bulk_edit_preview_apply_clear_stale_and_history(sites):  # noqa: F811
    service, _, ids = sites
    task = service.begin_task("Bulk field qualification")["task_id"]
    schema = service.query(PATH)["body"]
    assert "description" in schema["fields"] and "description" in schema["nullable_fields"]
    body = {"ids": ids, "values": {"description": "Bulk description", "status": "planned"}}
    preview = service.execute_action(task, "bulk-edit-preview", "POST", PATH, body)
    assert preview["last_receipt"]["status"] == 200, preview
    assert preview["state"] == "completed" and not preview["native_changes"]
    body.update(apply=True, expected=preview["last_receipt"]["body"]["expected"])
    saved = service.execute_action(task, "bulk-edit-apply", "POST", PATH, body)
    assert saved["state"] == "applied" and len(saved["native_changes"]) == 2, saved
    for pk in ids:
        actual = service.query(f"dcim/sites/{pk}/")["body"]
        assert actual["description"] == "Bulk description" and actual["status"]["value"] == "planned"
    assert service.api.request("POST", PATH, body)["status"] == 409
    clearing = {"ids": ids, "nullify": ["description"]}
    preview = service.api.request("POST", PATH, clearing)
    assert preview["status"] == 200, preview
    clearing.update(apply=True, expected=preview["body"]["expected"])
    assert service.api.request("POST", PATH, clearing)["status"] == 200
    for pk in ids:
        actual = service.query(f"dcim/sites/{pk}/")["body"]
        assert actual["description"] == "" and actual["status"]["value"] == "planned"


def test_bulk_edit_rejects_unknown_invalid_reserved_and_nonnullable_fields(sites):  # noqa: F811
    service, _, ids = sites
    for changes in [
        {"values": {"typo": "x"}},
        {"values": {"pk": ids}},
        {"values": {"background_job": True}},
        {"values": {"status": "invalid"}},
        {"nullify": ["name"]},
        {"ids": ids + ids},
    ]:
        result = service.api.request("POST", PATH, {"ids": ids, **changes})
        assert result["status"] == 400, result


def test_every_stock_bulk_edit_schema_serializes(queue_admin):  # noqa: F811
    service = queue_admin
    catalog = service.query("plugins/agent-support/bulk-edit/")["body"]
    assert catalog["count"] >= 100
    for row in catalog["results"]:
        response = service.query("plugins/agent-support/bulk-edit/" + row["model"] + "/")
        assert response["body"]["fields"], row["model"]


def test_native_bulk_tag_deltas_preserve_unselected_tags(sites):  # noqa: F811
    from tests.integration.test_configuration import shell

    service, prefix, ids = sites
    tags = []
    try:
        for suffix in ("keep", "remove", "add"):
            result = service.api.request(
                "POST", "extras/tags/", {"name": prefix + suffix, "slug": prefix + suffix}
            )
            assert result["status"] == 201, result
            tags.append(result["body"]["id"])
        for pk in ids:
            assert service.api.request("PATCH", f"dcim/sites/{pk}/", {"tags": tags[:2]})["status"] == 200
        body = {"ids": ids, "values": {"add_tags": tags[2:], "remove_tags": tags[1:2]}}
        preview = service.api.request("POST", PATH, body)
        assert preview["status"] == 200, preview
        result = service.api.request(
            "POST", PATH, {**body, "apply": True, "expected": preview["body"]["expected"]}
        )
        assert result["status"] == 200, result
        for pk in ids:
            assert {t["id"] for t in service.api.get(f"dcim/sites/{pk}/")["body"]["tags"]} == {
                tags[0],
                tags[2],
            }
    finally:
        shell(f"""
from extras.models import Tag
Tag.objects.filter(pk__in={tags!r}).delete()
""")
