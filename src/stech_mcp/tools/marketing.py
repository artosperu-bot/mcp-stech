from __future__ import annotations

from typing import Any


def register_marketing_tools(
    mcp: Any,
    *,
    context_service: Any,
    namespace: Any | None = None,
) -> dict[str, Any]:
    """Expose the read-only HERMES marketing contract through MCP."""

    @mcp.tool()
    def marketing_product_context(partnumber: str) -> dict[str, Any]:
        """Return verified product, technical, media and operational context for HERMES."""
        return context_service.get(partnumber)

    @mcp.tool()
    def marketing_readiness(partnumber: str) -> dict[str, Any]:
        """Check whether a product is safe to use as input for creative generation."""
        return context_service.readiness(partnumber)

    @mcp.tool()
    def marketing_media_manifest(partnumber: str) -> dict[str, Any]:
        """Return exact/approved product references and PRODUCT_LOCK policy."""
        return context_service.media_manifest(partnumber)

    registered = {
        "marketing_product_context": marketing_product_context,
        "marketing_readiness": marketing_readiness,
        "marketing_media_manifest": marketing_media_manifest,
    }
    if namespace is not None:
        for name, func in registered.items():
            setattr(namespace, name, func)
    return registered
