"""Stock member formset reorder and native primary-MAC relationship semantics."""

import os

import pytest

from tests.integration.test_batch_actions import cabling, create  # noqa: F401
from tests.integration.test_imports import importer  # noqa: F401
from tests.integration.test_configuration import shell

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("NETBOX_RW_LIVE") != "1", reason="Disposable lab opt-in required"),
]


def test_virtual_chassis_atomic_reorder_and_guards(cabling):  # noqa: F811
    service, prefix, site, devices = cabling
    vc = create(service, "dcim/virtual-chassis/", {"name": prefix})
    path = f"plugins/agent-support/virtual-chassis/{vc['id']}/members/"
    try:
        for position, pk in enumerate(devices):
            result = service.api.request(
                "PATCH",
                f"dcim/devices/{pk}/",
                {"virtual_chassis": vc["id"], "vc_position": position, "vc_priority": 100},
            )
            assert result["status"] == 200, result
        before = service.api.get(path)
        assert before["status"] == 200, before
        state = before["body"]
        members = [{**row, "vc_position": 1 - row["vc_position"]} for row in state["members"]]
        invalid = [{**row, "vc_position": 0} for row in members]
        for rows in [invalid, members[:1], members + members[:1]]:
            result = service.api.request("PUT", path, {"members": rows, "expected": state["expected"]})
            assert result["status"] == 400, result
            assert service.api.get(path)["body"] == state
        task = service.begin_task("Atomic virtual chassis position swap")["task_id"]
        result = service.execute_action(
            task, "swap-vc-members", "PUT", path, {"members": members, "expected": state["expected"]}
        )
        assert result["state"] == "applied", result
        assert service.api.get(path)["body"]["members"] == members
        assert (
            service.api.request("PUT", path, {"members": members, "expected": state["expected"]})["status"]
            == 409
        )
    finally:
        shell(f"""
from dcim.models import Device, VirtualChassis
Device.objects.filter(pk__in={devices!r}).update(virtual_chassis=None, vc_position=None, vc_priority=None)
VirtualChassis.objects.filter(pk={vc["id"]}).delete()
""")


def test_native_primary_mac_selection_and_foreign_assignment_rejection(cabling):  # noqa: F811
    service, prefix, site, devices = cabling
    interfaces = [
        create(service, "dcim/interfaces/", {"device": pk, "name": "eth0", "type": "1000base-t"})
        for pk in devices
    ]
    macs = []
    try:
        for index, interface in enumerate(interfaces):
            macs.append(
                create(
                    service,
                    "dcim/mac-addresses/",
                    {
                        "mac_address": f"02:00:00:01:01:{index:02x}",
                        "assigned_object_type": "dcim.interface",
                        "assigned_object_id": interface["id"],
                    },
                )
            )
        path = f"dcim/interfaces/{interfaces[0]['id']}/"
        assert service.api.request("PATCH", path, {"primary_mac_address": macs[1]["id"]})["status"] == 400
        result = service.api.request("PATCH", path, {"primary_mac_address": macs[0]["id"]})
        assert result["status"] == 200, result
        assert service.api.get(path)["body"]["primary_mac_address"]["id"] == macs[0]["id"]
        assert service.api.request("PATCH", path, {"primary_mac_address": None})["status"] == 200
    finally:
        shell(f"""
from dcim.models import MACAddress
MACAddress.objects.filter(pk__in={[m["id"] for m in macs]!r}).delete()
""")


def test_chassis_members_respect_read_visibility_and_native_edit_permissions(cabling):  # noqa: F811
    service, prefix, site, devices = cabling
    shell(f"""
from django.contrib.auth import get_user_model
from django.db import transaction
from core.models import ObjectType
from dcim.models import Device, VirtualChassis
from users.models import ObjectPermission, Token
from rest_framework.test import APIRequestFactory, force_authenticate
from netbox_agent_api.api.chassis import ChassisMembersView
with transaction.atomic():
    chassis = VirtualChassis.objects.create(name={prefix!r})
    for position, pk in enumerate({devices!r}):
        Device.objects.filter(pk=pk).update(virtual_chassis=chassis, vc_position=position)
    user = get_user_model().objects.create(username={prefix!r})
    perm = ObjectPermission.objects.create(name={prefix!r}, actions=['view'], constraints={{'id': chassis.pk}})
    perm.users.add(user)
    perm.object_types.add(ObjectType.objects.get(app_label='dcim', model='virtualchassis'))
    def read():
        fresh = get_user_model().objects.get(pk=user.pk)
        request = APIRequestFactory().get('/api/plugins/agent-support/virtual-chassis/' + str(chassis.pk) + '/members/')
        force_authenticate(request, user=fresh, token=Token(user=fresh, write_enabled=False, version=1))
        response = ChassisMembersView.as_view()(request, pk=chassis.pk)
        assert response.status_code == 200, response.data
        return [row['id'] for row in response.data['members']]
    assert read() == []
    device_perm = ObjectPermission.objects.create(name={prefix!r} + '-device', actions=['view'], constraints={{'id': {devices[0]}}})
    device_perm.users.add(user)
    device_perm.object_types.add(ObjectType.objects.get(app_label='dcim', model='device'))
    assert read() == [{devices[0]}]
    perm.actions = ['view', 'change']
    perm.save()
    assert read() == sorted({devices!r})
    perm.actions = ['change']
    perm.save()
    assert read() == sorted({devices!r})
    transaction.set_rollback(True)
""")
