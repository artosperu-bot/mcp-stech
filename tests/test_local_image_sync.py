from __future__ import annotations

from pathlib import Path

from PIL import Image

from stech_mcp.services.local_image_sync import LocalImageSyncService


class FakeImageRepository:
    def __init__(self):
        self.rows: list[dict] = []
        self._next_id = 1

    def upsert_local_image(self, **row):
        key = (row["partnumber"], row["sha256_hash"], row.get("variant_type", "ORIGINAL"))
        for current in self.rows:
            current_key = (
                current["partnumber"],
                current["sha256_hash"],
                current.get("variant_type", "ORIGINAL"),
            )
            if current_key == key:
                current.update(row)
                return dict(current)
        stored = {"product_image_id": self._next_id, **row}
        self._next_id += 1
        self.rows.append(stored)
        return dict(stored)

    def list_images(self, partnumber: str):
        wanted = partnumber.strip().upper()
        return [dict(row) for row in self.rows if row["partnumber"] == wanted]


def _write_png(path: Path, marker: int) -> None:
    image = Image.new("RGB", (1, 1), color=(marker % 255, (marker * 17) % 255, (marker * 31) % 255))
    image.save(path, format="PNG")


def _write_product_images(root: Path, partnumber: str, positions: list[int]) -> Path:
    folder = root / "LENOVO" / "COMPUTADORAS_NOTEBOOK" / partnumber
    folder.mkdir(parents=True)
    for position in positions:
        _write_png(folder / f"{partnumber}_{position:02d}.png", position)
    return folder


def test_sync_discovers_exact_partnumber_images_and_orders_01_as_main(tmp_path):
    partnumber = "82YU00XYLM"
    _write_product_images(tmp_path, partnumber, [4, 2, 1, 3])
    repo = FakeImageRepository()
    service = LocalImageSyncService(root=tmp_path, repository=repo)

    result = service.sync(partnumber)

    assert result["state"] == "READY"
    assert result["image_count"] == 4
    assert [row["position"] for row in result["images"]] == [1, 2, 3, 4]
    assert [row["is_main"] for row in result["images"]] == [True, False, False, False]
    assert all(row["partnumber"] == partnumber for row in result["images"])
    assert all(row["sha256_hash"] for row in result["images"])
    assert all(row["width_px"] == 1 and row["height_px"] == 1 for row in result["images"])
    assert all(row["format"] == "PNG" for row in result["images"])
    assert all(row["is_approved"] is True for row in result["images"])


def test_sync_is_idempotent_for_same_binary_files(tmp_path):
    partnumber = "82YU00XYLM"
    _write_product_images(tmp_path, partnumber, [1, 2])
    repo = FakeImageRepository()
    service = LocalImageSyncService(root=tmp_path, repository=repo)

    first = service.sync(partnumber)
    second = service.sync(partnumber)

    assert first["image_count"] == 2
    assert second["image_count"] == 2
    assert len(repo.rows) == 2


def test_validate_returns_review_and_no_main_when_01_is_missing(tmp_path):
    partnumber = "82YU00XYLM"
    _write_product_images(tmp_path, partnumber, [2, 3])
    repo = FakeImageRepository()
    service = LocalImageSyncService(root=tmp_path, repository=repo)

    sync_result = service.sync(partnumber)
    validation = service.validate(partnumber)

    assert sync_result["state"] == "REVIEW"
    assert validation["state"] == "REVIEW"
    assert validation["reason"] == "main_image_01_missing"
    assert not any(row["is_main"] for row in validation["images"])


def test_sync_ignores_partial_partnumber_matches(tmp_path):
    partnumber = "82YU00XYLM"
    _write_product_images(tmp_path, partnumber, [1])
    wrong_folder = tmp_path / "LENOVO" / "COMPUTADORAS_NOTEBOOK" / f"{partnumber}X"
    wrong_folder.mkdir(parents=True)
    _write_png(wrong_folder / f"{partnumber}X_01.png", 99)
    repo = FakeImageRepository()
    service = LocalImageSyncService(root=tmp_path, repository=repo)

    result = service.sync(partnumber)

    assert result["image_count"] == 1
    assert Path(result["images"][0]["storage_path"]).name == f"{partnumber}_01.png"
