"""Native script schema/source, file variables, scheduling, worker results and cleanup."""

import base64
from datetime import datetime, timedelta, timezone
import os
import time
import uuid

import pytest

from tests.integration.test_administration import queue_admin  # noqa: F401
from tests.integration.test_personal import people  # noqa: F401
from tests.integration.test_configuration import shell

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("NETBOX_RW_LIVE") != "1", reason="Disposable lab opt-in required"),
]


def test_native_script_form_source_files_scheduling_and_worker_result(queue_admin, people):  # noqa: F811
    service = queue_admin
    filename = "qualification_vars_" + uuid.uuid4().hex + ".py"
    source = """from extras.scripts import Script, StringVar, FileVar, ChoiceVar
class Qualification(Script):
    text = StringVar(default="default text")
    mode = ChoiceVar(choices=(("a", "Alpha"), ("b", "Beta")), default="a")
    attachment = FileVar()
    def run(self, data, commit):
        value = data["attachment"].read().decode()
        self.log_success("file=" + value + "; text=" + data["text"] + "; mode=" + data["mode"])
        return value
"""
    uploaded = service.api.request(
        "POST",
        "extras/scripts/upload/",
        {},
        files=[{"field": "file", "filename": filename, "base64": base64.b64encode(source.encode()).decode()}],
    )
    assert uploaded["status"] == 201, uploaded
    module_id = uploaded["body"]["id"]
    try:
        path = "extras/scripts/" + filename[:-3] + ".Qualification/"
        script = service.api.get(path)["body"]
        companion = f"plugins/agent-support/scripts/{script['id']}/"
        metadata = service.api.get(companion)["body"]
        assert metadata["fields"]["attachment"]["type"] == "FileField"
        assert [row for row in metadata["fields"]["mode"]["choices"] if row["value"]] == [
            {"value": "a", "label": "Alpha"},
            {"value": "b", "label": "Beta"},
        ]
        assert metadata["scheduling_enabled"]
        content = service.api.get(companion + "source/")["body"]
        assert base64.b64decode(content["base64"]).decode().startswith("class Qualification(Script):")
        assert "FileVar" in content["text"]
        assert service.api.request("GET", companion + "source/?expected_sha256=" + "0" * 64)["status"] == 412
        for client, readonly in people:
            assert client.api.request("GET", companion)["status"] == 403
            assert client.api.request("GET", companion + "source/")["status"] == 403
        invalid = service.api.request("POST", path, {"data": {"mode": "invalid"}, "commit": False})
        assert invalid["status"] == 400, invalid
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        task = service.begin_task("Native scheduled file-variable script")["task_id"]
        result = service.execute_action(
            task,
            "schedule-file-script",
            "POST",
            path,
            {"data": {}, "commit": False, "schedule_at": future, "notifications": "never"},
            files=[
                {
                    "field": "attachment",
                    "filename": "fixture.txt",
                    "base64": base64.b64encode(b"qualification payload").decode(),
                }
            ],
        )
        assert result["state"] == "accepted", result
        job = result["last_receipt"]["body"]["result"]
        assert job["status"]["value"] == "scheduled"
        queued = service.api.request("POST", f"core/background-tasks/{job['job_id']}/enqueue/", {})
        assert queued["status"] == 200, queued
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            service.reconcile()
            result = service.get_operation(result["id"])
            if result["state"] != "accepted":
                break
            time.sleep(0.5)
        assert result["state"] == "job_completed", result
        actual = service.api.get(f"core/jobs/{job['id']}/")["body"]
        assert actual["status"]["value"] == "completed"
        assert "file=qualification payload; text=default text; mode=a" in str(actual["data"])
        assert not actual["error"]
    finally:
        shell(f"""
from extras.models import ScriptModule
for module in ScriptModule.objects.filter(pk={module_id}):
    for script in module.scripts.all():
        for job in script.jobs.all():
            job.delete()
    module.delete()
""")
