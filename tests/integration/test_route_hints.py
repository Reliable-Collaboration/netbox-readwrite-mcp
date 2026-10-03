"""Recover wrong routes using the real NetBox schema without changing inventory."""

import json
import os

import pytest

from netbox_readwrite_mcp.server import build_service, call, error_result
from scripts.lab import STATE, URL

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("NETBOX_RW_LIVE") != "1", reason="Disposable lab opt-in required"),
]


def test_real_bookmark_route_hint_and_missing_device_are_distinct(tmp_path):
    config = json.loads((STATE / "broad-config.json").read_text())
    assert config["netbox_url"] == URL
    config["journal"] = str(tmp_path / "read-hints.sqlite")
    service = build_service(config)
    try:
        service.catalog.load_schema()
        assert call(service, "query", {"path": "dcim/sites", "filters": {"limit": 1}})["status"] == 200
        schema = call(service, "get_schema", {"object_type": "core/bookmarks/"})
        assert schema["candidate_paths"][0] == "extras/bookmarks/"
        args = {"path": "core/bookmarks/bookmark/bookmark/"}
        with pytest.raises(RuntimeError, match="HTTP 404") as exc:
            call(service, "query", args)
        response = error_result(service, {"name": "query", "arguments": args}, exc.value)["structuredContent"]
        assert response["candidate_paths"][0] == "extras/bookmarks/"
        assert response["mutation_outcome"] == "not_applicable"
        assert call(service, "query", {"path": response["candidate_paths"][0]})["status"] == 200
        args = {"path": "dcim/devices/2147483647/"}
        with pytest.raises(RuntimeError, match="HTTP 404") as exc:
            call(service, "query", args)
        response = error_result(service, {"name": "query", "arguments": args}, exc.value)["structuredContent"]
        assert "candidate_paths" not in response
        assert service.store.db.execute("SELECT count(*) FROM resource_operations").fetchone()[0] == 0
    finally:
        service.store.close()
