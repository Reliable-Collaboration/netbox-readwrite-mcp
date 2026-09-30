"""Discover the running server's API, rather than maintaining a model allowlist."""

import re
from urllib.parse import urlencode


def api_path(path):
    if (
        not isinstance(path, str)
        or not re.fullmatch(r"[A-Za-z0-9_./-]+/", path)
        or ".." in path
        or path.startswith(("/", "api/"))
    ):
        raise ValueError(
            "Use a path relative to /api/, for example ipam/prefixes/123/available-ips/. Remove the /api/ or api/ prefix; no URL, query string or traversal is allowed."
        )
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

    def load_schema(self):
        if self.schema is None:
            response = self.api.request("GET", "schema/?format=json")
            if response["status"] != 200 or not isinstance(response["body"], dict):
                raise RuntimeError("API schema unavailable")
            self.schema = response["body"]
        return self.schema

    def native_filters(self, resource):
        response = self.api.request(
            "GET", "plugins/agent-support/filter-schema/?" + query_string({"resource": resource})
        )
        if response["status"] == 200:
            metadata = response["body"]
            if (
                not isinstance(metadata, dict)
                or metadata.get("schema_version") != 1
                or metadata.get("resource") != resource
                or not isinstance(metadata.get("filters"), dict)
            ):
                raise RuntimeError("Companion filter metadata mismatch")
            return metadata["filters"]
        if response["status"] not in {400, 403, 404}:
            raise RuntimeError("Companion filter metadata unavailable")
        return None

    def validate_filters(self, resource, filters):
        """NetBox ignores unknown filters; reject them before a query can broaden scope."""
        if not filters:
            return
        query_string(filters)
        schema = self.load_schema()
        paths = schema.get("paths", {})
        concrete = "/api/" + resource
        path_spec = paths.get(concrete)
        if path_spec is None:
            segments = concrete.split("/")
            path_spec = next(
                (
                    spec
                    for template, spec in paths.items()
                    if len(template.split("/")) == len(segments)
                    and all(
                        a == b or (a.startswith("{") and a.endswith("}"))
                        for a, b in zip(template.split("/"), segments)
                    )
                ),
                None,
            )
        native = None
        if path_spec is None:
            native = self.native_filters(resource)
            if native is None:
                candidate = resource.replace("_", "-")
                suggestion = " Did you mean " + candidate + "?" if "/api/" + candidate in paths else ""
                raise ValueError(
                    "No filter schema found for resource "
                    + resource
                    + "."
                    + suggestion
                    + " Use discover_models to select the exact resource path; changing filters cannot fix an incorrect path. No inventory query was sent."
                )
            path_spec = {}
        operation = path_spec.get("get", {})
        parameters = path_spec.get("parameters", []) + operation.get("parameters", [])
        allowed = {p.get("name") for p in parameters if p.get("in") == "query"}
        unknown = set(filters) - allowed
        # Dynamic custom-field filters are absent from OpenAPI. The companion asks
        # the real FilterSet under the target view's native permissions.
        if unknown:
            allowed.update(native if native is not None else (self.native_filters(resource) or {}))
            unknown = set(filters) - allowed
        if unknown:
            raise ValueError(
                "Unknown filters for "
                + resource
                + ": "
                + ", ".join(sorted(unknown))
                + ". No query was sent: NetBox may silently ignore unknown filters and return unrelated objects. "
                "Inspect get_schema filters and use a supported exact-match filter; never retry by dropping the intended constraint."
            )

    def describe(self, resource, full=False, action=None):
        resource = self.resolve(resource)
        options = self.api.request("OPTIONS", resource)
        self.load_schema()
        paths = {
            p: value for p, value in self.schema.get("paths", {}).items() if p.startswith("/api/" + resource)
        }
        if action is not None:
            if not isinstance(action, str) or not re.fullmatch(r"[a-zA-Z0-9_-]+", action):
                raise ValueError("action must be a single action name, such as available-ips")
            paths = {p: value for p, value in paths.items() if p.endswith("/" + action + "/")}
            if not paths:
                raise ValueError("Action not found in this resource's schema")
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

        if full:
            collect(paths)
            return {"resource": resource, "options": options, "paths": paths, "schemas": schemas}
        # Response schemas recursively expand many unrelated models. Agents need the
        # actual writable request types, not the whole serializer dependency graph.
        compact_paths = {}
        filters = {}
        for path, methods in paths.items():
            compact_paths[path] = {}
            for method, spec in methods.items():
                if method not in {"get", "post", "put", "patch", "delete", "head", "options"}:
                    continue
                entry = {"tool_path": path.removeprefix("/api/")}
                request = spec.get("requestBody", {})
                content = request.get("content", {})
                request_schema = content.get("application/json", {}).get("schema")
                if request_schema is None and content:
                    request_schema = next(iter(content.values())).get("schema")
                if request_schema is None:
                    request_schema = request.get("schema")
                if request_schema:
                    entry["request"] = request_schema
                    if (action is not None or path == "/api/" + resource) and method == "post":
                        collect(request_schema)
                compact_paths[path][method] = entry
                if path == "/api/" + resource and method == "get":
                    for parameter in spec.get("parameters", []):
                        if parameter.get("in") == "query":
                            filters[parameter["name"]] = parameter.get("schema", {}).get(
                                "type", "see full schema"
                            )

        if action is None:
            for name, metadata in (self.native_filters(resource) or {}).items():
                filters.setdefault(name, metadata.get("type", "native filter"))

        def compact(value):
            if isinstance(value, list):
                return [compact(v) for v in value]
            if isinstance(value, dict):
                return {
                    k: compact(v)
                    for k, v in value.items()
                    if k not in {"description", "title", "example", "examples", "externalDocs"}
                }
            return value

        return {
            "resource": resource,
            "options_status": options["status"],
            "paths": compact_paths,
            "schemas": compact(schemas),
            "filters": filters,
            "guidance": "Schemas expand POST inputs (including bulk alternatives). Use action='available-ips', for example, to focus on a named action without a large response. Updates use writable fields with a fresh ETag. full=true includes full OPTIONS, filter choices, descriptions and response schemas.",
        }
