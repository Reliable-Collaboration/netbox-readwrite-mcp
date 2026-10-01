"""Self-service state under separate disposable, non-superuser identities."""

import json
import os
import secrets
import uuid

import pytest

from netbox_readwrite_mcp.server import build_service
from scripts.lab import STATE, URL
from tests.integration.test_configuration import shell

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("NETBOX_RW_LIVE") != "1", reason="Disposable lab opt-in required"),
]


@pytest.fixture
def people(tmp_path):
    suffix = uuid.uuid4().hex
    actors = []
    for i in range(2):
        name = f"personal-{suffix}-{i}"
        token = secrets.token_hex(20)
        readonly = secrets.token_hex(20)
        shell(f"""
from django.contrib.auth import get_user_model
from users.models import Token, ObjectPermission
from core.models import ObjectType
u = get_user_model().objects.create(username={name!r})
for value, writable in [({token!r}, True), ({readonly!r}, False)]:
    Token.objects.create(user=u, token=value, version=1, write_enabled=writable)
p = ObjectPermission.objects.create(name={name!r}, actions=['view'])
p.users.add(u)
p.object_types.add(ObjectType.objects.get(app_label='core', model='objectchange'))
""")
        cfg = json.loads((STATE / "broad-config.json").read_text())
        assert cfg["netbox_url"] == URL
        cfg.pop("web_password_file", None)
        path = tmp_path / f"token-{i}"
        path.write_text(token)
        path.chmod(0o600)
        cfg.update(actor=name, token_file=str(path), journal=str(tmp_path / f"journal-{i}.sqlite"))
        actors.append((build_service(cfg), readonly))
    try:
        yield actors
    finally:
        for svc, _ in actors:
            svc.store.close()
        shell(f"""
from django.contrib.auth import get_user_model
from users.models import ObjectPermission
get_user_model().objects.filter(username__startswith='personal-{suffix}-').delete()
ObjectPermission.objects.filter(name__startswith='personal-{suffix}-').delete()
""")


def test_native_preferences_merge_without_audit_marker_or_cross_user_changes(people):
    a, b = [entry[0] for entry in people]
    before_b = b.query("users/config/")["body"]
    task = a.begin_task("Own preferences")["task_id"]
    first = {"ui": {"theme": "dark", "density": "compact"}, "columns": ["name", "status"]}
    operation = a.execute_action(task, "preferences-first", "PATCH", "users/config/", first)
    assert operation["last_receipt"]["status"] == 200, operation
    assert a.query("users/config/")["body"] == first
    second = a.execute_action(
        task, "preferences-second", "PATCH", "users/config/", {"ui": {"theme": "light"}}
    )
    assert second["state"] == "completed" and second["native_changes"] == []
    assert a.query("users/config/")["body"] == {**first, "ui": {"theme": "light", "density": "compact"}}
    assert b.query("users/config/")["body"] == before_b
    assert (
        a.execute_action(task, "preferences-second", "PATCH", "users/config/", {"ui": {"theme": "light"}})[
            "id"
        ]
        == second["id"]
    )


DASHBOARD = "plugins/agent-support/self/dashboard/"


def note(content="Test note"):
    pk = str(uuid.uuid4())
    return {
        "layout": [{"id": pk, "w": 4, "h": 3, "x": 0, "y": 0}],
        "config": {
            pk: {
                "class": "extras.NoteWidget",
                "title": "Inventory notes",
                "color": "blue",
                "config": {"content": content},
            }
        },
    }


