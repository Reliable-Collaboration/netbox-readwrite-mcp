"""Own-account native validation, isolation and credential receipt handling."""

import json
import os
import secrets

import pytest

from netbox_readwrite_mcp.api import NetBox
from scripts.lab import URL
from tests.integration.test_configuration import shell
from tests.integration.test_personal import people  # noqa: F401

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("NETBOX_RW_LIVE") != "1", reason="Disposable lab opt-in required"),
]
PROFILE = "plugins/agent-support/self/profile/"
PREFERENCES = "plugins/agent-support/self/preferences/"
PASSWORD = "plugins/agent-support/self/password/"


def test_own_profile_without_user_administration_permission(people):  # noqa: F811
    a, b = [entry[0] for entry in people]
    for service in (a, b):
        profile = service.query(PROFILE)["body"]
        assert profile["username"] == service.actor and "password" not in profile
        assert service.api.request("GET", f"users/users/{profile['id']}/")["status"] == 403
    assert a.query(PROFILE)["body"]["id"] != b.query(PROFILE)["body"]["id"]


def test_validated_preferences_patch_clear_guards_and_isolation(people):  # noqa: F811
    a, b = [entry[0] for entry in people]
    initial = {"tables": {"SiteTable": {"columns": ["name"]}}, "private_local": {"keep": 42}}
    assert a.api.request("PATCH", "users/config/", initial)["status"] == 200
    untouched = b.query("users/config/")["body"]
    before = a.query(PREFERENCES)
    assert "ui.copilot_enabled" not in before["body"]["fields"]
    assert before["body"]["clearable_tables"] == ["tables.SiteTable"]
    task = a.begin_task("Native preference validation")["task_id"]
    changed = a.execute_action(
        task,
        "preference-change",
        "PATCH",
        PREFERENCES,
        {"values": {"pagination.per_page": 100}},
        before["headers"]["etag"],
    )
    assert changed["state"] == "completed" and changed["last_receipt"]["status"] == 200, changed
    actual = a.query("users/config/")["body"]
    assert actual == {**initial, "pagination": {"per_page": 100}}
    stale = a.api.request(
        "PATCH", PREFERENCES, {"values": {"pagination.per_page": 50}}, {"If-Match": before["headers"]["etag"]}
    )
    assert stale["status"] == 412
    current = a.query(PREFERENCES)
    for data in [
        {"values": {"pagination.per_page": "invalid"}},
        {"values": {"ui.copilot_enabled": True}},
        {"clear_tables": ["tables.OtherTable"]},
    ]:
        result = a.api.request("PATCH", PREFERENCES, data, {"If-Match": current["headers"]["etag"]})
        assert result["status"] == 400, result
        assert a.query("users/config/")["body"] == actual
    cleared = a.api.request(
        "PATCH", PREFERENCES, {"clear_tables": ["tables.SiteTable"]}, {"If-Match": current["headers"]["etag"]}
    )
    assert cleared["status"] == 200, cleared
    assert a.query("users/config/")["body"] == {
        "tables": {},
        "private_local": {"keep": 42},
        "pagination": {"per_page": 100},
    }
    assert b.query("users/config/")["body"] == untouched
    assert a.api.request("PATCH", PREFERENCES, {})["status"] == 428
    assert (
        NetBox(URL, people[0][1]).request("PATCH", PREFERENCES, {}, {"If-Match": current["headers"]["etag"]})[
            "status"
        ]
        == 403
    )


def test_password_native_validation_isolation_and_redacted_receipts(people):  # noqa: F811
    a, b = [entry[0] for entry in people]
    old, new = [secrets.token_urlsafe(24) for _ in range(2)]
    shell(f"""
from django.contrib.auth import get_user_model
for name in [{a.actor!r}, {b.actor!r}]:
    u = get_user_model().objects.get(username=name)
    u.set_password({old!r})
    u.save()
""")
    base = {"old_password": old, "new_password1": new, "new_password2": new}
    for changed in [{"old_password": "incorrect"}, {"new_password2": "mismatched"}]:
        response = a.api.request("POST", PASSWORD, {**base, **changed})
        assert response["status"] == 400
        assert old not in json.dumps(response) and new not in json.dumps(response)
    assert NetBox(URL, people[0][1]).request("POST", PASSWORD, base)["status"] == 403
    task = a.begin_task("Own password change")["task_id"]
    result = a.execute_action(task, "password-change", "POST", PASSWORD, base)
    assert result["last_receipt"]["status"] == 200, result
    assert result["last_receipt"]["body"] == {"changed": True}
    assert old not in json.dumps(result) and new not in json.dumps(result)
    assert a.execute_action(task, "password-change", "POST", PASSWORD, base)["id"] == result["id"]
    shell(f"""
from django.contrib.auth import get_user_model
assert get_user_model().objects.get(username={a.actor!r}).check_password({new!r})
assert get_user_model().objects.get(username={b.actor!r}).check_password({old!r})
""")
    for row in a.store.db.execute("SELECT payload FROM events"):
        assert old not in row[0] and new not in row[0]


