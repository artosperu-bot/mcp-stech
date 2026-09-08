from __future__ import annotations

from typing import Any

from stech_mcp.domain.product_schema import normalize_category_code, normalize_field_code


_SUPPORTED_CATEGORIES = {"LAPTOP", "PORTABLE_SPEAKER", "HEADPHONES"}
_CATEGORY_KEYS = (
    "category_code",
    "categoria_code",
    "categoria",
    "subcategoria",
    "familia",
    "tipo_producto",
    "tipo",
)
_CATEGORY_KEYWORDS = {
    "LAPTOP": ("LAPTOP", "NOTEBOOK", "PORTATIL", "PORTÁTIL"),
    "PORTABLE_SPEAKER": ("PARLANTE", "ALTAVOZ", "SPEAKER", "BOOMBOX"),
    "HEADPHONES": ("AUDIFONO", "AUDÍFONO", "AURICULAR", "HEADPHONE", "HEADSET"),
}


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    return True


def _resolve_category(product: dict[str, Any]) -> str:
    for key in _CATEGORY_KEYS:
        raw = product.get(key)
        if not _has_value(raw):
            continue
        normalized = normalize_category_code(raw)
        if normalized in _SUPPORTED_CATEGORIES:
            return normalized

    haystack = " ".join(
        str(product.get(key) or "")
        for key in (*_CATEGORY_KEYS, "nombre", "name", "descripcion")
    ).upper()
    for category_code, keywords in _CATEGORY_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            return category_code

    raise LookupError("supported technical category could not be resolved")


def _approved_value(row: dict[str, Any]) -> Any:
    if row.get("value_number") is not None:
        return row["value_number"]
    return row.get("value_text")


class ProductTechnicalStatusService:
    def __init__(
        self,
        *,
        product_repository: Any,
        enrichment_repository: Any,
        schema_repository: Any,
    ) -> None:
        self.product_repository = product_repository
        self.enrichment_repository = enrichment_repository
        self.schema_repository = schema_repository

    def get(self, partnumber: str) -> dict[str, Any]:
        normalized_pn = str(partnumber or "").strip().upper()
        if not normalized_pn:
            raise ValueError("partnumber is required")

        product = self.product_repository.get_by_partnumber(normalized_pn)
        if product is None:
            raise LookupError(f"product not found: {normalized_pn}")

        category_code = _resolve_category(product)
        schema = self.schema_repository.get_category_schema(category_code)
        if not schema:
            raise LookupError(f"technical schema not found: {category_code}")

        schema_fields = {item.field_code for item in schema}
        known_fields: dict[str, Any] = {}

        # Only accept already-canonical direct product keys here. Deltron
        # atributos_json is deliberately not interpreted until the dedicated
        # adapter/normalizers layer (Plan B Task 3).
        for field_code in schema_fields:
            value = product.get(field_code)
            if _has_value(value):
                known_fields[field_code] = value

        # Approved enrichment is canonical and has precedence over raw/direct
        # values. Commercial fields are impossible here because only schema
        # field codes are accepted.
        for row in self.enrichment_repository.get_approved(normalized_pn):
            field_code = normalize_field_code(row.get("field_code"))
            if field_code not in schema_fields:
                continue
            value = _approved_value(row)
            if _has_value(value):
                known_fields[field_code] = value

        missing_required = [
            item.field_code
            for item in schema
            if item.requirement == "REQUIRED" and item.field_code not in known_fields
        ]
        missing_recommended = [
            item.field_code
            for item in schema
            if item.requirement == "RECOMMENDED" and item.field_code not in known_fields
        ]
        completed = sum(1 for item in schema if item.field_code in known_fields)
        completion_pct = round((completed / len(schema)) * 100) if schema else 0

        return {
            "partnumber": normalized_pn,
            "category_code": category_code,
            "known_fields": known_fields,
            "missing_required": missing_required,
            "missing_recommended": missing_recommended,
            "conflicts": [],
            "completion_pct": completion_pct,
        }
