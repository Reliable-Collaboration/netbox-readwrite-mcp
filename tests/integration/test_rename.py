"""Transactional native bulk rename with preview, guards and MCP evidence."""

import json
import os

import pytest

from tests.integration.test_imports import importer  # noqa: F401

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("NETBOX_RW_LIVE") != "1", reason="Disposable lab opt-in required"),
]
PATH = "plugins/agent-support/bulk-rename/dcim.site/"


@pytest.fixture
def sites(importer):  # noqa: F811
    service, prefix = importer
    result = service.api.request(
        "POST",
        "plugins/agent-support/imports/dcim.site/",
        {
            "format": "json",
            "data": json.dumps(
                [
                    {"name": prefix + "-old-1", "slug": prefix + "-1", "status": "active"},
                    {"name": prefix + "-old-2", "slug": prefix + "-2", "status": "active"},
                ]
            ),
        },
    )
    assert result["status"] == 200, result
    return service, prefix, result["body"]["ids"]


@pytest.mark.parametrize("regex", [False, True])
def test_bulk_rename_preview_apply_stale_and_receipts(sites, regex):
    service, prefix, ids = sites
    task = service.begin_task("Bulk rename qualification")["task_id"]
    assert "name" in service.query(PATH)["body"]["fields"]
    body = {
        "ids": ids,
        "find": r"old-(\d)" if regex else "old-",
        "replace": r"new-\1" if regex else "new-",
        "use_regex": regex,
        "fields": ["name"],
    }
    preview = service.execute_action(task, "rename-preview", "POST", PATH, body)
    assert preview["state"] == "completed" and not preview["native_changes"], preview
    expected = preview["last_receipt"]["body"]["expected"]
    for pk in ids:
        assert service.query(f"dcim/sites/{pk}/")["body"]["name"] == expected[str(pk)]["name"]
    body.update(apply=True, expected=expected)
    renamed = service.execute_action(task, "rename-apply", "POST", PATH, body)
    assert renamed["state"] == "applied" and len(renamed["native_changes"]) == 2, renamed
    for index, pk in enumerate(ids, 1):
        assert service.query(f"dcim/sites/{pk}/")["body"]["name"] == f"{prefix}-new-{index}"
    stale = service.execute_action(task, "rename-stale", "POST", PATH, body)
    assert stale["state"] == "failed" and stale["last_receipt"]["status"] == 409
    assert service.execute_action(task, "rename-apply", "POST", PATH, body)["id"] == renamed["id"]


def test_rename_invalid_regex_fields_duplicates_and_atomic_uniqueness(sites):
    service, prefix, ids = sites
    before = [service.query(f"dcim/sites/{pk}/")["body"] for pk in ids]
    base = {"ids": ids, "find": "old-", "replace": "new-", "fields": ["name"]}
    for change in [
        {"find": "[", "use_regex": True},
        {"fields": ["description"]},
        {"ids": ids + ids},
        {"fields": ["name", "name"]},
    ]:
        result = service.api.request("POST", PATH, {**base, **change})
        assert result["status"] == 400, result
    assert service.api.request("POST", PATH, {**base, "apply": True})["status"] == 409
    collision = {**base, "find": r"old-\d", "replace": "collision", "use_regex": True}
    preview = service.api.request("POST", PATH, collision)
    assert preview["status"] == 200, preview
    collision.update(apply=True, expected=preview["body"]["expected"])
    result = service.api.request("POST", PATH, collision)
    assert result["status"] == 400, result
    assert [service.query(f"dcim/sites/{pk}/")["body"] for pk in ids] == before
