from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image

from stech_mcp.services.falabella_image_bridge import FalabellaImageBridgeService


class FakeLocalService:
    def __init__(self, source_path: Path):
        self.source_path = source_path

    def sync(self, partnumber: str):
        return {
            "state": "READY",
            "images": [
                {
                    "product_image_id": 1,
                    "partnumber": partnumber,
                    "storage_path": str(self.source_path),
                    "position": 1,
                    "is_approved": True,
                }
            ],
            "errors": [],
        }


class FakeRepository:
    def __init__(self):
        self.variant = None

    def insert_variant(self, **kwargs):
        self.variant = {
            "product_image_id": 101,
            "partnumber": "82YU00XYLM",
            "is_approved": False,
            **kwargs,
        }
        return dict(self.variant)

    def set_approval(self, product_image_id: int, approved: bool):
        assert product_image_id == 101
        assert approved is True
        self.variant["is_approved"] = True
        return dict(self.variant)


class FakeSigner:
    def sign(self, *, product_image_id: int, partnumber: str) -> str:
        return f"https://mcp.artos.pe/falabella-images/{partnumber}-{product_image_id}"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_prepare_creates_channel_variant_without_modifying_original(tmp_path):
    source_root = tmp_path / "master"
    channel_root = tmp_path / "channels"
    source_root.mkdir()
    source = source_root / "82YU00XYLM_01.png"

    image = Image.new("RGB", (1200, 800), "white")
    image.paste((20, 20, 20), (250, 180, 950, 620))
    image.save(source, "PNG")
    original_hash = _sha(source)

    service = FalabellaImageBridgeService(
        source_root=source_root,
        channel_root=channel_root,
        local_service=FakeLocalService(source),
        repository=FakeRepository(),
        signer=FakeSigner(),
        canvas_px=1500,
        max_bytes=150 * 1024,
        min_source_px=500,
        margin_px=30,
    )

    result = service.prepare("82YU00XYLM")

    assert result["state"] == "READY"
    assert result["image_count"] == 1
    prepared = result["images"][0]
    assert prepared["position"] == 1
    assert prepared["is_main"] is True
    assert prepared["width_px"] == 1500
    assert prepared["height_px"] == 1500
    assert prepared["file_size_bytes"] <= 150 * 1024
    assert prepared["url"].startswith("https://mcp.artos.pe/falabella-images/")
    assert _sha(source) == original_hash

    output = Path(prepared["storage_path"])
    assert output == channel_root / "FALABELLA" / "82YU00XYLM" / "82YU00XYLM_01.jpg"
    with Image.open(output) as rendered:
        assert rendered.size == (1500, 1500)
        assert rendered.format == "JPEG"


def test_prepare_flags_nonwhite_source_background(tmp_path):
    source_root = tmp_path / "master"
    channel_root = tmp_path / "channels"
    source_root.mkdir()
    source = source_root / "82YU00XYLM_01.jpg"
    Image.new("RGB", (1000, 1000), (80, 120, 160)).save(source, "JPEG")

    service = FalabellaImageBridgeService(
        source_root=source_root,
        channel_root=channel_root,
        local_service=FakeLocalService(source),
        repository=FakeRepository(),
        signer=FakeSigner(),
    )

    result = service.prepare("82YU00XYLM")

    assert result["state"] == "READY_WITH_WARNINGS"
    assert result["warning_count"] >= 1
    assert "source_background_requires_review" in result["images"][0]["warnings"]
    assert result["images"][0]["background_status"] == "REVIEW_NONWHITE_SOURCE"


def test_prepare_requires_main_position_01(tmp_path):
    class MissingMainLocal:
        def sync(self, partnumber: str):
            return {
                "state": "REVIEW",
                "images": [
                    {
                        "product_image_id": 2,
                        "partnumber": partnumber,
                        "storage_path": str(tmp_path / "unused.jpg"),
                        "position": 2,
                    }
                ],
                "errors": [],
            }

    service = FalabellaImageBridgeService(
        source_root=tmp_path,
        channel_root=tmp_path / "channels",
        local_service=MissingMainLocal(),
        repository=FakeRepository(),
        signer=FakeSigner(),
    )

    result = service.prepare("82YU00XYLM")

    assert result["state"] == "REVIEW"
    assert result["reason"] == "main_image_01_missing"
    assert result["images"] == []
