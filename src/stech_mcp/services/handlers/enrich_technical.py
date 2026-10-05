from __future__ import annotations

from typing import Any

import httpx

from stech_mcp.services.product_work_dispatcher import RetryableWorkError


class EnrichTechnicalHandler:
    """Map Product Enrichment Engine outcomes to Product Work queue outcomes."""

    def __init__(self, engine: Any) -> None:
        self.engine = engine

    @staticmethod
    def _input(item: dict[str, Any]) -> dict[str, Any]:
        payload = item.get("input")
        return payload if isinstance(payload, dict) else {}

    def __call__(self, item: dict[str, Any], progress: Any) -> dict[str, Any]:
        partnumber = str(item.get("partnumber") or "").strip().upper()
        payload = self._input(item)
        category_code = payload.get("category_code") or item.get("category_code")
        requested_fields = payload.get("requested_fields")
        if requested_fields is not None and not isinstance(requested_fields, list):
            requested_fields = None

        try:
            result = self.engine.enrich(
                partnumber,
                category_code,
                requested_fields,
                progress,
            )
        except LookupError as exc:
            detail = str(exc)
            if "product not found" in detail.lower():
                return {
                    "status": "NO_DATA_FOUND",
                    "current_step": "product not found",
                    "error_code": "PRODUCT_NOT_FOUND",
                    "error_detail": detail,
                }
            return {
                "status": "NO_DATA_FOUND",
                "current_step": "technical category not found",
                "error_code": "TECHNICAL_CATEGORY_NOT_FOUND",
                "error_detail": detail,
            }
        except (TimeoutError, httpx.TimeoutException, httpx.TransportError) as exc:
            raise RetryableWorkError(
                "TEMPORARY_RESEARCH_ERROR",
                f"{type(exc).__name__}: {exc}",
            ) from exc

        state = str(result.get("state") or "").strip().upper()
        conflicts = list(result.get("conflicts") or [])
        error_code = result.get("error_code")
        remaining = list(result.get("remaining_fields") or [])

        if state == "REVIEW_REQUIRED":
            return {
                "status": "REVIEW_REQUIRED",
                "current_step": "review required",
                "error_code": error_code or "FACT_CONFLICT",
                "error_detail": f"{len(conflicts)} technical conflict(s) require review",
            }
        if state == "PARTIAL":
            return {
                "status": "PARTIAL",
                "current_step": "partial technical enrichment",
                "error_code": error_code,
                "error_detail": (
                    f"remaining technical fields: {', '.join(remaining)}"
                    if remaining
                    else None
                ),
            }
        if state == "COMPLETED":
            return {
                "status": "COMPLETED",
                "current_step": "technical enrichment completed",
            }
        if state == "NO_DATA_FOUND":
            return {
                "status": "NO_DATA_FOUND",
                "current_step": "no technical data found",
                "error_code": error_code or "NO_DATA_FOUND",
            }

        return {
            "status": "FAILED",
            "current_step": "invalid enrichment result",
            "error_code": "INVALID_ENRICHMENT_STATE",
            "error_detail": f"unsupported enrichment state: {state or '<empty>'}",
        }
