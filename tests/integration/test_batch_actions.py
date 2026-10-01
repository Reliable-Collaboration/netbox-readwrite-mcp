"""Native atomic disconnect and data synchronization in the real lab."""

import json
import os
import time

import pytest

from tests.integration.test_imports import importer  # noqa: F401
from tests.integration.test_administration import queue_admin  # noqa: F401
from tests.integration.test_configuration import shell

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("NETBOX_RW_LIVE") != "1", reason="Disposable lab opt-in required"),
]
ROOT = "plugins/agent-support/"


def create(service, resource, data):
    result = service.api.request("POST", resource, data)
    assert result["status"] == 201, result
    return result["body"]


@pytest.fixture
def cabling(importer):  # noqa: F811
    service, prefix = importer
    try:
        site = create(service, "dcim/sites/", {"name": prefix, "slug": prefix})
        role = create(service, "dcim/device-roles/", {"name": prefix, "slug": prefix})
        vendor = create(service, "dcim/manufacturers/", {"name": prefix, "slug": prefix})
        dtype = create(
            service, "dcim/device-types/", {"manufacturer": vendor["id"], "model": prefix, "slug": prefix}
        )
        devices = [
            create(
                service,
                "dcim/devices/",
                {"name": prefix + str(i), "site": site["id"], "role": role["id"], "device_type": dtype["id"]},
            )
            for i in range(2)
        ]
        yield service, prefix, site["id"], [d["id"] for d in devices]
    finally:
        shell(f"""
from dcim.models import Cable, Device, DeviceType, DeviceRole, Manufacturer, PowerPanel, PowerFeed
Cable.objects.filter(label={prefix!r}).delete()
Device.objects.filter(name__startswith={prefix!r}).delete()
PowerFeed.objects.filter(power_panel__name={prefix!r}).delete()
PowerPanel.objects.filter(name={prefix!r}).delete()
DeviceType.objects.filter(slug={prefix!r}).delete()
DeviceRole.objects.filter(slug={prefix!r}).delete()
Manufacturer.objects.filter(slug={prefix!r}).delete()
""")


@pytest.mark.parametrize(
    "component",
    [
        "consoleport",
        "consoleserverport",
        "interface",
        "frontport",
        "rearport",
        "powerport",
        "poweroutlet",
        "powerfeed",
    ],
)
def test_all_native_bulk_disconnect_types(cabling, component):
    service, prefix, site, devices = cabling
    resources = {
        "consoleport": "console-ports",
        "consoleserverport": "console-server-ports",
        "interface": "interfaces",
        "frontport": "front-ports",
        "rearport": "rear-ports",
        "powerport": "power-ports",
        "poweroutlet": "power-outlets",
        "powerfeed": "power-feeds",
    }

    def termination(kind, device):
        values = {"name": kind, "device": device}
        if kind == "interface":
            values["type"] = "1000base-t"
        elif kind in {"frontport", "rearport"}:
            values["type"] = "8p8c"
            if kind == "frontport":
                rear = create(
                    service, "dcim/rear-ports/", {"device": device, "name": "rear-for-front", "type": "8p8c"}
                )
                values["rear_ports"] = [{"position": 1, "rear_port": rear["id"], "rear_port_position": 1}]
        elif kind == "powerfeed":
            panel = create(service, "dcim/power-panels/", {"name": prefix, "site": site})
            values = {"name": kind, "power_panel": panel["id"]}
        result = create(service, "dcim/" + resources[kind] + "/", values)
        return {"object_type": "dcim." + kind, "object_id": result["id"]}

    peer = {
        "consoleport": "consoleserverport",
        "consoleserverport": "consoleport",
        "powerport": "poweroutlet",
        "poweroutlet": "powerport",
        "powerfeed": "powerport",
    }.get(component, "interface")
    a, b = termination(component, devices[0]), termination(peer, devices[1])
    cable = create(
        service,
        "dcim/cables/",
        {"a_terminations": [a], "b_terminations": [b], "status": "connected", "label": prefix},
    )
    path = ROOT + "bulk-disconnect/dcim." + component + "/"
    body = {"ids": [a["object_id"]]}
    task = service.begin_task("Disconnect qualification")["task_id"]
    preview = service.execute_action(task, "disconnect-preview", "POST", path, body)
    assert preview["last_receipt"]["status"] == 200, preview
    assert preview["last_receipt"]["body"]["cable_ids"] == [cable["id"]]
    assert service.api.request("POST", path, {**body, "apply": True, "expected": {}})["status"] == 409
    applied = service.execute_action(
        task,
        "disconnect-apply",
        "POST",
        path,
        {**body, "apply": True, "expected": preview["last_receipt"]["body"]["expected"]},
    )
    assert applied["state"] == "applied", applied
    assert service.api.request("GET", f"dcim/cables/{cable['id']}/")["status"] == 404
    assert service.query("dcim/" + resources[component] + f"/{a['object_id']}/")["body"]["cable"] is None


