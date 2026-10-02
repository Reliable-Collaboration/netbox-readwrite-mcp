"""Failure detection must not turn client/provider failures into passing agent runs."""

import json
import pytest

from scripts.agent_clients import client_failed, used_host_tools, community_read_checks


@pytest.mark.parametrize(
    "event",
    [
        {"type": "error", "error": "provider failure"},
        {"type": "turn.failed", "error": {"message": "connection lost"}},
        {"type": "result", "is_error": True, "subtype": "error_during_execution"},
    ],
)
def test_client_failure_is_not_success(event):
    assert client_failed([{"type": "assistant"}, event])


def test_successful_result_is_not_failure():
    assert not client_failed([{"type": "result", "is_error": False}])


@pytest.mark.parametrize(
    "event",
    [
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash"}]}},
        {"type": "item.completed", "item": {"type": "command_execution"}},
        {"type": "item.completed", "item": {"type": "file_change"}},
        {"type": "item.completed", "item": {"type": "mcp_tool_call", "server": "other"}},
    ],
)
def test_host_tool_use_is_detected(event):
    assert used_host_tools([event])


def test_netbox_tool_calls_are_allowed():
    assert not used_host_tools(
        [
            {
                "type": "assistant",
                "message": {"content": [{"type": "tool_use", "name": "mcp__netbox__get_objects"}]},
            },
            {"type": "item.completed", "item": {"type": "mcp_tool_call", "server": "netbox"}},
        ]
    )


@pytest.mark.parametrize("client", ["claude", "codex", "opencode"])
def test_trace_requires_successful_response_for_own_cable(client):
    import json

    arguments = {"path": "dcim/interfaces/7/trace/"}
    payload = {"status": 200, "body": [{"label": "test-link"}]}

    def transcript(status, body):
        if client == "claude":
            return [
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {"type": "tool_use", "id": "q", "name": "mcp__netbox__query", "input": arguments}
                        ]
                    },
                },
                {
                    "type": "user",
                    "message": {
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "q",
                                "is_error": status != "completed",
                                "content": json.dumps(body),
                            }
                        ]
                    },
                },
            ]
        if client == "codex":
            return [
                {
                    "type": "item.completed",
                    "item": {
                        "type": "mcp_tool_call",
                        "server": "netbox",
                        "tool": "query",
                        "arguments": arguments,
                        "status": status,
                        "result": {"structured_content": body},
                    },
                }
            ]
        return [
            {
                "type": "tool_use",
                "part": {
                    "tool": "netbox_query",
                    "state": {"input": arguments, "status": status, "output": json.dumps(body)},
                },
            }
        ]

    assert community_read_checks(transcript("completed", payload), "test", [7])["native_trace_used"]
    assert not community_read_checks(transcript("failed", payload), "test", [7])["native_trace_used"]
    assert not community_read_checks(
        transcript("completed", {"status": 404, "body": "test-link"}), "test", [7]
    )["native_trace_used"]
    assert not community_read_checks(transcript("completed", payload), "other", [7])["native_trace_used"]
    assert not community_read_checks(transcript("completed", payload), "test", [8])["native_trace_used"]


def test_error_budget_requires_consecutive_failures_and_can_be_disabled():
    from scripts.agent_clients import consecutive_error_limit_reached

    failed = {"is_error": True}
    ok = {"is_error": False}
    assert consecutive_error_limit_reached([ok, failed, failed, failed], 3)
    assert not consecutive_error_limit_reached([failed, failed, ok, failed], 3)
    assert not consecutive_error_limit_reached([failed], 3)
    assert not consecutive_error_limit_reached([failed] * 20, 0)


def test_codex_evaluation_explicitly_disables_apps_plugins_and_hooks(tmp_path):
    import tomllib
    from pathlib import Path
    from scripts.agent_clients import native_command

    command = native_command(
        "codex", Path("/bin/codex"), ["python3", "server.pyz"], tmp_path, 14003, "Task", 60
    )
    settings = tomllib.loads("\n".join(command[i + 1] for i, value in enumerate(command) if value == "-c"))
    assert settings["features"]["apps"] is False
    assert settings["features"]["plugins"] is False
    assert settings["features"]["hooks"] is False
    assert settings["features"]["skip_host_skill_discovery"] is True
    assert set(settings["mcp_servers"]) == {"netbox"}
    assert "--ignore-user-config" in command and "--ephemeral" in command
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("client", ["claude", "codex", "opencode"])
def test_community_search_accepts_verified_get_objects_results(client):
    def transcript(payload, failed=False):
        args = {"object_type": "plugins/agent-support/search/", "filters": {"q": "test"}}
        if client == "claude":
            return [
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {"type": "tool_use", "name": "mcp__netbox__get_objects", "id": "a", "input": args}
                        ]
                    },
                },
                {
                    "type": "user",
                    "message": {
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "a",
                                "is_error": failed,
                                "content": json.dumps(payload),
                            }
                        ]
                    },
                },
            ]
        if client == "codex":
            return [
                {
                    "type": "item.completed",
                    "item": {
                        "type": "mcp_tool_call",
                        "server": "netbox",
                        "tool": "get_objects",
                        "arguments": args,
                        "status": "failed" if failed else "completed",
                        "result": {"structured_content": payload},
                    },
                }
            ]
        return [
            {
                "type": "tool_use",
                "part": {
                    "tool": "netbox_get_objects",
                    "state": {
                        "status": "error" if failed else "completed",
                        "input": args,
                        "output": json.dumps(payload),
                    },
                },
            }
        ]

    payload = {
        "resource": "plugins/agent-support/search/",
        "data": {"results": [{"display": "test-site", "id": 1}]},
    }
    assert community_read_checks(transcript(payload), "test", [])["search_api_used"]
    assert not community_read_checks(transcript(payload, True), "test", [])["search_api_used"]
    assert not community_read_checks(transcript({"status": "blocked"}), "test", [])["search_api_used"]
    assert not community_read_checks(transcript({**payload, "data": {"results": []}}), "test", [])[
        "search_api_used"
    ]
    assert not community_read_checks(transcript(payload), "unrelated", [])["search_api_used"]
