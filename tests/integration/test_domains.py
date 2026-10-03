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


def test_native_physical_and_virtual_circuit_graph(graph):
    service, prefix, site, devices, make = graph
    provider = make("circuits/providers/", {"name": prefix, "slug": prefix})
    account = make("circuits/provider-accounts/", {"provider": provider["id"], "account": prefix})
    network = make("circuits/provider-networks/", {"provider": provider["id"], "name": prefix})
    kind = make("circuits/circuit-types/", {"name": prefix, "slug": prefix})
    circuit = make(
        "circuits/circuits/",
        {"cid": prefix, "provider": provider["id"], "provider_account": account["id"], "type": kind["id"]},
    )
    ends = [
        make(
            "circuits/circuit-terminations/",
            {
                "circuit": circuit["id"],
                "term_side": side,
                "termination_type": model,
                "termination_id": pk,
                "port_speed": 1000000,
            },
        )
        for side, model, pk in [("A", "dcim.site", site), ("Z", "circuits.providernetwork", network["id"])]
    ]
    group = make("circuits/circuit-groups/", {"name": prefix, "slug": prefix})
    assignment = make(
        "circuits/circuit-group-assignments/",
        {
            "group": group["id"],
            "member_type": "circuits.circuit",
            "member_id": circuit["id"],
            "priority": "primary",
        },
    )
    vkind = make("circuits/virtual-circuit-types/", {"name": prefix, "slug": prefix})
    virtual = make(
        "circuits/virtual-circuits/",
        {
            "cid": prefix,
            "provider_network": network["id"],
            "provider_account": account["id"],
            "type": vkind["id"],
        },
    )
    interface = make("dcim/interfaces/", {"device": devices[0], "name": "wan0", "type": "virtual"})
    term = make(
        "circuits/virtual-circuit-terminations/",
        {"virtual_circuit": virtual["id"], "interface": interface["id"]},
    )
    assert term["interface"]["id"] == interface["id"]
    assert assignment["member_id"] == circuit["id"]
    assert {
        row["id"]
        for row in service.get_objects("circuits/circuit-terminations/", {"circuit_id": circuit["id"]})[
            "data"
        ]["results"]
    } == {row["id"] for row in ends}
    duplicate = service.api.request(
        "POST", "circuits/circuit-terminations/", {"circuit": circuit["id"], "term_side": "A"}
    )
    assert duplicate["status"] == 400
    protected = service.api.request("DELETE", f"circuits/providers/{provider['id']}/")
    assert protected["status"] in {400, 409}, protected
    assert service.api.get(f"circuits/circuits/{circuit['id']}/")["status"] == 200


def test_native_ike_ipsec_policy_graph_and_validation(graph):
    service, prefix, site, devices, make = graph
    proposal = make(
        "vpn/ike-proposals/",
        {
            "name": prefix,
            "authentication_method": "preshared-keys",
            "encryption_algorithm": "aes-256-cbc",
            "authentication_algorithm": "hmac-sha256",
            "group": 14,
        },
    )
    ike = make("vpn/ike-policies/", {"name": prefix, "version": 2, "proposals": [proposal["id"]]})
    proposal2 = make(
        "vpn/ipsec-proposals/",
        {"name": prefix, "encryption_algorithm": "aes-256-cbc", "authentication_algorithm": "hmac-sha256"},
    )
    policy = make("vpn/ipsec-policies/", {"name": prefix, "proposals": [proposal2["id"]], "pfs_group": 14})
    profile = make(
        "vpn/ipsec-profiles/",
        {"name": prefix, "mode": "esp", "ike_policy": ike["id"], "ipsec_policy": policy["id"]},
    )
    tunnel = make(
        "vpn/tunnels/",
        {"name": prefix, "status": "active", "encapsulation": "ipsec-tunnel", "ipsec_profile": profile["id"]},
    )
    assert tunnel["ipsec_profile"]["id"] == profile["id"]
    assert ike["proposals"][0]["id"] == proposal["id"]
    assert policy["proposals"][0]["id"] == proposal2["id"]
    rejected = service.api.request("PATCH", f"vpn/ike-proposals/{proposal['id']}/", {"group": 9999})
    assert rejected["status"] == 400
    assert service.api.get(f"vpn/ike-proposals/{proposal['id']}/")["body"]["group"]["value"] == 14


def test_native_device_and_vm_context_rendering(graph):
    service, prefix, site, devices, make = graph
    template = make(
        "extras/config-templates/",
        {"name": prefix, "template_code": "hostname {{ name }} role {{ role_label }}"},
    )
    vm = make("virtualization/virtual-machines/", {"name": prefix, "site": site})
    task = service.begin_task("Render inventory configuration")["task_id"]
    try:
        for resource, pk in [("dcim/devices/", devices[0]), ("virtualization/virtual-machines/", vm["id"])]:
            path = f"{resource}{pk}/"
            updated = service.api.request(
                "PATCH",
                path,
                {
                    "config_template": template["id"],
                    "local_context_data": {"name": prefix, "role_label": "lab"},
                },
            )
            assert updated["status"] == 200, updated
            result = service.execute_action(
                task, "render-" + str(pk) + resource.split("/")[0], "POST", path + "render-config/", {}
            )
            assert result["last_receipt"]["status"] == 200, result
            assert f"hostname {prefix} role lab" in str(result["last_receipt"]["body"])
        invalid = service.api.request(
            "PATCH",
            f"extras/config-templates/{template['id']}/",
            {"template_code": "{{ missing.required.value }}"},
        )
        assert invalid["status"] == 200
        failed = service.api.request("POST", f"virtualization/virtual-machines/{vm['id']}/render-config/", {})
        assert failed["status"] == 500, failed  # Native rendering contract for a template exception.
    finally:
        # Drop the physical device reference before graph's reverse-order template cleanup.
        assert (
            service.api.request("PATCH", f"dcim/devices/{devices[0]}/", {"config_template": None})["status"]
            == 200
        )


