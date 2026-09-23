from __future__ import annotations

from typing import Any

from stech_mcp.services.coolbox_preview import build_coolbox_preview
from stech_mcp.services.falabella_preview import build_falabella_preview


def build_marketplace_preview(
    *,
    product: dict[str, Any],
    marketplace: str,
    category: str,
    package: dict[str, Any] | None = None,
    enrichments: list[dict[str, Any]] | None = None,
    image_urls: list[str] | None = None,
    marketplace_inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    marketplace_code = marketplace.strip().upper()
    category_code = category.strip().upper()

    if marketplace_code == "COOLBOX" and category_code == "LAPTOP":
        preview = build_coolbox_preview(
            product,
            package=package,
            enrichments=enrichments,
        )
        return {
            "marketplace": marketplace_code,
            "category": category_code,
            **preview,
        }

    if marketplace_code == "FALABELLA" and category_code == "LAPTOP":
        preview = build_falabella_preview(
            product=product,
            package=package,
            enrichments=enrichments,
            image_urls=image_urls,
            marketplace_inputs=marketplace_inputs,
        )
        return {
            "marketplace": marketplace_code,
            "category": category_code,
            **preview,
        }

    raise ValueError(
        f"unsupported marketplace/category: {marketplace_code}/{category_code}"
    )
