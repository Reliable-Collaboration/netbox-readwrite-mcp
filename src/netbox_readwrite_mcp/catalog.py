"""Discover the running server's API, rather than maintaining a model allowlist."""

import re
from urllib.parse import urlencode


def api_path(path):
    if (
        not isinstance(path, str)
        or not re.fullmatch(r"[A-Za-z0-9_./-]+/", path)
        or ".." in path
        or path.startswith("/")
    ):
        raise ValueError("Use a relative API path ending in /, without URL, query, or traversal")
    return path


def query_string(filters):
    if not isinstance(filters, dict):
        raise ValueError("filters must be an object")
    for key, value in filters.items():
        if not isinstance(key, str) or not isinstance(value, (str, int, bool, list)):
            raise ValueError("Filter values must be strings, integers, booleans, or lists")
        if isinstance(value, list) and any(not isinstance(x, (str, int, bool)) for x in value):
            raise ValueError("Filter lists must contain scalar values")
    return urlencode(
        {k: str(v).lower() if isinstance(v, bool) else v for k, v in filters.items()}, doseq=True
    )


class Catalog:
    def __init__(self, api):
        self.api = api
        self.models = None
        self.schema = None

    def discover(self, refresh=False):
        if refresh:
            self.models = self.schema = None
        if self.models is None:
            root = self.api.get("")["body"]
            result = {}
            pending = list(root.items())
            visited = set()
            while pending:
                name, url = pending.pop(0)
                if not isinstance(url, str) or not url.startswith(self.api.url + "/api/"):
                    continue
                path = url[len(self.api.url + "/api/") :]
                if path in visited:
                    continue
                visited.add(path)
                if name in {"status", "schema", "docs", "redoc"}:
                    continue
                response = self.api.request("GET", path)
                body = response["body"]
                if (
                    isinstance(body, dict)
                    and body
                    and all(
                        isinstance(v, str) and v.startswith(self.api.url + "/api/") for v in body.values()
                    )
                ):
                    pending.extend(body.items())
                elif path.count("/") >= 2:
                    result[path] = {
                        "resource": path,
                        "name": name,
                        "accessible": response["status"] == 200,
                        "kind": "collection" if isinstance(body, dict) and "results" in body else "action",
                        "discovery_status": response["status"],
                    }
            self.models = result
        return list(self.models.values())

    def resolve(self, object_type):
        if "/" in object_type:
            return api_path(object_type.strip("/") + "/")
        matches = [
            x["resource"]
            for x in self.discover()
            if x["name"] == object_type or x["resource"].replace("/", ".").rstrip(".") == object_type
        ]
        if len(matches) != 1:
            raise ValueError(
                "Unknown or ambiguous object_type; use discover_models and a resource such as dcim/devices/"
            )
        return matches[0]

    def describe(self, resource):
        resource = self.resolve(resource)
        options = self.api.request("OPTIONS", resource)
        if self.schema is None:
            response = self.api.request("GET", "schema/?format=json")
            if response["status"] != 200 or not isinstance(response["body"], dict):
                raise RuntimeError("API schema unavailable")
            self.schema = response["body"]
        paths = {
            p: value for p, value in self.schema.get("paths", {}).items() if p.startswith("/api/" + resource)
        }
        refs = set()
        schemas = {}

        def collect(value):
            if isinstance(value, dict):
                ref = value.get("$ref", "")
                if ref.startswith("#/components/schemas/") and ref not in refs:
                    refs.add(ref)
                    key = ref.rsplit("/", 1)[1]
                    entry = self.schema.get("components", {}).get("schemas", {}).get(key, {})
                    schemas[key] = entry
                    collect(entry)
                for v in value.values():
                    collect(v)
            elif isinstance(value, list):
                for v in value:
                    collect(v)

        collect(paths)
        return {"resource": resource, "options": options, "paths": paths, "schemas": schemas}
