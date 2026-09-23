from __future__ import annotations

import inspect

import pytest

from stech_mcp.db.product_image_repository import ProductImageRepository
from stech_mcp.services.product_image_editor import ProductImageEditor


class FakeRepository:
    def __init__(self):
        self.rows = {
            1: {"product_image_id": 1, "partnumber": "82YU00XYLM", "variant_type": "ORIGINAL", "position": 1, "is_approved": 1},
            2: {"product_image_id": 2, "partnumber": "82YU00XYLM", "variant_type": "ORIGINAL", "position": 2, "is_approved": 0},
        }
        self.calls = []
        self.next_id = 3

    def get_by_id(self, image_id):
        row = self.rows.get(int(image_id))
        return dict(row) if row else None

    def list_images(self, partnumber):
        pn = str(partnumber).strip().upper()
        return sorted(
            [dict(row) for row in self.rows.values() if row["partnumber"] == pn],
            key=lambda row: (row["position"], row["product_image_id"]),
        )

    def set_approval(self, image_id, approved):
        self.calls.append(("approval", int(image_id), bool(approved)))
        self.rows[int(image_id)]["is_approved"] = 1 if approved else 0
        return dict(self.rows[int(image_id)])

    def reorder(self, partnumber, ordered_ids):
        self.calls.append(("reorder", str(partnumber).strip().upper(), list(ordered_ids)))
        for position, image_id in enumerate(ordered_ids, start=1):
            self.rows[int(image_id)]["position"] = position
        return self.list_images(partnumber)

    def insert_variant(self, **kwargs):
        self.calls.append(("variant", dict(kwargs)))
        image_id = self.next_id
        self.next_id += 1
        parent = self.rows[int(kwargs["parent_image_id"])]
        self.rows[image_id] = {
            "product_image_id": image_id,
            "partnumber": parent["partnumber"],
            "variant_type": kwargs["variant_type"],
            "parent_image_id": int(kwargs["parent_image_id"]),
            "storage_path": kwargs["storage_path"],
            "sha256_hash": kwargs["sha256_hash"],
            "width_px": kwargs["width_px"],
            "height_px": kwargs["height_px"],
            "format": kwargs["format"],
            "position": parent["position"],
            "is_approved": 0,
        }
        return dict(self.rows[image_id])


def test_repository_exposes_non_destructive_editor_writes_and_no_delete_contract():
    source = inspect.getsource(ProductImageRepository)
    assert hasattr(ProductImageRepository, "set_approval")
    assert hasattr(ProductImageRepository, "reorder")
    assert hasattr(ProductImageRepository, "insert_variant")
    assert "DELETE FROM dbo.product_image" not in source.upper()


def test_editor_approves_image_with_readback_contract():
    repo = FakeRepository()
    editor = ProductImageEditor(repo)

    result = editor.approve(2, True)

    assert result["product_image_id"] == 2
    assert result["is_approved"] == 1
    assert repo.calls == [("approval", 2, True)]


def test_editor_reorders_only_complete_unique_image_set_for_same_partnumber():
    repo = FakeRepository()
    editor = ProductImageEditor(repo)

    result = editor.reorder("82yu00xylm", [2, 1])

    assert [row["product_image_id"] for row in result] == [2, 1]
    assert [row["position"] for row in result] == [1, 2]

    with pytest.raises(ValueError, match="exactly all images"):
        editor.reorder("82YU00XYLM", [1])
    with pytest.raises(ValueError, match="duplicate"):
        editor.reorder("82YU00XYLM", [1, 1])


def test_editor_registers_child_variant_and_never_allows_original_variant_type():
    repo = FakeRepository()
    editor = ProductImageEditor(repo)
    digest = "a" * 64

    result = editor.register_variant(
        parent_image_id=1,
        storage_path=r"C:\STECH_IMAGENES\LENOVO\82YU00XYLM\edited_01.jpg",
        sha256_hash=digest,
        width_px=1200,
        height_px=1200,
        format="JPEG",
        variant_type="EDITED_STECH",
    )

    assert result["parent_image_id"] == 1
    assert result["variant_type"] == "EDITED_STECH"
    assert repo.rows[1]["variant_type"] == "ORIGINAL"

    with pytest.raises(ValueError, match="ORIGINAL"):
        editor.register_variant(
            parent_image_id=1,
            storage_path="new.jpg",
            sha256_hash=digest,
            width_px=1200,
            height_px=1200,
            format="JPEG",
            variant_type="ORIGINAL",
        )


def test_editor_rejects_unknown_parent_and_invalid_hash_before_repository_write():
    repo = FakeRepository()
    editor = ProductImageEditor(repo)

    with pytest.raises(ValueError, match="parent image"):
        editor.register_variant(
            parent_image_id=999,
            storage_path="new.jpg",
            sha256_hash="a" * 64,
            width_px=1200,
            height_px=1200,
            format="JPEG",
        )
    with pytest.raises(ValueError, match="sha256"):
        editor.register_variant(
            parent_image_id=1,
            storage_path="new.jpg",
            sha256_hash="bad",
            width_px=1200,
            height_px=1200,
            format="JPEG",
        )
