from __future__ import annotations

from typing import Any, Mapping

from stech_mcp.domain.derived_fact import DerivedFact


class ProductDataReadinessService:
    """Evaluate channel-neutral product-data readiness.

    Commercial and logistics inputs are intentionally excluded. A product can be
    data-ready even when price, stock, package logistics or a marketplace are not.
    """

    _IDENTITY_FIELDS = (
        ("partnumber", ("partnumber", "part_number")),
        ("brand", ("brand", "marca")),
        ("name", ("name", "nombre", "product_name")),
    )

    @staticmethod
    def _present(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        return True

    @classmethod
    def _first_present(cls, source: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
        for key in keys:
            value = source.get(key)
            if cls._present(value):
                return value
        return None

    def evaluate(
        self,
        *,
        product: Mapping[str, Any],
        technical: Mapping[str, Any] | None,
        derived_facts: Mapping[str, DerivedFact | Mapping[str, Any] | Any] | None = None,
    ) -> dict[str, Any]:
        technical_data = dict(technical or {})
        derived = dict(derived_facts or {})

        missing_identity = [
            canonical
            for canonical, aliases in self._IDENTITY_FIELDS
            if not self._present(self._first_present(product, aliases))
        ]

        raw_missing_required = [
            str(field or "").strip()
            for field in (technical_data.get("missing_required") or [])
            if str(field or "").strip()
        ]
        conflicts = [
            str(field or "").strip()
            for field in (technical_data.get("conflicts") or [])
            if str(field or "").strip()
        ]

        derived_fields: list[str] = []
        missing_required: list[str] = []
        for field_code in raw_missing_required:
            candidate = derived.get(field_code)
            if isinstance(candidate, DerivedFact):
                value = candidate.value
            elif isinstance(candidate, Mapping):
                value = candidate.get("value")
            else:
                value = candidate
            if self._present(value):
                derived_fields.append(field_code)
            else:
                missing_required.append(field_code)

        technical_state = str(technical_data.get("state") or "").strip().upper()
        schema_not_configured = technical_state == "NOT_CONFIGURED"

        if conflicts:
            status = "REVIEW_REQUIRED"
        elif missing_identity or missing_required or schema_not_configured:
            status = "INCOMPLETO"
        else:
            status = "LISTO"

        return {
            "product_data_status": status,
            "missing_identity": missing_identity,
            "missing_required": missing_required,
            "conflicts": conflicts,
            "derived_fields": derived_fields,
            "technical_state": technical_state or None,
            "commercial_fields_ignored": ["price", "stock", "cost", "promotion"],
            "logistics_fields_ignored": [
                "package_weight_g",
                "package_height_mm",
                "package_width_mm",
                "package_length_mm",
            ],
        }
