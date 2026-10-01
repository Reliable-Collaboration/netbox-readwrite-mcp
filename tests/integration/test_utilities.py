"""Native global search, Markdown, administrative views and image bytes."""

import base64
import hashlib
import os
import time
import uuid

import pytest

from tests.integration.test_patterns import parents  # noqa: F401
from tests.integration.test_batch_actions import data_source  # noqa: F401

from tests.integration.test_administration import queue_admin  # noqa: F401
from tests.integration.test_imports import importer  # noqa: F401
from tests.integration.test_personal import people  # noqa: F401
from tests.integration.test_configuration import shell

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("NETBOX_RW_LIVE") != "1", reason="Disposable lab opt-in required"),
]
ROOT = "plugins/agent-support/"
# A fixed, valid 1x1 PNG fixture; no external media/network dependency.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)


def test_native_global_search_permission_scope_and_invalid_inputs(importer, people):  # noqa: F811
    service, prefix = importer
    created = service.api.request("POST", "dcim/sites/", {"name": prefix, "slug": prefix})
    assert created["status"] == 201
    params = f"?q={prefix}&lookup=iexact&obj_types=dcim.site"
    deadline = time.monotonic() + 45
    while True:
        result = service.api.get(ROOT + "search/" + params)["body"]
        if result["count"] or time.monotonic() >= deadline:
            break
        time.sleep(0.25)
    assert [(row["object_type"], row["id"]) for row in result["results"]] == [
        ("dcim.site", created["body"]["id"])
    ]
    assert people[0][0].api.get(ROOT + "search/" + params)["body"]["count"] == 0
    for query in ["?q=x&lookup=invalid", "?q=x&obj_types=invalid.model", "?q=%5B&lookup=iregex"]:
        assert service.api.request("GET", ROOT + "search/" + query)["status"] == 400


def test_native_markdown_preview_without_changes(people):  # noqa: F811
    service = people[0][0]
    task = service.begin_task("Markdown preview")["task_id"]
    result = service.execute_action(
        task, "markdown-preview", "POST", ROOT + "render-markdown/", {"text": "**Inventory**\n\n- Rack"}
    )
    assert result["last_receipt"]["status"] == 200, result
    html = result["last_receipt"]["body"]["html"]
    assert "<strong>Inventory</strong>" in html and "<li>Rack</li>" in html
    assert result["state"] == "completed" and not result["native_changes"]


def test_system_schema_and_queue_registry_permissions(queue_admin, people):  # noqa: F811
    for path in ["system/", "database-schema/?table=dcim_site", "queue-tasks/"]:
        response = queue_admin.api.get(ROOT + path)
        assert response["status"] == 200
        assert people[0][0].api.request("GET", ROOT + path)["status"] == 403
    system = queue_admin.query(ROOT + "system/")["body"]
    assert "dcim.site" in system["objects"] and "netbox_agent_api" in system["plugins"]
    assert not any(key.startswith("COPILOT_") for key in system["config"])
    schema = queue_admin.api.get(ROOT + "database-schema/?table=dcim_site")["body"]
    assert schema["count"] == 1 and schema["results"][0]["name"] == "dcim_site"
    assert any(row["name"] == "name" for row in schema["results"][0]["columns"])
    assert "scheduled" in queue_admin.query(ROOT + "queue-tasks/")["body"]["statuses"]
    assert queue_admin.api.request("GET", ROOT + "queue-tasks/?queue=unknown")["status"] == 400
    assert queue_admin.api.request("GET", ROOT + "queue-tasks/?queue=default&status=unknown")["status"] == 400


