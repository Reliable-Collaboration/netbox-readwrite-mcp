"""Route recovery must not redirect missing-object or permission failures."""

from contextlib import nullcontext
from types import SimpleNamespace

from netbox_readwrite_mcp.catalog import Catalog
from netbox_readwrite_mcp.server import error_result


def service():
    catalog = Catalog(None)  # Any network access while constructing hints would fail.
    catalog.schema = {
        "paths": {
            "/api/extras/bookmarks/": {"get": {}},
            "/api/extras/bookmarks/{id}/": {"get": {}},
            "/api/core/jobs/": {"get": {}},
            "/api/dcim/devices/{id}/": {"get": {}},
            "/api/hidden/bookmarks/": {"post": {}},
        }
    }
    store = SimpleNamespace(lock=nullcontext, event=lambda *args: None)
    return SimpleNamespace(catalog=catalog, store=store)


def test_bad_read_path_suggests_cached_collection_without_network_access():
    s = service()
    result = error_result(
        s,
        {"name": "query", "arguments": {"path": "core/bookmarks/bookmark/bookmark/"}},
        RuntimeError("Read failed: HTTP 404"),
    )["structuredContent"]
    assert result["candidate_paths"] == ["extras/bookmarks/", "extras/bookmarks/{id}/"]
    assert result["mutation_outcome"] == "not_applicable"
    assert result["automatic_retry_allowed"] is False
    assert "receipt_lookup" not in result


def test_missing_object_has_no_alternative_object_suggestion():
    result = error_result(
        service(),
        {"name": "query", "arguments": {"path": "dcim/devices/999999/"}},
        RuntimeError("Read failed: HTTP 404"),
    )["structuredContent"]
    assert "candidate_paths" not in result
    assert "absent or hidden by permissions" in result["action"]


def test_permission_failure_does_not_suggest_another_route():
    result = error_result(
        service(),
        {"name": "query", "arguments": {"path": "core/bookmarks/"}},
        RuntimeError("Read failed: HTTP 403"),
    )["structuredContent"]
    assert "candidate_paths" not in result


def test_write_failure_keeps_recovery_semantics():
    result = error_result(
        service(),
        {"name": "execute_action", "arguments": {"path": "core/bookmarks/"}},
        RuntimeError("HTTP 404"),
    )["structuredContent"]
    assert "candidate_paths" not in result
    assert result["mutation_outcome"] == "inspect_durable_receipt"


def test_hints_are_bounded_and_do_not_load_schema():
    s = service()
    s.catalog.schema = {"paths": {f"/api/app{n}/bookmarks/": {"get": {}} for n in range(20)}}
    assert len(s.catalog.route_hints("wrong/bookmarks/")) == 5
    s.catalog.schema = None
    assert s.catalog.route_hints("wrong/bookmarks/") == []
