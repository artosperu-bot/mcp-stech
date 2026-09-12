from __future__ import annotations

from typing import Any

from stech_mcp.domain.product_schema import normalize_category_code
from stech_mcp.services.descriptions.technology import laptop_blocks, smartphone_blocks


def _resolved_value(value: Any) -> Any:
    if hasattr(value, "state") and hasattr(value, "value"):
        if str(getattr(value, "state", "") or "").strip().upper() != "RESOLVED":
            return None
        return getattr(value, "value")
    if isinstance(value, dict) and "state" in value and "value" in value:
        if str(value.get("state") or "").strip().upper() != "RESOLVED":
            return None
        return value.get("value")
    return value


def _clean_facts(facts: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, raw in dict(facts or {}).items():
        value = _resolved_value(raw)
        if value not in (None, "", [], (), {}):
            output[str(key)] = value
    return output


def _derived_value(derived_facts: dict[str, Any], field_code: str) -> Any:
    raw = dict(derived_facts or {}).get(field_code)
    if raw is None:
        return None
    if hasattr(raw, "value"):
        return getattr(raw, "value")
    if isinstance(raw, dict):
        return raw.get("value")
    return raw


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    if limit <= 1:
        return text[:limit]
    shortened = text[: limit - 1].rstrip()
    if " " in shortened:
        shortened = shortened.rsplit(" ", 1)[0].rstrip()
    return shortened + "…"


class DescriptionBuilder:
    """Generate deterministic descriptions only from supplied canonical facts."""

    def build(
        self,
        partnumber: str,
        category_code: str,
        facts: dict[str, Any],
        *,
        derived_facts: dict[str, Any] | None = None,
        max_chars: int = 3000,
        identity_footer: bool = True,
    ) -> str:
        pn = str(partnumber or "").strip().upper()
        if not pn:
            raise ValueError("partnumber is required")
        category = normalize_category_code(category_code)
        if not category:
            raise ValueError("category_code is required")
        limit = int(max_chars)
        if limit <= 0:
            raise ValueError("max_chars must be greater than zero")

        clean = _clean_facts(facts)
        if category == "LAPTOP":
            blocks = laptop_blocks(clean)
        elif category in {"SMARTPHONE", "CELULAR", "PHONE"}:
            blocks = smartphone_blocks(clean)
        else:
            subject = " ".join(
                value
                for value in (
                    str(clean.get("brand") or "").strip(),
                    str(clean.get("model") or "").strip(),
                )
                if value
            )
            blocks = [subject + "."] if subject else []

        gama = _derived_value(dict(derived_facts or {}), "gama")
        if gama not in (None, ""):
            blocks.append(f"Clasificación de gama: {gama}.")

        body = "\n\n".join(block.strip() for block in blocks if block.strip())
        footer_parts: list[str] = []
        if identity_footer:
            if clean.get("model") not in (None, ""):
                footer_parts.append(f"Modelo: {clean['model']}")
            footer_parts.append(f"Part Number: {pn}")
            for key, label in (("ean", "EAN"), ("upc", "UPC"), ("gtin", "GTIN")):
                if clean.get(key) not in (None, ""):
                    footer_parts.append(f"{label}: {clean[key]}")
        footer = " | ".join(footer_parts)

        if footer:
            separator = "\n\n" if body else ""
            full = body + separator + footer
            if len(full) <= limit:
                return full
            body_limit = limit - len(footer) - len(separator)
            if body_limit > 0:
                return _truncate(body, body_limit) + separator + footer
            return _truncate(footer, limit)
        return _truncate(body, limit)
