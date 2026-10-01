"""Native range expansion, templating, component replication and rollback."""

import os

import pytest

from tests.integration.test_imports import importer  # noqa: F401
from tests.integration.test_administration import queue_admin  # noqa: F401
from tests.integration.test_configuration import shell

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("NETBOX_RW_LIVE") != "1", reason="Disposable lab opt-in required"),
]
PATH = "plugins/agent-support/pattern-create/"


@pytest.fixture
def parents(importer):  # noqa: F811
    service, prefix = importer

    def create(path, data):
        result = service.api.request("POST", path, data)
        assert result["status"] == 201, result
        return result["body"]["id"]

    try:
        vrf = create("ipam/vrfs/", {"name": prefix, "enforce_unique": True})
        group = create("ipam/vlan-groups/", {"name": prefix, "slug": prefix})
        manufacturer = create("dcim/manufacturers/", {"name": prefix, "slug": prefix})
        device_type = create(
            "dcim/device-types/", {"manufacturer": manufacturer, "model": prefix, "slug": prefix}
        )
        yield service, prefix, {"vrf": vrf, "group": group, "device_type": device_type}
    finally:
        shell(f"""
from ipam.models import IPAddress, Prefix, VLAN, VLANGroup, VRF
from dcim.models import DeviceType, Manufacturer
IPAddress.objects.filter(vrf__name={prefix!r}).delete()
Prefix.objects.filter(vrf__name={prefix!r}).delete()
VRF.objects.filter(name={prefix!r}).delete()
VLAN.objects.filter(group__slug={prefix!r}).delete()
VLANGroup.objects.filter(slug={prefix!r}).delete()
DeviceType.objects.filter(slug={prefix!r}).delete()
Manufacturer.objects.filter(slug={prefix!r}).delete()
""")


@pytest.mark.parametrize(
    "model,resource,pattern,parent",
    [
        ("ipam.vlan", "ipam/vlans/", "3901-3903", "group"),
        ("ipam.ipaddress", "ipam/ip-addresses/", "203.0.113.[1-3]/24", "vrf"),
        ("ipam.prefix", "ipam/prefixes/", "192.0.[1-3].0/24", "vrf"),
    ],
)
def test_range_expansion_atomic_rollback_and_mcp_history(parents, model, resource, pattern, parent):
    service, prefix, ids = parents
    task = service.begin_task("Native range qualification")["task_id"]
    item = {"pattern": pattern, parent: ids[parent], "status": "active"}
    if model == "ipam.vlan":
        item["name"] = prefix + "-{vid}"
    body = {"items": [item]}
    created = service.execute_action(task, "range-create", "POST", PATH + model + "/", body)
    assert created["state"] == "applied" and len(created["native_changes"]) == 3, created
    created_ids = created["last_receipt"]["body"]["ids"]
    assert len(created_ids) == 3
    if model == "ipam.vlan":
        assert [service.query(resource + str(pk) + "/")["body"]["name"] for pk in created_ids] == [
            prefix + "-" + str(vid) for vid in range(3901, 3904)
        ]
    # First item would succeed, but the second violates the existing unique range.
    new = {**item, "pattern": pattern.replace("1-3", "4-5").replace("3901-3903", "3904-3905")}
    rejected = service.api.request("POST", PATH + model + "/", {"items": [new, item]})
    assert rejected["status"] == 400, rejected
    response = service.api.get(resource + f"?{parent}_id={ids[parent]}")
    assert response["body"]["count"] == 3, response
    assert (
        service.execute_action(task, "range-create", "POST", PATH + model + "/", body)["id"] == created["id"]
    )


def test_component_name_label_expansion_and_batch_rollback(parents):
    service, _, ids = parents
    task = service.begin_task("Native component patterns")["task_id"]
    body = {
        "items": [
            {
                "device_type": ids["device_type"],
                "name": "eth[1-3]",
                "label": "Port [1-3]",
                "type": "1000base-t",
            }
        ]
    }
    result = service.execute_action(task, "component-pattern", "POST", PATH + "dcim.interfacetemplate/", body)
    assert result["state"] == "applied" and len(result["native_changes"]) == 3, result
    actual = [
        service.query(f"dcim/interface-templates/{pk}/")["body"]
        for pk in result["last_receipt"]["body"]["ids"]
    ]
    assert [(r["name"], r["label"]) for r in actual] == [(f"eth{i}", f"Port {i}") for i in range(1, 4)]
    invalid = {"items": [{**body["items"][0], "name": "eth[4-6]"}, body["items"][0]]}
    assert service.api.request("POST", PATH + "dcim.interfacetemplate/", invalid)["status"] == 400
    assert (
        service.api.get(f"dcim/interface-templates/?device_type_id={ids['device_type']}")["body"]["count"]
        == 3
    )


def test_all_native_pattern_schemas(queue_admin):  # noqa: F811
    service = queue_admin
    catalog = service.query(PATH)["body"]
    assert catalog["count"] == 29
    for row in catalog["results"]:
        result = service.query(PATH + row["model"] + "/")
        assert result["body"]["pattern_fields"] and result["body"]["fields"], row
