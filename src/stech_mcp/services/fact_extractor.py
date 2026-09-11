from __future__ import annotations

import re
from typing import Any, Callable

from stech_mcp.domain.product_schema import normalize_field_code
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


Extractor = Callable[[str], tuple[str, Any] | None]


def _exact_pn_present(text: str, partnumber: str) -> bool:
    pattern = rf"(?<![A-Z0-9]){re.escape(partnumber)}(?![A-Z0-9])"
    return re.search(pattern, text, re.I) is not None


def _evidence_excerpt(text: str, raw_value: str, *, limit: int = 700) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    needle = str(raw_value or "").strip()
    index = compact.casefold().find(needle.casefold()) if needle else -1
    if index < 0:
        return compact[:limit]
    half = limit // 2
    start = max(0, index - half)
    end = min(len(compact), start + limit)
    return compact[start:end]


def _unique_match(text: str, pattern: str, *, flags: int = re.I) -> str | None:
    matches = [match.group(0).strip(" ,;:.()[]") for match in re.finditer(pattern, text, flags)]
    unique: list[str] = []
    for match in matches:
        if match and match.casefold() not in {value.casefold() for value in unique}:
            unique.append(match)
    return unique[0] if len(unique) == 1 else None


def _normalize_fragment(text: str, pattern: str, normalizer: Callable[[Any], Any]) -> tuple[str, Any] | None:
    fragment = _unique_match(text, pattern)
    if fragment is None:
        return None
    normalized = normalizer(fragment)
    return (fragment, normalized) if normalized is not None else None


def _gs1_valid(value: str) -> bool:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) not in {8, 12, 13, 14}:
        return False
    body = [int(char) for char in digits[:-1]]
    expected = int(digits[-1])
    weighted = 0
    for index, digit in enumerate(reversed(body)):
        weighted += digit * (3 if index % 2 == 0 else 1)
    return (10 - (weighted % 10)) % 10 == expected


def _barcode(text: str, field_code: str) -> tuple[str, Any] | None:
    labels = {
        "ean": r"EAN(?:[- ]?13)?",
        "upc": r"UPC(?:[- ]?A)?",
        "gtin": r"GTIN(?:[- ]?(?:8|12|13|14))?|BARCODE|C[ÓO]DIGO\s+DE\s+BARRAS",
    }
    label = labels[field_code]
    pattern = rf"\b(?:{label})\b\s*[:#\-]?\s*((?:\d[\s-]?){{7,13}}\d)"
    matches: list[tuple[str, str]] = []
    for match in re.finditer(pattern, text, re.I):
        raw = match.group(0).strip(" ,;:.()[]")
        digits = re.sub(r"\D", "", match.group(1))
        if not _gs1_valid(digits):
            continue
        if field_code == "ean" and len(digits) not in {8, 13}:
            continue
        if field_code == "upc" and len(digits) != 12:
            continue
        matches.append((raw, digits))
    values = {digits for _, digits in matches}
    if len(values) != 1:
        return None
    target = next(iter(values))
    raw = next(raw for raw, digits in matches if digits == target)
    return raw, target


def _ean(text: str) -> tuple[str, Any] | None:
    return _barcode(text, "ean")


def _upc(text: str) -> tuple[str, Any] | None:
    return _barcode(text, "upc")


def _gtin(text: str) -> tuple[str, Any] | None:
    return _barcode(text, "gtin")


def _bluetooth(text: str) -> tuple[str, Any] | None:
    return _normalize_fragment(text, r"\bBluetooth\s*(?:version|versi[oó]n|v)?\s*[2-6](?:\.\d{1,2})?\b", normalize_bluetooth)


def _ip_rating(text: str) -> tuple[str, Any] | None:
    return _normalize_fragment(text, r"\bIP\s*[0-6X][0-9X](?:[A-Z])?\b", normalize_ip_rating)


def _power(text: str) -> tuple[str, Any] | None:
    return _normalize_fragment(text, r"\b\d+(?:[.,]\d+)?\s*W\b", normalize_power_w)


def _duration(text: str) -> tuple[str, Any] | None:
    return _normalize_fragment(text, r"\b\d+(?:[.,]\d+)?\s*(?:h|hr|hrs|hora|horas)\b", normalize_duration_hours)


def _capacity_wh(text: str) -> tuple[str, Any] | None:
    return _normalize_fragment(text, r"\b\d+(?:[.,]\d+)?\s*W\s*H\b", normalize_capacity_wh)


def _frequency(text: str) -> tuple[str, Any] | None:
    return _normalize_fragment(text, r"\b\d+(?:[.,]\d+)?\s*k?\s*Hz\s*(?:-|–|—|a|to)\s*\d+(?:[.,]\d+)?\s*k?\s*Hz\b", normalize_frequency_range)


