"""Configuration API qualification on the isolated lab; never run beside agent evals."""

import concurrent.futures
import json
import os
import secrets
import subprocess
import uuid

import pytest

from netbox_readwrite_mcp.api import NetBox
from netbox_readwrite_mcp.server import build_service
from scripts.lab import PREFIX, STATE, URL, VERSION

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("NETBOX_RW_LIVE") != "1", reason="Disposable lab opt-in required"),
]
PATH = "plugins/agent-support/config-revisions/"


def shell(source):
    result = subprocess.run(
        [
            "podman",
            "exec",
            "-i",
            PREFIX + "-netbox",
            "/opt/netbox/venv/bin/python",
            "/opt/netbox/netbox/manage.py",
            "shell",
        ],
        input=source,
        text=True,
        capture_output=True,
    )
    # Shell input can contain an ephemeral credential; never include it in failures.
    assert result.returncode == 0, "Disposable fixture setup/cleanup failed"


@pytest.fixture
def admin():
    api = NetBox(URL, json.loads((STATE / "secrets.json").read_text())["token"])
    assert api.get("status/")["body"]["netbox-version"] == VERSION
    before = api.get(PATH)["body"]
    assert "results" in before, before
    yield api
    # Restore exactly the original revision set and cache, even after assertion failures.
    # Configuration revisions do not implement a native changelog or undo operation.
    shell(f"""
from core.models import ConfigRevision
from django.core.cache import cache
from netbox.config import clear_config
ConfigRevision.objects.exclude(pk__in={repr([row["id"] for row in before["results"]])}).delete()
original = ConfigRevision.objects.filter(pk={repr(before["active_revision"])}).first()
if original:
    original.activate()
else:
    cache.set('config', {{}}, None)
    cache.set('config_version', None, None)
clear_config()
""")


def create(api, value="qualification", expected="current"):
    if expected == "current":
        expected = api.get(PATH)["body"]["active_revision"]
    return api.request(
        "POST",
        PATH,
        {
            "expected_active_revision": expected,
            "comment": "Companion API qualification",
            "parameters": {"BANNER_TOP": value},
        },
    )


def test_configuration_lifecycle_and_native_activation(admin):
    first = create(admin)
    assert first["status"] == 201, first["body"]
    a = first["body"]["id"]
    assert first["body"]["active"] is True
    shell(f"""
from netbox.config import get_config, clear_config
clear_config()
assert get_config().version == {a}
assert get_config().BANNER_TOP == 'qualification'
""")
    second = create(admin, "second")["body"]
    b = second["id"]
    assert admin.get(PATH + f"{a}/")["body"]["active"] is False
    assert admin.request("DELETE", PATH + f"{b}/", {"expected_active_revision": b})["status"] == 409
    restore = admin.request("POST", PATH + f"{a}/activate/", {"expected_active_revision": b})
    assert restore["status"] == 200 and restore["body"]["active"] is True
    shell(f"""
from netbox.config import get_config, clear_config
clear_config()
assert get_config().version == {a}
assert get_config().BANNER_TOP == 'qualification'
""")
    assert admin.request("DELETE", PATH + f"{b}/", {"expected_active_revision": a})["status"] == 204
    assert admin.request("GET", PATH + f"{b}/")["status"] == 404


def test_configuration_invalid_inputs_do_not_activate(admin):
    before = admin.get(PATH)["body"]
    invalid = [
        {"UNKNOWN_SETTING": 1},
        {"COPILOT_ENABLED": True},
        {"PAGINATE_COUNT": "invalid"},
        {"PREFER_IPV4": "yes"},
        {"PAGINATE_COUNT": True},
        {"BANNER_TOP": {"x": 1}},
        {"ALLOWED_URL_SCHEMES": "https"},
        {"CHANGELOG_RETENTION": 90},  # Statically set by this disposable lab.
    ]
    for params in invalid:
        result = admin.request(
            "POST", PATH, {"expected_active_revision": before["active_revision"], "parameters": params}
        )
        assert result["status"] == 400, (params, result["body"])
    for body in [
        {"parameters": {}},
        {"expected_active_revision": before["active_revision"], "parameters": {}, "active": True},
    ]:
        assert admin.request("POST", PATH, body)["status"] == 400
    assert admin.get(PATH)["body"] == before


