from __future__ import annotations

import json
from typing import Any


def _clean(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return value


def _attrs(product: dict[str, Any]) -> dict[str, Any]:
    raw = product.get("atributos_json")
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _first(product: dict[str, Any], attrs: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = _clean(product.get(key))
        if value is not None:
            return value
        value = _clean(attrs.get(key))
        if value is not None:
            return value
    return None


def build_identity_context(product: dict[str, Any] | None) -> dict[str, Any]:
    """Build deterministic identity context from facts already stored for a SKU.

    The builder deliberately does not infer technical values from the title.
    Missing optional fields remain ``None`` so research can distinguish known
    facts from guesses.
    """
    row = dict(product or {})
    attrs = _attrs(row)
    brand = _first(row, attrs, "brand", "marca")
    partnumber = _first(row, attrs, "part_number", "partnumber", "mpn")
    category = _first(row, attrs, "category", "categoria")

    return {
        "brand": str(brand).strip().upper() if brand is not None else None,
        "part_number": str(partnumber).strip().upper() if partnumber is not None else None,
        "model": _first(row, attrs, "model", "modelo"),
        "category": str(category).strip().upper() if category is not None else None,
        "title": _first(row, attrs, "title", "nombre", "product_name"),
        "processor": _first(row, attrs, "processor", "procesador", "cpu"),
        "ram_gb": _first(row, attrs, "ram_gb", "memoria_ram_gb"),
        "storage_gb": _first(row, attrs, "storage_gb", "almacenamiento_gb", "ssd_gb"),
        "storage_type": _first(row, attrs, "storage_type", "tipo_almacenamiento"),
        "screen_inches": _first(row, attrs, "screen_inches", "pantalla_pulgadas"),
        "gpu": _first(row, attrs, "gpu", "graphics", "grafica"),
        "color": _first(row, attrs, "color"),
        "operating_system": _first(row, attrs, "operating_system", "sistema_operativo", "os"),
        "existing_ean": _first(row, attrs, "ean"),
        "existing_upc": _first(row, attrs, "upc"),
        "existing_gtin": _first(row, attrs, "gtin"),
    }