def test_bulk_interface_vlan_deltas_preserve_other_memberships(graph):
    service, prefix, site, devices, make = graph
    vlans = [make("ipam/vlans/", {"name": prefix + str(i), "vid": 3800 + i}) for i in range(3)]
    interface = make(
        "dcim/interfaces/",
        {
            "device": devices[0],
            "name": "trunk0",
            "type": "1000base-t",
            "mode": "tagged",
            "tagged_vlans": [v["id"] for v in vlans[:2]],
        },
    )
    path = "plugins/agent-support/bulk-edit/dcim.interface/"
    body = {
        "ids": [interface["id"]],
        "values": {
            "mode": "tagged",
            "add_tagged_vlans": [vlans[2]["id"]],
            "remove_tagged_vlans": [vlans[1]["id"]],
        },
    }
    preview = service.api.request("POST", path, body)
    assert preview["status"] == 200, preview
    saved = service.api.request(
        "POST", path, {**body, "apply": True, "expected": preview["body"]["expected"]}
    )
    assert saved["status"] == 200, saved
    actual = service.api.get(f"dcim/interfaces/{interface['id']}/")["body"]
    assert {v["id"] for v in actual["tagged_vlans"]} == {vlans[0]["id"], vlans[2]["id"]}


def test_native_bulk_delete_protection_rolls_back_then_records_all_changes(graph):
    service, prefix, site, devices, make = graph
    vendors = [
        make("dcim/manufacturers/", {"name": prefix + str(i), "slug": prefix + str(i)}) for i in range(2)
    ]
    dtype = make("dcim/device-types/", {"manufacturer": vendors[1]["id"], "model": prefix, "slug": prefix})
    task = service.begin_task("Native atomic bulk deletion")["task_id"]
    body = [{"id": row["id"]} for row in vendors]
    denied = service.execute_action(task, "protected-bulk-delete", "DELETE", "dcim/manufacturers/", body)
    assert denied["state"] == "failed" and denied["last_receipt"]["status"] in {400, 409}, denied
    assert all(service.api.get(f"dcim/manufacturers/{row['id']}/")["status"] == 200 for row in vendors)
    assert service.api.request("DELETE", f"dcim/device-types/{dtype['id']}/")["status"] == 204
    deleted = service.execute_action(task, "unprotected-bulk-delete", "DELETE", "dcim/manufacturers/", body)
    assert deleted["state"] == "applied", deleted
    assert len(deleted["native_changes"]) == 2
    assert all(
        service.api.request("GET", f"dcim/manufacturers/{row['id']}/")["status"] == 404 for row in vendors
    )
    replay = service.execute_action(task, "unprotected-bulk-delete", "DELETE", "dcim/manufacturers/", body)
    assert replay["id"] == deleted["id"]


def test_history_uses_immutable_evidence_without_live_object_expansion(graph):
    service, prefix, site, devices, make = graph
    rear = make("dcim/rear-ports/", {"device": devices[0], "name": "history-rear", "type": "8p8c"})
    front = make(
        "dcim/front-ports/",
        {
            "device": devices[0],
            "name": "history-front",
            "type": "8p8c",
            "rear_ports": [{"position": 1, "rear_port": rear["id"], "rear_port_position": 1}],
        },
    )
    peer = make("dcim/interfaces/", {"device": devices[1], "name": "history-peer", "type": "1000base-t"})
    make(
        "dcim/cables/",
        {
            "a_terminations": [{"object_type": "dcim.frontport", "object_id": front["id"]}],
            "b_terminations": [{"object_type": "dcim.interface", "object_id": peer["id"]}],
        },
    )
    task = service.begin_task("History evidence qualification")["task_id"]
    result = service.create_object(
        task, "history-site", "dcim/sites/", {"name": prefix + "-history", "slug": prefix + "-history"}
    )
    pk = result["last_receipt"]["body"]["id"]
    try:
        rows = service.api.history()
        row = next(row for row in rows if row["id"] == result["native_ids"][0])
        assert "changed_object" not in row and "user" not in row
        assert row["postchange_data"]["name"] == prefix + "-history"
        assert row["changed_object_id"] == pk and row["changed_object_type"] == "dcim.site"
        assert row["request_id"] == result["native_changes"][0]["request_id"]
        visible = service.get_changelogs({"changed_object_type": "dcim.portmapping"})["data"]["results"]
        assert any(item["postchange_data"].get("front_port") == front["id"] for item in visible)
        assert all("changed_object" not in item for item in visible)
    finally:
        assert service.api.request("DELETE", f"dcim/sites/{pk}/")["status"] == 204
