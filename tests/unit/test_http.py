"""Exercise urllib against an actual local HTTP server, not a mocked client."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import pytest
from netbox_readwrite_mcp.api import NetBox


@pytest.fixture
def http_api():
    class Handler(BaseHTTPRequestHandler):
        calls = []
        status_code = 200
        response_body = b'{"id":1}'
        location = None

        def do_GET(self):
            self.respond()

        def do_PATCH(self):
            self.respond()

        def respond(self):
            type(self).calls.append(
                {
                    "method": self.command,
                    "path": self.path,
                    "authorization": self.headers.get("Authorization"),
                    "if_match": self.headers.get("If-Match"),
                    "body": self.rfile.read(int(self.headers.get("Content-Length", "0"))),
                }
            )
            self.send_response(self.status_code)
            self.send_header("ETag", 'W/"123"')
            self.send_header("X-Request-ID", "request-1")
            self.send_header("Set-Cookie", "must-not-be-retained")
            if self.location:
                self.send_header("Location", self.location)
            self.end_headers()
            self.wfile.write(self.response_body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield NetBox(f"http://127.0.0.1:{server.server_port}", "secret"), Handler
    server.shutdown()
    thread.join()
    server.server_close()


def test_patch_precondition_receipt_and_no_secret_headers(http_api):
    api, handler = http_api
    result = api.request("PATCH", "dcim/devices/1/", {"description": "new"}, {"If-Match": 'W/"old"'})
    assert handler.calls[0]["authorization"] == "Token secret"
    assert handler.calls[0]["if_match"] == 'W/"old"'
    assert json.loads(handler.calls[0]["body"]) == {"description": "new"}
    assert result["headers"] == {"etag": 'W/"123"', "x-request-id": "request-1"}


def test_v2_token_uses_bearer(http_api):
    api, handler = http_api
    api.token = "nbt_public.secret"
    api.get("status/")
    assert handler.calls[0]["authorization"] == "Bearer nbt_public.secret"


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 412, 429, 500, 503])
def test_failure_is_a_receipt_and_never_retried(http_api, status):
    api, handler = http_api
    handler.status_code = status
    handler.response_body = b'{"detail":"Rejected"}'
    result = api.request("PATCH", "dcim/devices/1/", {"description": "new"})
    assert result["status"] == status
    assert result["body"]["detail"] == "Rejected"
    assert len(handler.calls) == 1
    with pytest.raises(RuntimeError, match=f"HTTP {status}"):
        api.get("status/")


def test_redirect_does_not_forward_credentials(http_api):
    api, handler = http_api
    handler.status_code = 302
    handler.location = api.url + "/redirect-target"
    assert api.request("PATCH", "dcim/devices/1/", {})["status"] == 302
    assert len(handler.calls) == 1


def test_non_json_and_oversized_responses(http_api):
    api, handler = http_api
    handler.response_body = b"<html>Error</html>"
    assert api.request("GET", "status/")["body"] == {"error": "Non-JSON response"}
    handler.response_body = b"x" * (16 * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match="size bound"):
        api.get("status/")
