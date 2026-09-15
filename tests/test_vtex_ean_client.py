from __future__ import annotations

import json

from stech_mcp.services.vtex_ean_client import VtexEanClient


class FakeResponse:
    def __init__(self, payload, status=200):
        self.status = status
        if isinstance(payload, bytes):
            self._body = payload
        elif payload is None:
            self._body = b""
        else:
            self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class RecordingOpener:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, request, timeout):
        self.calls.append((request, timeout))
        return self.responses.pop(0)


def client_with(responses):
    opener = RecordingOpener(responses)
    client = VtexEanClient(
        account_name="ststore227",
        environment="vtexcommercestable.com.br",
        app_key="app-key",
        app_token="app-token",
        timeout_seconds=30,
        opener=opener,
    )
    return client, opener


def test_get_sku_eans_uses_official_catalog_endpoint():
    client, opener = client_with([FakeResponse(["0197528523880"])])

    assert client.get_sku_eans(251) == ["0197528523880"]

    request, timeout = opener.calls[0]
    assert request.full_url.endswith("/api/catalog/pvt/stockkeepingunit/251/ean")
    assert request.get_method() == "GET"
    assert timeout == 30


def test_create_sku_ean_posts_path_value_without_body():
    client, opener = client_with([FakeResponse(None, status=200)])

    assert client.create_sku_ean(251, "0197528523880") == {}

    request, timeout = opener.calls[0]
    assert request.full_url.endswith(
        "/api/catalog/pvt/stockkeepingunit/251/ean/0197528523880"
    )
    assert request.get_method() == "POST"
    assert request.data is None
    assert timeout == 30
