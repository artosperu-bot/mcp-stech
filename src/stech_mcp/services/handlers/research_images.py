from __future__ import annotations

from typing import Any

import httpx

from stech_mcp.services.product_work_dispatcher import RetryableWorkError


class ResearchImagesHandler:
    """Map image research results to Product Work queue outcomes."""

    def __init__(self, service: Any) -> None:
        self.service = service

    @staticmethod
    def _input(item: dict[str, Any]) -> dict[str, Any]:
        payload = item.get("input")
        return payload if isinstance(payload, dict) else {}

    def __call__(self, item: dict[str, Any], progress: Any) -> dict[str, Any]:
        partnumber = str(item.get("partnumber") or "").strip().upper()
        payload = self._input(item)
        category_code = payload.get("category_code") or item.get("category_code")
        target_count = payload.get("image_target_count")
        progress("ANALYZING_MISSING_FIELDS", 10)
        try:
            result = self.service.research(
                partnumber,
                category_code=category_code,
                target_count=target_count,
            )
        except LookupError as exc:
            return {
                "status": "NO_DATA_FOUND",
                "current_step": "product not found",
                "error_code": "PRODUCT_NOT_FOUND",
                "error_detail": str(exc),
            }
        except (TimeoutError, httpx.TimeoutException, httpx.TransportError) as exc:
            raise RetryableWorkError(
                "TEMPORARY_IMAGE_RESEARCH_ERROR",
                f"{type(exc).__name__}: {exc}",
            ) from exc

        state = str(result.get("state") or "").strip().upper()
        candidate_count = int(result.get("candidate_count") or 0)
        if state == "READY":
            return {"status": "COMPLETED", "current_step": "image readiness completed"}
        if state == "REVIEW_REQUIRED":
            return {
                "status": "REVIEW_REQUIRED",
                "current_step": "image candidates require review",
                "error_code": "IMAGE_REVIEW_REQUIRED",
                "error_detail": f"{candidate_count} image candidate(s) require review",
            }
        if state == "NO_DATA_FOUND":
            return {
                "status": "NO_DATA_FOUND",
                "current_step": "no image data found",
                "error_code": "NO_IMAGE_DATA_FOUND",
            }
        if state == "INCOMPLETE":
            return {
                "status": "PARTIAL",
                "current_step": "image set incomplete",
                "error_code": "IMAGE_SET_INCOMPLETE",
            }
        return {
            "status": "FAILED",
            "current_step": "invalid image research result",
            "error_code": "INVALID_IMAGE_RESEARCH_STATE",
            "error_detail": state or "<empty>",
        }