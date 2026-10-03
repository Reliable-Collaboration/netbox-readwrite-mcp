"""Native administrative actions reachable through generic MCP API tools."""

import json
import os
import time
import uuid

import pytest

from netbox_readwrite_mcp.server import build_service
from scripts.lab import STATE, URL
from tests.integration.test_configuration import shell

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("NETBOX_RW_LIVE") != "1", reason="Disposable lab opt-in required"),
]


@pytest.fixture
def queue_admin(tmp_path):
    cfg = json.loads((STATE / "broad-config.json").read_text())
    assert cfg["netbox_url"] == URL
    token = tmp_path / "token"
    token.write_text(json.loads((STATE / "secrets.json").read_text())["token"])
    token.chmod(0o600)
    cfg.update(token_file=str(token), actor="audit-admin", journal=str(tmp_path / "journal.sqlite"))
    service = build_service(cfg)
    try:
        yield service
    finally:
        service.store.close()


def wait_task(service, path, status):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        response = service.query(path)
        assert response["status"] == 200, response
        if response["body"]["status"] == status:
            return response["body"]
        time.sleep(0.25)
    pytest.fail(f"Disposable RQ task did not reach {status}: {response['body']}")


@pytest.mark.parametrize("initial,action", [("scheduled", "enqueue"), ("failed", "requeue")])
def test_native_queue_execution_and_deletion(queue_admin, initial, action):
    """Real worker execution, receipt replay, and deletion of only our own job."""
    job_id = "qualification-" + uuid.uuid4().hex
    fixture = f"""
from django_rq import get_queue
from rq.job import Job, JobStatus
from rq.registry import FailedJobRegistry, ScheduledJobRegistry
from datetime import datetime, timedelta, timezone
queue = get_queue('default')
job_id = {job_id!r}
"""
    setup = """
job = Job.create('operator.add', args=(19, 23), connection=queue.connection,
                 origin=queue.name, id=job_id, result_ttl=300)
job.set_status(JobStatus.SCHEDULED if INITIAL == 'scheduled' else JobStatus.FAILED)
job.save()
if INITIAL == 'scheduled':
    ScheduledJobRegistry(queue=queue).schedule(job, datetime.now(timezone.utc) + timedelta(hours=1))
else:
    FailedJobRegistry(queue=queue).add(job, ttl=300)
""".replace("INITIAL", repr(initial))
    shell(fixture + setup)
    service = queue_admin
    path = "core/background-tasks/" + job_id + "/"
    try:
        assert service.query(path)["body"]["status"] == initial
        restricted = build_service(json.loads((STATE / "broad-config.json").read_text()))
        try:
            for verb, suffix in [("GET", ""), ("POST", action + "/"), ("POST", "delete/")]:
                assert restricted.api.request(verb, path + suffix)["status"] == 403
        finally:
            restricted.store.close()
        task = service.begin_task("Qualify disposable queue task")["task_id"]
        result = service.execute_action(task, "execute-job", "POST", path + action + "/", {})
        assert result["last_receipt"]["status"] == 200, result
        assert result["state"] == "completed" and result["native_changes"] == []
        wait_task(service, path, "finished")
        shell(
            fixture
            + "job = Job.fetch(job_id, connection=queue.connection)\nassert job.return_value() == 42\n"
        )
        assert (
            service.execute_action(task, "execute-job", "POST", path + action + "/", {})["id"] == result["id"]
        )
        removed = service.execute_action(task, "delete-job", "POST", path + "delete/", {})
        assert removed["last_receipt"]["status"] == 200
        shell(fixture + "assert not Job.exists(job_id, connection=queue.connection)\n")
        assert service.api.request("POST", path + "delete/", {})["status"] == 404
    finally:
        shell(
            fixture
            + "\nif Job.exists(job_id, connection=queue.connection):\n    Job.fetch(job_id, connection=queue.connection).delete()\n"
        )


