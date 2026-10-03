"""Lifecycle coverage for every native component pattern handler, including mappings."""

import os

import pytest

from tests.integration.test_batch_actions import cabling, create  # noqa: F401
from tests.integration.test_imports import importer  # noqa: F401
from tests.integration.test_configuration import shell

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("NETBOX_RW_LIVE") != "1", reason="Disposable lab opt-in required"),
]
ROOT = "plugins/agent-support/pattern-create/"
COMPONENTS = {
    "consoleport": "console-ports",
    "consoleserverport": "console-server-ports",
    "coolingintake": "cooling-intakes",
    "coolingoutflow": "cooling-outflows",
    "devicebay": "device-bays",
    "frontport": "front-ports",
    "interface": "interfaces",
    "inventoryitem": "inventory-items",
    "modulebay": "module-bays",
    "poweroutlet": "power-outlets",
    "powerport": "power-ports",
    "rearport": "rear-ports",
}
MODELS = ["dcim." + name + suffix for name in COMPONENTS for suffix in ("", "template")] + [
    "virtualization.vminterface",
    "virtualization.virtualdisk",
]


@pytest.mark.parametrize("model", MODELS)
def test_every_component_pattern_creates_two_verified_objects(cabling, model):  # noqa: F811
    service, prefix, site, devices = cabling
    kind = model.split(".")[1]
    template = kind.endswith("template")
    base = kind.removesuffix("template")
    vm = None
    device = service.api.get(f"dcim/devices/{devices[0]}/")["body"]
    dtype = device["device_type"]["id"]
    try:
        item = {"name": "qualification-[1-2]"}
        if model.startswith("virtualization."):
            vm = create(service, "virtualization/virtual-machines/", {"name": prefix, "site": site})
            item["virtual_machine"] = vm["id"]
            resource = "virtualization/" + ("interfaces/" if kind == "vminterface" else "virtual-disks/")
            if kind == "virtualdisk":
                item["size"] = 1024
        else:
            item["device_type" if template else "device"] = dtype if template else devices[0]
            resource = "dcim/" + COMPONENTS[base] + ("-templates/" if template else "/")
            # Template resource names use singular base before '-templates'.
            if template:
                resource = "dcim/" + COMPONENTS[base][:-1] + "-templates/"
            if base == "devicebay":
                response = service.api.request(
                    "PATCH", f"dcim/device-types/{dtype}/", {"subdevice_role": "parent"}
                )
                assert response["status"] == 200, response
            if base == "interface":
                item["type"] = "1000base-t"
            if base in {"frontport", "rearport"}:
                item.update(type="8p8c", positions=1)
            if base == "frontport":
                rear_resource = "dcim/rear-port-templates/" if template else "dcim/rear-ports/"
                rear = create(
                    service,
                    rear_resource,
                    {
                        "device_type" if template else "device": dtype if template else devices[0],
                        "name": "mapping-rear",
                        "type": "8p8c",
                        "positions": 2,
                    },
                )
                item["rear_ports"] = [f"{rear['id']}:1", f"{rear['id']}:2"]
                parent_name = "device_type" if template else "device"
                metadata = service.api.get(
                    ROOT + model + f"/?field=rear_ports&{parent_name}={item[parent_name]}"
                )["body"]
                assert {row["value"] for row in metadata["fields"]["rear_ports"]["choices"]} == set(
                    item["rear_ports"]
                )
            if base == "inventoryitem" and not template:
                item["status"] = "active"
            if base == "poweroutlet" and not template:
                item["status"] = "enabled"
        response = service.api.request("POST", ROOT + model + "/", {"items": [item]})
        assert response["status"] == 200, (model, response)
        assert response["body"]["count"] == 2
        rows = [service.api.get(resource + str(pk) + "/")["body"] for pk in response["body"]["ids"]]
        assert {row["name"] for row in rows} == {"qualification-1", "qualification-2"}
        parent = "virtual_machine" if vm else ("device_type" if template else "device")
        assert all(row[parent]["id"] == item[parent] for row in rows)
        if base == "frontport":
            assert all(
                len(row["rear_ports"]) == 1 and row["rear_ports"][0]["rear_port"] == rear["id"]
                for row in rows
            )
            assert {row["rear_ports"][0]["rear_port_position"] for row in rows} == {1, 2}
    finally:
        if vm:
            shell(f"""
from virtualization.models import VirtualMachine
VirtualMachine.objects.filter(pk={vm["id"]}).delete()
""")


def test_pattern_multi_parent_batch_is_atomic_and_inventory_component_is_preserved(cabling):  # noqa: F811
    service, prefix, site, devices = cabling
    interfaces = [{"device": pk, "name": "batch-[1-2]", "type": "1000base-t"} for pk in devices]
    path = ROOT + "dcim.interface/"
    rejected = service.api.request(
        "POST", path, {"items": [interfaces[0], {**interfaces[1], "type": "invalid"}]}
    )
    assert rejected["status"] == 400, rejected
    for pk in devices:
        assert service.api.get(f"dcim/interfaces/?device_id={pk}")["body"]["count"] == 0
    created = service.api.request("POST", path, {"items": interfaces})
    assert created["status"] == 200 and created["body"]["count"] == 4, created
    component = created["body"]["ids"][0]
    attached = service.api.request(
        "POST",
        ROOT + "dcim.inventoryitem/",
        {
            "items": [
                {"device": devices[0], "name": "optic-[1-2]", "interface": component, "status": "active"}
            ]
        },
    )
    assert attached["status"] == 200, attached
    for pk in attached["body"]["ids"]:
        row = service.api.get(f"dcim/inventory-items/{pk}/")["body"]
        assert row["component_type"] == "dcim.interface" and row["component_id"] == component
