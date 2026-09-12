from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from stech_mcp.domain.product_schema import normalize_category_code, normalize_field_code


@dataclass(frozen=True)
class GapRequest:
    field_code: str
    reason: str
    action: str


class ProductGapPlanner:
    """Turn canonical fact state into bounded research/review work."""

    def __init__(self, resolver: Any) -> None:
        self.resolver = resolver

    def plan(
        self,
        partnumber: str,
        category_code: str,
        field_codes: list[str] | tuple[str, ...],
        *,
        stale_fields: list[str] | tuple[str, ...] | None = None,
    ) -> list[GapRequest]:
        pn = str(partnumber or "").strip().upper()
        category = normalize_category_code(category_code)
        fields: list[str] = []
        for raw in field_codes or []:
            code = normalize_field_code(raw)
            if code and code not in fields:
                fields.append(code)
        stale = {
            normalize_field_code(value)
            for value in (stale_fields or [])
            if normalize_field_code(value)
        }

        resolution = self.resolver.resolve(pn, fields, category)
        gaps: list[GapRequest] = []
        for code in fields:
            fact = resolution.facts.get(code)
            if fact is None:
                continue
            state = str(getattr(fact, "state", "") or "").strip().upper()
            if state == "MISSING":
                gaps.append(GapRequest(field_code=code, reason="MISSING", action="RESEARCH"))
            elif state == "CONFLICT":
                gaps.append(GapRequest(field_code=code, reason="CONFLICT", action="REVIEW"))
            elif code in stale:
                gaps.append(GapRequest(field_code=code, reason="STALE", action="RESEARCH"))
        return gaps