def test_dashboard_first_use_edit_reset_and_user_isolation(people):
    a, b = [entry[0] for entry in people]
    initial = a.query(DASHBOARD)
    assert initial["body"] == {"initialized": False, "layout": [], "config": {}}
    task = a.begin_task("Own dashboard")["task_id"]
    created = a.execute_action(
        task, "dashboard-initialize", "POST", DASHBOARD, {}, initial["headers"]["etag"]
    )
    assert created["last_receipt"]["status"] == 200, created
    assert created["last_receipt"]["body"]["initialized"]
    assert created["last_receipt"]["body"]["layout"]
    current = a.query(DASHBOARD)
    content = note()
    changed = a.execute_action(
        task, "dashboard-replace", "PUT", DASHBOARD, content, current["headers"]["etag"]
    )
    assert changed["last_receipt"]["status"] == 200, changed
    assert changed["state"] == "completed" and changed["native_changes"] == []
    assert a.query(DASHBOARD)["body"] == {"initialized": True, **content}
    assert b.query(DASHBOARD)["body"]["initialized"] is False
    # Assert the native Dashboard can instantiate and lay out what the API saved.
    shell(f"""
from django.contrib.auth import get_user_model
u = get_user_model().objects.get(username={a.actor!r})
widgets = u.dashboard.get_layout()
assert len(widgets) == 1
assert widgets[0].config['content'] == 'Test note'
""")
    stale = a.execute_action(
        task, "dashboard-stale", "PUT", DASHBOARD, note("stale"), current["headers"]["etag"]
    )
    assert stale["last_receipt"]["status"] == 412
    assert a.query(DASHBOARD)["body"] == {"initialized": True, **content}
    current = a.query(DASHBOARD)
    cleared = a.execute_action(task, "dashboard-reset", "DELETE", DASHBOARD, {}, current["headers"]["etag"])
    assert cleared["last_receipt"]["status"] == 204
    assert a.query(DASHBOARD)["body"] == initial["body"]


@pytest.mark.parametrize("method", ["PUT", "PATCH"])
def test_dashboard_rejects_invalid_fields_and_readonly_token(people, method):
    from netbox_readwrite_mcp.api import NetBox

    a, readonly = people[0]
    before = a.query(DASHBOARD)
    headers = {"If-Match": before["headers"]["etag"]}
    assert NetBox(URL, readonly).request(method, DASHBOARD, note(), headers)["status"] == 403
    assert a.api.request(method, DASHBOARD, note())["status"] == 428
    bad = note()
    bad["layout"][0]["id"] = str(uuid.uuid4())
    assert a.api.request(method, DASHBOARD, bad, headers)["status"] == 400
    for config in [{"content": ""}, {"content": "ok", "invented": 1}]:
        bad = note()
        next(iter(bad["config"].values()))["config"] = config
        assert a.api.request(method, DASHBOARD, bad, headers)["status"] == 400
    bad = note()
    next(iter(bad["config"].values()))["class"] = "commercial.NotAllowed"
    assert a.api.request(method, DASHBOARD, bad, headers)["status"] == 400
    bad = note()
    bad["user"] = 1
    assert a.api.request(method, DASHBOARD, bad, headers)["status"] == 400
    assert a.query(DASHBOARD)["body"] == before["body"]


@pytest.mark.parametrize("method", ["PUT", "PATCH"])
def test_dashboard_concurrent_first_writes_and_empty_layout(people, method):
    from concurrent.futures import ThreadPoolExecutor

    a, _ = people[0]
    before = a.query(DASHBOARD)
    headers = {"If-Match": before["headers"]["etag"]}
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(lambda text: a.api.request(method, DASHBOARD, note(text), headers), ["one", "two"])
        )
    assert sorted(r["status"] for r in responses) == [200, 412], responses
    current = a.query(DASHBOARD)
    empty = a.api.request(
        "PUT", DASHBOARD, {"layout": [], "config": {}}, {"If-Match": current["headers"]["etag"]}
    )
    assert empty["status"] == 200, empty
    assert empty["body"] == {"initialized": True, "layout": [], "config": {}}


