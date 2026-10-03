"""Cold disposable REST startup may fail after the HTML health check succeeds."""

from types import SimpleNamespace

import pytest

from scripts import lab


def test_authenticated_readiness_retries_reads_only_and_stops_on_auth_failure(monkeypatch):
    calls = []
    responses = iter([500, 503, 200])
    monkeypatch.setattr(lab.time, "sleep", lambda delay: None)

    def request(method, path):
        calls.append((method, path))
        return {"status": next(responses)}

    api = SimpleNamespace(url=lab.URL, request=request)
    lab.ready_api(api)
    assert calls == [("GET", "dcim/sites/?limit=1")] * 3
    api.request = lambda *args: {"status": 403}
    with pytest.raises(RuntimeError, match="HTTP 403"):
        lab.ready_api(api)
    api.url = "https://production.invalid"
    with pytest.raises(ValueError, match="disposable"):
        lab.ready_api(api)


def test_readiness_has_a_deadline_without_fixture_writes(monkeypatch):
    clock = iter([0, 0, 2, 4])
    monkeypatch.setattr(lab.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(lab.time, "sleep", lambda delay: None)
    calls = []

    def request(method, path):
        calls.append(method)
        raise OSError("not ready")

    with pytest.raises(RuntimeError, match="no fixture writes"):
        lab.ready_api(SimpleNamespace(url=lab.URL, request=request), timeout=4)
    assert calls == ["GET", "GET"]
