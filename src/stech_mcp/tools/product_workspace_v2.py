from __future__ import annotations

from collections import Counter
from typing import Any

from stech_mcp.tools.core import set_health_extra_provider


def register_product_workspace_v2_tools(
    mcp: Any,
    *,
    runtime: Any,
    work_service: Any,
    image_readiness_service: Any,
    image_research_service: Any | None = None,
    candidate_repository: Any | None = None,
    candidate_import_service: Any | None = None,
    channel_gap_analyzer: Any | None = None,
    channel_draft_service: Any | None = None,
    workspace_service: Any | None = None,
    namespace: Any | None = None,
) -> dict[str, Any]:
    """Register safe V2 controls without exposing channel publication writes."""

    def _partnumbers(values: list[str], *, max_items: int = 2000) -> list[str]:
        rows: list[str] = []
        seen: set[str] = set()
        for raw in list(values or [])[:max_items]:
            pn = str(raw or "").strip().upper()
            if not pn or pn in seen:
                continue
            seen.add(pn)
            rows.append(pn)
        if not rows:
            raise ValueError("at least one valid partnumber is required")
        return rows

    def _research_rows(
        partnumbers: list[str],
        category_code: str | None,
        target_count: int | None,
    ) -> list[dict[str, Any]]:
        category = str(category_code or "").strip().upper()
        desired = None if target_count in (None, "") else max(1, min(int(target_count), 20))
        rows: list[dict[str, Any]] = []
        for pn in _partnumbers(partnumbers):
            row: dict[str, Any] = {"partnumber": pn, "scope": "MASTER"}
            if category:
                row["category_code"] = category
            if desired is not None:
                row["image_target_count"] = desired
            rows.append(row)
        return rows

    def _health_extra() -> dict[str, Any]:
        background = dict(runtime.status())
        threads = list(getattr(runtime, "_worker_threads", []) or [])
        background["workers_alive"] = sum(1 for thread in threads if thread.is_alive())
        recent_jobs = list(work_service.list_jobs(limit=50))
        background["jobs"] = dict(
            Counter(str(row.get("status") or "UNKNOWN").upper() for row in recent_jobs)
        )
        background["recovery"] = "LEASE_RECOVERY_ON_WORKER_START"
        return {"authoritative_v2": True, "background": background}

    set_health_extra_provider(_health_extra)

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
    def background_job_get(job_id: int) -> dict[str, Any]:
        row = work_service.get_job(int(job_id))
        if row is None:
            return {"found": False, "job_id": int(job_id)}
        return {"found": True, **row}

    @mcp.tool()
    def background_job_retry(item_id: int) -> dict[str, Any]:
        return work_service.retry_item(int(item_id))

    @mcp.tool()
    def background_job_cancel(item_id: int) -> dict[str, Any]:
        return work_service.cancel_item(int(item_id))

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
        return work_service.create_job(
            rows=_research_rows([partnumber], category_code, target_count),
            work_type="RESEARCH_IMAGES",
            source_name="MANUAL_WORKSPACE",
            actor_source="MCP",
            priority=100,
        )

    @mcp.tool()
    def product_images_research_batch(
        partnumbers: list[str],
        category_code: str | None = None,
        target_count: int | None = None,
    ) -> dict[str, Any]:
        return work_service.create_job(
            rows=_research_rows(partnumbers, category_code, target_count),
            work_type="RESEARCH_IMAGES",
            source_name="MANUAL_WORKSPACE_BATCH",
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
    def product_image_candidate_import(candidate_id: int) -> dict[str, Any]:
        if candidate_import_service is None:
            raise RuntimeError("image candidate import is not configured")
        return candidate_import_service.import_candidate(int(candidate_id))

    @mcp.tool()
    def product_image_candidate_reject(candidate_id: int) -> dict[str, Any]:
        if candidate_repository is None:
            raise RuntimeError("image candidate repository is not configured")
        return candidate_repository.set_state(int(candidate_id), "REJECTED")

    @mcp.tool()
    def product_channel_gap_get(
        partnumber: str,
        channel_code: str,
        category_code: str,
        requirements_version: str | None = None,
    ) -> dict[str, Any]:
        if channel_gap_analyzer is None:
            return {"state": "NOT_CONFIGURED"}
        return channel_gap_analyzer.get(partnumber, channel_code, category_code, requirements_version)

    @mcp.tool()
    def product_channel_gap_batch(
        partnumbers: list[str],
        channel_code: str,
        category_code: str,
        requirements_version: str | None = None,
    ) -> dict[str, Any]:
        if channel_gap_analyzer is None:
            return {"count": 0, "by_state": {"NOT_CONFIGURED": 0}, "results": []}
        pns = _partnumbers(partnumbers)
        results = [
            channel_gap_analyzer.get(pn, channel_code, category_code, requirements_version)
            for pn in pns
        ]
        counts = Counter(str(row.get("state") or "UNKNOWN").upper() for row in results)
        return {"count": len(results), "by_state": dict(counts), "results": results}

    @mcp.tool()
    def product_channel_draft_prepare(
        partnumber: str,
        channel_code: str,
        category_code: str,
        requirements_version: str | None = None,
    ) -> dict[str, Any]:
        if channel_draft_service is None:
            return {"created": False, "state": "NOT_CONFIGURED"}
        return channel_draft_service.prepare(partnumber, channel_code, category_code, requirements_version)

    @mcp.tool()
    def product_channel_draft_prepare_batch(
        partnumbers: list[str],
        channel_code: str,
        category_code: str,
        requirements_version: str | None = None,
    ) -> dict[str, Any]:
        if channel_draft_service is None:
            return {"count": 0, "created_count": 0, "blocked_count": 0, "results": []}
        pns = _partnumbers(partnumbers)
        results = [
            channel_draft_service.prepare(pn, channel_code, category_code, requirements_version)
            for pn in pns
        ]
        created = sum(1 for row in results if bool(row.get("created")))
        return {
            "count": len(results),
            "created_count": created,
            "blocked_count": len(results) - created,
            "results": results,
        }

    @mcp.tool()
    def product_channel_draft_history(
        partnumber: str,
        channel_code: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        pn = str(partnumber or "").strip().upper()
        channel = str(channel_code or "").strip().upper() or None
        if not pn:
            raise ValueError("partnumber is required")
        if channel_draft_service is None:
            return {"partnumber": pn, "channel_code": channel, "count": 0, "drafts": []}
        rows = channel_draft_service.history(pn, channel, limit=limit)
        return {"partnumber": pn, "channel_code": channel, "count": len(rows), "drafts": rows}

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
        "background_job_get": background_job_get,
        "background_job_retry": background_job_retry,
        "background_job_cancel": background_job_cancel,
        "product_images_readiness": product_images_readiness,
        "product_images_research": product_images_research,
        "product_images_research_batch": product_images_research_batch,
        "product_image_candidates": product_image_candidates,
        "product_image_candidate_import": product_image_candidate_import,
        "product_image_candidate_reject": product_image_candidate_reject,
        "product_channel_gap_get": product_channel_gap_get,
        "product_channel_gap_batch": product_channel_gap_batch,
        "product_channel_draft_prepare": product_channel_draft_prepare,
        "product_channel_draft_prepare_batch": product_channel_draft_prepare_batch,
        "product_channel_draft_history": product_channel_draft_history,
        "product_workspace_v2_get": product_workspace_v2_get,
    }
    if namespace is not None:
        for name, func in registered.items():
            setattr(namespace, name, func)
    return registered
