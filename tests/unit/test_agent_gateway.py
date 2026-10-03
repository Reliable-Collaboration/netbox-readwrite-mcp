"""The evaluation observer must see incremental progress without recording secrets."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import urllib.request

import pytest

from scripts.agent_gateway import Activity, Gateway


def test_activity_distinguishes_keepalive_from_generation():
    activity = Activity()
    ident = activity.begin({"messages": [{"content": "private prompt"}], "tools": []})
    activity.chunk(ident, b": keepalive\n", [b": keepalive"])
    assert activity.snapshot()["last_network_age_seconds"] is not None
    assert activity.snapshot()["last_generation_age_seconds"] is None
    activity.chunk(ident, b"x", [b'data: {"choices":[{"delta":{"reasoning_content":"secret thinking"}}]}'])
    snapshot = activity.snapshot()
    assert snapshot["reasoning_content_chunks"] == 1
    assert snapshot["last_generation_age_seconds"] is not None
    assert "secret" not in json.dumps(snapshot) and "private" not in json.dumps(snapshot)
    activity.end(ident)
    assert not activity.snapshot()["active_requests"]


@pytest.mark.parametrize(
    "endpoint,first,counter",
    [
        (
            "/v1/chat/completions",
            b'data: {"choices":[{"delta":{"content":"private payload"}}]}\n\n',
            "content_chunks",
        ),
        (
            "/v1/messages?beta=true",
            b'data: {"type":"content_block_delta","delta":{"type":"thinking_delta","thinking":"private payload"}}\n\n',
            "reasoning_chunks",
        ),
        (
            "/v1/responses",
            b'data: {"type":"response.output_text.delta","delta":"private payload"}\n\n',
            "response_delta_chunks",
        ),
    ],
)
def test_gateway_forwards_stream_incrementally_without_retaining_body(endpoint, first, counter):
    first_read = threading.Event()
    last = b"data: [DONE]\n\n"

    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            assert self.path == endpoint
            assert self.headers["x-api-key"] == "test-anthropic-secret"
            assert self.headers["Authorization"] == "Bearer test-secret"
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(first) + len(last)))
            self.end_headers()
            self.wfile.write(first)
            self.wfile.flush()
            assert first_read.wait(5), "Gateway buffered the stream until EOF"
            self.wfile.write(last)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    gateway = Gateway(server.server_port, timeout=5)
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{gateway.port}{endpoint}",
            data=json.dumps({"messages": [], "stream": True}).encode(),
            headers={
                "Authorization": "Bearer test-secret",
                "x-api-key": "test-anthropic-secret",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            assert response.readline() == first.splitlines(keepends=True)[0]
            snapshot = gateway.activity.snapshot()
            assert snapshot[counter] == 1
            assert snapshot["active_requests"]
            assert "private payload" not in json.dumps(snapshot)
            assert "test-secret" not in json.dumps(snapshot)
            first_read.set()
            assert response.read() == b"\n" + last
    finally:
        first_read.set()
        gateway.close()
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


def test_activity_reports_terminal_status_and_sizes_without_content():
    activity = Activity()
    ident = activity.begin({"instructions": "private instructions", "tools": [], "input": "private input"})
    activity.chunk(
        ident,
        b"x",
        [
            b'data: {"type":"response.incomplete","response":{"status":"incomplete","output":"private output"}}'
        ],
    )
    activity.chunk(ident, b"x", [b'data: {"type":"message_delta","delta":{"stop_reason":"max_tokens"}}'])
    state = activity.snapshot()
    assert state["response_incomplete"] == 1
    assert state["stop_max_tokens"] == 1
    assert state["request_bytes"] > state["largest_instructions_bytes"] > 0
    assert "private" not in json.dumps(state)


@pytest.mark.parametrize(
    "output,empty,text_chars",
    [
        ([], True, 0),
        ([{"type": "message", "content": None}], True, 0),
        ([{"type": "reasoning", "summary": "private reasoning"}], True, 0),
        ([{"type": "function_call", "name": "private tool", "arguments": "private arguments"}], False, 0),
        ([{"type": "message", "content": [{"type": "output_text", "text": "private answer"}]}], False, 14),
    ],
)
def test_terminal_response_shape_distinguishes_empty_answers_without_retaining_content(
    output, empty, text_chars
):
    activity = Activity()
    ident = activity.begin({})
    line = (
        b"data: "
        + json.dumps(
            {"type": "response.completed", "response": {"status": "completed", "output": output}}
        ).encode()
    )
    activity.chunk(ident, line, [line])
    state = activity.snapshot()
    assert bool(state.get("response_completed_without_text_or_function_call")) is empty
    assert state["last_response_shape"]["text_characters"] == text_chars
    assert state["last_response_shape"]["output_items"] == len(output)
    assert state["last_response_shape"]["request_number"] == ident
    assert "private" not in json.dumps(state)
