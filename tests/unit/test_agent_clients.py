"""Failure detection must not turn client/provider failures into passing agent runs."""

import pytest

from scripts.agent_clients import client_failed, used_host_tools


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
