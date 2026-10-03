"""Failure cleanup, credential intent protection and prefixed website requests."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from netbox_readwrite_mcp.intent import fingerprint, matches
from netbox_readwrite_mcp.setup import configure
from netbox_readwrite_mcp.store import digest
from netbox_readwrite_mcp.web import Website
from tests.unit.test_workspace import broad  # noqa: F401


@pytest.mark.parametrize(
    "filename,stage",
    [("config.json", "write"), ("config.json", "close"), ("token", "write"), ("token", "close")],
)
def test_setup_cleans_only_new_files_including_buffered_close(tmp_path, monkeypatch, filename, stage):
    target = tmp_path / "private" / "config.json"
    original = Path.open

    class BrokenOutput:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def write(self, value):
            if stage == "write":
                raise OSError("synthetic write failure")
            return self.stream.write(value)

        def __exit__(self, *args):
            result = self.stream.__exit__(*args)
            if stage == "close":
                raise OSError("synthetic buffered close failure")
            return result

    def opening(path, *args, **kwargs):
        stream = original(path, *args, **kwargs)
        return BrokenOutput(stream) if path.name == filename else stream

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", opening)
        with pytest.raises(OSError, match="synthetic"):
            configure(target, "https://netbox.example", "inventory", "synthetic-token")
    assert not target.exists() and not (target.parent / "token").exists()
    configure(target, "https://netbox.example", "inventory", "synthetic-token")
    assert target.exists()


def test_prefixed_origin_retains_port_but_not_path():
    requests = []

    class Captured(Exception):
        pass

    def capture(request, **kwargs):
        requests.append(request)
        raise Captured

    site = Website(SimpleNamespace(url="https://netbox.example:8443/netbox"), "inventory", None)
    site.opener = SimpleNamespace(open=capture)
    with pytest.raises(Captured):
        site.request("/login/", {"username": "inventory"})
    assert requests[0].get_header("Origin") == "https://netbox.example:8443"
    assert requests[0].get_header("Referer") == "https://netbox.example:8443/netbox/login/"


def test_intent_fingerprints_are_slow_salted_and_replay_exactly():
    value = {"old_password": "old", "new_password1": "new"}
    first, second = fingerprint(value), fingerprint(value)
    assert first.startswith("scrypt-v1:") and first != second
    assert first != digest(value)
    assert matches(value, first)
    assert not matches({**value, "new_password1": "changed"}, first)
    assert matches(value, digest(value))  # Existing immutable journal compatibility.


def test_password_workflow_protects_all_persisted_intent_layers(broad, monkeypatch):  # noqa: F811
    import json

    path = "plugins/agent-support/self/password/"
    calls = []

    def request(method, target, data=None, *args, **kwargs):
        calls.append(data)
        return {"status": 200, "body": {"changed": True}, "headers": {}}

    monkeypatch.setattr(broad.api, "request", request)
    payload = {"old_password": "old-private", "new_password1": "new-private", "new_password2": "new-private"}
    code = f'result = tool("execute_action", method="POST", path={path!r}, data={payload!r})'
    first = broad.run_workflow(broad.task, "password-workflow", code)
    assert first["status"] == "completed", first
    assert broad.run_workflow(broad.task, "password-workflow", code) == first
    assert len(calls) == 1
    with pytest.raises(ValueError, match="different workflow"):
        broad.run_workflow(broad.task, "password-workflow", code.replace("new-private", "changed-private"))
    entries = [
        (row["kind"], json.loads(row["payload"]))
        for row in broad.store.db.execute("SELECT kind,payload FROM events")
    ]
    assert any(
        kind == "workflow_started" and row["code_hash"].startswith("scrypt-v1:") for kind, row in entries
    )
    assert any(
        kind == "workflow_step" and row["fingerprint"].startswith("scrypt-v1:") for kind, row in entries
    )
    op = broad.get_task(broad.task)["operations"][0]
    assert op["fingerprint"].startswith("scrypt-v1:")
    assert "old-private" not in json.dumps(entries) and "new-private" not in json.dumps(entries)


def test_native_user_passwords_are_redacted_without_changing_dispatch(broad, monkeypatch):  # noqa: F811
    import json

    sent = []

    def request(method, path, data=None, *args, **kwargs):
        sent.append(data)
        return {"status": 201, "body": {"id": 8, "username": "synthetic"}, "headers": {}}

    monkeypatch.setattr(broad.api, "request", request)
    data = [{"username": "synthetic", "password": "native-secret"}]
    op = broad.execute_action(broad.task, "native-user-password", "POST", "users/users/", data)
    assert sent == [data]
    assert op["requested"] == [{"username": "synthetic", "password": "[REDACTED]"}]
    assert "native-secret" not in json.dumps(
        [row[0] for row in broad.store.db.execute("SELECT payload FROM events")]
    )


@pytest.mark.parametrize("status", [413, 415, 428])
def test_definite_request_rejections_do_not_block_later_operations(broad, monkeypatch, status):  # noqa: F811
    responses = iter([status, 200])

    def request(method, path, data=None, *args, **kwargs):
        return {"status": next(responses), "body": {"detail": "synthetic rejection"}, "headers": {}}

    monkeypatch.setattr(broad.api, "request", request)
    first = broad.execute_action(
        broad.task, "definite-rejection", "POST", "plugins/agent-support/exports/dcim.site/", {}
    )
    assert first["state"] == "failed"
    second = broad.execute_action(
        broad.task, "corrected-request", "POST", "plugins/agent-support/exports/dcim.site/", {}
    )
    assert second["state"] == "completed"
