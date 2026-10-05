from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Evidence:
    value: str
    source_type: str
    confidence_grade: str
    source_partnumber: str | None = None
    source_url: str | None = None
    evidence_text: str | None = None


_RANK = {"A1": 500, "A2": 400, "B": 300, "C": 200, "D": 100, "E": 0}
_VARIANT_SPECIFIC = {
    # Legacy/general aliases kept for compatibility.
    "ram",
    "ssd",
    "cpu",
    "operating_system",
    "color",
    "gpu",
    "storage",
    # Canonical V2 technical fields whose value may differ by exact PN/variant.
    "cpu_model",
    "ram_gb",
    "storage_gb",
    "storage_type",
    "os_name",
    "battery_wh",
    "speaker_power_w",
    "battery_runtime_hours",
    "battery_capacity_wh",
    "charging_time_hours",
}


def choose_best_evidence(items: list[Evidence]) -> Evidence:
    if not items:
        raise ValueError("At least one evidence item is required")
    return max(items, key=lambda item: _RANK.get(item.confidence_grade.upper(), -1))


def is_variant_sensitive(field_code: str) -> bool:
    return field_code.strip().lower() in _VARIANT_SPECIFIC


def can_use_same_chassis(field_code: str) -> bool:
    return not is_variant_sensitive(field_code)