def sync_source(service, pk):
    result = service.api.request("POST", f"core/data-sources/{pk}/sync/", {})
    assert result["status"] == 200, result
    deadline = time.monotonic() + 45
    while True:
        body = service.query(f"core/data-sources/{pk}/")["body"]
        if body["status"]["value"] in {"completed", "failed"} or time.monotonic() > deadline:
            break
        time.sleep(0.25)
    assert body["status"]["value"] == "completed", body


@pytest.fixture
def data_source(importer):  # noqa: F811
    service, prefix = importer
    directory = "/opt/netbox/netbox/scripts/qualification-data-" + prefix
    shell(f"""
from pathlib import Path
p = Path({directory!r})
p.mkdir()
(p / 'data.json').write_text('{{"type":"object", "description":"initial"}}')
""")
    try:
        source = create(
            service, "core/data-sources/", {"name": prefix, "type": "local", "source_url": directory}
        )
        sync_source(service, source["id"])
        files = service.api.get(f"core/data-files/?source_id={source['id']}")["body"]["results"]
        assert len(files) == 1
        yield service, prefix, source["id"], files[0]["id"], directory
    finally:
        shell(f"""
from extras.models import ConfigContext, ConfigContextProfile, ConfigTemplate, ExportTemplate
from core.models import DataSource
import shutil
for model in (ConfigContext, ConfigContextProfile, ConfigTemplate, ExportTemplate):
    model.objects.filter(name__startswith={prefix!r}).delete()
DataSource.objects.filter(name={prefix!r}).delete()
shutil.rmtree({directory!r})
""")


@pytest.mark.parametrize(
    "model,resource,field",
    [
        ("configcontext", "config-contexts", "data"),
        ("configcontextprofile", "config-context-profiles", "schema"),
        ("configtemplate", "config-templates", "template_code"),
        ("exporttemplate", "export-templates", "template_code"),
    ],
)
def test_native_source_worker_and_bulk_sync(data_source, model, resource, field):
    service, prefix, source_id, file_id, directory = data_source
    data = {
        "name": prefix,
        "data_file": file_id,
        field: {"type": "object"} if field in {"data", "schema"} else "initial",
    }
    if model == "exporttemplate":
        data["object_types"] = ["dcim.site"]
    obj = create(service, "extras/" + resource + "/", data)
    path = ROOT + "bulk-sync/extras." + model + "/"
    body = {"ids": [obj["id"]]}
    preview = service.api.request("POST", path, body)
    assert preview["status"] == 200, preview
    updated = '{"type":"object", "description":"updated"}'
    shell(f"""
from pathlib import Path
Path({directory!r}, 'data.json').write_text({updated!r})
""")
    sync_source(service, source_id)
    assert (
        service.api.request("POST", path, {**body, "apply": True, "expected": preview["body"]["expected"]})[
            "status"
        ]
        == 409
    )
    before = service.query(f"extras/{resource}/{obj['id']}/")["body"][field]
    preview = service.api.request("POST", path, body)
    task = service.begin_task("Bulk native synchronization")["task_id"]
    applied = service.execute_action(
        task,
        "sync-batch-apply",
        "POST",
        path,
        {**body, "apply": True, "expected": preview["body"]["expected"]},
    )
    assert applied["state"] == "applied", applied
    actual = service.query(f"extras/{resource}/{obj['id']}/")["body"][field]
    assert actual != before and actual == (json.loads(updated) if field in {"data", "schema"} else updated)


def test_bulk_sync_invalid_second_file_rolls_back_first(data_source):
    service, prefix, source_id, file_id, directory = data_source
    shell(f"""
from pathlib import Path
Path({directory!r}, 'second.yaml').write_text('description: initial second')
""")
    sync_source(service, source_id)
    files = service.api.get(f"core/data-files/?source_id={source_id}")["body"]["results"]
    objects = [
        create(
            service,
            "extras/config-contexts/",
            {"name": prefix + str(i), "data_file": row["id"], "data": {"initial": True}},
        )
        for i, row in enumerate(files)
    ]
    shell(f"""
from pathlib import Path
Path({directory!r}, 'data.json').write_text('{{"description":"new first"}}')
Path({directory!r}, 'second.yaml').write_text('broken: [')
""")
    sync_source(service, source_id)
    path = ROOT + "bulk-sync/extras.configcontext/"
    ids = [obj["id"] for obj in objects]
    before = [service.api.get(f"extras/config-contexts/{pk}/")["body"] for pk in ids]
    preview = service.api.request("POST", path, {"ids": ids})
    assert preview["status"] == 200, preview
    result = service.api.request(
        "POST", path, {"ids": ids, "apply": True, "expected": preview["body"]["expected"]}
    )
    assert result["status"] == 400, result
    after = [service.api.get(f"extras/config-contexts/{pk}/")["body"] for pk in ids]
    assert before == after