def test_dashboard_cold_schema_and_widget_catalog(people):
    a, _ = people[0]
    schema = a.api.get("schema/?format=json&dashboard=" + uuid.uuid4().hex)["body"]
    assert set(schema["paths"]["/api/" + DASHBOARD]) >= {"get", "put", "patch", "post", "delete"}
    a.catalog.schema = schema
    compact = a.get_schema(DASHBOARD)
    write = compact["schemas"]["DashboardWriteRequest"]
    assert write["properties"]["config"]["additionalProperties"]["$ref"].endswith("DashboardWidgetRequest")
    widget = compact["schemas"]["DashboardWidgetRequest"]
    assert "class" in widget["required"]
    assert "config" in widget["properties"]
    patch = a.get_schema(DASHBOARD, method="PATCH")
    patch_type = patch["paths"]["/api/" + DASHBOARD]["patch"]["request"]["$ref"].rsplit("/", 1)[1]
    assert {"layout", "config", "remove"} <= set(patch["schemas"][patch_type]["properties"])
    widgets = a.query("plugins/agent-support/dashboard-widgets/")["body"]
    assert widgets["extras.NoteWidget"]["fields"]["content"]["required"]


@pytest.mark.parametrize(
    ("widget", "config"),
    [
        ("NoteWidget", {"content": "A note"}),
        ("ObjectCountsWidget", {"models": ["dcim.device"], "filters": {"status": "active"}}),
        ("ObjectListWidget", {"model": "dcim.device", "page_size": 5, "url_params": {"status": "active"}}),
        ("RSSFeedWidget", {"feed_url": "https://example.invalid/feed"}),
        ("BookmarksWidget", {"order_by": "-created", "max_items": 5}),
    ],
)
def test_every_builtin_dashboard_widget_uses_native_forms(people, widget, config):
    a, _ = people[0]
    body = note()
    entry = next(iter(body["config"].values()))
    entry.update({"class": "extras." + widget, "config": config})
    current = a.query(DASHBOARD)
    saved = a.api.request("PUT", DASHBOARD, body, {"If-Match": current["headers"]["etag"]})
    assert saved["status"] == 200, saved
    shell(f"""
from django.contrib.auth import get_user_model
u = get_user_model().objects.get(username={a.actor!r})
widgets = u.dashboard.get_layout()
assert len(widgets) == 1
assert widgets[0].name == {"extras." + widget!r}
""")
    invalid = {
        "NoteWidget": {"content": ""},
        "ObjectCountsWidget": {"models": ["missing.model"]},
        "ObjectListWidget": {"page_size": 101},
        "RSSFeedWidget": {"max_entries": 0},
        "BookmarksWidget": {"order_by": "invented"},
    }
    entry["config"] = {**config, **invalid[widget]}
    rejected = a.api.request("PUT", DASHBOARD, body, {"If-Match": saved["headers"]["etag"]})
    assert rejected["status"] == 400, rejected
    assert a.query(DASHBOARD)["body"] == saved["body"]


@pytest.mark.parametrize("verb", ["PUT", "PATCH"])
def test_dashboard_response_loss_is_uncertain_without_blind_replay(people, monkeypatch, verb):
    a, _ = people[0]
    before = a.query(DASHBOARD)
    task = a.begin_task("Lost dashboard response")["task_id"]
    original = a.api.request

    def lose(method, path, *args, **kwargs):
        response = original(method, path, *args, **kwargs)
        if method == verb and path == DASHBOARD:
            assert response["status"] == 200
            raise OSError("Lost response after commit")
        return response

    monkeypatch.setattr(a.api, "request", lose)
    body = note()
    result = a.execute_action(task, "dashboard-loss", verb, DASHBOARD, body, before["headers"]["etag"])
    assert result["state"] == "uncertain"
    assert a.query(DASHBOARD)["body"] == {"initialized": True, **body}
    assert (
        a.execute_action(task, "dashboard-loss", verb, DASHBOARD, body, before["headers"]["etag"])["id"]
        == result["id"]
    )


