from __future__ import annotations

from typing import Any, Callable

from stech_mcp.domain.derived_fact import DerivedFact
from stech_mcp.domain.product_schema import normalize_category_code, normalize_field_code
from stech_mcp.services.rules.laptop_gama_v1 import derive_laptop_gama_v1


Rule = Callable[..., DerivedFact | None]


class DerivedRuleEngine:
    """Dispatch deterministic derived facts by canonical field and category."""

    def __init__(self) -> None:
        self._rules: dict[tuple[str, str], Rule] = {
            ("LAPTOP", "gama"): derive_laptop_gama_v1,
        }

    def derive(
        self,
        field_code: str,
        category_code: str,
        facts: dict[str, Any],
        *,
        context: dict[str, Any] | None = None,
    ) -> DerivedFact | None:
        category = normalize_category_code(category_code)
        field = normalize_field_code(field_code)
        rule = self._rules.get((category, field))
        if rule is None:
            return None
        return rule(dict(facts or {}), context=dict(context or {}))
