from __future__ import annotations

from typing import Any


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def calculate_readiness(
    *,
    product: dict[str, Any],
    coolbox_preview: dict[str, Any],
    package: dict[str, Any] | None,
    images: list[dict[str, Any]],
) -> dict[str, Any]:
    identity_present = sum(
        1
        for key in ("part_number", "marca", "nombre")
        if _present(product.get(key) or product.get({"part_number": "partnumber"}.get(key, "")))
    )
    if _present(product.get("ean")) or _present(product.get("upc")):
        identity_present += 1
    identity_score = round(identity_present / 4 * 100)

    fields = list(coolbox_preview.get("fields") or [])
    noncommercial = [
        field for field in fields if str(field.get("status") or "").upper() != "MARKETPLACE_INPUT"
    ]
    non_missing = [
        field for field in noncommercial if str(field.get("status") or "").upper() != "RESEARCH_REQUIRED"
    ]
    technical_score = round(len(non_missing) / len(noncommercial) * 100) if noncommercial else 0

    approved_images = sum(1 for image in images if bool(image.get("is_approved")))
    if approved_images >= 4:
        image_score = 100
    elif approved_images == 3:
        image_score = 75
    elif approved_images == 2:
        image_score = 50
    elif approved_images == 1:
        image_score = 25
    else:
        image_score = 0

    package_method = str((package or {}).get("method") or "").upper()
    package_score = 100 if package_method == "VERIFIED" else 70 if package_method == "ESTIMATED" else 0

    research_required = sum(1 for field in fields if str(field.get("status") or "").upper() == "RESEARCH_REQUIRED")
    marketplace_input = sum(1 for field in fields if str(field.get("status") or "").upper() == "MARKETPLACE_INPUT")
    field_count = int(coolbox_preview.get("field_count") or len(fields) or 0)
    denominator = max(field_count - marketplace_input, 0)
    coolbox_score = round((field_count - research_required - marketplace_input) / denominator * 100) if denominator else 0

    missing_fields = list(coolbox_preview.get("ready_for_research") or [
        field.get("field") for field in fields if str(field.get("status") or "").upper() == "RESEARCH_REQUIRED"
    ])
    estimated_fields = list(coolbox_preview.get("estimated_fields") or [
        field.get("field") for field in fields if str(field.get("status") or "").upper() == "ESTIMATED"
    ])

    if image_score == 0:
        state = "FALTAN_IMAGENES"
    elif research_required > 0:
        state = "FALTAN_DATOS"
    else:
        state = "LISTO_PARA_REVISAR"

    return {
        "state": state,
        "identity_score": identity_score,
        "technical_score": technical_score,
        "image_score": image_score,
        "package_score": package_score,
        "coolbox_score": coolbox_score,
        "missing_fields": missing_fields,
        "estimated_fields": estimated_fields,
        "image_count": len(images),
        "approved_image_count": approved_images,
    }
