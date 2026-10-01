import asyncio
import json
import subprocess
import sys
import pytest
from netbox_readwrite_mcp.config import load_config, validate_config
from netbox_readwrite_mcp.server import call, error_result, TOOLS
from netbox_readwrite_mcp.api import NetBox, NoRedirect


@pytest.fixture
def config(tmp_path):
    token = tmp_path / "token"
    token.write_text("test-token-never-sent")
    return {
        "netbox_url": "https://netbox.invalid",
        "token_file": str(token),
        "journal": str(tmp_path / "journal.sqlite"),
        "instance_id": "test-lineage",
        "actor": "agent",
        "allowed_device_ids": [1, 2],
    }


@pytest.mark.parametrize(
    "url",
    [
        "http://production.example",
        "ftp://netbox.example",
        "https://user:pass@netbox.example",
        "https://netbox.example?query=1",
        "https://netbox.example#fragment",
        "https://netbox.example/api/",
    ],
)
def test_unsafe_configuration_url(config, url):
    with pytest.raises(ValueError):
        validate_config({**config, "netbox_url": url})


@pytest.mark.parametrize("ids", [[], [True], [0], [-1], [1, 1], ["1"], None, "all"])
def test_configuration_scope_is_explicit(config, ids):
    with pytest.raises(ValueError):
        validate_config({**config, "allowed_device_ids": ids})


def test_config_relative_paths_and_typos(config, tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({**config, "token_file": "token", "journal": "journal.sqlite"}))
    assert load_config(path)["token_file"] == str(tmp_path / "token")
    with pytest.raises(ValueError, match="exactly"):
        validate_config({**config, "allow_everything": True})
    with pytest.raises(ValueError, match="different files"):
        validate_config({**config, "journal": config["token_file"]})


@pytest.mark.parametrize(
    "url", ["http://127.0.0.1:18790", "http://[::1]:18790", "https://netbox.example/netbox"]
)
def test_safe_urls(config, url):
    assert validate_config({**config, "netbox_url": url})["netbox_url"] == url


@pytest.mark.parametrize(
    "tool,args",
    [
        ("delete_device", {"device_id": 1}),
        ("create_device", {}),
        ("bulk_update", {}),
        ("raw_request", {"method": "POST"}),
        ("update_device", {"force": True}),
        ("read_device", {"device_id": True}),
        ("read_device", {"device_id": -1}),
        ("read_device", {"device_id": "1"}),
        ("read_device", {"device_id": 1, "extra": 1}),
        ("begin_task", {"purpose": None}),
        ("capabilities", []),
    ],
)
def test_mcp_schema_refusals(service, tool, args):
    with pytest.raises(ValueError):
        call(service, tool, args)
    assert service.api.patches == 0


@pytest.mark.parametrize(
    "text,code",
    [
        ("Stale expected_etag", "STALE_STATE"),
        ("Idempotency key reused", "KEY_REUSED"),
        ("Unsupported edit", "UNSUPPORTED_EDIT"),
        ("Device is outside the configured allowlist", "OUT_OF_SCOPE"),
        ("Device has unresolved operations", "UNRESOLVED_OPERATION"),
        ("Native history missing", "HISTORY_UNAVAILABLE"),
        ("projection mismatch", "INTEGRITY_FAILURE"),
    ],
)
def test_error_guidance_is_structured(service, text, code):
    result = error_result(service, {"name": "update_device", "arguments": {}}, ValueError(text))
    assert result["isError"]
    out = result["structuredContent"]
    assert out["code"] == code
    assert out["action"] and out["warning"]
    assert out["automatic_retry_allowed"] is False


def test_exception_after_commit_contains_durable_lookup(service, edit):
    edit()
    out = error_result(
        service,
        {"name": "update_device", "arguments": {"operation_key": "test-edit-0001"}},
        OSError("response delivery failed"),
    )["structuredContent"]
    assert out["receipt_lookup"]["operation"]["state"] == "applied"
    assert out["mutation_outcome"] == "inspect_durable_receipt"


def test_tools_have_honest_annotations():
    tools = {t["name"]: t for t in TOOLS}
    assert tools["update_device"]["annotations"]["destructiveHint"]
    assert not tools["preview_undo"]["annotations"]["readOnlyHint"]
    assert tools["get_operation"]["annotations"]["readOnlyHint"]


