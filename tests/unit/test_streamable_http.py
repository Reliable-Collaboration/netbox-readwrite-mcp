import asyncio
import json
import threading
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
import pytest

from netbox_readwrite_mcp.http_server import create_server


@pytest.fixture
def http_mcp(tmp_path):
    token = tmp_path / "http-token"
    token.write_text("a" * 40)
    netbox_token = tmp_path / "netbox-token"
    netbox_token.write_text("b" * 40)
    config = {
        "netbox_url": "https://netbox.invalid",
        "actor": "test",
        "token_file": str(netbox_token),
        "journal": str(tmp_path / "journal.sqlite"),
        "instance_id": "test",
    }
    server = create_server(config, "127.0.0.1", 0, str(token))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/mcp"
    server.shutdown()
    server.server_close()
    thread.join()


def test_official_sdk_http_initialization_discovery_and_local_tools(http_mcp):
    async def run():
        async with httpx.AsyncClient(headers={"Authorization": "Bearer " + "a" * 40}) as http_client:
            async with streamable_http_client(http_mcp, http_client=http_client) as (read, write, _):
                async with ClientSession(read, write) as session:
                    initialized = await session.initialize()
                    assert "get_guidance" in initialized.instructions
                    guide = await session.call_tool("get_guidance", {})
                    assert "operation" in guide.structuredContent["instructions"]
                    tools = await session.list_tools()
                    assert "create_object" in [x.name for x in tools.tools]
                    cap = await session.call_tool("capabilities", {})
                    assert cap.structuredContent["netbox_versions"]["accepted"] == ">=4.7.0 (stable releases)"
                    task = await session.call_tool("begin_task", {"purpose": "HTTP SDK test"})
                    assert task.structuredContent["task_id"]
                    refused = await session.call_tool("begin_task", {})
                    assert refused.isError
                    reference = refused.structuredContent["diagnostic_reference"]
                    assert reference.startswith("event:")
                    assert json.loads(refused.content[0].text)["diagnostic_reference"] == reference

    asyncio.run(run())


@pytest.mark.parametrize(
    "headers,expected",
    [
        ({}, 401),
        ({"Authorization": "Bearer wrong"}, 401),
        ({"Authorization": "Bearer " + "a" * 40, "Origin": "https://evil.invalid"}, 403),
        ({"Authorization": "Bearer " + "a" * 40, "Origin": "https://[invalid"}, 403),
    ],
)
def test_http_rejects_missing_credentials_and_cross_origin(http_mcp, headers, expected):
    with pytest.raises(HTTPError) as error:
        urlopen(Request(http_mcp, data=b"{}", headers=headers))
    with error.value:
        assert error.value.code == expected


def test_http_session_and_protocol_errors(http_mcp):
    headers = {"Authorization": "Bearer " + "a" * 40, "Content-Type": "application/json"}

    def post(body, extra=None):
        return urlopen(
            Request(http_mcp, data=json.dumps(body).encode(), headers={**headers, **(extra or {})})
        )

    with pytest.raises(HTTPError) as exc:
        post({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    with exc.value:
        assert exc.value.code == 404
    response = post(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}}
    )
    session = response.headers["Mcp-Session-Id"]
    response.close()
    with pytest.raises(HTTPError) as exc:
        post(
            {"jsonrpc": "2.0", "id": 2, "method": "ping"},
            {"Mcp-Session-Id": session, "MCP-Protocol-Version": "bad"},
        )
    with exc.value:
        assert exc.value.code == 400
    with post({"jsonrpc": "2.0", "id": 3, "method": "missing"}, {"Mcp-Session-Id": session}) as response:
        assert json.load(response)["error"]["code"] == -32601


def test_idle_client_does_not_block_another_agent(http_mcp):
    import http.client
    from urllib.parse import urlsplit

    endpoint = urlsplit(http_mcp)
    first = http.client.HTTPConnection(endpoint.hostname, endpoint.port, timeout=3)
    second = http.client.HTTPConnection(endpoint.hostname, endpoint.port, timeout=3)
    headers = {"Authorization": "Bearer " + "a" * 40, "Content-Type": "application/json"}
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}}
    )
    try:
        first.request("POST", "/mcp", body, headers)
        response = first.getresponse()
        assert response.status == 200
        response.read()  # Keep the first authenticated connection idle and open.
        second.request("POST", "/mcp", body, headers)
        response = second.getresponse()
        assert response.status == 200
        response.read()
    finally:
        first.close()
        second.close()


def test_abandoned_sessions_expire_without_evicting_active_clients(http_mcp, monkeypatch):
    from types import SimpleNamespace
    from netbox_readwrite_mcp import http_server

    now = [0.0]
    monkeypatch.setattr(http_server, "time", SimpleNamespace(monotonic=lambda: now[0]))
    headers = {"Authorization": "Bearer " + "a" * 40}
    with httpx.Client(headers=headers) as client:

        def initialize():
            return client.post(
                http_mcp,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"protocolVersion": "2025-11-25"},
                },
            )

        sessions = [initialize().headers["Mcp-Session-Id"] for _ in range(128)]
        assert initialize().status_code == 503
        now[0] = http_server.SESSION_IDLE_SECONDS - 1

        def ping(session):
            return client.post(
                http_mcp,
                headers={"Mcp-Session-Id": session},
                json={"jsonrpc": "2.0", "id": 2, "method": "ping"},
            )

        assert ping(sessions[0]).status_code == 200
        now[0] += 2
        assert initialize().status_code == 200
        assert ping(sessions[0]).status_code == 200
        assert ping(sessions[1]).status_code == 404


@pytest.mark.parametrize(
    "method,path,extra,status",
    [
        ("POST", "/mcp", {"Content-Type": "text/plain"}, 415),
        ("POST", "/mcp", {"Content-Type": "application/json-invalid"}, 415),
        ("POST", "/mcp", {"Content-Type": "application/json", "Content-Length": "invalid"}, 400),
        ("POST", "/other", {"Content-Type": "application/json"}, 404),
        ("GET", "/mcp", {}, 405),
        ("DELETE", "/mcp", {}, 404),
    ],
)
def test_rejected_body_closes_connection_before_it_can_be_parsed_as_http(
    http_mcp, method, path, extra, status
):
    import http.client
    from urllib.parse import urlsplit

    endpoint = urlsplit(http_mcp)
    connection = http.client.HTTPConnection(endpoint.hostname, endpoint.port, timeout=3)
    try:
        connection.request(
            method,
            path,
            body=b"unconsumed request body",
            headers={
                "Authorization": "Bearer " + "a" * 40,
                **extra,
            },
        )
        response = connection.getresponse()
        assert response.status == status
        assert response.will_close
        response.read()
    finally:
        connection.close()
