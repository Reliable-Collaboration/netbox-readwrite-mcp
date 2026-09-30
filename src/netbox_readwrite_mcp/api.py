"""Bounded direct REST transport. Never retries writes or follows redirects."""

import base64
import json
import uuid
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class NetBox:
    def __init__(self, url, token, timeout=20):
        parsed = urlparse(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "NetBox URL must be an http(s) origin/base path without credentials/query/fragment"
            )
        self.url = url.rstrip("/")
        self.token = token.strip()
        if not self.token or any(c in self.token for c in "\r\n"):
            raise ValueError("Invalid API token")
        self.timeout = timeout
        self.opener = build_opener(NoRedirect())

    def request(self, method, path, data=None, headers=None, files=None):
        if path.startswith("/") or "://" in path or ".." in path:
            raise ValueError("Only relative API paths are allowed")
        return self._send(method, self.url + "/api/" + path, data, headers, files)

    def graphql(self, query, variables):
        return self._send("POST", self.url + "/graphql/", {"query": query, "variables": variables})

    def _send(self, method, url, data=None, headers=None, files=None):
        raw = None if data is None else json.dumps(data).encode()
        content_type = "application/json"
        if files:
            raw, content_type = multipart(data or {}, files)
        authorization = ("Bearer " if self.token.startswith("nbt_") else "Token ") + self.token
        req = Request(
            url,
            data=raw,
            method=method,
            headers={"Authorization": authorization, "Content-Type": content_type, **(headers or {})},
        )
        try:
            response = self.opener.open(req, timeout=self.timeout)
        except HTTPError as exc:
            response = exc
        with response:
            raw = response.read(16 * 1024 * 1024 + 1)
            if len(raw) > 16 * 1024 * 1024:
                raise ValueError("Response exceeds size bound; outcome may be uncertain")
            try:
                body = json.loads(raw) if raw else None
            except ValueError:
                body = {"error": "Non-JSON response"}
            # Retain only useful receipt headers; no credentials or cookies.
            kept = {
                k.lower(): v
                for k, v in response.headers.items()
                if k.lower() in {"etag", "x-request-id", "api-version"}
            }
            return {"status": response.status, "headers": kept, "body": body}

    def get(self, path):
        result = self.request("GET", path)
        if result["status"] != 200:
            raise RuntimeError(f"Read failed: HTTP {result['status']} on {path}")
        return result

    def history(self):
        path = "core/object-changes/?limit=1000&ordering=id"
        records = []
        visited = set()
        while path:
            if path in visited:
                raise RuntimeError("Repeated history page")
            visited.add(path)
            page = self.get(path)["body"]
            records.extend(page["results"])
            nxt = page.get("next")
            if nxt:
                if not nxt.startswith(self.url + "/api/"):
                    raise RuntimeError("History pagination crossed the configured origin")
                path = nxt[len(self.url + "/api/") :]
            else:
                path = None
        return records


def multipart(data, files):
    """Encode explicit in-memory uploads; never reads agent-supplied filesystem paths."""
    if not isinstance(data, dict) or not isinstance(files, list):
        raise ValueError("Multipart data must be an object and files a list")
    boundary = "netboxrw" + uuid.uuid4().hex
    chunks = []

    def part(name, value, filename=None, content_type=None):
        if not isinstance(name, str) or any(c in name for c in '\r\n"'):
            raise ValueError("Invalid multipart field name")
        disposition = f'Content-Disposition: form-data; name="{name}"'
        if filename is not None:
            if not isinstance(filename, str) or any(c in filename for c in '\r\n"/\\'):
                raise ValueError("Invalid filename")
            disposition += f'; filename="{filename}"'
        chunks.append(f"--{boundary}\r\n{disposition}\r\n".encode())
        if content_type:
            if not isinstance(content_type, str) or any(c in content_type for c in "\r\n"):
                raise ValueError("Invalid content type")
            chunks.append(f"Content-Type: {content_type}\r\n".encode())
        chunks.extend([b"\r\n", value, b"\r\n"])

    for key, value in data.items():
        for item in value if isinstance(value, list) else [value]:
            part(key, str(item).encode())
    for file in files:
        if not isinstance(file, dict) or not {"field", "filename", "base64"} <= file.keys():
            raise ValueError("Files require field, filename and base64")
        part(
            file["field"],
            base64.b64decode(file["base64"], validate=True),
            file["filename"],
            file.get("content_type", "application/octet-stream"),
        )
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), "multipart/form-data; boundary=" + boundary