def test_dashboard_preserves_existing_native_defaults_when_adding_widget(people):
    from copy import deepcopy

    a, _ = people[0]
    current = a.query(DASHBOARD)
    original = a.api.request("POST", DASHBOARD, {}, {"If-Match": current["headers"]["etag"]})
    assert original["status"] == 200
    body = {k: deepcopy(original["body"][k]) for k in ("layout", "config")}
    addition = note("New note without rewriting existing widgets")
    body["layout"].extend(addition["layout"])
    body["config"].update(addition["config"])
    saved = a.api.request("PUT", DASHBOARD, body, {"If-Match": original["headers"]["etag"]})
    assert saved["status"] == 200, saved
    for pk, config in original["body"]["config"].items():
        assert saved["body"]["config"][pk] == config
    restored = a.api.request(
        "PUT",
        DASHBOARD,
        {k: original["body"][k] for k in ("layout", "config")},
        {"If-Match": saved["headers"]["etag"]},
    )
    assert restored["status"] == 200
    assert restored["body"] == original["body"]


def test_dashboard_widget_patch_preserves_every_other_widget(people):
    from copy import deepcopy

    a, _ = people[0]
    initial = a.query(DASHBOARD)
    original = a.api.request("POST", DASHBOARD, {}, {"If-Match": initial["headers"]["etag"]})
    task = a.begin_task("One widget at a time")["task_id"]
    # A native stored layout may omit optional coordinates. PATCH must not
    # normalize an unrelated entry by adding serializer defaults to it.
    shell(f"""
from django.contrib.auth import get_user_model
d = get_user_model().objects.get(username={a.actor!r}).dashboard
d.layout[0].pop('x', None)
d.save(update_fields=['layout'])
""")
    original = a.query(DASHBOARD)
    addition = note()
    pk = addition["layout"][0]["id"]
    saved = a.execute_action(
        task, "widget-addition", "PATCH", DASHBOARD, addition, original["headers"]["etag"]
    )
    assert saved["state"] == "completed"
    current = a.query(DASHBOARD)
    assert current["body"]["layout"] == original["body"]["layout"] + addition["layout"]
    assert current["body"]["config"] == {**original["body"]["config"], **addition["config"]}
    stale = a.execute_action(
        task, "widget-stale-remove", "PATCH", DASHBOARD, {"remove": [pk]}, original["headers"]["etag"]
    )
    assert stale["last_receipt"]["status"] == 412
    changed = deepcopy(addition["config"])
    changed[pk]["config"]["content"] = "Changed only this widget"
    for patch in [{"config": changed}, {"layout": [{"id": pk, "w": 6, "h": 4, "x": 0, "y": 0}]}]:
        response = a.api.request("PATCH", DASHBOARD, patch, {"If-Match": current["headers"]["etag"]})
        assert response["status"] == 200, response
        current = a.query(DASHBOARD)
        assert current["body"]["layout"][:-1] == original["body"]["layout"]
        assert {k: v for k, v in current["body"]["config"].items() if k != pk} == original["body"]["config"]
    assert current["body"]["config"][pk] == changed[pk]
    assert current["body"]["layout"][-1]["w"] == 6
    restored = a.execute_action(
        task, "widget-remove-own", "PATCH", DASHBOARD, {"remove": [pk]}, current["headers"]["etag"]
    )
    assert restored["last_receipt"]["body"] == original["body"]
    before = a.query(DASHBOARD)
    unknown = str(uuid.uuid4())
    existing = original["body"]["layout"][0]["id"]
    for patch in [
        {},
        {"remove": [unknown]},
        {"remove": [existing, existing]},
        {"layout": addition["layout"] * 2, "config": addition["config"]},
        {**addition, "remove": [pk]},
        {"config": addition["config"]},
    ]:
        response = a.api.request("PATCH", DASHBOARD, patch, {"If-Match": before["headers"]["etag"]})
        assert response["status"] == 400, response
        assert a.query(DASHBOARD)["body"] == before["body"]