def test_configuration_native_field_validation_and_replacement(admin):
    parameters = {
        "BANNER_TOP": "native fields",
        "PREFER_IPV4": True,
        "ALLOWED_URL_SCHEMES": ["http", "https"],
        "DEFAULT_USER_PREFERENCES": {"pagination": {"per_page": 25}},
    }
    response = admin.request(
        "POST",
        PATH,
        {
            "expected_active_revision": admin.get(PATH)["body"]["active_revision"],
            "parameters": parameters,
        },
    )
    assert response["status"] == 201, response["body"]
    assert response["body"]["data"] == parameters
    shell(f"""
import json
from core.forms import ConfigRevisionForm
from django import forms
parameters = {parameters!r}
form = ConfigRevisionForm()
for name, value in parameters.items():
    field = form.fields[name]
    assert field.clean(json.dumps(value) if isinstance(field, forms.JSONField) else value) == value
""")
    replacement = create(admin, "replacement")["body"]
    assert replacement["data"] == {"BANNER_TOP": "replacement"}
    # A stale restore must not change the active configuration.
    denied = admin.request(
        "POST",
        PATH + f"{response['body']['id']}/activate/",
        {"expected_active_revision": response["body"]["id"]},
    )
    assert denied["status"] == 409
    assert admin.get(PATH)["body"]["active_revision"] == replacement["id"]
    assert (
        admin.request(
            "DELETE",
            PATH + f"{response['body']['id']}/",
            {"expected_active_revision": replacement["id"]},
            {"If-Match": '"wrong"'},
        )["status"]
        == 412
    )
    empty = admin.request(
        "POST",
        PATH,
        {
            "expected_active_revision": replacement["id"],
            "parameters": {"BANNER_TOP": "", "ALLOWED_URL_SCHEMES": [], "PREFER_IPV4": False},
        },
    )
    assert empty["status"] == 201
    assert empty["body"]["data"] == {"PREFER_IPV4": False}


def test_configuration_concurrent_writers_have_one_winner(admin):
    expected = admin.get(PATH)["body"]["active_revision"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda label: create(admin, label, expected), ["race-a", "race-b"]))
    assert sorted(r["status"] for r in responses) == [201, 409]
    winner = next(r["body"] for r in responses if r["status"] == 201)
    assert admin.get(PATH)["body"]["active_revision"] == winner["id"]
    assert (
        admin.request("DELETE", PATH + f"{winner['id']}/", {"expected_active_revision": expected})["status"]
        == 409
    )


def test_configuration_preserves_excluded_and_static_overrides(admin):
    shell("""
from core.models import ConfigRevision
ConfigRevision.objects.create(comment='Native existing settings',
    data={'COPILOT_ENABLED': False, 'CHANGELOG_RETENTION': 17, 'BANNER_TOP': 'existing'})
""")
    original = admin.get(PATH)["body"]["active_revision"]
    created = create(admin, "updated")["body"]
    assert created["data"] == {
        "COPILOT_ENABLED": False,
        "CHANGELOG_RETENTION": 17,
        "BANNER_TOP": "updated",
    }
    # Simulate an old saved revision containing a commercial flag without ever
    # activating that flag. The OSS extension must not activate it indirectly.
    shell(f"""
from core.models import ConfigRevision
ConfigRevision.objects.filter(pk={original}).update(data={{'COPILOT_ENABLED': True}})
""")
    result = admin.request(
        "POST", PATH + f"{original}/activate/", {"expected_active_revision": created["id"]}
    )
    assert result["status"] == 409
    assert admin.get(PATH)["body"]["active_revision"] == created["id"]