def run_protocol(config, tmp_path, lines):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    process = subprocess.run(
        [sys.executable, "-m", "netbox_readwrite_mcp", "--config", str(path)],
        input=lines,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert process.returncode == 0, process.stderr
    return [json.loads(line) for line in process.stdout.splitlines()]


@pytest.mark.parametrize(
    "wire_request,code",
    [
        ("{bad json}\n", -32700),
        ("[]\n", -32600),
        ('{"jsonrpc":"2.0","id":true,"method":"ping"}\n', -32600),
        ('{"jsonrpc":"2.0","id":1,"method":"ping","params":[]}\n', -32602),
        ('{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n', -32000),
    ],
)
def test_protocol_errors_are_json_rpc(config, tmp_path, wire_request, code):
    assert run_protocol(config, tmp_path, wire_request)[0]["error"]["code"] == code


def test_oversized_request_closes_without_processing_remainder(config, tmp_path):
    rows = run_protocol(
        config,
        tmp_path,
        "x" * (1024 * 1024 + 1) + "\n" + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "ping"}) + "\n",
    )
    assert len(rows) == 1
    assert rows[0]["error"]["code"] == -32600


def test_official_mcp_sdk_interoperability(config, tmp_path):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))

    async def exercise():
        args = StdioServerParameters(
            command=sys.executable, args=["-m", "netbox_readwrite_mcp", "--config", str(path)]
        )
        async with stdio_client(args) as (read, write):
            async with ClientSession(read, write) as session:
                info = await session.initialize()
                assert info.serverInfo.name == "netbox-readwrite-mcp"
                listed = await session.list_tools()
                assert "undo_operation" in {tool.name for tool in listed.tools}
                result = await session.call_tool("begin_task", {"purpose": "SDK interoperability"})
                assert result.structuredContent["task_id"]
                refused = await session.call_tool("delete_device", {"device_id": 1})
                assert refused.isError
                assert refused.structuredContent["action"]
                capabilities = await session.call_tool("capabilities", {})
                assert capabilities.structuredContent["approval_required"] is False

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "path", ["/api/dcim/devices/", "../secret", "https://evil.invalid", "//evil.invalid"]
)
def test_transport_refuses_unsafe_paths(path):
    api = NetBox("https://netbox.invalid", "test-token")
    with pytest.raises(ValueError):
        api.get(path)


def test_transport_rejects_redirects_and_header_injection():
    assert NoRedirect().redirect_request(None, None, None, None, None, None) is None
    with pytest.raises(ValueError):
        NetBox("https://netbox.invalid", "token\r\nInjected: value")


def test_history_refuses_cross_origin_pagination_and_loops():
    api = NetBox("https://netbox.invalid", "test-token")
    api.get = lambda path: {"body": {"results": [], "next": "https://evil.invalid/api/?x=1"}}
    with pytest.raises(RuntimeError, match="origin"):
        api.history()
    api.get = lambda path: {"body": {"results": [], "next": api.url + "/api/" + path}}
    with pytest.raises(RuntimeError, match="Repeated"):
        api.history()


def test_cli_backup_export_and_no_overwrite(config, tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    command = [sys.executable, "-m", "netbox_readwrite_mcp", "--config", str(path)]
    subprocess.run(command + ["--backup", str(tmp_path / "backup.sqlite")], check=True, capture_output=True)
    subprocess.run(command + ["--export", str(tmp_path / "export.json")], check=True, capture_output=True)
    assert (tmp_path / "export.json.sha256").exists()
    assert json.loads((tmp_path / "export.json").read_text())["operations"] == []
    assert (
        subprocess.run(command + ["--export", str(tmp_path / "export.json")], capture_output=True).returncode
        != 0
    )


@pytest.mark.parametrize("version", [{}, [], None, True, 1, ""])
def test_bad_initialize_does_not_crash_or_initialize(config, tmp_path, version):
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": version}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/list"},
    ]
    rows = run_protocol(config, tmp_path, "".join(json.dumps(row) + "\n" for row in requests))
    assert rows[0]["error"]["code"] == -32602
    assert rows[1]["error"]["code"] == -32000
    assert rows[2]["result"]["protocolVersion"] == "2025-11-25"
    assert rows[3]["result"]["tools"]


def test_excessive_nesting_returns_error_and_allows_next_request(config, tmp_path):
    wire = "[" * 2000 + "0" + "]" * 2000 + "\n"
    wire += json.dumps({"jsonrpc": "2.0", "id": 2, "method": "ping"}) + "\n"
    rows = run_protocol(config, tmp_path, wire)
    assert rows[0]["error"]["code"] == -32700
    assert rows[1]["result"] == {}


def test_bad_tool_arguments_do_not_claim_storage_outage(service):
    result = error_result(service, {"name": "read_device", "arguments": []}, ValueError("Invalid arguments"))
    assert "journal_available" not in result["structuredContent"]
    assert service.observability()["event_counts"]["tool_refused"] == 1


def test_catalog_accepts_native_worker_names_without_accepting_external_paths():
    from netbox_readwrite_mcp.catalog import api_path

    path = "core/background-workers/worker@host+1/"
    assert api_path(path) == path
    for unsafe in [
        "https://user@evil.invalid/",
        "//user@evil.invalid/",
        "../worker@host/",
        "core/workers/x?y=1/",
    ]:
        with pytest.raises(ValueError):
            api_path(unsafe)
