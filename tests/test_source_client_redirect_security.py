import pytest

from stech_mcp.http.source_client import SourceClient


class FakeResponse:
    def __init__(self, *, url, status_code, headers=None, content=b""):
        self.url = url
        self.status_code = status_code
        self.headers = headers or {}
        self._content = content

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_bytes(self):
        yield self._content


class RedirectAwareFakeClient:
    def __init__(self):
        self.requested = []

    def stream(self, method, url, *, timeout, follow_redirects):
        del method, timeout
        public = "https://public.example/spec"
        private = "http://127.0.0.1/private"
        if url != public:
            raise AssertionError(f"private redirect was requested: {url}")
        self.requested.append(url)

        # Emulate what an auto-following HTTP client would do before returning
        # control to SourceClient: the private destination has already been hit.
        if follow_redirects:
            self.requested.append(private)
            return FakeResponse(url=private, status_code=200, content=b"private")

        return FakeResponse(
            url=public,
            status_code=302,
            headers={"Location": private},
        )

    def close(self):
        pass


def test_redirect_to_private_host_is_rejected_before_private_request():
    http = RedirectAwareFakeClient()
    client = SourceClient(http_client=http, resolve_dns=False)

    with pytest.raises(ValueError, match="private|non-public"):
        client.fetch("https://public.example/spec")

    assert http.requested == ["https://public.example/spec"]
