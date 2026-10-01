"""Native relationship lifecycles across OSS domains beyond basic physical inventory."""

import os

import pytest

from tests.integration.test_batch_actions import cabling, create  # noqa: F401
from tests.integration.test_imports import importer  # noqa: F401

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("NETBOX_RW_LIVE") != "1", reason="Disposable lab opt-in required"),
]


@pytest.fixture
def graph(cabling):  # noqa: F811
    service, prefix, site, devices = cabling
    objects = []

    def make(resource, values):
        obj = create(service, resource, values)
        objects.append((resource, obj["id"]))
        return obj

    try:
        yield service, prefix, site, devices, make
    finally:
        for resource, pk in reversed(objects):
            result = service.api.request("DELETE", resource + str(pk) + "/")
            assert result["status"] in {204, 404}, (resource, pk, result)


def test_native_vpn_tunnel_and_l2vpn_termination_relationships(graph):
    service, prefix, site, devices, make = graph
    interface = make("dcim/interfaces/", {"device": devices[0], "name": "vpn0", "type": "virtual"})
    address = make(
        "ipam/ip-addresses/",
        {
            "address": "192.0.2.240/32",
            "assigned_object_type": "dcim.interface",
            "assigned_object_id": interface["id"],
        },
    )
    group = make("vpn/tunnel-groups/", {"name": prefix, "slug": prefix})
    tunnel = make(
        "vpn/tunnels/", {"name": prefix, "status": "active", "encapsulation": "gre", "group": group["id"]}
    )
    termination = make(
        "vpn/tunnel-terminations/",
        {
            "tunnel": tunnel["id"],
            "role": "peer",
            "termination_type": "dcim.device",
            "termination_id": devices[0],
            "outside_ip": address["id"],
        },
    )
    l2 = make("vpn/l2vpns/", {"name": prefix, "slug": prefix, "type": "vxlan", "identifier": 4242})
    assigned = make(
        "vpn/l2vpn-terminations/",
        {"l2vpn": l2["id"], "assigned_object_type": "dcim.interface", "assigned_object_id": interface["id"]},
    )
    assert termination["tunnel"]["id"] == tunnel["id"] and termination["termination_id"] == devices[0]
    assert assigned["assigned_object_id"] == interface["id"]
    assert service.get_objects("vpn/tunnel-terminations/", {"tunnel_id": tunnel["id"]})["data"]["count"] == 1
    task = service.begin_task("VPN relationship maintenance")["task_id"]
    current = service.get_object_by_id("vpn/tunnels/", tunnel["id"])
    changed = service.update_object(
        task, "vpn-status-change", "vpn/tunnels/", tunnel["id"], current["etag"], {"status": "disabled"}
    )
    assert changed["state"] == "applied", changed
    assert service.api.get(f"vpn/tunnels/{tunnel['id']}/")["body"]["status"]["value"] == "disabled"
    bad = service.api.request(
        "POST",
        "vpn/tunnel-terminations/",
        {
            "tunnel": tunnel["id"],
            "role": "invalid",
            "termination_type": "dcim.device",
            "termination_id": devices[1],
        },
    )
    assert bad["status"] == 400


def test_native_wireless_lan_and_link_relationships(graph):
    service, prefix, site, devices, make = graph
    group = make("wireless/wireless-lan-groups/", {"name": prefix, "slug": prefix})
    vlan = make("ipam/vlans/", {"name": prefix, "vid": 3888})
    lan = make("wireless/wireless-lans/", {"ssid": prefix, "group": group["id"], "vlan": vlan["id"]})
    interfaces = [
        make(
            "dcim/interfaces/",
            {"device": pk, "name": "radio0", "type": "ieee802.11ac", "wireless_lans": [lan["id"]]},
        )
        for pk in devices
    ]
    link = make(
        "wireless/wireless-links/",
        {
            "interface_a": interfaces[0]["id"],
            "interface_b": interfaces[1]["id"],
            "ssid": prefix,
            "status": "connected",
        },
    )
    assert (
        link["interface_a"]["id"] == interfaces[0]["id"] and link["interface_b"]["id"] == interfaces[1]["id"]
    )
    assert interfaces[0]["wireless_lans"][0]["id"] == lan["id"]
    bad = service.api.request(
        "POST",
        "wireless/wireless-links/",
        {"interface_a": interfaces[0]["id"], "interface_b": interfaces[1]["id"], "status": "invalid"},
    )
    assert bad["status"] == 400
    assert service.get_objects("wireless/wireless-lans/", {"group_id": group["id"]})["data"]["count"] == 1


def test_native_contacts_journals_and_child_filters(graph):
    service, prefix, site, devices, make = graph
    group = make("tenancy/contact-groups/", {"name": prefix, "slug": prefix})
    contact = make(
        "tenancy/contacts/", {"name": prefix, "groups": [group["id"]], "email": "fixture@example.invalid"}
    )
    role = make("tenancy/contact-roles/", {"name": prefix, "slug": prefix})
    assignment = make(
        "tenancy/contact-assignments/",
        {
            "object_type": "dcim.site",
            "object_id": site,
            "contact": contact["id"],
            "role": role["id"],
            "priority": "primary",
        },
    )
    journal = make(
        "extras/journal-entries/",
        {
            "assigned_object_type": "dcim.device",
            "assigned_object_id": devices[0],
            "kind": "info",
            "comments": "Synthetic physical inventory inspected",
        },
    )
    contacts = service.get_objects(
        "tenancy/contact-assignments/", {"object_type": "dcim.site", "object_id": site}
    )["data"]["results"]
    assert [row["id"] for row in contacts] == [assignment["id"]]
    journals = service.get_objects(
        "extras/journal-entries/", {"assigned_object_type": "dcim.device", "assigned_object_id": devices[0]}
    )["data"]["results"]
    assert [row["id"] for row in journals] == [journal["id"]]
    children = service.get_objects("dcim/devices/", {"site_id": site})["data"]["results"]
    assert {row["id"] for row in children} == set(devices)
    assert (
        service.api.request(
            "PATCH", f"tenancy/contact-assignments/{assignment['id']}/", {"priority": "invalid"}
        )["status"]
        == 400
    )


def test_native_vm_primary_mac_and_fhrp_assignments(graph):
    service, prefix, site, devices, make = graph
    vm = make("virtualization/virtual-machines/", {"name": prefix, "site": site})
    interface = make("virtualization/interfaces/", {"name": "eth0", "virtual_machine": vm["id"]})
    mac = make(
        "dcim/mac-addresses/",
        {
            "mac_address": "02:00:00:02:00:01",
            "assigned_object_type": "virtualization.vminterface",
            "assigned_object_id": interface["id"],
        },
    )
    path = f"virtualization/interfaces/{interface['id']}/"
    result = service.api.request("PATCH", path, {"primary_mac_address": mac["id"]})
    assert result["status"] == 200, result
    assert service.api.get(path)["body"]["primary_mac_address"]["id"] == mac["id"]
    group = make("ipam/fhrp-groups/", {"name": prefix, "protocol": "vrrp3", "group_id": 42})
    assigned = make(
        "ipam/fhrp-group-assignments/",
        {
            "group": group["id"],
            "interface_type": "virtualization.vminterface",
            "interface_id": interface["id"],
            "priority": 100,
        },
    )
    assert assigned["interface_id"] == interface["id"]
    assert (
        service.api.request("PATCH", f"ipam/fhrp-group-assignments/{assigned['id']}/", {"priority": 9999})[
            "status"
        ]
        == 400
    )
