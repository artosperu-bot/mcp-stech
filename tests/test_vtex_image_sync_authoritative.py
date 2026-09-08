from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from stech_mcp.services.vtex_image_sync_authoritative import VtexImageSyncService


PARTNUMBER = "82YU00XYLM"


def _image(position: int, *, image_id: int | None = None, hash_marker: str | None = None) -> dict:
    return {
        "product_image_id": int(image_id if image_id is not None else position),
        "partnumber": PARTNUMBER,
        "storage_path": str(Path(f"{PARTNUMBER}_{position:02d}.jpg")),
        "position": position,
        "is_main": position == 1,
        "is_approved": True,
        "sha256_hash": (hash_marker or f"{position:064x}")[:64].ljust(64, "0"),
        "format": "JPEG",
    }


def _asset_id(position: int) -> str:
    return f"{PARTNUMBER}_{position:02d}.jpg"


def _asset(asset_id: str) -> dict:
    return {
        "id": asset_id,
        "url": f"https://ststore227.vtexassets.com/assets/vtex.catalog-images/products/{asset_id}",
    }


def _product(target_ids: list[str], *, extra_product_ids: list[str] | None = None) -> dict:
    product_ids = list(target_ids)
    for value in extra_product_ids or []:
        if value not in product_ids:
            product_ids.append(value)
    return {
        "id": "251",
        "externalId": PARTNUMBER,
        "status": "active",
        "name": "Laptop Lenovo V15 G4 AMN",
        "description": "Descripcion actual",
        "brandId": "27",
        "categoryIds": ["519"],
        "specs": [],
        "attributes": [],
        "slug": "laptop-lenovo-v15-g4-amn-82yu00xylm",
        "images": [_asset(value) for value in product_ids],
        "skus": [
            {
                "id": "251",
                "externalId": f"{PARTNUMBER}-S",
                "manufacturerCode": PARTNUMBER,
                "name": "Laptop Lenovo V15 G4 AMN",
                "ean": "0197528523880",
                "isActive": False,
                "weight": 2450,
                "dimensions": {"width": 31.4, "height": 7, "length": 49.2},
                "specs": [],
                "images": list(target_ids),
            }
        ],
        "origin": "ststore227",
    }


class FakeLocalImageService:
    def __init__(self, images: list[dict]):
        self.images = [dict(row) for row in images]

    def sync(self, partnumber: str):
        assert partnumber == PARTNUMBER
        return {
            "found": True,
            "partnumber": partnumber,
            "state": "READY",
            "reason": None,
            "image_count": len(self.images),
            "images": [dict(row) for row in self.images],
            "errors": [],
        }

    def validate(self, partnumber: str):
        return self.sync(partnumber)


class FakePublicationRepository:
    def __init__(self, rows: list[dict] | None = None):
        self.rows = [dict(row) for row in (rows or [])]

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
            current
            for current in self.rows
            if (
                current["account_code"],
                int(current["remote_sku_id"]),
                int(current["product_image_id"]),
            )
            != key
        ]
        stored = {"product_image_publication_id": len(self.rows) + 1, **row}
        self.rows.append(stored)
        return dict(stored)

    def mark_verified(self, **row):
        clean = dict(row)
        clean.pop("status", None)
        clean["status"] = "VERIFIED"
        clean["last_error"] = None
        return self.upsert_publication(**clean)


class FakeAuditRepository:
    def __init__(self):
        self.events = []

    def add_audit_event(self, **event):
        self.events.append(dict(event))


class FakeVtexClient:
    def __init__(self, product: dict):
        self.account_name = "ststore227"
        self.environment = "vtexcommercestable.com.br"
        self.product = deepcopy(product)
        self.upload_calls: list[tuple[str, str]] = []
        self.update_calls: list[tuple[str, dict]] = []
        self.token_calls = 0

    def resolve_sku_id(self, ref_id: str):
        assert ref_id == f"{PARTNUMBER}-S"
        return 251

    def get_sku_context(self, sku_id: int):
        return {"Id": sku_id, "ProductId": 251, "ProductRefId": PARTNUMBER}

    def get_seller_product(self, product_id: str):
        assert str(product_id) == "251"
        return deepcopy(self.product)

    def get_local_token(self):
        self.token_calls += 1
        return "token"

    def upload_catalog_image(self, file_path, *, token: str, file_name: str | None = None):
        name = str(file_name or Path(file_path).name)
        self.upload_calls.append((Path(file_path).name, name))
        return {
            "id": name,
            "fullUrl": f"https://ststore227.vtexassets.com/assets/vtex.catalog-images/products/{name}",
            "conflict": False,
        }

    def update_seller_product(self, product_id: str, payload: dict):
        self.update_calls.append((str(product_id), deepcopy(payload)))
        self.product = deepcopy(payload)
        return {}


