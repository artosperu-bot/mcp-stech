from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from stech_mcp.services.vtex_image_client import VtexImageApiError
from stech_mcp.services.vtex_image_sync import VtexImageSyncService


class FakeLocalImageService:
    def __init__(self, images, state="READY", reason=None):
        self.images = [dict(row) for row in images]
        self.state = state
        self.reason = reason
        self.sync_calls = []
        self.validate_calls = []

    def sync(self, partnumber: str):
        self.sync_calls.append(partnumber)
        return {
            "found": True,
            "partnumber": partnumber,
            "state": self.state,
            "reason": self.reason,
            "image_count": len(self.images),
            "images": [dict(row) for row in self.images],
            "errors": [],
        }

    def validate(self, partnumber: str):
        self.validate_calls.append(partnumber)
        return {
            "found": True,
            "partnumber": partnumber,
            "state": self.state,
            "reason": self.reason,
            "image_count": len(self.images),
            "images": [dict(row) for row in self.images],
        }


class FakeSigner:
    def sign(self, *, product_image_id: int, partnumber: str):
        raise AssertionError("CatalogV2 flow must not use public signed URLs")


def _seller_product(*, with_legacy=False):
    images = []
    sku_images = []
    if with_legacy:
        images = [
            {
                "id": "legacy.jpg",
                "url": "https://ststore227.vtexassets.com/assets/vtex.catalog-images/products/legacy.jpg",
                "alt": "Legacy",
            }
        ]
        sku_images = ["legacy.jpg"]
    return {
        "id": "251",
        "externalId": "82YU00XYLM",
        "status": "active",
        "name": "Laptop Lenovo V15 G4 AMN Ryzen 5 7520U",
        "description": "Descripcion actual que debe preservarse",
        "brandId": "27",
        "brandName": "LENOVO",
        "categoryIds": ["519"],
        "categoryNames": ["/coolboxpe/Computo/Laptops/"],
        "specs": [],
        "attributes": [
            {"name": "Modelo", "value": "V15 G4 AMN", "groupName": "Attribute List"},
            {"name": "Memoria RAM", "value": "16 GB", "groupName": "Attribute List"},
        ],
        "slug": "laptop-lenovo-v15-g4-amn-82yu00xylm",
        "images": images,
        "skus": [
            {
                "id": "251",
                "externalId": "82YU00XYLM-S",
                "ean": "0197528523880",
                "manufacturerCode": "82YU00XYLM",
                "isActive": False,
                "name": "Laptop Lenovo V15 G4 AMN Ryzen 5 7520U",
                "weight": 2450,
                "dimensions": {"width": 31.4, "height": 7, "length": 49.2},
                "specs": [],
                "images": sku_images,
            }
        ],
        "origin": "ststore227",
        "createdAt": "2026-09-01T00:00:00Z",
        "updatedAt": "2026-09-05T00:00:00Z",
    }


class FakeVtexClient:
    def __init__(self, product=None):
        self.account_name = "ststore227"
        self.environment = "vtexcommercestable.com.br"
        self.product = deepcopy(product or _seller_product())
        self.product_reads = []
        self.product_id_reads = []
        self.token_calls = 0
        self.upload_calls = []
        self.update_calls = []
        self.upload_error_at = None
        self.conflict_names = set()
        self.classic_pvt_calls = []

    def get_seller_product_by_external_id(self, external_id: str):
        self.product_reads.append(external_id)
        return deepcopy(self.product)

    def get_seller_product(self, product_id: str):
        self.product_id_reads.append(str(product_id))
        return deepcopy(self.product)

    def get_local_token(self):
        self.token_calls += 1
        return "local-token"

    def upload_catalog_image(self, file_path, *, token: str):
        file_name = Path(file_path).name
        self.upload_calls.append((str(file_path), token))
        if self.upload_error_at == file_name:
            raise VtexImageApiError(
                operation="upload_catalog_image",
                status=500,
                body="upload failed",
                url=f"https://app.io.vtex.com/images/save/{file_name}",
            )
        return {
            "id": file_name,
            "fullUrl": (
                "https://ststore227.vtexassets.com/assets/vtex.catalog-images/products/"
                f"{file_name.replace('.jpg', '')}___hash.jpg"
            ),
            "conflict": file_name in self.conflict_names,
        }

    def update_seller_product(self, product_id: str, payload: dict):
        self.update_calls.append((str(product_id), deepcopy(payload)))
        updated = deepcopy(payload)
        updated["brandName"] = self.product.get("brandName")
        updated["categoryNames"] = deepcopy(self.product.get("categoryNames"))
        updated["createdAt"] = self.product.get("createdAt")
        updated["updatedAt"] = "2026-09-06T00:00:00Z"
        self.product = updated
        return {}

    # Regression guard: CatalogV2 sync must not touch broken Classic Catalog PVT.
    def list_sku_files(self, sku_id: int):
        self.classic_pvt_calls.append(("GET", sku_id))
        raise AssertionError("Classic Catalog PVT must not be called for CatalogV2 images")

    def create_sku_file(self, sku_id: int, payload: dict):
        self.classic_pvt_calls.append(("POST", sku_id))
        raise AssertionError("Classic Catalog PVT must not be called for CatalogV2 images")


