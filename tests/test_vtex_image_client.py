from __future__ import annotations

import io
import json
from urllib.error import HTTPError

import pytest

from stech_mcp.services.vtex_image_client import VtexImageApiError, VtexImageClient


class FakeResponse:
    def __init__(self, payload, status=200):
        self.status = status
        self._body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")

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
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _client(opener):
    return VtexImageClient(
        account_name="ststore227",
        environment="vtexcommercestable.com.br",
        app_key="app-key",
        app_token="app-token",
        timeout_seconds=30,
        opener=opener,
    )


def test_client_uses_exact_classic_catalog_sku_file_endpoints_and_auth_headers():
    opener = RecordingOpener(
        [
            FakeResponse(251),
            FakeResponse([]),
            FakeResponse({"Id": 520, "SkuId": 251, "ArchiveId": 155467, "IsMain": True, "Label": "Main"}),
        ]
    )
    client = _client(opener)

    sku_id = client.resolve_sku_id("82YU00XYLM-S")
    files = client.list_sku_files(sku_id)
    created = client.create_sku_file(
        sku_id,
        {
            "IsMain": True,
            "Label": "Main",
            "Name": "82YU00XYLM_01.jpg",
            "Url": "https://mcp.artos.pe/vtex-images/signed",
        },
    )

    assert sku_id == 251
    assert files == []
    assert created["Id"] == 520

    resolve_request, resolve_timeout = opener.calls[0]
    assert resolve_request.full_url.endswith(
        "/api/catalog_system/pvt/sku/stockkeepingunitidbyrefid/82YU00XYLM-S"
    )
    assert resolve_request.get_method() == "GET"
    assert resolve_timeout == 30
    assert resolve_request.get_header("X-vtex-api-appkey") == "app-key"
    assert resolve_request.get_header("X-vtex-api-apptoken") == "app-token"

    list_request, _ = opener.calls[1]
    assert list_request.full_url.endswith("/api/catalog/pvt/stockkeepingunit/251/file")
    assert list_request.get_method() == "GET"

    create_request, _ = opener.calls[2]
    assert create_request.full_url.endswith("/api/catalog/pvt/stockkeepingunit/251/file")
    assert create_request.get_method() == "POST"
    assert json.loads(create_request.data.decode("utf-8"))["IsMain"] is True
    assert json.loads(create_request.data.decode("utf-8"))["Name"] == "82YU00XYLM_01.jpg"


def test_client_surfaces_vtex_http_status_operation_and_response_body():
    body = b'{"Message":"Image URL could not be downloaded"}'
    error = HTTPError(
        url="https://ststore227.vtexcommercestable.com.br/api/catalog/pvt/stockkeepingunit/251/file",
        code=400,
        msg="Bad Request",
        hdrs=None,
        fp=io.BytesIO(body),
    )
    client = _client(RecordingOpener([error]))

    with pytest.raises(VtexImageApiError) as caught:
        client.list_sku_files(251)

    assert caught.value.status == 400
    assert caught.value.operation == "list_sku_files"
    assert "Image URL could not be downloaded" in str(caught.value)
