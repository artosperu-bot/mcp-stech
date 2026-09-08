from __future__ import annotations

import json
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
    normalize_dimensions,
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


def _label(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text).strip().lower()
    return " ".join(text.split())


def _load_specs(product: dict[str, Any]) -> dict[str, Any]:
    raw = product.get("atributos_json")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, json.JSONDecodeError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    specs = parsed.get("especificaciones")
    return specs if isinstance(specs, dict) else {}


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


# Aliases describe distributor labels only. No marketplace/Excel column names
# are used here, which keeps canonical enrichment channel-neutral.
_CATEGORY_FIELDS: dict[str, dict[str, tuple[tuple[str, ...], Normalizer]]] = {
    "PORTABLE_SPEAKER": {
        "speaker_power_w": (("potencia", "potencia rms", "potencia de salida", "output power"), normalize_power_w),
        "bluetooth_version": (("bluetooth", "version bluetooth", "bluetooth version"), normalize_bluetooth),
        "battery_runtime_hours": (("autonomia", "duracion de bateria", "battery life", "tiempo de reproduccion"), normalize_duration_hours),
        "battery_capacity_wh": (("capacidad bateria wh", "bateria wh", "battery capacity wh"), normalize_capacity_wh),
        "ip_rating": (("proteccion", "grado de proteccion", "ip rating", "resistencia al agua"), normalize_ip_rating),
        "frequency_response_hz": (("respuesta de frecuencia", "rango de frecuencia", "frequency response"), normalize_frequency_range),
        "weight_kg": (("peso", "peso neto", "weight"), _weight_kg),
        "dimensions_mm": (("dimensiones", "medidas", "dimensions"), normalize_dimensions),
        "box_contents": (("contenido de caja", "incluye", "contenido", "box contents"), _list_or_text),
    },
    "HEADPHONES": {
        "driver_size_mm": (("driver", "tamano del driver", "diametro del driver", "driver size"), normalize_mm),
        "anc": (("anc", "cancelacion activa de ruido", "active noise cancellation"), normalize_boolean),
        "transparency_mode": (("modo transparencia", "ambient aware", "transparency mode"), normalize_boolean),
        "bluetooth_version": (("bluetooth", "version bluetooth", "bluetooth version"), normalize_bluetooth),
        "codec": (("codec", "codecs", "codec de audio", "audio codec"), _list_or_text),
        "microphone": (("microfono", "incluye microfono", "microphone"), normalize_boolean),
        "battery_runtime_hours": (("autonomia", "duracion de bateria", "battery life"), normalize_duration_hours),
        "charging_time_hours": (("tiempo de carga", "charging time"), normalize_duration_hours),
        "impedance_ohm": (("impedancia", "impedance"), normalize_ohm),
        "sensitivity_db": (("sensibilidad", "sensitivity"), normalize_db),
        "frequency_response_hz": (("respuesta de frecuencia", "rango de frecuencia", "frequency response"), normalize_frequency_range),
        "weight_g": (("peso", "peso neto", "weight"), _weight_g),
    },
    "LAPTOP": {
        "cpu_model": (("cpu", "procesador", "modelo de procesador", "processor"), normalize_text),
        "ram_gb": (("memoria ram", "ram", "memoria"), normalize_ram_gb),
        "storage_gb": (("ssd", "almacenamiento", "capacidad ssd", "storage"), normalize_storage_gb),
        "storage_type": (("tipo de almacenamiento", "tipo de disco", "storage type"), normalize_storage_type),
        "screen_inches": (("tamano de pantalla", "pantalla pulgadas", "screen size"), normalize_inches),
        "resolution": (("resolucion", "resolucion de pantalla", "screen resolution"), normalize_resolution),
        "wifi": (("wifi", "wi fi", "wireless lan"), normalize_text),
        "bluetooth_version": (("bluetooth", "version bluetooth", "bluetooth version"), normalize_bluetooth),
        "battery_wh": (("bateria wh", "capacidad bateria wh", "battery wh"), normalize_capacity_wh),
        "weight_kg": (("peso", "peso neto", "weight"), _weight_kg),
        "dimensions_mm": (("dimensiones", "medidas", "dimensions"), normalize_dimensions),
        "os_name": (("sistema operativo", "so", "operating system", "os"), normalize_text),
    },
}


class DeltronFactAdapter:
    def adapt(self, product: dict[str, Any], *, category_code: str) -> list[dict[str, Any]]:
        category = normalize_category_code(category_code)
        field_map = _CATEGORY_FIELDS.get(category)
        if field_map is None:
            return []

        partnumber = str(product.get("part_number") or product.get("partnumber") or "").strip().upper()
        if not partnumber:
            return []

        specs = _load_specs(product)
        normalized_specs: dict[str, tuple[str, Any]] = {}
        for source_label, raw_value in specs.items():
            key = _label(source_label)
            if key and key not in normalized_specs:
                normalized_specs[key] = (str(source_label), raw_value)

        candidates: list[dict[str, Any]] = []
        for field_code, (aliases, normalizer) in field_map.items():
            source_entry: tuple[str, Any] | None = None
            for alias in aliases:
                source_entry = normalized_specs.get(_label(alias))
                if source_entry is not None:
                    break
            if source_entry is None:
                continue

            source_label, raw_value = source_entry
            normalized = normalizer(raw_value)
            if normalized is None:
                continue

            unit = None
            normalized_value = normalized
            if isinstance(normalized, dict) and "value" in normalized:
                normalized_value = normalized.get("value")
                unit = normalized.get("unit")

            candidates.append({
                "partnumber": partnumber,
                "category_code": category,
                "field_code": field_code,
                "raw_value": raw_value,
                "normalized_value": normalized_value,
                "unit": unit,
                "source_label": source_label,
                "source_type": "AUTHORIZED_DISTRIBUTOR",
                "source_name": "DELTRON",
                "source_partnumber": partnumber,
                "confidence_rank": "B",
            })

        return candidates
