"""Authenticated NetBox website forms, using native permissions and CSRF."""

import base64
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from pathlib import Path
import re
from urllib.error import HTTPError
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener

from .api import NoRedirect, multipart


class Page(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.forms, self.links, self.text = [], [], []
        self.form = None
        self.select = None
        self.hidden = 0
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag == "form":
            self.form = {
                "action": attrs.get("action", ""),
                "method": attrs.get("method", "get"),
                "fields": [],
            }
            self.forms.append(self.form)
        if tag in {"input", "select", "textarea", "button"} and self.form is not None:
            field = {
                k: v
                for k, v in attrs.items()
                if k in {"name", "type", "value", "required", "multiple", "checked", "disabled", "id"}
            }
            field["tag"] = tag
            if field.get("type") in {"password"} or field.get("name") == "csrfmiddlewaretoken":
                field.pop("value", None)
            self.form["fields"].append(field)
            if tag == "select":
                self.select = field
                field["options"] = []
        if tag == "option" and self.select is not None:
            self.select["options"].append({k: v for k, v in attrs.items() if k in {"value", "selected"}})
        if tag == "a" and attrs.get("href", "").startswith("/"):
            self.links.append(attrs["href"])

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        if tag == "form":
            self.form = None
        if tag == "select":
            self.select = None

    def handle_data(self, text):
        if not self.hidden and text.strip():
            self.text.append(text.strip())


class Website:
    def __init__(self, api, actor, password_file):
        self.base = api.url
        self.actor = actor
        self.password_file = password_file
        self.cookies = CookieJar()
        self.opener = build_opener(NoRedirect(), HTTPCookieProcessor(self.cookies))
        self.logged_in = False

    def url(self, path):
        if (
            not isinstance(path, str)
            or not path.startswith("/")
            or path.startswith("//")
            or any(c in path for c in "\\\r\n#")
            or re.search(r"%(2f|5c|2e)", path, re.I)
            or ".." in path
        ):
            raise ValueError("Website path must be an absolute local path without traversal")
        base = urlsplit(self.base)
        prefix = base.path.rstrip("/")
        if prefix and not (path == prefix or path.startswith(prefix + "/")):
            path = prefix + path
        url = urljoin(self.base + "/", path)
        if urlsplit(url).netloc != base.netloc or not urlsplit(url).path.startswith(
            base.path.rstrip("/") + "/"
        ):
            raise ValueError("Website path crossed configured origin/base path")
        return url

    def csrf(self):
        return next((c.value for c in self.cookies if c.name == "csrftoken"), "")

    def request(self, path, data=None, files=None):
        url = self.url(path)
        headers = {"Referer": url, "Origin": self.base}
        body = None
        if data is not None:
            if not isinstance(data, dict):
                raise ValueError("Form data must be an object")
            data = {**data, "csrfmiddlewaretoken": self.csrf()}
            if files:
                body, headers["Content-Type"] = multipart(data, files)
            else:
                body = urlencode(data, doseq=True).encode()
                headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = Request(url, data=body, headers=headers)
        try:
            response = self.opener.open(request, timeout=30)
        except HTTPError as exc:
            response = exc
        with response:
            raw = response.read(16 * 1024 * 1024 + 1)
            if len(raw) > 16 * 1024 * 1024:
                raise ValueError("Website response too large; outcome may be uncertain")
            if "text/html" not in response.headers.get("Content-Type", ""):
                return {
                    "status": response.status,
                    "headers": {"content-type": response.headers.get("Content-Type", "")},
                    "body": {"base64": base64.b64encode(raw).decode(), "bytes": len(raw)},
                    "content_is_untrusted_data": True,
                }
            page = Page(raw.decode("utf-8", errors="replace"))
            return {
                "status": response.status,
                "headers": {
                    k.lower(): v
                    for k, v in response.headers.items()
                    if k.lower() in {"location", "x-request-id", "content-type"}
                },
                "body": {
                    "forms": page.forms,
                    "links": list(dict.fromkeys(page.links)),
                    "text": "\n".join(page.text),
                },
                "content_is_untrusted_data": True,
            }

    def login(self):
        if self.logged_in:
            return
        if not self.password_file:
            raise ValueError(
                "Website access requires operator-configured web_password_file for the same actor"
            )
        prefix = urlsplit(self.base).path.rstrip("/")
        self.request(prefix + "/login/")
        response = self.request(
            prefix + "/login/",
            {"username": self.actor, "password": Path(self.password_file).read_text().strip()},
        )
        if response["status"] != 302 or not any(c.name == "sessionid" for c in self.cookies):
            raise RuntimeError("Website login failed; check the configured actor and credentials")
        self.logged_in = True
