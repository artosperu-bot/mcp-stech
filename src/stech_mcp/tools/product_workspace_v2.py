from __future__ import annotations

from collections import Counter
from typing import Any


def register_product_workspace_v2_tools(
    mcp: Any,
    *,
    runtime: Any,
    work_service: Any,
    image_readiness_service: Any,
    image_research_service: Any | None = None,
    candidate_repository: Any | None = None,
    channel_gap_analyzer: Any | None = None,
    channel_draft_service: Any | None = None,
    workspace_service: Any | None = None,
    namespace: Any | None = None,
) -> dict[str, Any]:
    """Register safe V2 controls without exposing channel publication writes."""

    @mcp.tool()
    def background_status() -> dict[str, Any]:
        return runtime.status()

    @mcp.tool()
    def background_pause() -> dict[str, Any]:
        return runtime.pause()

    @mcp.tool()
    def background_resume() -> dict[str, Any]:
        return runtime.resume()

    @mcp.tool()
    def background_scan_now() -> dict[str, Any]:
        return runtime.scan_now()

    @mcp.tool()
    def background_config_get() -> dict[str, Any]:
        return runtime.config_get()

    @mcp.tool()
    def background_jobs_summary(limit: int = 200) -> dict[str, Any]:
        bounded = max(1, min(int(limit), 200))
        rows = list(work_service.list_jobs(limit=bounded))
        counts = Counter(str(row.get("status") or "UNKNOWN").upper() for row in rows)
        return {"count": len(rows), "by_status": dict(counts), "jobs": rows}

    @mcp.tool()
    def product_images_readiness(
        partnumber: str,
        category_code: str | None = None,
        channel_code: str = "MASTER",
    ) -> dict[str, Any]:
        return image_readiness_service.get(
            partnumber,
            category_code=category_code,
            channel_code=channel_code,
        )

    @mcp.tool()
    def product_images_research(
        partnumber: str,
        category_code: str | None = None,
        target_count: int | None = None,
    ) -> dict[str, Any]:
        pn = str(partnumber or "").strip().upper()
        if not pn:
            raise ValueError("partnumber is required")
        row: dict[str, Any] = {"partnumber": pn, "scope": "MASTER"}
        category = str(category_code or "").strip().upper()
        if category:
            row["category_code"] = category
        if target_count not in (None, ""):
            row["image_target_count"] = max(1, min(int(target_count), 20))
        return work_service.create_job(
            rows=[row],
            work_type="RESEARCH_IMAGES",
            source_name="MANUAL_WORKSPACE",
            actor_source="MCP",
            priority=100,
        )

    @mcp.tool()
    def product_image_candidates(partnumber: str) -> dict[str, Any]:
        pn = str(partnumber or "").strip().upper()
        if not pn:
            raise ValueError("partnumber is required")
        if candidate_repository is None:
            return {"partnumber": pn, "count": 0, "candidates": []}
        rows = list(candidate_repository.list_for_product(pn))
        return {"partnumber": pn, "count": len(rows), "candidates": rows}

    @mcp.tool()
    def product_channel_gap_get(
        partnumber: str,
        channel_code: str,
        category_code: str,
        requirements_version: str | None = None,
    ) -> dict[str, Any]:
        if channel_gap_analyzer is None:
            return {"state": "NOT_CONFIGURED"}
        return channel_gap_analyzer.get(
            partnumber,
            channel_code,
            category_code,
            requirements_version,
        )

    @mcp.tool()
    def product_channel_draft_prepare(
        partnumber: str,
        channel_code: str,
        category_code: str,
        requirements_version: str | None = None,
    ) -> dict[str, Any]:
        if channel_draft_service is None:
            return {"created": False, "state": "NOT_CONFIGURED"}
        return channel_draft_service.prepare(
            partnumber,
            channel_code,
            category_code,
            requirements_version,
        )

    @mcp.tool()
    def product_workspace_v2_get(partnumber: str) -> dict[str, Any]:
        if workspace_service is None:
            return {"found": False, "partnumber": str(partnumber or "").strip().upper()}
        return workspace_service.get(partnumber)

    registered = {
        "background_status": background_status,
        "background_pause": background_pause,
        "background_resume": background_resume,
        "background_scan_now": background_scan_now,
        "background_config_get": background_config_get,
        "background_jobs_summary": background_jobs_summary,
        "product_images_readiness": product_images_readiness,
        "product_images_research": product_images_research,
        "product_image_candidates": product_image_candidates,
        "product_channel_gap_get": product_channel_gap_get,
        "product_channel_draft_prepare": product_channel_draft_prepare,
        "product_workspace_v2_get": product_workspace_v2_get,
    }
    if namespace is not None:
        for name, func in registered.items():
            setattr(namespace, name, func)
    return registered
