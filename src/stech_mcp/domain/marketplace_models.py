from __future__ import annotations

from decimal import Decimal
from typing import Literal, TypedDict


class ResolvedPackage(TypedDict):
    width_cm: Decimal
    length_cm: Decimal
    height_cm: Decimal
    weight_g: int
    status: str
    method: str
    source: str
    rule_code: str | None
    confidence_grade: str


class MarketplaceFieldState(TypedDict, total=False):
    field: str
    value: object
    status: Literal[
        "DISTRIBUTOR",
        "VERIFIED",
        "DERIVED",
        "ESTIMATED",
        "MANUAL",
        "RESEARCH_REQUIRED",
        "OPTIONAL",
        "MARKETPLACE_INPUT",
        "CONFLICT",
    ]
    source: str | None
    method: str | None
    note: str | None