@pytest.mark.parametrize("resource", ["extras/bookmarks/", "extras/subscriptions/", "extras/notifications/"])
def test_native_own_object_lifecycle_and_cross_user_denial(people, resource):  # noqa: F811
    a, b = [entry[0] for entry in people]
    users = [service.query(PROFILE)["body"]["id"] for service in (a, b)]
    name = "own-object-" + secrets.token_hex(8)
    shell(f"""
from dcim.models import Site
Site.objects.create(name={name!r}, slug={name!r})
""")
    try:
        # Obtain only the fixture's ID through a native view permission.
        shell(f"""
from users.models import ObjectPermission
from core.models import ObjectType
for name in [{a.actor!r}, {b.actor!r}]:
    p = ObjectPermission.objects.get(name=name)
    p.object_types.add(ObjectType.objects.get(app_label='dcim', model='site'))
""")
        site = a.get_objects("dcim/sites/", {"slug": name})["data"]["results"][0]
        data = {"object_type": "dcim.site", "object_id": site["id"], "user": users[0]}
        if resource == "extras/notifications/":
            data["event_type"] = "object_updated"
        created = a.api.request("POST", resource, data)
        assert created["status"] == 201, created
        pk = created["body"]["id"]
        assert b.api.get(resource)["body"]["count"] == 0
        assert b.api.request("GET", resource + str(pk) + "/")["status"] == 404
        assert b.api.request("DELETE", resource + str(pk) + "/")["status"] == 404
        denied = a.api.request("POST", resource, {**data, "user": users[1]})
        assert denied["status"] == 403, denied
        assert b.api.get(resource)["body"]["count"] == 0
        if resource == "extras/notifications/":
            response = a.api.request("PATCH", resource + str(pk) + "/", {"read": "2026-10-01T00:00:00Z"})
            assert response["status"] == 200 and response["body"]["read"] is not None, response
        assert a.api.request("DELETE", resource + str(pk) + "/")["status"] == 204
        assert a.api.get(resource)["body"]["count"] == 0
    finally:
        shell(f"""
from dcim.models import Site
Site.objects.filter(slug={name!r}).delete()
""")


def test_native_own_v2_token_create_revoke_and_no_cross_user_grant(people):  # noqa: F811
    a, b = [entry[0] for entry in people]
    users = [service.query(PROFILE)["body"]["id"] for service in (a, b)]
    body = {
        "user": users[0],
        "version": 2,
        "write_enabled": False,
        "description": "Disposable own-token qualification",
    }
    response = a.api.request("POST", "users/tokens/", body)
    assert response["status"] == 201
    token = response["body"]
    pk = token["id"]
    try:
        # Avoid putting ephemeral token plaintext in assertion diagnostics.
        assert token["token"] and token["key"]
        auth = "nbt_" + token["key"] + "." + token["token"]
        client = NetBox(URL, auth)
        assert client.get(PROFILE)["body"]["id"] == users[0]
        assert b.api.request("GET", f"users/tokens/{pk}/")["status"] == 404
        assert a.api.request("POST", "users/tokens/", {**body, "user": users[1]})["status"] == 403
        assert not a.api.get(f"users/tokens/{pk}/")["body"]["token"]
        changed = a.api.request("PATCH", f"users/tokens/{pk}/", {"enabled": False})
        assert changed["status"] == 200
        assert client.request("GET", PROFILE)["status"] == 403
    finally:
        assert a.api.request("DELETE", f"users/tokens/{pk}/")["status"] == 204


def test_own_notification_batch_actions_are_isolated_and_atomic(people):  # noqa: F811
    a, b = [entry[0] for entry in people]
    path = "plugins/agent-support/self/notifications/"
    users = [service.query(PROFILE)["body"]["id"] for service in (a, b)]
    shell(f"""
from extras.models import Notification
from core.models import ObjectType
from dcim.models import Site
sites = [Site.objects.create(name={a.actor!r} + str(i), slug={a.actor!r} + str(i)) for i in range(3)]
for user_id in {users!r}:
    for site in sites:
        Notification.objects.create(user_id=user_id, object_type=ObjectType.objects.get(app_label='dcim', model='site'), object_id=site.pk, event_type='object_updated')
""")
    try:
        own = a.api.get(path)["body"]
        other = b.api.get(path)["body"]
        assert own["count"] == other["count"] == 3
        ids = [item["id"] for item in own["results"]]
        assert a.api.get(path + "?limit=1")["body"]["next_offset"] == 1
        for values, status in [
            ({"action": "read", "ids": [ids[0], other["results"][0]["id"]]}, 404),
            ({"action": "read", "ids": [ids[0], ids[0]]}, 400),
            ({"action": "dismiss_unread", "ids": ids}, 400),
            ({"action": "read"}, 400),
        ]:
            assert a.api.request("POST", path, values)["status"] == status
            assert a.api.get(path + "?unread=true")["body"]["count"] == 3
        assert NetBox(URL, people[0][1]).request("POST", path, {"action": "dismiss_unread"})["status"] == 403
        task = a.begin_task("Own notification management")["task_id"]
        read = a.execute_action(task, "read-notification", "POST", path, {"action": "read", "ids": ids[:1]})
        assert read["last_receipt"]["status"] == 200, read
        assert a.api.get(path + "?unread=true")["body"]["count"] == 2
        dismissed = a.api.request("POST", path, {"action": "dismiss_unread"})
        assert dismissed["status"] == 200 and dismissed["body"]["count"] == 2, dismissed
        remaining = a.api.get(path)["body"]
        assert remaining["count"] == 1 and remaining["results"][0]["id"] == ids[0]
        assert a.api.request("POST", path, {"action": "dismiss", "ids": ids[:1]})["status"] == 200
        assert a.api.get(path)["body"]["count"] == 0
        assert b.api.get(path)["body"] == other
    finally:
        shell(f"""
from dcim.models import Site
Site.objects.filter(slug__startswith={a.actor!r}).delete()
""")