class FakePublicationRepository:
    def __init__(self):
        self.rows = []

    def get_publications(self, *, partnumber: str, account_code: str, remote_sku_id: int):
        return [
            dict(row)
            for row in self.rows
            if row["partnumber"] == partnumber
            and row["account_code"] == account_code
            and int(row["remote_sku_id"]) == int(remote_sku_id)
        ]

    def upsert_publication(self, **row):
        key = (row["account_code"], int(row["remote_sku_id"]), int(row["product_image_id"]))
        self.rows = [
            existing
            for existing in self.rows
            if (
                existing["account_code"],
                int(existing["remote_sku_id"]),
                int(existing["product_image_id"]),
            )
            != key
        ]
        stored = {"product_image_publication_id": len(self.rows) + 1, **row}
        self.rows.append(stored)
        return dict(stored)

    def mark_verified(self, **row):
        return self.upsert_publication(status="VERIFIED", **row)


class FakeAuditRepository:
    def __init__(self):
        self.events = []

    def add_audit_event(self, **event):
        self.events.append(dict(event))


def _images():
    return [
        {
            "product_image_id": position,
            "partnumber": "82YU00XYLM",
            "storage_path": str(Path(f"82YU00XYLM_{position:02d}.jpg")),
            "position": position,
            "is_main": position == 1,
            "is_approved": True,
            "sha256_hash": f"{position:064x}",
            "format": "JPEG",
        }
        for position in range(1, 5)
    ]


def _service(vtex, publications=None, audit=None, local=None):
    return VtexImageSyncService(
        local_service=local or FakeLocalImageService(_images()),
        vtex_client=vtex,
        publication_repository=publications or FakePublicationRepository(),
        signer=FakeSigner(),
        audit_repository=audit or FakeAuditRepository(),
    )


def _target_sku(payload):
    return next(row for row in payload["skus"] if str(row["id"]) == "251")


def test_sync_catalog_v2_uploads_assets_updates_only_images_and_puts_01_first():
    original = _seller_product()
    vtex = FakeVtexClient(original)
    publications = FakePublicationRepository()
    audit = FakeAuditRepository()
    service = _service(vtex, publications=publications, audit=audit)

    result = service.sync("82YU00XYLM", account_code="VTEX_STECH")

    assert result["state"] == "SYNCED"
    assert result["transport"] == "catalog_seller_portal"
    assert result["remote_sku_id"] == 251
    assert result["uploaded_count"] == 4
    assert result["verified_count"] == 4
    assert result["product_update_performed"] is True
    assert vtex.token_calls == 1
    assert [Path(path).name for path, _ in vtex.upload_calls] == [
        "82YU00XYLM_01.jpg",
        "82YU00XYLM_02.jpg",
        "82YU00XYLM_03.jpg",
        "82YU00XYLM_04.jpg",
    ]
    assert len(vtex.update_calls) == 1
    _, payload = vtex.update_calls[0]
    assert [row["id"] for row in payload["images"]] == [
        "82YU00XYLM_01.jpg",
        "82YU00XYLM_02.jpg",
        "82YU00XYLM_03.jpg",
        "82YU00XYLM_04.jpg",
    ]
    assert _target_sku(payload)["images"] == [
        "82YU00XYLM_01.jpg",
        "82YU00XYLM_02.jpg",
        "82YU00XYLM_03.jpg",
        "82YU00XYLM_04.jpg",
    ]

    # Guardrails: every non-image field is copied, not mutated.
    assert payload["status"] == original["status"]
    assert payload["description"] == original["description"]
    assert payload["brandId"] == original["brandId"]
    assert payload["categoryIds"] == original["categoryIds"]
    assert payload["attributes"] == [
        {"name": row["name"], "value": row["value"]}
        for row in original["attributes"]
    ]
    assert payload["slug"] == original["slug"]
    assert _target_sku(payload)["isActive"] is original["skus"][0]["isActive"]
    assert _target_sku(payload)["ean"] == original["skus"][0]["ean"]
    assert _target_sku(payload)["weight"] == original["skus"][0]["weight"]
    assert _target_sku(payload)["dimensions"] == original["skus"][0]["dimensions"]
    assert vtex.classic_pvt_calls == []
    assert all(row["status"] == "VERIFIED" for row in publications.rows)
    assert audit.events[-1]["event_type"] == "VTEX_IMAGES_SYNC"


