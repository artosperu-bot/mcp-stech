from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from stech_mcp.domain.product_schema import normalize_category_code, normalize_field_code


_COMMERCIAL_FIELDS = frozenset(
    {
        "price",
        "precio",
        "sale_price",
        "stock",
        "stock_total",
        "cost",
        "costo",
        "promotion",
        "promotions",
        "promotion_start",
        "promotion_end",
    }
)


@dataclass(frozen=True)
class FactResolution:
    field_code: str
    state: str
    value: Any | None = None
    method: str | None = None
    source: str | None = None
    confidence_grade: str | None = None
    policy_code: str | None = None
    alternatives: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProductResolution:
    partnumber: str
    category_code: str
    facts: dict[str, FactResolution]
    rejected_fields: tuple[str, ...] = ()


def _row_value(row: dict[str, Any]) -> Any:
    if row.get("value_number") is not None:
        return row.get("value_number")
    if row.get("value_text") not in (None, ""):
        return row.get("value_text")
    return row.get("normalized_value")


def _value_key(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return str(value)


def _unique_values(values: list[Any], *, exclude: Any | None = None) -> tuple[str, ...]:
    excluded = None if exclude is None else _value_key(exclude)
    output: list[str] = []
    for value in values:
        if value is None:
            continue
        key = _value_key(value)
        if key == excluded or key in output:
            continue
        output.append(key)
    return tuple(output)


class ProductFactResolver:
    """Read canonical product truth without mutating source or channel data.

    Manual approved values always win. Deltron exact-PN data is usable directly
    when no stronger approved value exists, and may be declared authoritative
    per field. Without explicit precedence, incompatible approved and Deltron
    values are exposed as a conflict instead of silently overwriting either one.
    """

    def __init__(
        self,
        *,
        product_repository: Any,
        enrichment_repository: Any,
        deltron_adapter: Any,
        fact_candidate_repository: Any,
        field_policy: dict[str, str] | None = None,
    ) -> None:
        self.product_repository = product_repository
        self.enrichment_repository = enrichment_repository
        self.deltron_adapter = deltron_adapter
        self.fact_candidate_repository = fact_candidate_repository
        self.field_policy = {
            normalize_field_code(field): str(policy or "").strip().upper()
            for field, policy in dict(field_policy or {}).items()
            if normalize_field_code(field)
        }

    def resolve(
        self,
        partnumber: str,
        field_codes: list[str] | tuple[str, ...],
        category_code: str,
    ) -> ProductResolution:
        pn = str(partnumber or "").strip().upper()
        category = normalize_category_code(category_code)
        if not pn:
            raise ValueError("partnumber is required")
        if not category:
            raise ValueError("category_code is required")

        product = self.product_repository.get_by_partnumber(pn)
        if product is None:
            raise LookupError(f"product not found: {pn}")

        requested: list[str] = []
        rejected: list[str] = []
        for raw in field_codes or []:
            code = normalize_field_code(raw)
            if not code or code in requested or code in rejected:
                continue
            if code in _COMMERCIAL_FIELDS:
                rejected.append(code)
            else:
                requested.append(code)

        approved_rows = self.enrichment_repository.get_approved(pn, requested or None) or []
        approved_by_field = {
            normalize_field_code(row.get("field_code")): row
            for row in approved_rows
            if normalize_field_code(row.get("field_code")) in requested
        }
        deltron_rows = self.deltron_adapter.adapt(product, category_code=category) or []
        deltron_by_field = {
            normalize_field_code(row.get("field_code")): row
            for row in deltron_rows
            if normalize_field_code(row.get("field_code")) in requested
            and str(row.get("source_partnumber") or "").strip().upper() == pn
        }
        candidate_rows = self.fact_candidate_repository.list_for_product(pn) or []
        conflicts_by_field: dict[str, list[dict[str, Any]]] = {}
        for row in candidate_rows:
            code = normalize_field_code(row.get("field_code"))
            if code not in requested:
                continue
            if str(row.get("state") or "").strip().upper() == "CONFLICT":
                conflicts_by_field.setdefault(code, []).append(row)

        facts: dict[str, FactResolution] = {}
        for code in requested:
            approved = approved_by_field.get(code)
            distributor = deltron_by_field.get(code)
            conflict_rows = conflicts_by_field.get(code, [])
            approved_value = _row_value(approved) if approved else None
            distributor_value = _row_value(distributor) if distributor else None
            conflict_values = [_row_value(row) for row in conflict_rows]
            method = str((approved or {}).get("method") or "").strip().upper()
            policy = self.field_policy.get(code)

            if approved is not None and method == "MANUAL":
                facts[code] = FactResolution(
                    field_code=code,
                    state="RESOLVED",
                    value=approved_value,
                    method="MANUAL",
                    source="APPROVED_ENRICHMENT",
                    confidence_grade=str(approved.get("confidence_grade") or "").strip().upper() or None,
                    alternatives=_unique_values(
                        [distributor_value, *conflict_values],
                        exclude=approved_value,
                    ),
                )
                continue

            if policy == "DELTRON_AUTHORITATIVE" and distributor is not None:
                facts[code] = FactResolution(
                    field_code=code,
                    state="RESOLVED",
                    value=distributor_value,
                    method="DISTRIBUTOR",
                    source="DELTRON",
                    confidence_grade=str(distributor.get("confidence_rank") or "B").strip().upper() or "B",
                    policy_code=policy,
                    alternatives=_unique_values(
                        [approved_value, *conflict_values],
                        exclude=distributor_value,
                    ),
                )
                continue

            has_candidate_conflict = bool(conflict_rows)
            approved_disagrees = (
                approved is not None
                and distributor is not None
                and _value_key(approved_value) != _value_key(distributor_value)
            )
            if has_candidate_conflict or approved_disagrees:
                facts[code] = FactResolution(
                    field_code=code,
                    state="CONFLICT",
                    alternatives=_unique_values(
                        [approved_value, distributor_value, *conflict_values]
                    ),
                )
                continue

            if approved is not None:
                facts[code] = FactResolution(
                    field_code=code,
                    state="RESOLVED",
                    value=approved_value,
                    method=method or "VERIFIED",
                    source="APPROVED_ENRICHMENT",
                    confidence_grade=str(approved.get("confidence_grade") or "").strip().upper() or None,
                )
                continue

            if distributor is not None:
                facts[code] = FactResolution(
                    field_code=code,
                    state="RESOLVED",
                    value=distributor_value,
                    method="DISTRIBUTOR",
                    source="DELTRON",
                    confidence_grade=str(distributor.get("confidence_rank") or "B").strip().upper() or "B",
                )
                continue

            facts[code] = FactResolution(field_code=code, state="MISSING")

        return ProductResolution(
            partnumber=pn,
            category_code=category,
            facts=facts,
            rejected_fields=tuple(rejected),
        )
