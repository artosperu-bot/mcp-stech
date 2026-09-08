from __future__ import annotations

from string import hexdigits
from typing import Any


class ProductImageEditor:
    def __init__(self, repository: Any):
        self.repository = repository

    def approve(self, product_image_id: int, approved: bool = True) -> dict[str, Any]:
        current = self.repository.get_by_id(int(product_image_id))
        if current is None:
            raise ValueError("product image not found")
        return self.repository.set_approval(int(product_image_id), bool(approved))

    def reorder(self, partnumber: str, ordered_ids: list[int]) -> list[dict[str, Any]]:
        normalized = str(partnumber or "").strip().upper()
        if not normalized:
            raise ValueError("partnumber is required")
        ids = [int(value) for value in ordered_ids]
        if len(ids) != len(set(ids)):
            raise ValueError("ordered_ids contains duplicate image ids")
        current = self.repository.list_images(normalized)
        current_ids = [int(row["product_image_id"]) for row in current]
        if len(ids) != len(current_ids) or set(ids) != set(current_ids):
            raise ValueError("ordered_ids must contain exactly all images for the Part Number")
        return self.repository.reorder(normalized, ids)

    def register_variant(
        self,
        *,
        parent_image_id: int,
        storage_path: str,
        sha256_hash: str,
        width_px: int,
        height_px: int,
        format: str,
        variant_type: str = "EDITED_STECH",
    ) -> dict[str, Any]:
        parent = self.repository.get_by_id(int(parent_image_id))
        if parent is None:
            raise ValueError("parent image not found")
        variant = str(variant_type or "").strip().upper()
        if not variant or variant == "ORIGINAL":
            raise ValueError("ORIGINAL cannot be created as an edited child variant")
        digest = str(sha256_hash or "").strip().lower()
        if len(digest) != 64 or any(char not in hexdigits for char in digest):
            raise ValueError("sha256_hash must contain 64 hexadecimal characters")
        if not str(storage_path or "").strip():
            raise ValueError("storage_path is required")
        if int(width_px) <= 0 or int(height_px) <= 0:
            raise ValueError("image dimensions must be positive")
        return self.repository.insert_variant(
            parent_image_id=int(parent_image_id),
            storage_path=str(storage_path).strip(),
            sha256_hash=digest,
            width_px=int(width_px),
            height_px=int(height_px),
            format=str(format or "").strip().upper(),
            variant_type=variant,
        )