def _verified_rows(images: list[dict]) -> list[dict]:
    return [
        {
            "product_image_publication_id": index,
            "product_image_id": int(image["product_image_id"]),
            "partnumber": PARTNUMBER,
            "channel": "VTEX",
            "account_code": "VTEX_STECH",
            "remote_sku_id": 251,
            "remote_file_id": None,
            "remote_archive_id": None,
            "remote_url": f"https://ststore227.vtexassets.com/{image['position']}.jpg",
            "position": int(image["position"]),
            "is_main": int(image["position"]) == 1,
            "status": "VERIFIED",
        }
        for index, image in enumerate(images, start=1)
    ]


def _service(images: list[dict], product: dict, publications: list[dict] | None = None):
    vtex = FakeVtexClient(product)
    repo = FakePublicationRepository(publications)
    service = VtexImageSyncService(
        local_service=FakeLocalImageService(images),
        vtex_client=vtex,
        publication_repository=repo,
        signer=None,
        audit_repository=FakeAuditRepository(),
    )
    return service, vtex, repo


def _target_ids(product: dict) -> list[str]:
    return list(product["skus"][0]["images"])


def test_sync_repairs_current_nine_remote_images_to_exact_eight_local_positions():
    images = [_image(position) for position in range(1, 9)]
    managed = [_asset_id(position) for position in range(1, 9)]
    product = _product([*managed, "legacy-position-05.jpg"])
    service, vtex, _ = _service(images, product, _verified_rows(images))

    result = service.sync(PARTNUMBER, account_code="VTEX_STECH")

    assert result["state"] == "SYNCED"
    assert result["remote_before_count"] == 9
    assert result["remote_after_count"] == 8
    assert result["removed_extra_count"] == 1
    assert result["uploaded_count"] == 0
    assert result["replaced_count"] == 0
    assert result["skipped_count"] == 8
    assert vtex.upload_calls == []
    assert len(vtex.update_calls) == 1
    assert _target_ids(vtex.product) == managed
    assert [row["id"] for row in vtex.product["images"]] == managed


def test_sync_adds_only_positions_six_to_eight_when_one_to_five_are_verified():
    images = [_image(position) for position in range(1, 9)]
    existing = [_asset_id(position) for position in range(1, 6)]
    product = _product(existing)
    service, vtex, _ = _service(images, product, _verified_rows(images[:5]))

    result = service.sync(PARTNUMBER, account_code="VTEX_STECH")

    assert result["state"] == "SYNCED"
    assert result["uploaded_count"] == 3
    assert result["replaced_count"] == 0
    assert result["skipped_count"] == 5
    assert result["removed_extra_count"] == 0
    assert [remote_name for _, remote_name in vtex.upload_calls] == [
        _asset_id(6),
        _asset_id(7),
        _asset_id(8),
    ]
    assert _target_ids(vtex.product) == [_asset_id(position) for position in range(1, 9)]


def test_sync_changed_binary_replaces_same_position_without_creating_an_extra_slot():
    current = [_image(1), _image(2), _image(3, image_id=33, hash_marker="a" * 64), _image(4)]
    old = [_image(1), _image(2), _image(3, image_id=3, hash_marker="3" * 64), _image(4)]
    existing = [_asset_id(position) for position in range(1, 5)]
    product = _product(existing)
    service, vtex, repo = _service(current, product, _verified_rows(old))

    result = service.sync(PARTNUMBER, account_code="VTEX_STECH")

    assert result["state"] == "SYNCED"
    assert result["uploaded_count"] == 0
    assert result["replaced_count"] == 1
    assert result["skipped_count"] == 3
    assert result["remote_before_count"] == 4
    assert result["remote_after_count"] == 4
    assert result["removed_extra_count"] == 0
    assert len(vtex.upload_calls) == 1
    local_name, remote_name = vtex.upload_calls[0]
    assert local_name == _asset_id(3)
    assert remote_name.startswith(f"{PARTNUMBER}_03__")
    assert remote_name.endswith(".jpg")
    assert _target_ids(vtex.product)[0] == _asset_id(1)
    assert _target_ids(vtex.product)[1] == _asset_id(2)
    assert _target_ids(vtex.product)[2] == remote_name
    assert _target_ids(vtex.product)[3] == _asset_id(4)
    assert _asset_id(3) not in _target_ids(vtex.product)
    current_publication = next(row for row in repo.rows if int(row["product_image_id"]) == 33)
    assert current_publication["status"] == "VERIFIED"
    assert current_publication["position"] == 3


def test_sync_adopts_matching_preexisting_positions_when_publication_history_is_empty():
    images = [_image(position) for position in range(1, 5)]
    existing = [_asset_id(position) for position in range(1, 5)]
    product = _product(existing)
    service, vtex, repo = _service(images, product, publications=[])

    result = service.sync(PARTNUMBER, account_code="VTEX_STECH")

    assert result["state"] == "SYNCED"
    assert result["uploaded_count"] == 0
    assert result["replaced_count"] == 0
    assert result["skipped_count"] == 4
    assert result["remote_before_count"] == 4
    assert result["remote_after_count"] == 4
    assert vtex.upload_calls == []
    assert vtex.update_calls == []
    assert _target_ids(vtex.product) == existing
    assert len([row for row in repo.rows if row["status"] == "VERIFIED"]) == 4
