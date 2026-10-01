"""Native administrative actions reachable through generic MCP API tools."""

import json
import os
import uuid

import pytest

from netbox_readwrite_mcp.server import build_service
from scripts.lab import STATE, URL
from tests.integration.test_configuration import shell

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("NETBOX_RW_LIVE") != "1", reason="Disposable lab opt-in required"),
]


def test_native_worker_name_with_at_and_plus(tmp_path):
    name = "qualification@host+" + uuid.uuid4().hex
    fixture = f"""
from django_rq.queues import get_redis_connection
from django_rq.settings import get_queues_list
from rq.worker import Worker
connection = get_redis_connection(get_queues_list()[0]['connection_config'])
worker = Worker([], connection=connection, name={name!r})
"""
    shell(fixture + "worker.register_birth()\n")
    cfg = json.loads((STATE / "broad-config.json").read_text())
    assert cfg["netbox_url"] == URL
    token = tmp_path / "token"
    token.write_text(json.loads((STATE / "secrets.json").read_text())["token"])
    token.chmod(0o600)
    cfg.update(token_file=str(token), actor="audit-admin", journal=str(tmp_path / "journal.sqlite"))
    service = build_service(cfg)
    try:
        response = service.query("core/background-workers/" + name + "/")
        assert response["status"] == 200
        assert response["body"]["name"] == name
        restricted = build_service(json.loads((STATE / "broad-config.json").read_text()))
        try:
            assert restricted.api.request("GET", "core/background-workers/" + name + "/")["status"] == 403
        finally:
            restricted.store.close()
    finally:
        service.store.close()
        shell(fixture + "worker.register_death()\n")
