"""Bounded direct REST transport. Never retries writes or follows redirects."""
import json
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

class NetBox:
    def __init__(self, url, token, timeout=20):
        parsed = urlparse(url)
        if parsed.scheme not in {'http', 'https'} or not parsed.netloc or parsed.username or parsed.query or parsed.fragment:
            raise ValueError('NetBox URL must be an http(s) origin/base path without credentials/query/fragment')
        self.url = url.rstrip('/')
        self.token = token.strip()
        if not self.token or any(c in self.token for c in '\r\n'):
            raise ValueError('Invalid API token')
        self.timeout = timeout
        self.opener = build_opener(NoRedirect())

    def request(self, method, path, data=None, headers=None):
        if path.startswith('/') or '://' in path or '..' in path:
            raise ValueError('Only relative API paths are allowed')
        authorization = ('Bearer ' if self.token.startswith('nbt_') else 'Token ') + self.token
        req = Request(self.url + '/api/' + path,
                      data=None if data is None else json.dumps(data).encode(), method=method,
                      headers={'Authorization': authorization, 'Content-Type': 'application/json', **(headers or {})})
        try:
            response = self.opener.open(req, timeout=self.timeout)
        except HTTPError as exc:
            response = exc
        with response:
            raw = response.read(16 * 1024 * 1024 + 1)
            if len(raw) > 16 * 1024 * 1024:
                raise ValueError('Response exceeds size bound; outcome may be uncertain')
            try:
                body = json.loads(raw) if raw else None
            except ValueError:
                body = {'error': 'Non-JSON response'}
            # Retain only useful receipt headers; no credentials or cookies.
            kept = {k.lower(): v for k, v in response.headers.items()
                    if k.lower() in {'etag', 'x-request-id', 'api-version'}}
            return {'status': response.status, 'headers': kept, 'body': body}

    def get(self, path):
        result = self.request('GET', path)
        if result['status'] != 200:
            raise RuntimeError(f"Read failed: HTTP {result['status']} on {path}")
        return result

    def history(self):
        path = 'core/object-changes/?limit=1000&ordering=id'
        records = []
        visited = set()
        while path:
            if path in visited:
                raise RuntimeError('Repeated history page')
            visited.add(path)
            page = self.get(path)['body']
            records.extend(page['results'])
            nxt = page.get('next')
            if nxt:
                if not nxt.startswith(self.url + '/api/'):
                    raise RuntimeError('History pagination crossed the configured origin')
                path = nxt[len(self.url + '/api/'):]
            else:
                path = None
        return records
