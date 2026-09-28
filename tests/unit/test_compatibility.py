import json

import pytest

from netbox_readwrite_mcp.compatibility import QUALIFIED_VERSIONS, normalization_profile
from netbox_readwrite_mcp.server import capabilities


@pytest.mark.parametrize("version", [*QUALIFIED_VERSIONS, "4.7.2", "4.7.100"])
def test_stable_version_write_and_exact_undo(service, edit, version):
    service.api.version = version
    before = service.read_device(1)["values"]
    op = edit({"description": "  B  ", "serial": " S ", "status": "planned"})
    assert op["state"] == "applied"
    intent = service.store.db.execute(
        "SELECT payload FROM events WHERE kind='normalized_intent' AND operation_id=?", (op["id"],)
    ).fetchone()
    intent = json.loads(intent[0])
    assert intent["netbox_version"] == version
    assert intent["profile"] == normalization_profile(version)
    assert service.undo_operation(op["id"], "compatibility-undo")["status"] == "applied"
    assert service.read_device(1)["values"] == before


@pytest.mark.parametrize(
    "version",
    [
        "4.6.9",
        "4.6.11",
        "4.8.0",
        "5.0.0",
        "4.7",
        "4.7.01",
        "4.7.-1",
        "4.7.1-dev",
        "4.7.0-beta2",
        "4.7.1+local",
        "4.7.1\n",
        "v4.7.1",
        "",
        None,
        {},
        [],
        True,
        4.7,
    ],
)
def test_unsupported_version_refused_before_dispatch(service, edit, version):
    service.api.version = version
    with pytest.raises(RuntimeError, match="Unsupported NetBox version.*stable 4.7.x"):
        edit()
    assert service.api.patches == 0
    assert service.store.db.execute("SELECT count(*) FROM operations").fetchone()[0] == 0


def test_capabilities_distinguish_acceptance_from_qualification():
    policy = capabilities()["netbox_versions"]
    assert "4.7.x" in policy["accepted"]
    assert policy["qualified"] == list(QUALIFIED_VERSIONS)
    assert "4.7.100" not in policy["qualified"]