def _dimensions(text: str) -> tuple[str, Any] | None:
    return _normalize_fragment(text.replace("×", "x"), r"\b\d+(?:[.,]\d+)?\s*x\s*\d+(?:[.,]\d+)?\s*x\s*\d+(?:[.,]\d+)?\s*(?:mm|cm)\b", normalize_dimensions)


def _weight_kg(text: str) -> tuple[str, Any] | None:
    fragment = _unique_match(text, r"\b\d+(?:[.,]\d+)?\s*(?:kg|g)\b")
    if fragment is None:
        return None
    normalized = normalize_weight(fragment, target_unit="kg")
    return (fragment, normalized) if normalized is not None else None


def _weight_g(text: str) -> tuple[str, Any] | None:
    fragment = _unique_match(text, r"\b\d+(?:[.,]\d+)?\s*(?:kg|g)\b")
    if fragment is None:
        return None
    normalized = normalize_weight(fragment, target_unit="g")
    return (fragment, normalized) if normalized is not None else None


def _ram(text: str) -> tuple[str, Any] | None:
    return _normalize_fragment(text, r"\b(?:RAM|memoria(?:\s+RAM)?|memory)\s*[:\-]?\s*\d+(?:[.,]\d+)?\s*(?:GB|TB)\b(?:\s*(?:LP)?DDR\d\w*)?", normalize_ram_gb)


def _storage(text: str) -> tuple[str, Any] | None:
    return _normalize_fragment(text, r"\b(?:SSD|storage|almacenamiento|disco)\s*[:\-]?\s*\d+(?:[.,]\d+)?\s*(?:GB|TB)\b|\b\d+(?:[.,]\d+)?\s*(?:GB|TB)\s*(?:SSD|NVMe|UFS|eMMC|HDD)\b", normalize_storage_gb)


def _storage_type(text: str) -> tuple[str, Any] | None:
    fragment = _unique_match(text, r"\b(?:NVMe|SSD|HDD|eMMC|UFS)\b")
    if fragment is None:
        return None
    normalized = normalize_storage_type(fragment)
    return (fragment, normalized) if normalized is not None else None


def _resolution(text: str) -> tuple[str, Any] | None:
    return _normalize_fragment(text.replace("×", "x"), r"\b\d{3,5}\s*x\s*\d{3,5}\b", normalize_resolution)


def _screen_inches(text: str) -> tuple[str, Any] | None:
    return _normalize_fragment(text, r"\b\d{1,2}(?:[.,]\d+)?\s*(?:inches|inch|in|pulgadas?|\")", normalize_inches)


def _driver_mm(text: str) -> tuple[str, Any] | None:
    fragment = _unique_match(text, r"\b(?:driver|transductor)\s*[:\-]?\s*\d+(?:[.,]\d+)?\s*mm\b")
    if fragment is None:
        return None
    normalized = normalize_mm(fragment)
    return (fragment, normalized) if normalized is not None else None


def _impedance(text: str) -> tuple[str, Any] | None:
    return _normalize_fragment(text, r"\b\d+(?:[.,]\d+)?\s*(?:ohm|Ω)\b", normalize_ohm)


def _sensitivity(text: str) -> tuple[str, Any] | None:
    return _normalize_fragment(text, r"\b\d+(?:[.,]\d+)?\s*dB\b", normalize_db)


def _label_text(text: str, labels: tuple[str, ...]) -> tuple[str, Any] | None:
    label_expr = "|".join(re.escape(label) for label in labels)
    match = re.search(rf"\b(?:{label_expr})\b\s*[:\-]\s*([^\n;|]+)", text, re.I)
    if not match:
        return None
    raw = " ".join(match.group(1).split()).strip(" ,.;")
    normalized = normalize_text(raw)
    return (raw, normalized) if normalized is not None else None


def _cpu(text: str) -> tuple[str, Any] | None:
    return _label_text(text, ("CPU", "processor", "procesador"))


def _os(text: str) -> tuple[str, Any] | None:
    return _label_text(text, ("operating system", "sistema operativo", "OS", "SO"))


def _wifi(text: str) -> tuple[str, Any] | None:
    fragment = _unique_match(text, r"\b(?:Wi[- ]?Fi|802\.11)[^,;|\n]{0,45}")
    if fragment is None:
        return None
    return fragment, " ".join(fragment.split())


def _boolean_labeled(text: str, labels: tuple[str, ...]) -> tuple[str, Any] | None:
    label_expr = "|".join(re.escape(label) for label in labels)
    match = re.search(rf"\b(?:{label_expr})\b\s*[:\-]?\s*(s[ií]|yes|no|true|false|incluye|incluido|no incluye)\b", text, re.I)
    if not match:
        return None
    raw = match.group(0)
    normalized = normalize_boolean(match.group(1))
    return (raw, normalized) if normalized is not None else None


