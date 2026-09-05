from __future__ import annotations

from decimal import Decimal
from typing import Any

from stech_mcp.domain.marketplace_models import ResolvedPackage


_PACKAGE_FIELDS = (
    "package_width_cm",
    "package_length_cm",
    "package_height_cm",
    "package_weight_g",
)
_CONFIDENCE_RANK = {"A1": 1, "A2": 2, "B": 3, "C": 4, "D": 5, "E": 6}


def _as_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _resolved_from_enrichment(rows: list[dict[str, Any]]) -> ResolvedPackage | None:
    by_code = {str(row.get("field_code")): row for row in rows}
    if not all(code in by_code for code in _PACKAGE_FIELDS):
        return None

    width = _as_decimal(by_code["package_width_cm"].get("value_number"))
    length = _as_decimal(by_code["package_length_cm"].get("value_number"))
    height = _as_decimal(by_code["package_height_cm"].get("value_number"))
    weight = _as_decimal(by_code["package_weight_g"].get("value_number"))
    if None in (width, length, height, weight):
        return None
    assert width is not None and length is not None and height is not None and weight is not None
    if width <= 0 or length <= 0 or height <= 0 or weight <= 0:
        return None

    methods = [str(by_code[code].get("method") or "VERIFIED").upper() for code in _PACKAGE_FIELDS]
    method = "VERIFIED" if all(item == "VERIFIED" for item in methods) else methods[0]
    grades = [str(by_code[code].get("confidence_grade") or "E").upper() for code in _PACKAGE_FIELDS]
    confidence_grade = max(grades, key=lambda item: _CONFIDENCE_RANK.get(item, 99))

    sources = [
        str(by_code[code].get("source") or "").strip()
        for code in _PACKAGE_FIELDS
        if str(by_code[code].get("source") or "").strip()
    ]
    source = sources[0] if sources and len(set(sources)) == 1 else "STECH_MCP.product_enrichment"

    return {
        "width_cm": width,
        "length_cm": length,
        "height_cm": height,
        "weight_g": int(weight),
        "status": method,
        "method": method,
        "source": source,
        "rule_code": None,
        "confidence_grade": confidence_grade,
    }


def resolve_package(
    *,
    partnumber: str,
    category_code: str,
    screen_inches: Decimal,
    enrichment_repository: Any,
    packaging_rule_repository: Any,
) -> ResolvedPackage:
    approved = enrichment_repository.get_approved(partnumber.strip(), list(_PACKAGE_FIELDS))
    resolved = _resolved_from_enrichment(approved)
    if resolved is not None:
        return resolved

    rule = packaging_rule_repository.match(category_code.strip().upper(), screen_inches)
    if rule is None:
        raise LookupError(
            f"No packaging data or fallback rule for category={category_code.strip().upper()} "
            f"screen_inches={screen_inches}"
        )

    return {
        "width_cm": Decimal(str(rule["width_cm"])),
        "length_cm": Decimal(str(rule["length_cm"])),
        "height_cm": Decimal(str(rule["height_cm"])),
        "weight_g": int(rule["weight_g"]),
        "status": "ESTIMATED",
        "method": "ESTIMATED",
        "source": str(rule["source_code"]),
        "rule_code": str(rule["rule_code"]),
        "confidence_grade": "E",
    }