def test_sync_preserves_preexisting_images_and_makes_01_first_without_deleting_anything():
    vtex = FakeVtexClient(_seller_product(with_legacy=True))
    service = _service(vtex)

    result = service.sync("82YU00XYLM")

    assert result["state"] == "SYNCED"
    _, payload = vtex.update_calls[0]
    assert [row["id"] for row in payload["images"]] == [
        "82YU00XYLM_01.jpg",
        "82YU00XYLM_02.jpg",
        "82YU00XYLM_03.jpg",
        "82YU00XYLM_04.jpg",
        "legacy.jpg",
    ]
    assert _target_sku(payload)["images"] == [
        "82YU00XYLM_01.jpg",
        "82YU00XYLM_02.jpg",
        "82YU00XYLM_03.jpg",
        "82YU00XYLM_04.jpg",
        "legacy.jpg",
    ]


def test_second_sync_is_idempotent_and_does_not_upload_or_put_again():
    vtex = FakeVtexClient()
    service = _service(vtex)

    first = service.sync("82YU00XYLM")
    upload_count = len(vtex.upload_calls)
    put_count = len(vtex.update_calls)
    second = service.sync("82YU00XYLM")

    assert first["state"] == "SYNCED"
    assert upload_count == 4
    assert put_count == 1
    assert second["state"] == "SYNCED"
    assert second["uploaded_count"] == 0
    assert second["product_update_performed"] is False
    assert len(vtex.upload_calls) == 4
    assert len(vtex.update_calls) == 1


def test_manual_01_asset_conflict_is_reused_and_other_assets_are_uploaded():
    vtex = FakeVtexClient()
    vtex.conflict_names.add("82YU00XYLM_01.jpg")
    service = _service(vtex)

    result = service.sync("82YU00XYLM")

    assert result["state"] == "SYNCED"
    assert result["uploaded_count"] == 3
    assert result["asset_reused_count"] == 1
    assert result["verified_count"] == 4
    _, payload = vtex.update_calls[0]
    assert _target_sku(payload)["images"][0] == "82YU00XYLM_01.jpg"


def test_status_uses_seller_portal_and_never_calls_broken_classic_catalog_pvt():
    vtex = FakeVtexClient(_seller_product(with_legacy=True))
    status = _service(vtex).status("82YU00XYLM")

    assert status["state"] == "READY"
    assert status["transport"] == "catalog_seller_portal"
    assert status["remote_sku_id"] == 251
    assert status["remote_image_count"] == 1
    assert status["remote_main_file"]["name"] == "legacy.jpg"
    assert vtex.classic_pvt_calls == []


def test_status_reports_synced_only_when_all_local_images_exist_and_01_is_first():
    product = _seller_product()
    product["images"] = [
        {
            "id": f"82YU00XYLM_{position:02d}.jpg",
            "url": f"https://ststore227.vtexassets.com/{position}.jpg",
        }
        for position in range(1, 5)
    ]
    product["skus"][0]["images"] = [f"82YU00XYLM_{position:02d}.jpg" for position in range(1, 5)]
    vtex = FakeVtexClient(product)

    status = _service(vtex).status("82YU00XYLM")

    assert status["state"] == "SYNCED"
    assert status["remote_main_file"]["name"] == "82YU00XYLM_01.jpg"


def test_missing_01_stops_before_any_vtex_write():
    images = [row for row in _images() if row["position"] != 1]
    local = FakeLocalImageService(images, state="REVIEW", reason="main_image_01_missing")
    vtex = FakeVtexClient()
    service = _service(vtex, local=local)

    result = service.sync("82YU00XYLM")

    assert result["state"] == "REVIEW"
    assert result["reason"] == "main_image_01_missing"
    assert vtex.product_reads == []
    assert vtex.upload_calls == []
    assert vtex.update_calls == []


def test_sync_stops_before_product_put_when_catalog_image_upload_fails():
    vtex = FakeVtexClient()
    vtex.upload_error_at = "82YU00XYLM_02.jpg"
    audit = FakeAuditRepository()
    service = _service(vtex, audit=audit)

    result = service.sync("82YU00XYLM")

    assert result["state"] == "ERROR"
    assert result["reason"] == "vtex_catalog_images_unavailable"
    assert result["write_blocked"] is True
    assert [Path(path).name for path, _ in vtex.upload_calls] == [
        "82YU00XYLM_01.jpg",
        "82YU00XYLM_02.jpg",
    ]
    assert vtex.update_calls == []
    assert result["vtex_error"]["stage"] == "upload_catalog_image"
    assert audit.events[-1]["detail"]["reason"] == "vtex_catalog_images_unavailable"


def test_sync_blocks_origin_mismatch_before_asset_or_product_write():
    product = _seller_product()
    product["origin"] = "marketplace"
    vtex = FakeVtexClient(product)
    service = _service(vtex)

    result = service.sync("82YU00XYLM")

    assert result["state"] == "BLOCKED"
    assert result["reason"] == "seller_portal_origin_mismatch"
    assert vtex.upload_calls == []
    assert vtex.update_calls == []
