from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from typing import Any

from stech_mcp.domain.product_schema import normalize_category_code
from stech_mcp.services.fact_normalizers import (
    normalize_bluetooth,
    normalize_boolean,
    normalize_capacity_wh,
    normalize_db,
    normalize_duration_hours,
    normalize_frequency_range,
    normalize_inches,
    normalize_ip_rating,
    normalize_mm,
    normalize_ohm,
    normalize_power_w,
    normalize_ram_gb,
    normalize_resolution,
    normalize_storage_gb,
    normalize_storage_type,
    normalize_text,
    normalize_weight,
)


Normalizer = Callable[[Any], Any]
SpecKey = tuple[str, str]


def _label(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text).strip().upper()
    return " ".join(text.split())


def _weight_kg(value: Any) -> Any:
    return normalize_weight(value, target_unit="kg")


def _weight_g(value: Any) -> Any:
    return normalize_weight(value, target_unit="g")


def _list_or_text(value: Any) -> list[str] | str | None:
    if isinstance(value, (list, tuple)):
        items = [normalize_text(item) for item in value]
        clean = [item for item in items if item]
        return clean or None
    text = normalize_text(value)
    if not text:
        return None
    parts = [item.strip() for item in re.split(r"[;,|]", text) if item.strip()]
    return parts if len(parts) > 1 else text


def _index_rows(specifications: list[dict[str, Any]]) -> dict[SpecKey, dict[str, Any]]:
    indexed: dict[SpecKey, dict[str, Any]] = {}
    for row in specifications:
        section = _label(row.get("seccion_normalizada") or row.get("seccion"))
        attribute = _label(row.get("atributo_normalizado") or row.get("atributo_original"))
        if section and attribute and (section, attribute) not in indexed:
            indexed[(section, attribute)] = row
    return indexed


def _find(indexed: dict[SpecKey, dict[str, Any]], pairs: tuple[SpecKey, ...]) -> dict[str, Any] | None:
    for section, attribute in pairs:
        row = indexed.get((_label(section), _label(attribute)))
        if row is not None:
            return row
    return None


def _normalize_candidate_value(row: dict[str, Any], normalizer: Normalizer) -> tuple[Any, str | None] | None:
    raw_value = row.get("valor_original")
    normalized = normalizer(raw_value)
    if normalized is None:
        return None
    if isinstance(normalized, dict) and "value" in normalized:
        return normalized.get("value"), normalized.get("unit")
    return normalized, None


# Mapping is intentionally based on Deltron's structured section + attribute
# identity. Marketplace/Excel names never participate here.
_CATEGORY_FIELDS: dict[str, dict[str, tuple[tuple[SpecKey, ...], Normalizer]]] = {
    "LAPTOP": {
        "cpu_model": ((("CPU", "ESPECIFICACION"),), normalize_text),
        "ram_gb": ((("MEMORIA", "CAPACIDAD"),), normalize_ram_gb),
        "storage_gb": ((("ALMACENAMIENTO", "CAPACIDAD"),), normalize_storage_gb),
        "storage_type": ((("ALMACENAMIENTO", "TIPO"),), normalize_storage_type),
        "screen_inches": ((("PANTALLA", "ESPECIFICACION"),), normalize_inches),
        "resolution": ((("PANTALLA", "ESPECIFICACION"),), normalize_resolution),
        "wifi": ((("CONECTIVIDAD", "WIRELESS"),), normalize_text),
        "bluetooth_version": ((("CONECTIVIDAD", "BLUETOOTH"),), normalize_bluetooth),
        "battery_wh": ((("BATERIA", "CAPACIDAD"),), normalize_capacity_wh),
        "weight_kg": ((("PESO", "ESPECIFICACION"),), _weight_kg),
        "os_name": ((("SISTEMA OPERATIVO", "VERSION"), ("SISTEMA OPERATIVO", "ESPECIFICACION")), normalize_text),
    },
    "PORTABLE_SPEAKER": {
        "speaker_power_w": ((("POTENCIA", "ESPECIFICACION"), ("AUDIO", "POTENCIA"), ("SONIDO", "POTENCIA")), normalize_power_w),
        "bluetooth_version": ((("CONECTIVIDAD", "BLUETOOTH"), ("BLUETOOTH", "ESPECIFICACION")), normalize_bluetooth),
        "battery_runtime_hours": ((("BATERIA", "AUTONOMIA"), ("AUTONOMIA", "ESPECIFICACION")), normalize_duration_hours),
        "battery_capacity_wh": ((("BATERIA", "CAPACIDAD"),), normalize_capacity_wh),
        "ip_rating": ((("PROTECCION", "ESPECIFICACION"), ("RESISTENCIA", "AGUA"), ("CERTIFICACION", "IP")), normalize_ip_rating),
        "frequency_response_hz": ((("SONIDO", "RESPUESTA DE FRECUENCIA"), ("AUDIO", "RESPUESTA DE FRECUENCIA"), ("RESPUESTA DE FRECUENCIA", "ESPECIFICACION")), normalize_frequency_range),
        "weight_kg": ((("PESO", "ESPECIFICACION"),), _weight_kg),
        "box_contents": ((("CONTENIDO DE CAJA", "ESPECIFICACION"), ("INCLUYE", "ESPECIFICACION")), _list_or_text),
    },
    "HEADPHONES": {
        "driver_size_mm": ((("AUDIO", "DRIVER"), ("DRIVER", "ESPECIFICACION")), normalize_mm),
        "anc": ((("AUDIO", "ANC"), ("CANCELACION DE RUIDO", "ESPECIFICACION")), normalize_boolean),
        "transparency_mode": ((("AUDIO", "MODO TRANSPARENCIA"), ("MODO TRANSPARENCIA", "ESPECIFICACION")), normalize_boolean),
        "bluetooth_version": ((("CONECTIVIDAD", "BLUETOOTH"), ("BLUETOOTH", "ESPECIFICACION")), normalize_bluetooth),
        "codec": ((("AUDIO", "CODEC"), ("CODEC", "ESPECIFICACION")), _list_or_text),
        "microphone": ((("AUDIO", "MICROFONO"), ("MICROFONO", "ESPECIFICACION")), normalize_boolean),
        "battery_runtime_hours": ((("BATERIA", "AUTONOMIA"), ("AUTONOMIA", "ESPECIFICACION")), normalize_duration_hours),
        "charging_time_hours": ((("BATERIA", "TIEMPO DE CARGA"), ("TIEMPO DE CARGA", "ESPECIFICACION")), normalize_duration_hours),
        "impedance_ohm": ((("AUDIO", "IMPEDANCIA"), ("IMPEDANCIA", "ESPECIFICACION")), normalize_ohm),
        "sensitivity_db": ((("AUDIO", "SENSIBILIDAD"), ("SENSIBILIDAD", "ESPECIFICACION")), normalize_db),
        "frequency_response_hz": ((("AUDIO", "RESPUESTA DE FRECUENCIA"), ("RESPUESTA DE FRECUENCIA", "ESPECIFICACION")), normalize_frequency_range),
        "weight_g": ((("PESO", "ESPECIFICACION"),), _weight_g),
    },
}


