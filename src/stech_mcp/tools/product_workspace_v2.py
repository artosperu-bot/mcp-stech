from __future__ import annotations

from collections import Counter
import re
from typing import Any

from stech_mcp.tools.core import set_health_extra_provider


_IDENTITY_FIELDS = {
    "ean",
    "upc",
    "gtin",
    "gtin_8",
    "gtin_12",
    "gtin_13",
    "gtin_14",
    "barcode",
    "codigo_barras",
    "codigo_de_barras",
}


def _field_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"#\s*\d+\s*$", "", text).strip()
    text = (
        text.replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ñ", "n")
    )
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


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

    def _normalize_partnumbers(partnumbers: list[str]) -> list[str]:
        rows: list[str] = []
        seen: set[str] = set()
        for raw in list(partnumbers or [])[:2000]:
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
        for pn in _normalize_partnumbers(partnumbers):
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
    def product_workspace_smart_complete(
        partnumbers: list[str],
        requested_fields: list[str] | None = None,
        image_target_count: int | None = None,
        category_code: str | None = None,
        channel_code: str | None = None,
        template_code: str | None = None,
        requirements_version: str | None = None,
        source_name: str = "SCR_SMART_COMPLETE",
    ) -> dict[str, Any]:
        """Queue only the work required by the requested template fields.

        The caller may provide PNs that already exist in Product Workspace or new/manual
        PNs. Existing verified values and sufficient local images are reused. This tool
        never writes price, stock, cost, publication state or marketplace inventory.
        """

        pns = _normalize_partnumbers(partnumbers)
        category = str(category_code or "").strip().upper() or None
        channel = str(channel_code or "").strip().upper() or None
        template = str(template_code or "").strip() or None
        version = str(requirements_version or "").strip() or None
        source = str(source_name or "").strip() or "SCR_SMART_COMPLETE"
        target = None if image_target_count in (None, "") else max(0, min(int(image_target_count), 20))

        requested: list[tuple[str, str]] = []
        seen_fields: set[str] = set()
        for raw in list(requested_fields or []):
            label = str(raw or "").strip()
            key = _field_key(label)
            if not key or key in seen_fields:
                continue
            seen_fields.add(key)
            requested.append((label, key))

        technical_rows: list[dict[str, Any]] = []
        identity_rows: list[dict[str, Any]] = []
        image_rows: list[dict[str, Any]] = []
        result_items: list[dict[str, Any]] = []

        for pn in pns:
            workspace = (
                workspace_service.get(pn)
                if workspace_service is not None
                else {"found": False, "partnumber": pn}
            )
            found = bool(workspace.get("found"))
            technical = dict(workspace.get("technical") or {})
            master = dict(workspace.get("master") or {})
            known = dict(technical.get("known_fields") or {})

            normalized_known: dict[str, Any] = {}
            for key, value in {**master, **known}.items():
                normalized_known[_field_key(key)] = value

            # Canonical identity aliases: a verified EAN/UPC can satisfy generic GTIN/barcode.
            generic_identity = next(
                (
                    value
                    for key in ("ean", "upc", "gtin", "barcode")
                    if _has_value(normalized_known.get(key))
                    for value in [normalized_known[key]]
                ),
                None,
            )
            if _has_value(generic_identity):
                normalized_known.setdefault("gtin", generic_identity)
                normalized_known.setdefault("barcode", generic_identity)
                normalized_known.setdefault("codigo_barras", generic_identity)
                normalized_known.setdefault("codigo_de_barras", generic_identity)

            missing_pairs = [
                (label, key)
                for label, key in requested
                if not _has_value(normalized_known.get(key))
            ]
            missing_identity = [label for label, key in missing_pairs if key in _IDENTITY_FIELDS]
            missing_technical = [label for label, key in missing_pairs if key not in _IDENTITY_FIELDS]

            image_state = image_readiness_service.get(
                pn,
                category_code=category,
                channel_code=channel or "MASTER",
            )
            current_images = int(image_state.get("image_count") or 0)
            effective_target = current_images if target is None else target
            image_missing = max(0, effective_target - current_images)

            context: dict[str, Any] = {
                "partnumber": pn,
                "scope": "TEMPLATE_SMART_COMPLETE",
            }
            if category:
                context["category_code"] = category
            if channel:
                context["channel_code"] = channel
            if template:
                context["template_code"] = template
            if version:
                context["requirements_version"] = version

            if missing_technical:
                technical_rows.append({**context, "requested_fields": missing_technical})
            if missing_identity:
                identity_rows.append(
                    {
                        "partnumber": pn,
                        "scope": "TEMPLATE_SMART_COMPLETE",
                        "requested_fields": missing_identity,
                    }
                )
            if image_missing > 0:
                image_row = dict(context)
                image_row["image_target_count"] = effective_target
                image_row["image_missing_count"] = image_missing
                image_rows.append(image_row)

            missing_fields = [label for label, _key in missing_pairs]
            has_work = bool(missing_fields or image_missing)
            result_items.append(
                {
                    "partnumber": pn,
                    "found": found,
                    "state": "PROCESSING" if has_work else "READY",
                    "requested_fields": len(requested),
                    "resolved_fields": len(requested) - len(missing_fields),
                    "missing_fields": missing_fields,
                    "images": {
                        "current": current_images,
                        "target": effective_target,
                        "missing": image_missing,
                    },
                }
            )

        jobs: dict[str, Any] = {}
        if technical_rows:
            jobs["technical"] = work_service.create_job(
                rows=technical_rows,
                work_type="ENRICH_TECHNICAL",
                source_name=source,
                actor_source="SCR_UI",
                priority=90,
            )
        if identity_rows:
            jobs["identity"] = work_service.create_job(
                rows=identity_rows,
                work_type="RESEARCH_IDENTITY",
                source_name=source,
                actor_source="SCR_UI",
                priority=95,
            )
        if image_rows:
            jobs["images"] = work_service.create_job(
                rows=image_rows,
                work_type="RESEARCH_IMAGES",
                source_name=source,
                actor_source="SCR_UI",
                priority=90,
            )

        ready_count = sum(1 for row in result_items if row["state"] == "READY")
        return {
            "requested_count": len(pns),
            "ready_count": ready_count,
            "processing_count": len(pns) - ready_count,
            "requested_field_count": len(requested),
            "image_target_count": target,
            "jobs": jobs,
            "items": result_items,
        }

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
        "product_workspace_smart_complete": product_workspace_smart_complete,
        "product_image_candidates": product_image_candidates,
        "product_image_candidate_import": product_image_candidate_import,
        "product_image_candidate_reject": product_image_candidate_reject,
        "product_channel_gap_get": product_channel_gap_get,
        "product_channel_draft_prepare": product_channel_draft_prepare,
        "product_workspace_v2_get": product_workspace_v2_get,
    }
    if namespace is not None:
        for name, func in registered.items():
            setattr(namespace, name, func)
    return registered
