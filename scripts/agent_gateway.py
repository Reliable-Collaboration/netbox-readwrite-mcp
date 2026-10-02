"""Loopback-only observation of a lab model stream, without retaining prompts or tokens."""

from collections import Counter
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time


class Activity:
    def __init__(self):
        self.lock = threading.Lock()
        self.counts = Counter()
        self.active = {}
        self.last_network = None
        self.last_generation = None
        self.last_response = None

    def begin(self, body):
        with self.lock:
            self.counts["requests"] += 1
            self.counts["request_bytes"] += len(json.dumps(body).encode())
            for field in ("instructions", "tools", "input", "messages"):
                size = len(json.dumps(body.get(field, "")).encode())
                self.counts["largest_" + field + "_bytes"] = max(
                    self.counts["largest_" + field + "_bytes"], size
                )
            ident = self.counts["requests"]
            self.active[ident] = {
                "started": time.time(),
                "messages": len(body.get("messages", body.get("input", []))),
                "tools": len(body.get("tools", [])),
                "response_bytes": 0,
            }
            return ident

    def chunk(self, ident, data, lines):
        now = time.time()
        with self.lock:
            self.last_network = now
            self.counts["response_bytes"] += len(data)
            self.counts["network_chunks"] += 1
            self.active[ident]["response_bytes"] += len(data)
            for line in lines:
                if not line.startswith(b"data:"):
                    continue
                try:
                    event = json.loads(line[5:])
                except (ValueError, UnicodeDecodeError):
                    continue
                kind = event.get("type", "")
                if kind in {"response.completed", "response.incomplete", "response.failed"}:
                    response = event.get("response") or {}
                    status = response.get("status", "unknown")
                    if status in {"completed", "incomplete", "failed", "unknown"}:
                        self.counts["response_" + status] += 1
                    output = response.get("output")
                    if isinstance(output, list):
                        # Retain shape only, never generated text, arguments or identifiers.
                        types = Counter(
                            item.get("type", "unknown")
                            for item in output
                            if isinstance(item, dict)
                            and item.get("type") in {"message", "function_call", "reasoning"}
                        )
                        text_chars = sum(
                            len(part["text"])
                            for item in output
                            if isinstance(item, dict) and item.get("type") == "message"
                            for part in (item.get("content") or [])
                            if isinstance(part, dict) and isinstance(part.get("text"), str)
                        )
                        self.last_response = {
                            "request_number": ident,
                            "status": status
                            if status in {"completed", "incomplete", "failed"}
                            else "unknown",
                            "output_items": len(output),
                            "known_item_types": dict(types),
                            "text_characters": text_chars,
                        }
                        if status == "completed" and not text_chars and not types["function_call"]:
                            self.counts["response_completed_without_text_or_function_call"] += 1
                if kind == "message_delta":
                    reason = (event.get("delta") or {}).get("stop_reason")
                    if reason in {"end_turn", "tool_use", "max_tokens", "stop_sequence"}:
                        self.counts["stop_" + reason] += 1
                delta = event.get("delta")
                if kind == "content_block_delta" and isinstance(delta, dict):
                    for field, counter in (
                        ("text", "content"),
                        ("thinking", "reasoning"),
                        ("partial_json", "tool_calls"),
                    ):
                        if delta.get(field):
                            self.counts[counter + "_chunks"] += 1
                            self.last_generation = now
                if kind.startswith("response.") and kind.endswith(".delta") and delta:
                    self.counts["response_delta_chunks"] += 1
                    self.last_generation = now
                for choice in event.get("choices", []):
                    delta = choice.get("delta") or {}
                    for key in ("content", "reasoning_content", "reasoning", "tool_calls"):
                        if delta.get(key):
                            self.counts[key + "_chunks"] += 1
                            self.last_generation = now
                    if choice.get("finish_reason"):
                        self.counts["finished_choices"] += 1
                        if choice["finish_reason"] in {"stop", "length", "tool_calls", "content_filter"}:
                            self.counts["finish_" + choice["finish_reason"]] += 1

    def end(self, ident, error=False):
        with self.lock:
            self.active.pop(ident, None)
            self.counts["finished_requests"] += 1
            self.counts["transport_errors"] += int(error)

    def snapshot(self):
        now = time.time()
        with self.lock:
            return {
                **self.counts,
                "last_response_shape": self.last_response,
                "active_requests": [
                    {**value, "age_seconds": round(now - value["started"], 1)}
                    for value in self.active.values()
                ],
                "last_network_age_seconds": None
                if self.last_network is None
                else round(now - self.last_network, 1),
                "last_generation_age_seconds": None
                if self.last_generation is None
                else round(now - self.last_generation, 1),
            }


class Gateway:
    def __init__(self, upstream_port, timeout=14400):
        self.activity = Activity()
        activity = self.activity

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def do_POST(self):
                if self.path.split("?")[0] not in {
                    "/v1/chat/completions",
                    "/v1/messages",
                    "/v1/messages/count_tokens",
                    "/v1/responses",
                }:
                    self.send_error(404)
                    return
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 16 * 1024 * 1024:
                    self.send_error(413)
                    return
                raw = self.rfile.read(size)
                try:
                    body = json.loads(raw)
                except ValueError:
                    self.send_error(400)
                    return
                ident = activity.begin(body)
                upstream = http.client.HTTPConnection("127.0.0.1", upstream_port, timeout=timeout)
                error = False
                try:
                    upstream.request(
                        "POST",
                        self.path,
                        body=raw,
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": self.headers.get("Authorization", ""),
                            "x-api-key": self.headers.get("x-api-key", ""),
                            "anthropic-version": self.headers.get("anthropic-version", "2023-06-01"),
                        },
                    )
                    response = upstream.getresponse()
                    self.send_response(response.status)
                    self.send_header("Content-Type", response.getheader("Content-Type", "application/json"))
                    self.send_header("Transfer-Encoding", "chunked")
                    self.end_headers()
                    pending = b""
                    while data := response.read1(16384):
                        pending += data
                        lines = pending.split(b"\n")
                        pending = lines.pop()
                        # A malformed/no-newline body must not grow the observation buffer without bound.
                        if len(pending) > 1024 * 1024:
                            pending = b""
                        activity.chunk(ident, data, lines)
                        self.wfile.write(f"{len(data):x}\r\n".encode() + data + b"\r\n")
                        self.wfile.flush()
                    self.wfile.write(b"0\r\n\r\n")
                    self.wfile.flush()
                except (OSError, http.client.HTTPException):
                    error = True
                    self.close_connection = True
                finally:
                    upstream.close()
                    activity.end(ident, error)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
