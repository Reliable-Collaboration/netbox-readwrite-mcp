"""Failure detection must not turn client/provider failures into passing agent runs."""

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
