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
_VARIANT_SPECIFIC = {"ram", "ssd", "cpu", "operating_system", "color", "gpu", "storage"}


def choose_best_evidence(items: list[Evidence]) -> Evidence:
    if not items:
        raise ValueError("At least one evidence item is required")
    return max(items, key=lambda item: _RANK.get(item.confidence_grade.upper(), -1))


def can_use_same_chassis(field_code: str) -> bool:
    return field_code.strip().lower() not in _VARIANT_SPECIFIC
