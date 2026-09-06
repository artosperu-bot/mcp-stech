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

def test_client_reads_sku_context_from_catalog_system():
    opener = RecordingOpener(
        [
            FakeResponse(
                {
                    "Id": 251,
                    "ProductRefId": "82YU00XYLM",
                    "ManufacturerCode": "82YU00XYLM",
                    "AlternateIds": {"RefId": "82YU00XYLM-S"},
                    "Images": [],
                }
            )
        ]
    )
    client = _client(opener)

    context = client.get_sku_context(251)

    assert context["Id"] == 251
    assert context["AlternateIds"]["RefId"] == "82YU00XYLM-S"
    request, timeout = opener.calls[0]
    assert request.full_url.endswith(
        "/api/catalog_system/pvt/sku/stockkeepingunitbyid/251"
    )
    assert request.get_method() == "GET"
    assert timeout == 30


def test_api_error_exposes_structured_diagnostic_fields():
    error = VtexImageApiError(
        operation="list_sku_files",
        status=500,
        body="",
        url="https://ststore227.vtexcommercestable.com.br/api/catalog/pvt/stockkeepingunit/251/file",
    )

    detail = error.as_dict()

    assert detail == {
        "exception_type": "VtexImageApiError",
        "operation": "list_sku_files",
        "status_http": 500,
        "url": "https://ststore227.vtexcommercestable.com.br/api/catalog/pvt/stockkeepingunit/251/file",
        "body": "",
        "message": "VTEX HTTP 500 en list_sku_files: sin detalle",
    }


def _seller_product():
    return {
        "id": "251",
        "externalId": "82YU00XYLM",
        "status": "active",
        "name": "Laptop Lenovo V15 G4 AMN",
        "description": "Descripcion",
        "brandId": "27",
        "brandName": "LENOVO",
        "categoryIds": ["519"],
        "categoryNames": ["/coolboxpe/Computo/Laptops/"],
        "specs": [],
        "attributes": [{"name": "Modelo", "value": "V15 G4 AMN"}],
        "slug": "laptop-lenovo-v15-g4-amn-82yu00xylm",
        "images": [],
        "skus": [
            {
                "id": "251",
                "externalId": "82YU00XYLM-S",
                "ean": "0197528523880",
                "manufacturerCode": "82YU00XYLM",
                "isActive": False,
                "name": "Laptop Lenovo V15 G4 AMN",
                "weight": 2450,
                "dimensions": {"width": 31.4, "height": 7, "length": 49.2},
                "specs": [],
                "images": [],
            }
        ],
        "origin": "ststore227",
    }


def test_client_reads_catalog_v2_product_by_external_id_and_updates_by_id():
    product = _seller_product()
    opener = RecordingOpener([FakeResponse(product), FakeResponse(b"", status=204)])
    client = _client(opener)

    fetched = client.get_seller_product_by_external_id("82YU00XYLM")
    result = client.update_seller_product("251", product)

    assert fetched["id"] == "251"
    assert result == {}

    get_request, _ = opener.calls[0]
    assert get_request.full_url.endswith(
        "/api/catalog-seller-portal/products/external-id=82YU00XYLM"
    )
    assert get_request.get_method() == "GET"

    put_request, _ = opener.calls[1]
    assert put_request.full_url.endswith("/api/catalog-seller-portal/products/251")
    assert put_request.get_method() == "PUT"
    payload = json.loads(put_request.data.decode("utf-8"))
    assert payload["status"] == "active"
    assert payload["skus"][0]["isActive"] is False


def test_client_gets_local_token_and_uploads_catalog_image(tmp_path):
    image_path = tmp_path / "82YU00XYLM_01.jpg"
    image_path.write_bytes(b"jpeg-bytes-here")
    uploaded = {
        "id": "82YU00XYLM_01.jpg",
        "slug": "/assets/vtex.catalog-images/products/82YU00XYLM_01___hash.jpg",
        "fullUrl": "https://ststore227.vtexassets.com/assets/vtex.catalog-images/products/82YU00XYLM_01___hash.jpg",
    }
    opener = RecordingOpener(
        [
            FakeResponse({"authStatus": "Success", "token": "local-token", "expires": 1788695926}),
            FakeResponse(uploaded),
        ]
    )
    client = _client(opener)

    token = client.get_local_token()
    result = client.upload_catalog_image(image_path, token=token)

    assert token == "local-token"
    assert result["id"] == "82YU00XYLM_01.jpg"
    assert result["fullUrl"].startswith("https://ststore227.vtexassets.com/")

    auth_request, _ = opener.calls[0]
    assert auth_request.full_url == (
        "https://api.vtexcommercestable.com.br/api/vtexid/apptoken/login?an=ststore227"
    )
    assert auth_request.get_method() == "POST"
    auth_payload = json.loads(auth_request.data.decode("utf-8"))
    assert auth_payload == {"appkey": "app-key", "apptoken": "app-token"}

    upload_request, _ = opener.calls[1]
    assert upload_request.full_url.endswith(
        "/vtex.catalog-images/v0/ststore227/master/images/save/82YU00XYLM_01.jpg"
    )
    assert upload_request.get_method() == "POST"
    assert upload_request.get_header("Vtexidclientautcookie") == "local-token"
    assert upload_request.get_header("Content-type").startswith("multipart/form-data; boundary=")
    assert b'filename="82YU00XYLM_01.jpg"' in upload_request.data
    assert b"jpeg-bytes-here" in upload_request.data


def test_catalog_image_conflict_reuses_existing_asset_url(tmp_path):
    image_path = tmp_path / "82YU00XYLM_01.jpg"
    image_path.write_bytes(b"jpeg")
    conflict_url = (
        "https://ststore227.vtexassets.com/assets/vtex.catalog-images/products/"
        "82YU00XYLM_01___da4a579c26e9e4210d43e0e6beff18ba.jpg"
    )
    error = HTTPError(
        url=(
            "https://app.io.vtex.com/vtex.catalog-images/v0/ststore227/master/"
            "images/save/82YU00XYLM_01.jpg"
        ),
        code=409,
        msg="Conflict",
        hdrs=None,
        fp=io.BytesIO(json.dumps({"url": conflict_url}).encode("utf-8")),
    )
    client = _client(RecordingOpener([error]))

    result = client.upload_catalog_image(image_path, token="local-token")

    assert result == {
        "id": "82YU00XYLM_01.jpg",
        "fullUrl": conflict_url,
        "conflict": True,
    }
