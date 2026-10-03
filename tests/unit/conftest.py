import pytest
from netbox_readwrite_mcp.service import Service
from .fakes import NetBoxModel


@pytest.fixture
def service(tmp_path):
    instance = Service(NetBoxModel(), tmp_path / "journal.sqlite", "lineage", "agent", [1, 2])
    yield instance
    instance.store.close()


@pytest.fixture
def edit(service):
    task = service.begin_task("Unit test")["task_id"]

    def perform(changes=None, key="test-edit-0001", device=1):
        return service.update_device(
            task,
            key,
            device,
            service.read_device(device)["etag"],
            {"description": "B"} if changes is None else changes,
        )

    return perform
