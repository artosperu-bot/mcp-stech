from __future__ import annotations

import re
from typing import Any


_NUMBER = r"(-?\d+(?:[.,]\d+)?)"


def _number(value: str) -> float:
    return float(value.replace(",", "."))


def _compact(value: float) -> int | float:
    rounded = round(float(value), 6)
    return int(rounded) if rounded.is_integer() else rounded


def normalize_weight(value: Any, *, target_unit: str | None = None) -> dict[str, Any] | None:
    text = str(value or "").strip()
    match = re.search(rf"{_NUMBER}\s*(kg|g)\b", text, re.I)
    if not match:
        return None
    amount = _number(match.group(1))
    source_unit = match.group(2).lower()
    target = (target_unit or source_unit).strip().lower()
    if target not in {"kg", "g"}:
        return None
    grams = amount * 1000 if source_unit == "kg" else amount
    normalized = grams / 1000 if target == "kg" else grams
    return {"value": _compact(normalized), "unit": target}


def normalize_bluetooth(value: Any) -> str | None:
    text = str(value or "").strip()
    match = re.search(r"(?:bluetooth\s*)?(?:v(?:ersion)?\s*)?([2-6](?:\.\d{1,2})?)\b", text, re.I)
    return match.group(1) if match else None


def normalize_ip_rating(value: Any) -> str | None:
    match = re.search(r"\bIP\s*([0-6X][0-9X](?:[A-Z])?)\b", str(value or ""), re.I)
    return f"IP{match.group(1).upper()}" if match else None


def normalize_power_w(value: Any) -> dict[str, Any] | None:
    match = re.search(rf"{_NUMBER}\s*W\b", str(value or ""), re.I)
    if not match:
        return None
    return {"value": _compact(_number(match.group(1))), "unit": "W"}


def normalize_capacity_wh(value: Any) -> dict[str, Any] | None:
    match = re.search(rf"{_NUMBER}\s*W\s*H\b", str(value or ""), re.I)
    if not match:
        return None
    return {"value": _compact(_number(match.group(1))), "unit": "Wh"}


def normalize_duration_hours(value: Any) -> dict[str, Any] | None:
    text = str(value or "").strip()
    match = re.search(rf"{_NUMBER}\s*(?:h|hr|hrs|hora|horas)\b", text, re.I)
    if not match:
        return None
    return {"value": _compact(_number(match.group(1))), "unit": "h"}


def normalize_dimensions(value: Any) -> dict[str, Any] | None:
    text = str(value or "").strip().replace("×", "x")
    match = re.search(
        rf"{_NUMBER}\s*[xX]\s*{_NUMBER}\s*[xX]\s*{_NUMBER}\s*(mm|cm)\b",
        text,
        re.I,
    )
    if not match:
        return None
    numbers = [_number(match.group(i)) for i in (1, 2, 3)]
    source_unit = match.group(4).lower()
    multiplier = 10 if source_unit == "cm" else 1
    return {"value": [_compact(number * multiplier) for number in numbers], "unit": "mm"}


def _frequency_to_hz(number: str, prefix: str | None) -> float:
    value = _number(number)
    return value * 1000 if (prefix or "").lower() == "k" else value


def normalize_frequency_range(value: Any) -> dict[str, Any] | None:
    text = str(value or "").strip().replace("–", "-").replace("—", "-")
    match = re.search(
        rf"{_NUMBER}\s*(k)?\s*hz\s*(?:-|a|to)\s*{_NUMBER}\s*(k)?\s*hz\b",
        text,
        re.I,
    )
    if not match:
        return None
    low = _frequency_to_hz(match.group(1), match.group(2))
    high = _frequency_to_hz(match.group(3), match.group(4))
    if low <= 0 or high <= low:
        return None
    return {"value": [_compact(low), _compact(high)], "unit": "Hz"}


def normalize_ram_gb(value: Any) -> dict[str, Any] | None:
    match = re.search(rf"{_NUMBER}\s*(GB|TB)\b", str(value or ""), re.I)
    if not match:
        return None
    amount = _number(match.group(1))
    if match.group(2).upper() == "TB":
        amount *= 1024
    return {"value": _compact(amount), "unit": "GB"}


def normalize_storage_gb(value: Any) -> dict[str, Any] | None:
    return normalize_ram_gb(value)


def normalize_resolution(value: Any) -> str | None:
    text = str(value or "").replace("×", "x")
    match = re.search(r"\b(\d{3,5})\s*[xX]\s*(\d{3,5})\b", text)
    return f"{int(match.group(1))}x{int(match.group(2))}" if match else None


def normalize_mm(value: Any) -> dict[str, Any] | None:
    match = re.search(rf"{_NUMBER}\s*mm\b", str(value or ""), re.I)
    if not match:
        return None
    return {"value": _compact(_number(match.group(1))), "unit": "mm"}


def normalize_inches(value: Any) -> dict[str, Any] | None:
    text = str(value or "").strip()
    match = re.search(rf'{_NUMBER}\s*(?:inches?|in|pulg(?:adas?)?|")', text, re.I)
    if not match:
        return None
    return {"value": _compact(_number(match.group(1))), "unit": "in"}


def normalize_ohm(value: Any) -> dict[str, Any] | None:
    match = re.search(rf"{_NUMBER}\s*(?:ohm|Ω)\b?", str(value or ""), re.I)
    if not match:
        return None
    return {"value": _compact(_number(match.group(1))), "unit": "ohm"}


def normalize_db(value: Any) -> dict[str, Any] | None:
    match = re.search(rf"{_NUMBER}\s*dB\b", str(value or ""), re.I)
    if not match:
        return None
    return {"value": _compact(_number(match.group(1))), "unit": "dB"}


def normalize_boolean(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"si", "sí", "yes", "true", "1", "incluye", "incluido"}:
        return True
    if text in {"no", "false", "0", "no incluye"}:
        return False
    return None


def normalize_text(value: Any) -> str | None:
    text = " ".join(str(value or "").split())
    return text or None


def normalize_storage_type(value: Any) -> str | None:
    upper = str(value or "").upper()
    for token in ("NVME", "SSD", "HDD", "EMMC", "UFS"):
        if re.search(rf"\b{token}\b", upper):
            return token
    return None
