from __future__ import annotations

from pathlib import Path

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
        return f"https://mcp.artos.pe/vtex-images/signed-{partnumber}-{product_image_id}"


class FakeVtexClient:
    def __init__(self):
        self.resolve_calls = []
        self.list_calls = []
        self.create_calls = []
        self.files = []
        self._next_id = 700

    def resolve_sku_id(self, ref_id: str):
        self.resolve_calls.append(ref_id)
        return 251

    def list_sku_files(self, sku_id: int):
        self.list_calls.append(sku_id)
        return [dict(row) for row in self.files]

    def create_sku_file(self, sku_id: int, payload: dict):
        self.create_calls.append((sku_id, dict(payload)))
        created = {
            "Id": self._next_id,
            "SkuId": sku_id,
            "ArchiveId": self._next_id + 1000,
            "IsMain": bool(payload["IsMain"]),
            "Label": payload["Label"],
            "Name": payload["Name"],
            "Url": payload["Url"],
        }
        self._next_id += 1
        self.files.append(created)
        return dict(created)


class FakePublicationRepository:
    def __init__(self):
        self.rows = []

    def get_publications(self, *, partnumber: str, account_code: str, remote_sku_id: int):
        return [
            dict(row)
            for row in self.rows
            if row["partnumber"] == partnumber
            and row["account_code"] == account_code
            and row["remote_sku_id"] == remote_sku_id
        ]

    def upsert_publication(self, **row):
        key = (row["account_code"], row["remote_sku_id"], row["product_image_id"])
        for current in self.rows:
            current_key = (
                current["account_code"],
                current["remote_sku_id"],
                current["product_image_id"],
            )
            if current_key == key:
                current.update(row)
                return dict(current)
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


def test_sync_uploads_01_to_04_in_order_and_marks_01_as_main():
    local = FakeLocalImageService(_images())
    vtex = FakeVtexClient()
    publications = FakePublicationRepository()
    audit = FakeAuditRepository()
    service = VtexImageSyncService(
        local_service=local,
        vtex_client=vtex,
        publication_repository=publications,
        signer=FakeSigner(),
        audit_repository=audit,
    )

    result = service.sync("82YU00XYLM", account_code="VTEX_STECH")

    assert result["state"] == "SYNCED"
    assert result["remote_sku_id"] == 251
    assert result["uploaded_count"] == 4
    assert result["verified_count"] == 4
    assert vtex.resolve_calls == ["82YU00XYLM-S"]
    assert [payload["Name"] for _, payload in vtex.create_calls] == [
        "82YU00XYLM_01.jpg",
        "82YU00XYLM_02.jpg",
        "82YU00XYLM_03.jpg",
        "82YU00XYLM_04.jpg",
    ]
    assert [payload["IsMain"] for _, payload in vtex.create_calls] == [True, False, False, False]
    assert all(row["status"] == "VERIFIED" for row in publications.rows)
    assert audit.events[-1]["event_type"] == "VTEX_IMAGES_SYNC"


def test_second_sync_is_idempotent_and_does_not_post_again():
    local = FakeLocalImageService(_images())
    vtex = FakeVtexClient()
    publications = FakePublicationRepository()
    service = VtexImageSyncService(
        local_service=local,
        vtex_client=vtex,
        publication_repository=publications,
        signer=FakeSigner(),
        audit_repository=FakeAuditRepository(),
    )

    first = service.sync("82YU00XYLM", account_code="VTEX_STECH")
    first_post_count = len(vtex.create_calls)
    second = service.sync("82YU00XYLM", account_code="VTEX_STECH")

    assert first["uploaded_count"] == 4
    assert first_post_count == 4
    assert second["uploaded_count"] == 0
    assert second["skipped_count"] == 4
    assert len(vtex.create_calls) == 4
    assert len(vtex.list_calls) >= 4  # before/after on both executions


def test_missing_01_stops_before_any_vtex_write():
    images = [row for row in _images() if row["position"] != 1]
    local = FakeLocalImageService(images, state="REVIEW", reason="main_image_01_missing")
    vtex = FakeVtexClient()
    service = VtexImageSyncService(
        local_service=local,
        vtex_client=vtex,
        publication_repository=FakePublicationRepository(),
        signer=FakeSigner(),
        audit_repository=FakeAuditRepository(),
    )

    result = service.sync("82YU00XYLM", account_code="VTEX_STECH")

    assert result["state"] == "REVIEW"
    assert result["reason"] == "main_image_01_missing"
    assert vtex.resolve_calls == []
    assert vtex.create_calls == []
