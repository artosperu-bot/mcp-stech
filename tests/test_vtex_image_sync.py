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
        self.update_calls = []
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

    def update_sku_file(self, sku_id: int, sku_file_id: int, payload: dict):
        self.update_calls.append((sku_id, sku_file_id, dict(payload)))
        for index, current in enumerate(self.files):
            if int(current.get("Id") or 0) != int(sku_file_id):
                continue
            updated = {
                **current,
                **payload,
                "Id": int(sku_file_id),
                "SkuId": int(sku_id),
            }
            self.files[index] = updated
            return dict(updated)
        raise RuntimeError(f"file_not_found:{sku_file_id}")


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


def _service(local, vtex, publications=None, audit=None):
    return VtexImageSyncService(
        local_service=local,
        vtex_client=vtex,
        publication_repository=publications or FakePublicationRepository(),
        signer=FakeSigner(),
        audit_repository=audit or FakeAuditRepository(),
    )


def test_sync_uploads_01_to_04_in_order_and_marks_01_as_main():
    local = FakeLocalImageService(_images())
    vtex = FakeVtexClient()
    publications = FakePublicationRepository()
    audit = FakeAuditRepository()
    result = _service(local, vtex, publications, audit).sync("82YU00XYLM", account_code="VTEX_STECH")

    assert result["state"] == "SYNCED"
    assert result["remote_sku_id"] == 251
    assert result["uploaded_count"] == 4
    assert result["replaced_count"] == 0
    assert result["verified_count"] == 4
    assert vtex.resolve_calls == ["82YU00XYLM-S"]
    assert [payload["Name"] for _, payload in vtex.create_calls] == [
        "82YU00XYLM_01.jpg",
        "82YU00XYLM_02.jpg",
        "82YU00XYLM_03.jpg",
        "82YU00XYLM_04.jpg",
    ]
    assert [payload["IsMain"] for _, payload in vtex.create_calls] == [True, False, False, False]
    assert not vtex.update_calls
    assert all(row["status"] == "VERIFIED" for row in publications.rows)
    assert audit.events[-1]["event_type"] == "VTEX_IMAGES_SYNC"


def test_second_sync_is_idempotent_and_does_not_write_again():
    local = FakeLocalImageService(_images())
    vtex = FakeVtexClient()
    publications = FakePublicationRepository()
    service = _service(local, vtex, publications)

    first = service.sync("82YU00XYLM", account_code="VTEX_STECH")
    second = service.sync("82YU00XYLM", account_code="VTEX_STECH")

    assert first["uploaded_count"] == 4
    assert second["uploaded_count"] == 0
    assert second["replaced_count"] == 0
    assert second["skipped_count"] == 4
    assert len(vtex.create_calls) == 4
    assert not vtex.update_calls
    assert len(vtex.list_calls) >= 4


def test_sync_after_adding_images_uploads_only_the_new_positions():
    local = FakeLocalImageService(_images())
    vtex = FakeVtexClient()
    publications = FakePublicationRepository()
    service = _service(local, vtex, publications)

    first = service.sync("82YU00XYLM", account_code="VTEX_STECH")
    assert first["uploaded_count"] == 4

    local.images.extend(
        {
            "product_image_id": position,
            "partnumber": "82YU00XYLM",
            "storage_path": str(Path(f"82YU00XYLM_{position:02d}.jpg")),
            "position": position,
            "is_main": False,
            "is_approved": True,
            "sha256_hash": f"{position:064x}",
            "format": "JPEG",
        }
        for position in range(5, 9)
    )
    before_second = len(vtex.create_calls)
    second = service.sync("82YU00XYLM", account_code="VTEX_STECH")

    second_payloads = [payload for _, payload in vtex.create_calls[before_second:]]
    assert second["state"] == "SYNCED"
    assert second["uploaded_count"] == 4
    assert second["replaced_count"] == 0
    assert second["skipped_count"] == 4
    assert second["verified_count"] == 8
    assert [payload["Name"] for payload in second_payloads] == [
        "82YU00XYLM_05.jpg",
        "82YU00XYLM_06.jpg",
        "82YU00XYLM_07.jpg",
        "82YU00XYLM_08.jpg",
    ]
    assert all(payload["IsMain"] is False for payload in second_payloads)