def test_native_worker_name_with_at_and_plus(tmp_path):
    name = "qualification@host+" + uuid.uuid4().hex
    fixture = f"""
from django_rq.queues import get_redis_connection
from django_rq.settings import get_queues_list
from rq.worker import Worker
connection = get_redis_connection(get_queues_list()[0]['connection_config'])
worker = Worker([], connection=connection, name={name!r})
"""
    shell(fixture + "worker.register_birth()\n")
    cfg = json.loads((STATE / "broad-config.json").read_text())
    assert cfg["netbox_url"] == URL
    token = tmp_path / "token"
    token.write_text(json.loads((STATE / "secrets.json").read_text())["token"])
    token.chmod(0o600)
    cfg.update(token_file=str(token), actor="audit-admin", journal=str(tmp_path / "journal.sqlite"))
    service = build_service(cfg)
    try:
        response = service.query("core/background-workers/" + name + "/")
        assert response["status"] == 200
        assert response["body"]["name"] == name
        restricted = build_service(json.loads((STATE / "broad-config.json").read_text()))
        try:
            assert restricted.api.request("GET", "core/background-workers/" + name + "/")["status"] == 403
        finally:
            restricted.store.close()
    finally:
        service.store.close()
        shell(fixture + "worker.register_death()\n")


def test_native_stop_running_task(queue_admin):
    job_id = "qualification-" + uuid.uuid4().hex
    fixture = f"""
from django_rq import get_queue
from rq.job import Job
queue = get_queue('default')
job_id = {job_id!r}
"""
    shell(fixture + "queue.enqueue('time.sleep', 90, job_id=job_id, job_timeout=120, failure_ttl=300)\n")
    service = queue_admin
    path = "core/background-tasks/" + job_id + "/"
    try:
        wait_task(service, path, "started")
        task = service.begin_task("Stop only the disposable test task")["task_id"]
        result = service.execute_action(task, "stop-running", "POST", path + "stop/", {})
        assert result["state"] == "completed" and result["last_receipt"]["status"] == 200, result
        wait_task(service, path, "stopped")
        assert service.execute_action(task, "stop-running", "POST", path + "stop/", {})["id"] == result["id"]
    finally:
        shell(
            fixture
            + "\nif Job.exists(job_id, connection=queue.connection):\n    from rq.command import send_stop_job_command\n    job = Job.fetch(job_id, connection=queue.connection)\n    if job.get_status() == 'started':\n        send_stop_job_command(queue.connection, job_id)\n    job.delete()\n"
        )


def test_native_user_group_permission_grant_and_revoke(queue_admin):  # noqa: F811
    import secrets

    from netbox_readwrite_mcp.api import NetBox

    service = queue_admin
    name = "qualification-access-" + uuid.uuid4().hex
    created = []

    def make(resource, values):
        response = service.api.request("POST", resource, values)
        assert response["status"] == 201
        obj = response["body"]
        created.append((resource, obj["id"]))
        return obj

    try:
        user = make(
            "users/users/", {"username": name, "password": secrets.token_urlsafe(24), "is_active": True}
        )
        token = make(
            "users/tokens/",
            {
                "user": user["id"],
                "version": 2,
                "write_enabled": True,
                "description": "Disposable permission fixture",
            },
        )
        client = NetBox(URL, "nbt_" + token["key"] + "." + token["token"])
        assert client.request("GET", "dcim/sites/")["status"] == 403
        group = make("users/groups/", {"name": name})
        make(
            "users/permissions/",
            {
                "name": name,
                "actions": ["view", "add", "change", "delete"],
                "object_types": ["dcim.site"],
                "groups": [group["id"]],
                "constraints": {"slug__startswith": name},
            },
        )
        assert (
            service.api.request("PATCH", f"users/users/{user['id']}/", {"groups": [group["id"]]})["status"]
            == 200
        )
        assert client.get("dcim/sites/")["body"]["count"] == 0
        site = client.request("POST", "dcim/sites/", {"name": name, "slug": name})
        assert site["status"] == 201, site
        created.append(("dcim/sites/", site["body"]["id"]))
        denied = client.request("POST", "dcim/sites/", {"name": "outside-" + name, "slug": "outside-" + name})
        assert denied["status"] == 403, denied
        assert service.api.get("dcim/sites/?slug=outside-" + name)["body"]["count"] == 0
        assert client.get("dcim/sites/")["body"]["count"] == 1
        assert service.api.request("PATCH", f"users/users/{user['id']}/", {"groups": []})["status"] == 200
        assert client.request("GET", "dcim/sites/")["status"] == 403
    finally:
        for resource, pk in reversed(created):
            assert service.api.request("DELETE", resource + str(pk) + "/")["status"] in {204, 404}
