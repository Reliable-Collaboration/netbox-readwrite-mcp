"""Exercise snapshot storage I/O, replacement, expiration and isolation without NetBox."""

import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest


@pytest.fixture
def downloads(monkeypatch):
    values, reads, timeouts = {}, [], []

    def get(key):
        value = values.get(key)
        reads.append(len(value.get("raw", b"")) if value else 0)
        return value

    def set_value(key, value, timeout):
        values[key] = value
        timeouts.append(timeout)

    cache = SimpleNamespace(get=get, set=set_value)
    conf = ModuleType("django.conf")
    conf.settings = SimpleNamespace(PLUGINS_CONFIG={})
    core_exceptions = ModuleType("django.core.exceptions")
    core_exceptions.ImproperlyConfigured = type("ImproperlyConfigured", (Exception,), {})
    monkeypatch.setitem(sys.modules, "django.conf", conf)
    monkeypatch.setitem(sys.modules, "django.core.exceptions", core_exceptions)
    cache_module = ModuleType("django.core.cache")
    cache_module.cache = cache
    exceptions = ModuleType("rest_framework.exceptions")
    exceptions.APIException = type("APIException", (Exception,), {})
    monkeypatch.setitem(sys.modules, "django.core.cache", cache_module)
    monkeypatch.setitem(sys.modules, "rest_framework.exceptions", exceptions)
    path = Path(__file__).resolve().parents[2] / "companion/netbox_agent_api/api/downloads.py"
    spec = importlib.util.spec_from_file_location("download_snapshot_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, values, reads, timeouts


def test_ranges_render_once_and_read_only_intersecting_blocks(downloads):
    mod, values, reads, timeouts = downloads
    raw = bytes(range(256)) * 1024
    produced = []

    def produce():
        produced.append(True)
        return raw, {"filename": "synthetic"}

    user = SimpleNamespace(pk=1)
    first = mod.snapshot(user, "media", {"revision": 1}, None, produce, 0, 16384)
    output = first["chunk"]
    reads.clear()
    for offset in range(16384, len(raw), 16384):
        output += mod.snapshot(user, "media", {"revision": 1}, first["sha256"], produce, offset, 16384)[
            "chunk"
        ]
    assert output == raw and len(produced) == 1
    assert max(reads) <= mod.BLOCK and sum(reads) < len(raw) * 4
    assert all(t == mod.TTL for t in timeouts)
    assert sum(len(v.get("raw", b"")) for v in values.values()) == len(raw)
    mod.snapshot(SimpleNamespace(pk=2), "media", {"revision": 1}, first["sha256"], produce)
    assert len(produced) == 2
    mod.snapshot(user, "media", {"revision": 2}, first["sha256"], produce)
    assert len(produced) == 3


def test_missing_or_replaced_blocks_fail_instead_of_mixing(downloads):
    mod, values, _, _ = downloads
    user = SimpleNamespace(pk=1)

    def produce():
        return b"a" * (mod.BLOCK + 2), {}

    first = mod.snapshot(user, "export", {}, None, produce)
    block_key = "netbox-agent-download-v1:export:1:1"
    values[block_key]["generation"] = "different"
    with pytest.raises(mod.SnapshotChanged):
        mod.snapshot(user, "export", {}, first["sha256"], produce, mod.BLOCK, 2)
    del values[block_key]
    with pytest.raises(mod.SnapshotChanged):
        mod.snapshot(user, "export", {}, first["sha256"], produce, mod.BLOCK, 2)


def test_snapshot_slots_and_initial_read_are_bounded(downloads):
    mod, values, _, _ = downloads
    mod.MAX_BYTES = 8
    with pytest.raises(mod.DownloadTooLarge):
        mod.bounded_bytes([b"1234", b"56789"])
    with pytest.raises(mod.DownloadTooLarge):
        mod.snapshot(SimpleNamespace(pk=1), "media", {}, None, lambda: (b"123456789", {}))
    assert not values
