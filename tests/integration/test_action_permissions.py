"""Native permissions and token restrictions on companion mutation families."""

import os

import pytest

from netbox_readwrite_mcp.api import NetBox
from scripts.lab import URL
from tests.integration.test_personal import people  # noqa: F401
from tests.integration.test_batch_actions import cabling, create  # noqa: F401
from tests.integration.test_imports import importer  # noqa: F401
from tests.integration.test_configuration import shell

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("NETBOX_RW_LIVE") != "1", reason="Disposable lab opt-in required"),
]


def test_companion_mutation_families_require_native_permissions_and_writable_token(people):  # noqa: F811
    actor, readonly = people[0]
    reader = NetBox(URL, readonly)
    actions = [
        ("POST", "bulk-disconnect/dcim.interface/", {"ids": [1]}),
        ("POST", "bulk-sync/extras.configcontext/", {"ids": [1]}),
        ("POST", "native-delete/core.datafile/", {"id": 1}),
        ("POST", "bulk-edit/dcim.site/", {"ids": [1], "values": {"description": "forbidden"}}),
        ("POST", "bulk-rename/dcim.site/", {"ids": [1]}),
        ("PUT", "virtual-chassis/1/members/", {"members": [], "expected": "invalid"}),
    ]
    for method, path, body in actions:
        endpoint = "plugins/agent-support/" + path
        for client in (actor.api, reader):
            response = client.request(method, endpoint, body)
            assert response["status"] == 403, (endpoint, response)


def test_bulk_disconnect_mixed_object_constraints_are_atomic(cabling, people):  # noqa: F811
    service, prefix, site, devices = cabling
    actor, _ = people[0]
    interfaces = [
        create(service, "dcim/interfaces/", {"device": device, "name": "guard0", "type": "1000base-t"})
        for device in devices
    ]
    cable = create(
        service,
        "dcim/cables/",
        {
            "a_terminations": [{"object_type": "dcim.interface", "object_id": interfaces[0]["id"]}],
            "b_terminations": [{"object_type": "dcim.interface", "object_id": interfaces[1]["id"]}],
        },
    )
    username = actor.query("plugins/agent-support/self/profile/")["body"]["username"]
    shell(f"""
from django.contrib.auth import get_user_model
from core.models import ObjectType
from users.models import ObjectPermission
p = ObjectPermission.objects.create(name={username!r} + '-interfaces', actions=['view', 'change'], constraints={{'id': {interfaces[0]["id"]}}})
p.users.add(get_user_model().objects.get(username={username!r}))
p.object_types.add(ObjectType.objects.get(app_label='dcim', model='interface'))
""")
    endpoint = "plugins/agent-support/bulk-disconnect/dcim.interface/"
    try:
        mixed = actor.api.request("POST", endpoint, {"ids": [row["id"] for row in interfaces]})
        assert mixed["status"] == 403, mixed
        assert service.api.get(f"dcim/cables/{cable['id']}/")["status"] == 200
        preview = actor.api.request("POST", endpoint, {"ids": [interfaces[0]["id"]]})
        assert preview["status"] == 200, preview
        result = actor.api.request(
            "POST",
            endpoint,
            {"ids": [interfaces[0]["id"]], "apply": True, "expected": preview["body"]["expected"]},
        )
        assert result["status"] == 200, result
        assert service.api.request("GET", f"dcim/cables/{cable['id']}/")["status"] == 404
    finally:
        service.api.request("DELETE", f"dcim/cables/{cable['id']}/")


def test_disconnect_lost_receipt_retains_one_operation_and_reconciles(cabling, monkeypatch):  # noqa: F811
    service, prefix, site, devices = cabling
    endpoints = [
        create(service, "dcim/interfaces/", {"device": pk, "name": "loss0", "type": "1000base-t"})
        for pk in devices
    ]
    cable = create(
        service,
        "dcim/cables/",
        {
            "a_terminations": [{"object_type": "dcim.interface", "object_id": endpoints[0]["id"]}],
            "b_terminations": [{"object_type": "dcim.interface", "object_id": endpoints[1]["id"]}],
        },
    )
    path = "plugins/agent-support/bulk-disconnect/dcim.interface/"
    body = {"ids": [endpoints[0]["id"]]}
    preview = service.api.request("POST", path, body)
    assert preview["status"] == 200, preview
    body.update(apply=True, expected=preview["body"]["expected"])
    task = service.begin_task("Disconnect lost response")["task_id"]
    original = service.api.request
    calls = []

    def lose(method, target, *args, **kwargs):
        result = original(method, target, *args, **kwargs)
        if method == "POST" and target == path:
            calls.append(target)
            assert result["status"] == 200
            raise OSError("Lost committed disconnect response")
        return result

    monkeypatch.setattr(service.api, "request", lose)
    first = service.execute_action(task, "lost-disconnect", "POST", path, body)
    assert first["state"] == "uncertain", first
    repeated = service.execute_action(task, "lost-disconnect", "POST", path, body)
    assert repeated["id"] == first["id"] and len(calls) == 1
    assert service.api.request("GET", f"dcim/cables/{cable['id']}/")["status"] == 404
    service.reconcile()
    reconciled = service.get_operation(first["id"])
    assert reconciled["state"] == "applied", reconciled
    assert any(
        row["changed_object_type"] == "dcim.cable" and row["changed_object_id"] == cable["id"]
        for row in reconciled["native_changes"]
    )