def test_configuration_restricted_identity_and_readonly_token(admin):
    suffix = uuid.uuid4().hex
    token = secrets.token_hex(20)
    readonly = secrets.token_hex(20)
    shell(f"""
from django.contrib.auth import get_user_model
from users.models import Token, ObjectPermission
from core.models import ObjectType
u = get_user_model().objects.create(username='config-test-{suffix}')
for value, writable in [({token!r}, True), ({readonly!r}, False)]:
    Token.objects.create(user=u, token=value, plaintext=value, version=1, write_enabled=writable)
p = ObjectPermission.objects.create(name='config-test-{suffix}', actions=['view','add','delete'], constraints={{'comment': 'permitted'}})
p.users.add(u)
p.object_types.add(ObjectType.objects.get(app_label='core', model='configrevision'))
""")
    actor = NetBox(URL, token)
    try:
        initial = admin.get(PATH)["body"]
        # An add permission for some objects must not allow an out-of-scope revision
        # to activate before the permission check rolls back its database insert.
        assert create(actor, expected=initial["active_revision"])["status"] == 403
        assert admin.get(PATH)["body"] == initial
        shell(f"""
from netbox.config import get_config, clear_config
clear_config()
assert get_config().version == {initial["active_revision"]!r}
""")
        allowed = {
            "expected_active_revision": initial["active_revision"],
            "parameters": {},
            "comment": "permitted",
        }
        assert NetBox(URL, readonly).request("POST", PATH, allowed)["status"] == 403
        created = actor.request("POST", PATH, allowed)
        assert created["status"] == 201, created["body"]
        pk = created["body"]["id"]
        assert actor.get(PATH + f"{pk}/")["status"] == 200
        assert (
            actor.request("POST", PATH + f"{pk}/activate/", {"expected_active_revision": pk})["status"] == 403
        )
        other = create(admin)["body"]["id"]
        assert actor.request("GET", PATH + f"{other}/")["status"] == 404
        assert (
            actor.request("DELETE", PATH + f"{other}/", {"expected_active_revision": other})["status"] == 404
        )
    finally:
        shell(f"""
from django.contrib.auth import get_user_model
from users.models import ObjectPermission
get_user_model().objects.filter(username='config-test-{suffix}').delete()
ObjectPermission.objects.filter(name='config-test-{suffix}').delete()
""")
    cfg = json.loads((STATE / "config.json").read_text())
    svc = build_service(cfg)
    try:
        assert svc.api.request("GET", PATH)["status"] == 403
        assert (
            svc.api.request("POST", PATH, {"expected_active_revision": None, "parameters": {}})["status"]
            == 403
        )
    finally:
        svc.store.close()


def test_configuration_discovery_and_mcp_receipt(admin, tmp_path, monkeypatch):
    cfg = json.loads((STATE / "broad-config.json").read_text())
    cfg.update(journal=str(tmp_path / "journal.sqlite"), actor="audit-admin")
    # Use an administrator only for the administrative test, never upgrade inventory actor.
    token_path = tmp_path / "token"
    token_path.write_text(json.loads((STATE / "secrets.json").read_text())["token"])
    token_path.chmod(0o600)
    cfg["token_file"] = str(token_path)
    svc = build_service(cfg)
    try:
        assert PATH in {m["resource"] for m in svc.discover_models(refresh=True)["models"]}
        cold = admin.get("schema/?format=json&config-qualification=" + uuid.uuid4().hex)
        assert cold["status"] == 200
        assert "post" in cold["body"]["paths"]["/api/" + PATH]
        task = svc.begin_task("Configuration revision qualification")["task_id"]
        result = svc.execute_action(
            task,
            "revision",
            "POST",
            PATH,
            {
                "expected_active_revision": admin.get(PATH)["body"]["active_revision"],
                "parameters": {"BANNER_TOP": "MCP qualification"},
            },
        )
        assert result["last_receipt"]["status"] == 201, result
        assert result["last_receipt"]["body"]["data"]["BANNER_TOP"] == "MCP qualification"
        replay = svc.execute_action(task, "revision", "POST", PATH, result["requested"])
        assert replay["id"] == result["id"]
        assert result["state"] == "completed" and result["native_changes"] == []
        pk = result["last_receipt"]["body"]["id"]
        successor = create(admin, "successor")["body"]["id"]
        detail = svc.query(PATH + f"{pk}/")
        deleted = svc.execute_action(
            task,
            "revision-delete",
            "DELETE",
            PATH + f"{pk}/",
            {"expected_active_revision": successor},
            detail["headers"]["etag"],
        )
        assert deleted["last_receipt"]["status"] == 204

        original_request = svc.api.request

        def lost_response(method, path, *args, **kwargs):
            response = original_request(method, path, *args, **kwargs)
            if method == "POST" and path == PATH:
                assert response["status"] == 201
                raise OSError("Simulated response loss after NetBox committed")
            return response

        monkeypatch.setattr(svc.api, "request", lost_response)
        payload = {"expected_active_revision": successor, "parameters": {"BANNER_TOP": "lost response"}}
        lost = svc.execute_action(task, "revision-response-loss", "POST", PATH, payload)
        assert lost["state"] == "uncertain"
        after = admin.get(PATH)["body"]
        assert after["active_revision"] != successor
        assert svc.execute_action(task, "revision-response-loss", "POST", PATH, payload)["id"] == lost["id"]
        assert admin.get(PATH)["body"] == after
    finally:
        svc.store.close()
