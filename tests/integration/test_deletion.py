"""Native deletion gaps, cascade previews and external effects in the real lab."""

import os
import uuid

import pytest

from tests.integration.test_administration import queue_admin  # noqa: F401
from tests.integration.test_batch_actions import data_source, sync_source  # noqa: F401
from tests.integration.test_imports import importer  # noqa: F401
from tests.integration.test_configuration import shell

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("NETBOX_RW_LIVE") != "1", reason="Disposable lab opt-in required"),
]
ROOT = "plugins/agent-support/native-delete/"


def remove(service, model, pk):
    path = ROOT + model + "/"
    preview = service.api.request("POST", path, {"id": pk})
    assert preview["status"] == 200, preview
    assert preview["body"]["cascade"] and preview["body"]["effects"]
    assert service.api.request("POST", path, {"id": pk, "apply": True, "expected": "stale"})["status"] == 409
    task = service.begin_task("Guarded native deletion")["task_id"]
    result = service.execute_action(
        task,
        "native-delete-apply",
        "POST",
        path,
        {"id": pk, "apply": True, "expected": preview["body"]["expected"]},
    )
    assert result["last_receipt"]["status"] == 200, result
    assert result["last_receipt"]["body"]["applied"]
    replay = service.execute_action(
        task,
        "native-delete-apply",
        "POST",
        path,
        {"id": pk, "apply": True, "expected": preview["body"]["expected"]},
    )
    assert replay["id"] == result["id"]
    assert service.api.request("POST", path, {"id": pk})["status"] == 404
    return result


def test_native_datafile_delete_and_worker_recreation(data_source):  # noqa: F811
    service, prefix, source_id, file_id, directory = data_source
    assert service.api.request("DELETE", f"core/data-files/{file_id}/")["status"] == 405
    remove(service, "core.datafile", file_id)
    assert service.api.request("GET", f"core/data-files/{file_id}/")["status"] == 404
    sync_source(service, source_id)
    rows = service.api.get(f"core/data-files/?source_id={source_id}")["body"]["results"]
    assert len(rows) == 1 and rows[0]["id"] != file_id


def test_native_job_delete_cancels_its_scheduled_queue_task(queue_admin):  # noqa: F811
    service = queue_admin
    name = "qualification-delete-" + uuid.uuid4().hex
    shell(f"""
from core.models import Job
from django_rq import get_queue
from rq.job import Job as RQJob, JobStatus
from rq.registry import ScheduledJobRegistry
from datetime import datetime, timedelta, timezone
queue = get_queue('default')
import uuid
record = Job.objects.create(name={name!r}, queue_name='default', job_id=uuid.uuid4())
job = RQJob.create('operator.add', args=(19, 23), connection=queue.connection, origin=queue.name, id=str(record.job_id), result_ttl=300)
job.set_status(JobStatus.SCHEDULED)
job.save()
ScheduledJobRegistry(queue=queue).schedule(job, datetime.now(timezone.utc) + timedelta(hours=1))
""")
    try:
        rows = service.api.get("core/jobs/?name=" + name)["body"]["results"]
        assert len(rows) == 1
        pk, job_id = rows[0]["id"], rows[0]["job_id"]
        remove(service, "core.job", pk)
        shell(f"""
from django_rq import get_queue
from rq.job import Job, JobStatus
job = Job.fetch({job_id!r}, connection=get_queue('default').connection)
assert job.get_status() == JobStatus.CANCELED
job.delete()
""")
    finally:
        shell(f"""
from core.models import Job
for job in Job.objects.filter(name={name!r}):
    job.delete()
""")


def test_native_script_module_delete_removes_source(queue_admin):  # noqa: F811
    service = queue_admin
    filename = "qualification_delete_" + uuid.uuid4().hex + ".py"
    shell(f"""
from extras.models import ScriptModule
from pathlib import Path
path = Path('/opt/netbox/netbox/scripts', {filename!r})
path.write_text('from extras.scripts import Script\\nclass Disposable(Script):\\n    def run(self, data, commit):\\n        return "done"\\n')
ScriptModule.objects.create(file_root='scripts', file_path={filename!r})
""")
    try:
        # Native script detail exposes its parent module ID.
        script = service.api.get("extras/scripts/" + filename[:-3] + ".Disposable/")["body"]
        remove(service, "extras.scriptmodule", script["module"])
        shell(f"""
from pathlib import Path
from extras.models import ScriptModule
assert not Path('/opt/netbox/netbox/scripts', {filename!r}).exists()
assert not ScriptModule.objects.filter(file_root='scripts', file_path={filename!r}).exists()
""")
    finally:
        shell(f"""
from extras.models import ScriptModule
from pathlib import Path
for module in ScriptModule.objects.filter(file_root='scripts', file_path={filename!r}):
    module.delete()
Path('/opt/netbox/netbox/scripts', {filename!r}).unlink(missing_ok=True)
""")
