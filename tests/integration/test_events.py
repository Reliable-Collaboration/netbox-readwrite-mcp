"""Real event-rule worker delivery to an isolated Podman webhook receiver."""

import base64
import hashlib
import hmac
import json
import os
import subprocess
import time

import pytest

from scripts.lab import PREFIX, ROOT
from tests.integration.test_imports import importer  # noqa: F401
from tests.integration.test_batch_actions import create

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("NETBOX_RW_LIVE") != "1", reason="Disposable lab opt-in required"),
]


def test_native_event_rule_webhook_worker_delivery_and_signature(importer):  # noqa: F811
    service, prefix = importer
    receiver = PREFIX + "-webhook-" + prefix
    image = json.loads((ROOT / "scripts/images.lock.json").read_text())["netbox"]["4.7.2"]["digest"]
    code = """from http.server import HTTPServer, BaseHTTPRequestHandler
import base64, json
class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        raw = self.rfile.read(min(int(self.headers.get("Content-Length", "0")), 1048576))
        print(json.dumps({"body":base64.b64encode(raw).decode(), "signature":self.headers.get("X-Hook-Signature")}), flush=True)
        self.send_response(200)
        self.end_headers()
    def log_message(self, *args):
        pass
HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
"""
    subprocess.run(
        [
            "podman",
            "run",
            "-d",
            "--rm",
            "--name",
            receiver,
            "--network",
            PREFIX,
            "--entrypoint",
            "/opt/netbox/venv/bin/python",
            image,
            "-u",
            "-c",
            code,
        ],
        check=True,
        capture_output=True,
    )
    webhook = rule = None
    secret = "qualification-only-signature-key"
    try:
        webhook = create(
            service,
            "extras/webhooks/",
            {"name": prefix, "payload_url": f"http://{receiver}:8080/", "secret": secret},
        )
        rule = create(
            service,
            "extras/event-rules/",
            {
                "name": prefix,
                "object_types": ["dcim.site"],
                "event_types": ["object_created"],
                "action_type": "webhook",
                "action_object_type": "extras.webhook",
                "action_object_id": webhook["id"],
                "conditions": {"and": [{"attr": "slug", "value": prefix}]},
            },
        )
        task = service.begin_task("Native event delivery qualification")["task_id"]
        result = service.create_object(
            task, "webhook-site-create", "dcim/sites/", {"name": prefix, "slug": prefix, "status": "active"}
        )
        assert result["state"] == "applied", result
        deadline = time.monotonic() + 60
        deliveries = []
        while time.monotonic() < deadline:
            output = subprocess.run(
                ["podman", "logs", receiver], capture_output=True, text=True, check=True
            ).stdout
            deliveries = [json.loads(line) for line in output.splitlines() if line.startswith("{")]
            if deliveries:
                break
            time.sleep(0.5)
        assert len(deliveries) == 1, deliveries
        raw = base64.b64decode(deliveries[0]["body"])
        assert deliveries[0]["signature"] == hmac.new(secret.encode(), raw, hashlib.sha512).hexdigest()
        body = json.loads(raw)
        assert body["data"]["slug"] == prefix
        assert body["data"]["id"] == result["last_receipt"]["body"]["id"]
        assert body["event"] == "created"
        assert body["request"]["id"] == result["last_receipt"]["headers"]["x-request-id"]
        assert (
            service.api.request("PATCH", f"extras/event-rules/{rule['id']}/", {"action_type": "invalid"})[
                "status"
            ]
            == 400
        )
    finally:
        if rule:
            assert service.api.request("DELETE", f"extras/event-rules/{rule['id']}/")["status"] == 204
        if webhook:
            assert service.api.request("DELETE", f"extras/webhooks/{webhook['id']}/")["status"] == 204
        subprocess.run(["podman", "rm", "--force", receiver], check=True, capture_output=True)
