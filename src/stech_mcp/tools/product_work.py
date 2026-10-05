from __future__ import annotations

from typing import Any


def register_product_work_tools(mcp: Any, service: Any, *, namespace: Any | None = None) -> dict[str, Any]:
    """Register V2 background-work controls without changing existing server tools."""

    @mcp.tool()
    def product_work_job_create(
        items: list[dict[str, Any]],
        work_type: str = "ENRICH_TECHNICAL",
        source_name: str = "MCP",
        actor_source: str = "CHATGPT",
        priority: int = 50,
    ) -> dict[str, Any]:
        """Create a persistent product work job and return immediately."""
        return service.create_job(
            rows=items,
            work_type=work_type,
            source_name=source_name,
            actor_source=actor_source,
            priority=priority,
        )

    @mcp.tool()
    def product_work_job_get(job_id: int) -> dict[str, Any]:
        """Read a persistent product work job and its items."""
        job = service.get_job(job_id)
        return {"found": job is not None, "job": job}

    @mcp.tool()
    def product_work_job_list(limit: int = 50) -> dict[str, Any]:
        """List recent persistent product work jobs."""
        rows = service.list_jobs(limit=limit)
        return {"count": len(rows), "jobs": rows}

    @mcp.tool()
    def product_work_item_retry(item_id: int) -> dict[str, Any]:
        """Manually requeue an eligible product work item."""
        return service.retry_item(item_id)

    @mcp.tool()
    def product_work_item_cancel(item_id: int) -> dict[str, Any]:
        """Cancel a non-completed product work item."""
        return service.cancel_item(item_id)

    registered = {
        "product_work_job_create": product_work_job_create,
        "product_work_job_get": product_work_job_get,
        "product_work_job_list": product_work_job_list,
        "product_work_item_retry": product_work_item_retry,
        "product_work_item_cancel": product_work_item_cancel,
    }
    if namespace is not None:
        for name, func in registered.items():
            setattr(namespace, name, func)
    return registered