def test_sync_replaces_only_changed_image_at_same_position():
    local = FakeLocalImageService(_images())
    vtex = FakeVtexClient()
    publications = FakePublicationRepository()
    service = _service(local, vtex, publications)

    first = service.sync("82YU00XYLM", account_code="VTEX_STECH")
    assert first["uploaded_count"] == 4
    old_position_3 = next(row for row in publications.rows if row["position"] == 3)
    remote_file_id = int(old_position_3["remote_file_id"])

    local.images = [
        ({
            **row,
            "product_image_id": 103,
            "sha256_hash": "f" * 64,
            "storage_path": str(Path("82YU00XYLM_03.jpg")),
        } if row["position"] == 3 else row)
        for row in local.images
    ]
    before_create = len(vtex.create_calls)
    second = service.sync("82YU00XYLM", account_code="VTEX_STECH")

    assert second["state"] == "SYNCED"
    assert second["uploaded_count"] == 0
    assert second["replaced_count"] == 1
    assert second["skipped_count"] == 3
    assert second["verified_count"] == 4
    assert len(vtex.create_calls) == before_create
    assert len(vtex.update_calls) == 1
    sku_id, updated_file_id, payload = vtex.update_calls[0]
    assert sku_id == 251
    assert updated_file_id == remote_file_id
    assert payload["Name"] == "82YU00XYLM_03.jpg"
    assert payload["IsMain"] is False
    assert payload["Url"].endswith("-103")
    current = next(row for row in publications.rows if row["product_image_id"] == 103)
    assert current["status"] == "VERIFIED"
    assert int(current["remote_file_id"]) == remote_file_id


def test_existing_remote_unpadded_name_is_adopted_by_position_without_duplicate():
    local = FakeLocalImageService([_images()[0]])
    vtex = FakeVtexClient()
    vtex.files.append(
        {
            "Id": 901,
            "SkuId": 251,
            "ArchiveId": 1901,
            "IsMain": True,
            "Label": "Main",
            "Name": "82YU00XYLM_1.jpg",
            "Url": "https://vtex.example/old-main.jpg",
        }
    )
    publications = FakePublicationRepository()

    result = _service(local, vtex, publications).sync("82YU00XYLM", account_code="VTEX_STECH")

    assert result["state"] == "SYNCED"
    assert result["uploaded_count"] == 0
    assert result["replaced_count"] == 0
    assert result["skipped_count"] == 1
    assert not vtex.create_calls
    assert not vtex.update_calls
    assert publications.rows[0]["remote_file_id"] == 901
    assert publications.rows[0]["status"] == "VERIFIED"


def test_missing_01_stops_before_any_vtex_write():
    images = [row for row in _images() if row["position"] != 1]
    local = FakeLocalImageService(images, state="REVIEW", reason="main_image_01_missing")
    vtex = FakeVtexClient()
    result = _service(local, vtex).sync("82YU00XYLM", account_code="VTEX_STECH")

    assert result["state"] == "REVIEW"
    assert result["reason"] == "main_image_01_missing"
    assert vtex.resolve_calls == []
    assert vtex.create_calls == []
    assert vtex.update_calls == []


def test_status_is_not_synced_until_every_local_image_has_verified_publication():
    local = FakeLocalImageService(_images())
    vtex = FakeVtexClient()
    publications = FakePublicationRepository()
    publications.rows.append(
        {
            "product_image_publication_id": 1,
            "product_image_id": 1,
            "partnumber": "82YU00XYLM",
            "channel": "VTEX",
            "account_code": "VTEX_STECH",
            "remote_sku_id": 251,
            "status": "VERIFIED",
            "position": 1,
            "is_main": True,
        }
    )
    status = _service(local, vtex, publications).status("82YU00XYLM", account_code="VTEX_STECH")

    assert status["state"] == "READY"
    assert status["local_image_count"] == 4
    assert status["verified_publication_count"] == 1
