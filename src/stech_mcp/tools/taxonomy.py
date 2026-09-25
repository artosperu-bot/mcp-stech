from __future__ import annotations

from typing import Any


def register_taxonomy_tools(
    mcp: Any,
    *,
    service: Any,
    namespace: Any | None = None,
) -> dict[str, Any]:
    """Expose review-first STECH taxonomy tools.

    Detection and proposals are safe/read-only for DB_DISTRIBUIDORES.
    taxonomy_apply is the only source write and requires an APPROVED review.
    """

    @mcp.tool()
    def taxonomy_missing_list(
        limit: int = 100,
        distributor: str | None = None,
    ) -> dict[str, Any]:
        """List active source products missing category or subcategory."""
        return service.missing(limit=limit, distributor=distributor)

    @mcp.tool()
    def taxonomy_catalog_get(limit: int = 1000) -> dict[str, Any]:
        """Return existing STECH category/subcategory pairs and product counts."""
        return service.catalog(limit=limit)

    @mcp.tool()
    def taxonomy_review_sync(
        limit: int = 1000,
        distributor: str | None = None,
    ) -> dict[str, Any]:
        """Detect taxonomy gaps and place them in the STECH_MCP review queue."""
        return service.sync(limit=limit, distributor=distributor)

    @mcp.tool()
    def taxonomy_review_list(
        status: str | None = "PENDING",
        limit: int = 100,
    ) -> dict[str, Any]:
        """List taxonomy review rows by workflow status."""
        return service.list(status=status, limit=limit)

    @mcp.tool()
    def taxonomy_review_get(review_id: int) -> dict[str, Any]:
        """Read one taxonomy review and its proposal/audit fields."""
        return service.get(int(review_id))

    @mcp.tool()
    def taxonomy_propose(
        review_id: int,
        category: str,
        subcategory: str,
        confidence: str = "MEDIA",
        reason: str = "",
        evidence: list[str] | None = None,
        proposed_by: str = "CHATGPT",
    ) -> dict[str, Any]:
        """Store a proposal and mark whether it reuses or extends STECH taxonomy."""
        return service.propose(
            int(review_id),
            category=category,
            subcategory=subcategory,
            confidence=confidence,
            reason=reason,
            evidence=evidence,
            proposed_by=proposed_by,
        )

    @mcp.tool()
    def taxonomy_sql_preview(review_id: int) -> dict[str, Any]:
        """Preview the guarded SQL/parameters that an approved review will apply."""
        return service.sql_preview(int(review_id))

    @mcp.tool()
    def taxonomy_approve(
        review_id: int,
        approved_by: str = "USER",
    ) -> dict[str, Any]:
        """Explicitly approve a proposed taxonomy change; does not write source yet."""
        return service.approve(int(review_id), approved_by=approved_by)

    @mcp.tool()
    def taxonomy_reject(
        review_id: int,
        rejected_by: str = "USER",
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Reject a taxonomy proposal without changing DB_DISTRIBUIDORES."""
        return service.reject(int(review_id), rejected_by=rejected_by, reason=reason)

    @mcp.tool()
    def taxonomy_apply(
        review_id: int,
        applied_by: str = "CHATGPT",
    ) -> dict[str, Any]:
        """Apply only an APPROVED review to missing source fields by source product id."""
        return service.apply(int(review_id), applied_by=applied_by)

    registered = {
        "taxonomy_missing_list": taxonomy_missing_list,
        "taxonomy_catalog_get": taxonomy_catalog_get,
        "taxonomy_review_sync": taxonomy_review_sync,
        "taxonomy_review_list": taxonomy_review_list,
        "taxonomy_review_get": taxonomy_review_get,
        "taxonomy_propose": taxonomy_propose,
        "taxonomy_sql_preview": taxonomy_sql_preview,
        "taxonomy_approve": taxonomy_approve,
        "taxonomy_reject": taxonomy_reject,
        "taxonomy_apply": taxonomy_apply,
    }
    if namespace is not None:
        for name, func in registered.items():
            setattr(namespace, name, func)
    return registered