def _anc(text: str) -> tuple[str, Any] | None:
    if re.search(r"\b(?:ANC|active noise cancellation|cancelaci[oó]n activa de ruido)\b", text, re.I):
        return "ANC", True
    return None


def _transparency(text: str) -> tuple[str, Any] | None:
    if re.search(r"\b(?:transparency mode|modo transparencia|ambient aware)\b", text, re.I):
        return "transparency mode", True
    return None


def _microphone(text: str) -> tuple[str, Any] | None:
    if re.search(r"\b(?:microphone|micr[oó]fono)\b", text, re.I):
        return "microphone", True
    return None


def _list_labeled(text: str, labels: tuple[str, ...]) -> tuple[str, Any] | None:
    result = _label_text(text, labels)
    if result is None:
        return None
    raw, normalized = result
    values = [item.strip() for item in re.split(r"[,;/|]", str(normalized)) if item.strip()]
    return raw, values if len(values) > 1 else normalized


def _codec(text: str) -> tuple[str, Any] | None:
    return _list_labeled(text, ("codec", "codecs", "audio codec"))


def _box_contents(text: str) -> tuple[str, Any] | None:
    return _list_labeled(text, ("box contents", "contenido de caja", "incluye"))


_FIELD_EXTRACTORS: dict[str, Extractor] = {
    "ean": _ean,
    "upc": _upc,
    "gtin": _gtin,
    "bluetooth_version": _bluetooth,
    "ip_rating": _ip_rating,
    "speaker_power_w": _power,
    "battery_runtime_hours": _duration,
    "charging_time_hours": _duration,
    "battery_capacity_wh": _capacity_wh,
    "battery_wh": _capacity_wh,
    "frequency_response_hz": _frequency,
    "dimensions_mm": _dimensions,
    "weight_kg": _weight_kg,
    "weight_g": _weight_g,
    "ram_gb": _ram,
    "storage_gb": _storage,
    "storage_type": _storage_type,
    "resolution": _resolution,
    "screen_inches": _screen_inches,
    "driver_size_mm": _driver_mm,
    "impedance_ohm": _impedance,
    "sensitivity_db": _sensitivity,
    "cpu_model": _cpu,
    "os_name": _os,
    "wifi": _wifi,
    "anc": _anc,
    "transparency_mode": _transparency,
    "microphone": _microphone,
    "codec": _codec,
    "box_contents": _box_contents,
}


class FactExtractor:
    """Extract deterministic candidates from already-ingested source text.

    This layer never writes approved enrichment. It returns evidence candidates
    only, and leaves unsupported/ambiguous fields missing.
    """

    def extract(self, document: dict[str, Any], target_fields: list[str], partnumber: str) -> list[dict[str, Any]]:
        pn = str(partnumber or "").strip().upper()
        if not pn:
            raise ValueError("partnumber is required")

        source_url = str(document.get("url") or "").strip() or None
        source_type = str(document.get("source_type") or "OFFICIAL_DOCUMENT").strip().upper()
        confidence = str(document.get("confidence_rank") or "A2").strip().upper()
        pages = document.get("pages") if isinstance(document.get("pages"), list) else []

        fields: list[str] = []
        for raw in target_fields:
            code = normalize_field_code(raw)
            if code and code not in fields:
                fields.append(code)

        candidates: list[dict[str, Any]] = []
        extracted_fields: set[str] = set()
        for page in pages:
            text = str(page.get("text") or "") if isinstance(page, dict) else ""
            if not text:
                continue
            page_number = int(page.get("page") or 1) if isinstance(page, dict) else 1
            exact_page = _exact_pn_present(text, pn)

            for field_code in fields:
                if field_code in extracted_fields:
                    continue
                extractor = _FIELD_EXTRACTORS.get(field_code)
                if extractor is None:
                    continue
                result = extractor(text)
                if result is None:
                    continue
                raw_value, normalized = result
                unit = None
                normalized_value = normalized
                if isinstance(normalized, dict) and "value" in normalized:
                    normalized_value = normalized.get("value")
                    unit = normalized.get("unit")

                candidates.append({
                    "field_code": field_code,
                    "raw_value": raw_value,
                    "normalized_value": normalized_value,
                    "unit": unit,
                    "source_type": source_type,
                    "source_name": document.get("title"),
                    "source_url": source_url,
                    "source_partnumber": pn if exact_page else None,
                    "evidence_text": _evidence_excerpt(text, str(raw_value)),
                    "page_number": page_number,
                    "confidence_rank": confidence,
                    "status": "PENDING",
                })
                extracted_fields.add(field_code)

        return candidates
