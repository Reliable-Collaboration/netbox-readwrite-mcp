"""Native nested type imports, related permissions and atomic malformed-child rejection."""

import json
import os

import pytest

from tests.integration.test_imports import importer  # noqa: F401
from tests.integration.test_patterns import parents  # noqa: F401
from tests.integration.test_personal import people  # noqa: F401
from tests.integration.test_configuration import shell

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("NETBOX_RW_LIVE") != "1", reason="Disposable lab opt-in required"),
]
ROOT = "plugins/agent-support/imports/"


@pytest.mark.parametrize("delimiter,value", [(",", ","), (";", ";"), ("|", "|"), ("\t", "\t")])
def test_native_explicit_csv_delimiters(importer, delimiter, value):  # noqa: F811
    service, prefix = importer
    body = {
        "format": "csv",
        "csv_delimiter": value,
        "data": delimiter.join(["name", "slug", "status"])
        + "\n"
        + delimiter.join([prefix, prefix, "active"])
        + "\n",
    }
    result = service.api.request("POST", ROOT + "dcim.site/", body)
    assert result["status"] == 200, result
    assert service.api.get(f"dcim/sites/{result['body']['ids'][0]}/")["body"]["slug"] == prefix


@pytest.mark.parametrize("model,resource", [("devicetype", "device-types"), ("moduletype", "module-types")])
def test_nested_type_import_native_hooks_and_atomic_rejection(parents, model, resource):  # noqa: F811
    service, prefix, ids = parents
    dtype = service.api.get(f"dcim/device-types/{ids['device_type']}/")["body"]
    values = {
        "manufacturer": dtype["manufacturer"]["name"],
        "model": prefix + "-nested",
        "interfaces": [{"name": "eth1", "type": "1000base-t"}, {"name": "eth2", "type": "1000base-t"}],
    }
    if model == "devicetype":
        values["slug"] = prefix + "-nested"
        values["u_height"] = 1
    path = ROOT + "dcim." + model + "/"
    try:
        for bad in [
            "not-a-list",
            ["not-an-object"],
            [{"name": "eth1", "type": "invalid"}],
            [{"name": "eth1", "type": "1000base-t", "typo": "reject"}],
        ]:
            result = service.api.request(
                "POST", path, {"format": "json", "data": json.dumps({**values, "interfaces": bad})}
            )
            assert result["status"] == 400, result
            assert service.api.get(f"dcim/{resource}/?model={values['model']}")["body"]["count"] == 0
        task = service.begin_task("Nested native type import")["task_id"]
        result = service.execute_action(
            task, "nested-type-import", "POST", path, {"format": "json", "data": json.dumps(values)}
        )
        assert result["state"] == "applied", result
        pk = result["last_receipt"]["body"]["ids"][0]
        parent = "device_type" if model == "devicetype" else "module_type"
        children = service.api.get(f"dcim/interface-templates/?{parent}_id={pk}")["body"]["results"]
        assert {row["name"] for row in children} == {"eth1", "eth2"}
        assert all(row[parent]["id"] == pk for row in children)
        assert len(result["native_changes"]) == 3, result
    finally:
        shell(f"""
from dcim.models import DeviceType, ModuleType
for cls in (DeviceType, ModuleType):
    cls.objects.filter(model={values["model"]!r}).delete()
""")


def test_nested_import_enforces_related_object_add_constraints(parents, people):  # noqa: F811
    service, prefix, ids = parents
    actor = people[0][0]
    dtype = service.api.get(f"dcim/device-types/{ids['device_type']}/")["body"]
    shell(f"""
from users.models import ObjectPermission
from core.models import ObjectType
from django.contrib.auth import get_user_model
user = get_user_model().objects.get(username={actor.actor!r})
p = ObjectPermission.objects.get(name={actor.actor!r})
p.object_types.add(*ObjectType.objects.filter(app_label='dcim'))
for suffix, types, constraints in [
    ('-add', ObjectType.objects.filter(app_label='dcim').exclude(model='interfacetemplate'), {{}}),
    ('-templates', ObjectType.objects.filter(app_label='dcim', model='interfacetemplate'), {{'name__startswith': 'allowed-'}}),
]:
    p = ObjectPermission.objects.create(name={actor.actor!r}+suffix, actions=['add'], constraints=constraints)
    p.users.add(user)
    p.object_types.set(types)
""")
    values = {
        "manufacturer": dtype["manufacturer"]["name"],
        "model": prefix + "-forbidden",
        "slug": prefix + "-forbidden",
        "u_height": 1,
        "interfaces": [
            {"name": "allowed-one", "type": "1000base-t"},
            {"name": "forbidden-two", "type": "1000base-t"},
        ],
    }
    result = actor.api.request(
        "POST", ROOT + "dcim.devicetype/", {"format": "json", "data": json.dumps(values)}
    )
    assert result["status"] == 403, result
    assert service.api.get(f"dcim/device-types/?slug={values['slug']}")["body"]["count"] == 0