def test_native_scheduled_registry_lists_synthetic_job(queue_admin):  # noqa: F811
    job_id = "registry-" + uuid.uuid4().hex
    fixture = f"""
from django_rq import get_queue
from rq.job import Job, JobStatus
from rq.registry import ScheduledJobRegistry
from datetime import datetime, timedelta, timezone
queue = get_queue('default')
job_id = {job_id!r}
"""
    shell(
        fixture
        + """
job = Job.create('operator.add', args=(1, 2), connection=queue.connection, origin=queue.name, id=job_id)
job.set_status(JobStatus.SCHEDULED)
job.save()
ScheduledJobRegistry(queue=queue).schedule(job, datetime.now(timezone.utc) + timedelta(hours=1))
"""
    )
    try:
        rows = queue_admin.api.get(ROOT + "queue-tasks/?queue=default&status=scheduled")["body"]["results"]
        assert any(row["id"] == job_id and row["status"] == "scheduled" for row in rows)
    finally:
        shell(fixture + "Job.fetch(job_id, connection=queue.connection).delete()\n")


def test_media_native_upload_chunked_download_and_permissions(importer, people):  # noqa: F811
    service, prefix = importer
    site = service.api.request("POST", "dcim/sites/", {"name": prefix, "slug": prefix})["body"]
    created = service.api.request(
        "POST",
        "extras/image-attachments/",
        {"object_type": "dcim.site", "object_id": site["id"], "name": "Qualification image"},
        files=[
            {
                "field": "image",
                "filename": prefix + ".png",
                "base64": base64.b64encode(PNG).decode(),
                "content_type": "image/png",
            }
        ],
    )
    assert created["status"] == 201, created
    pk = created["body"]["id"]
    path = ROOT + f"media/extras.imageattachment/{pk}/image/"
    try:
        first = service.api.get(path + "?length=20")["body"]
        assert first["sha256"] == hashlib.sha256(PNG).hexdigest() and first["size"] == len(PNG)
        result = base64.b64decode(first["base64"])
        offset = first["next_offset"]
        while offset is not None:
            row = service.api.get(path + f"?offset={offset}&length=20&expected_sha256={first['sha256']}")[
                "body"
            ]
            result += base64.b64decode(row["base64"])
            offset = row["next_offset"]
        assert result == PNG
        assert people[0][0].api.request("GET", path)["status"] == 404
        assert service.api.request("GET", path + "?expected_sha256=" + "0" * 64)["status"] == 412
        assert service.api.request("GET", path + "?offset=999999")["status"] == 416
        assert service.api.request("GET", path + "?length=999999")["status"] == 400
        assert service.api.request("GET", path.replace("/image/", "/password/"))["status"] == 404
    finally:
        service.api.request("DELETE", f"extras/image-attachments/{pk}/")


@pytest.mark.parametrize("field", ["front_image", "rear_image"])
def test_device_type_image_upload_download(parents, field):  # noqa: F811
    service, prefix, ids = parents
    pk = ids["device_type"]
    result = service.api.request(
        "PATCH",
        f"dcim/device-types/{pk}/",
        {},
        files=[
            {
                "field": field,
                "filename": prefix + ".png",
                "base64": base64.b64encode(PNG).decode(),
                "content_type": "image/png",
            }
        ],
    )
    assert result["status"] == 200, result
    content = service.api.get(ROOT + f"media/dcim.devicetype/{pk}/{field}/")["body"]
    assert base64.b64decode(content["base64"]) == PNG
    assert content["sha256"] == hashlib.sha256(PNG).hexdigest()


def test_native_datafile_content_binary_chunks_and_permissions(data_source, people):  # noqa: F811
    from tests.integration.test_batch_actions import sync_source

    service, prefix, source_id, file_id, directory = data_source
    raw = b"\x00\xffbinary\nqualification\x00"
    shell(f"""
from pathlib import Path
Path({directory!r}, 'fixture.bin').write_bytes({raw!r})
""")
    sync_source(service, source_id)
    files = service.api.get(f"core/data-files/?source_id={source_id}")["body"]["results"]
    pk = next(row["id"] for row in files if row["path"] == "fixture.bin")
    path = ROOT + f"media/core.datafile/{pk}/data/"
    first = service.api.get(path + "?length=5")["body"]
    last = service.api.get(path + f"?offset=5&expected_sha256={first['sha256']}")["body"]
    assert base64.b64decode(first["base64"]) + base64.b64decode(last["base64"]) == raw
    assert first["sha256"] == hashlib.sha256(raw).hexdigest()
    assert people[0][0].api.request("GET", path)["status"] == 404