def _dimension_candidate(
    indexed: dict[SpecKey, dict[str, Any]],
    *,
    partnumber: str,
    category: str,
) -> dict[str, Any] | None:
    rows = [
        _find(indexed, (("DIMENSIONES", "LARGO"),)),
        _find(indexed, (("DIMENSIONES", "ANCHO"),)),
        _find(indexed, (("DIMENSIONES", "ALTO"),)),
    ]
    if any(row is None for row in rows):
        return None

    values: list[float | int] = []
    raw_parts: list[str] = []
    for row in rows:
        assert row is not None
        raw = str(row.get("valor_original") or "").strip()
        raw_parts.append(raw)
        match = re.search(r"(-?\d+(?:[.,]\d+)?)\s*(mm|cm)\b", raw, re.I)
        if not match:
            return None
        amount = float(match.group(1).replace(",", "."))
        if match.group(2).lower() == "cm":
            amount *= 10
        rounded = round(amount, 6)
        values.append(int(rounded) if rounded.is_integer() else rounded)

    return {
        "partnumber": partnumber,
        "category_code": category,
        "field_code": "dimensions_mm",
        "raw_value": " x ".join(raw_parts),
        "normalized_value": values,
        "unit": "mm",
        "source_label": "DIMENSIONES / LARGO+ANCHO+ALTO",
        "source_type": "AUTHORIZED_DISTRIBUTOR",
        "source_name": "DELTRON",
        "source_partnumber": partnumber,
        "confidence_rank": "B",
    }


class DeltronFactAdapter:
    def adapt(
        self,
        product: dict[str, Any],
        *,
        category_code: str,
        specifications: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Map PRD_DELTRON_ESPECIFICACION rows to canonical technical fields.

        Legacy PRD_PRODUCTO_DISTRIBUIDOR.atributos_json is intentionally ignored.
        """
        category = normalize_category_code(category_code)
        field_map = _CATEGORY_FIELDS.get(category)
        if field_map is None:
            return []

        partnumber = str(product.get("part_number") or product.get("partnumber") or "").strip().upper()
        if not partnumber:
            return []

        indexed = _index_rows(list(specifications or []))
        candidates: list[dict[str, Any]] = []
        for field_code, (pairs, normalizer) in field_map.items():
            row = _find(indexed, pairs)
            if row is None:
                continue
            normalized = _normalize_candidate_value(row, normalizer)
            if normalized is None:
                continue
            normalized_value, unit = normalized
            candidates.append({
                "partnumber": partnumber,
                "category_code": category,
                "field_code": field_code,
                "raw_value": row.get("valor_original"),
                "normalized_value": normalized_value,
                "unit": unit or row.get("unidad"),
                "source_label": f"{row.get('seccion')} / {row.get('atributo_original')}",
                "source_type": "AUTHORIZED_DISTRIBUTOR",
                "source_name": "DELTRON",
                "source_partnumber": partnumber,
                "confidence_rank": "B",
            })

        if category in {"LAPTOP", "PORTABLE_SPEAKER"}:
            dimensions = _dimension_candidate(indexed, partnumber=partnumber, category=category)
            if dimensions is not None:
                candidates.append(dimensions)

        return candidates
