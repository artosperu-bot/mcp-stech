from __future__ import annotations

from dataclasses import asdict
from typing import Any

from stech_mcp.domain.product_schema import normalize_category_code


def register_product_schema_tools(
    mcp: Any,
    *,
    schema_repository: Any,
    technical_status_service: Any,
    namespace: Any | None = None,
) -> dict[str, Any]:
    """Register channel-neutral technical schema/status tools additively."""

    @mcp.tool()
    def product_schema_get(category: str) -> dict[str, Any]:
        """Return the canonical STECH technical schema for a supported category."""
        category_code = normalize_category_code(category)
        rows = schema_repository.get_category_schema(category_code)
        return {
            "found": bool(rows),
            "category_code": category_code,
            "field_count": len(rows),
            "fields": [asdict(row) for row in rows],
        }

    @mcp.tool()
    def product_technical_status(partnumber: str) -> dict[str, Any]:
        """Return known and missing canonical technical fields for one product."""
        try:
            result = technical_status_service.get(partnumber)
        except LookupError as exc:
            return {
                "found": False,
                "partnumber": str(partnumber or "").strip().upper(),
                "error": str(exc),
            }
        return {"found": True, **result}

    registered = {
        "product_schema_get": product_schema_get,
        "product_technical_status": product_technical_status,
    }
    if namespace is not None:
        for name, func in registered.items():
            setattr(namespace, name, func)
    return registered
