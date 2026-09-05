from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


def _normalize_partnumber(value: Any) -> str:
    return str(value or "").strip().upper()


def _source_domain(url: Any) -> str | None:
    raw = str(url or "").strip()
    if not raw:
        return None
    parsed = urlparse(raw)
    return str(parsed.hostname).lower() if parsed.hostname else None


def normalize_deltron_images(partnumber: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map PRD_DELTRON_IMAGEN rows into the Product Workspace image contract.

    Source images do not require editing. They are considered source-eligible only
    when the Part Number snapshot matches exactly, a source URL exists, and the
    row has not been moved/deleted. Manual approval remains a separate concept.
    """
    normalized_pn = _normalize_partnumber(partnumber)
    images: list[dict[str, Any]] = []

    for row in rows:
        snapshot = _normalize_partnumber(row.get("part_number_snapshot"))
        if snapshot:
            partnumber_match = "EXACT" if snapshot == normalized_pn else "MISMATCH"
        else:
            partnumber_match = "UNKNOWN"

        source_url = str(row.get("url_origen") or "").strip() or None
        deleted = row.get("fecha_eliminacion") is not None or bool(row.get("ruta_papelera"))
        source_eligible = bool(
            normalized_pn
            and partnumber_match == "EXACT"
            and source_url
            and not deleted
        )

        storage_path = row.get("ruta_actual") or row.get("ruta_relativa")
        hash_value = row.get("hash_sha256")
        if hash_value is not None:
            hash_value = str(hash_value).strip() or None

        images.append(
            {
                "source_image_id": row.get("imagen_id"),
                "producto_distribuidor_id": row.get("producto_distribuidor_id"),
                "partnumber": normalized_pn,
                "source_type": "DELTRON_DB",
                "source_url": source_url,
                "source_domain": _source_domain(source_url),
                "part_number_snapshot": snapshot or None,
                "partnumber_match": partnumber_match,
                "model_snapshot": row.get("modelo_snapshot"),
                "brand_snapshot": row.get("marca_snapshot"),
                "storage_path": storage_path,
                "relative_path": row.get("ruta_relativa"),
                "current_path": row.get("ruta_actual"),
                "filename": row.get("nombre_archivo"),
                "variant_type": "ORIGINAL",
                "sha256_hash": hash_value,
                "width_px": row.get("ancho_px"),
                "height_px": row.get("alto_px"),
                "megapixels": row.get("megapixeles"),
                "file_size_bytes": row.get("tamano_bytes"),
                "format": row.get("formato"),
                "quality": row.get("calidad"),
                "download_status": row.get("estado_descarga"),
                "file_status": row.get("estado_archivo"),
                "trash_path": row.get("ruta_papelera"),
                "downloaded_at": row.get("fecha_descarga"),
                "verified_at": row.get("fecha_verificacion"),
                "deleted_at": row.get("fecha_eliminacion"),
                "last_error": row.get("ultimo_error"),
                "category_snapshot": row.get("categoria_snapshot"),
                "subcategory_snapshot": row.get("subcategoria_snapshot"),
                "source_eligible": source_eligible,
                "is_approved": False,
                "editing_required": False,
                "position": row.get("orden_imagen") or 0,
            }
        )

    return images
