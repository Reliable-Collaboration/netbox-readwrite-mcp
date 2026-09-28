"""Small independent NetBox model; live tests remain the server-contract authority."""

from copy import deepcopy
import uuid


class NetBoxModel:
    url = "https://netbox.invalid"

    def __init__(self):
        self.devices = {
            i: {"id": i, "name": f"device-{i}", "description": "A", "serial": "", "status": "active"}
            for i in (1, 2)
        }
        self.revisions = {1: 1, 2: 1}
        self.rows = []
        self.patches = 0
        self.version = "4.6.10"

    def etag(self, pk):
        return f'W/"revision-{self.revisions[pk]}"'

    def get(self, path):
        if path == "status/":
            return {"status": 200, "headers": {}, "body": {"netbox-version": self.version}}
        pk = int(path.strip("/").split("/")[-1])
        body = deepcopy(self.devices[pk])
        body["status"] = {"value": body["status"], "label": body["status"]}
        return {"status": 200, "headers": {"etag": self.etag(pk)}, "body": body}

    def request(self, method, path, data=None, headers=None):
        assert method == "PATCH", "The service must never send another mutation type"
        self.patches += 1
        pk = int(path.strip("/").split("/")[-1])
        if (headers or {}).get("If-Match") != self.etag(pk):
            return {"status": 412, "body": {"detail": "Object changed"}, "headers": {}}
        if data.get("status", "active") not in ("active", "planned", "offline", "failed"):
            return {"status": 400, "body": {"status": ["Invalid choice."]}, "headers": {}}
        normalized = {
            key: value.strip() if key in ("description", "serial") else value for key, value in data.items()
        }
        request_id = self.change(pk, normalized, actor="agent")
        result = self.get(path)
        result["headers"]["x-request-id"] = request_id
        return result

    def change(self, pk, data, actor="other"):
        before = deepcopy(self.devices[pk])
        self.devices[pk].update({k: v for k, v in data.items() if k != "changelog_message"})
        self.revisions[pk] += 1
        request_id = str(uuid.uuid4())
        self.rows.append(
            {
                "id": len(self.rows) + 1,
                "time": str(len(self.rows)),
                "user_name": actor,
                "request_id": request_id,
                "action": {"value": "update"},
                "changed_object_type": "dcim.device",
                "changed_object_id": pk,
                "object_repr": before["name"],
                "message": data.get("changelog_message", ""),
                "prechange_data": before,
                "postchange_data": deepcopy(self.devices[pk]),
            }
        )
        return request_id

    def history(self):
        return deepcopy(self.rows)
