from __future__ import annotations

import json

from stech_mcp.services.vtex_image_client import VtexImageApiError, VtexImageClient
from stech_mcp.services.vtex_product_ensure import VtexProductEnsureService


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


def _http_client(opener):
    return VtexImageClient(
        account_name="ststore227",
        environment="vtexcommercestable.com.br",
        app_key="app-key",
        app_token="app-token",
        timeout_seconds=30,
        opener=opener,
    )


def test_client_exposes_minimal_classic_catalog_product_and_sku_crud_helpers():
    opener = RecordingOpener(
        [
            FakeResponse({"Id": 400, "RefId": "NEW-001"}),
            FakeResponse({"Id": 400, "RefId": "NEW-001"}),
            FakeResponse({"Id": 500, "RefId": "NEW-001-S", "ProductId": 400}),
            FakeResponse({"Id": 500, "RefId": "NEW-001-S", "ProductId": 400}),
        ]
    )
    client = _http_client(opener)

    product_payload = {"Name": "Producto", "RefId": "NEW-001", "CategoryId": 65, "BrandId": 27}
    sku_payload = {"ProductId": 400, "Name": "Producto", "RefId": "NEW-001-S", "IsActive": False}

    assert client.create_product(product_payload)["Id"] == 400
    assert client.get_product(400)["RefId"] == "NEW-001"
    assert client.create_sku(sku_payload)["Id"] == 500
    assert client.get_sku(500)["RefId"] == "NEW-001-S"

    assert opener.calls[0][0].full_url.endswith("/api/catalog/pvt/product")
    assert opener.calls[0][0].get_method() == "POST"
    assert json.loads(opener.calls[0][0].data.decode("utf-8"))["RefId"] == "NEW-001"
    assert opener.calls[1][0].full_url.endswith("/api/catalog/pvt/product/400")
    assert opener.calls[1][0].get_method() == "GET"
    assert opener.calls[2][0].full_url.endswith("/api/catalog/pvt/stockkeepingunit")
    assert opener.calls[2][0].get_method() == "POST"
    assert opener.calls[3][0].full_url.endswith("/api/catalog/pvt/stockkeepingunit/500")
    assert opener.calls[3][0].get_method() == "GET"


class FakeVtexClient:
    def __init__(self, seller_product=None):
        self.seller_product = seller_product
        self.calls = []
        self.product_id = None
        self.sku_id = None

    def get_seller_product_by_external_id(self, partnumber):
        self.calls.append(("lookup_product", partnumber))
        if self.seller_product is None:
            raise VtexImageApiError(
                operation="get_seller_product_by_external_id",
                status=404,
                body="not found",
                url="https://example.invalid/product",
            )
        return self.seller_product

    def create_product(self, payload):
        self.calls.append(("create_product", dict(payload)))
        self.product_id = 400
        return {"Id": 400, "RefId": payload["RefId"]}

    def get_product(self, product_id):
        self.calls.append(("get_product", product_id))
        return {"Id": product_id, "RefId": "NEW-001", "CategoryId": 65, "BrandId": 27}

    def resolve_sku_id(self, ref_id):
        self.calls.append(("resolve_sku", ref_id))
        if self.sku_id is None:
            raise VtexImageApiError(
                operation="resolve_sku_id",
                status=404,
                body="not found",
                url="https://example.invalid/sku",
            )
        return self.sku_id

    def create_sku(self, payload):
        self.calls.append(("create_sku", dict(payload)))
        self.sku_id = 500
        return {"Id": 500, "RefId": payload["RefId"], "ProductId": payload["ProductId"]}

    def get_sku(self, sku_id):
        self.calls.append(("get_sku", sku_id))
        return {"Id": sku_id, "RefId": "NEW-001-S", "ProductId": 400, "IsActive": False}


def test_ensure_existing_exact_product_and_sku_is_idempotent():
    client = FakeVtexClient(
        seller_product={
            "id": "251",
            "externalId": "82YU00XYLM",
            "skus": [{"id": "251", "externalId": "82YU00XYLM-S", "isActive": False}],
        }
    )
    service = VtexProductEnsureService(client)

    result = service.ensure(
        "82YU00XYLM",
        {"product_name": "Laptop Lenovo", "brand": "LENOVO"},
        category_id=65,
        brand_id=27,
    )

    assert result["status"] == "EXISTS"
    assert result["product_id"] == 251
    assert result["sku_id"] == 251
    assert result["product_created"] is False
    assert result["sku_created"] is False
    assert not any(call[0].startswith("create_") for call in client.calls)


def test_ensure_requires_explicit_positive_category_and_brand_before_any_create():
    client = FakeVtexClient(seller_product=None)
    service = VtexProductEnsureService(client)

    result = service.ensure(
        "NEW-001",
        {"product_name": "Producto nuevo"},
        category_id=0,
        brand_id=0,
    )

    assert result["status"] == "REVIEW_REQUIRED"
    assert set(result["blocking_reasons"]) == {"VTEX_CATEGORY_ID_REQUIRED", "VTEX_BRAND_ID_REQUIRED"}
    assert not any(call[0].startswith("create_") for call in client.calls)


def test_ensure_creates_inactive_product_and_sku_then_verifies_exact_refids():
    client = FakeVtexClient(seller_product=None)
    service = VtexProductEnsureService(client)

    result = service.ensure(
        "NEW-001",
        {
            "product_name": "Producto nuevo",
            "package_height_cm": 7,
            "package_length_cm": 49.2,
            "package_width_cm": 31.4,
            "package_weight_g": 2450,
        },
        category_id=65,
        brand_id=27,
    )

    assert result == {
        "status": "CREATED",
        "product_created": True,
        "sku_created": True,
        "product_id": 400,
        "sku_id": 500,
        "product_ref_id": "NEW-001",
        "sku_ref_id": "NEW-001-S",
        "read_back_verified": True,
    }

    product_payload = next(call[1] for call in client.calls if call[0] == "create_product")
    sku_payload = next(call[1] for call in client.calls if call[0] == "create_sku")
    assert product_payload["RefId"] == "NEW-001"
    assert product_payload["CategoryId"] == 65
    assert product_payload["BrandId"] == 27
    assert product_payload["IsVisible"] is False
    assert sku_payload["RefId"] == "NEW-001-S"
    assert sku_payload["ProductId"] == 400
    assert sku_payload["IsActive"] is False
    assert sku_payload["ActivateIfPossible"] is False


def test_ensure_detects_product_created_sku_missing_and_only_creates_sku():
    client = FakeVtexClient(
        seller_product={"id": "400", "externalId": "NEW-001", "skus": []}
    )
    service = VtexProductEnsureService(client)

    result = service.ensure(
        "NEW-001",
        {"product_name": "Producto nuevo"},
        category_id=65,
        brand_id=27,
    )

    assert result["product_created"] is False
    assert result["sku_created"] is True
    assert not any(call[0] == "create_product" for call in client.calls)
    assert any(call[0] == "create_sku" for call in client.calls)
