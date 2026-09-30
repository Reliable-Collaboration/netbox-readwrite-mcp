"""The evaluation observer must see incremental progress without recording secrets."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import urllib.request

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


def test_gateway_forwards_stream_incrementally_without_retaining_body():
    first_read = threading.Event()
    first = b'data: {"choices":[{"delta":{"content":"private payload"}}]}\n\n'
    last = b"data: [DONE]\n\n"

    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
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
            f"http://127.0.0.1:{gateway.port}/v1/chat/completions",
            data=json.dumps({"messages": [], "stream": True}).encode(),
            headers={"Authorization": "Bearer test-secret", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            assert response.readline() == first.splitlines(keepends=True)[0]
            snapshot = gateway.activity.snapshot()
            assert snapshot["content_chunks"] == 1
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
