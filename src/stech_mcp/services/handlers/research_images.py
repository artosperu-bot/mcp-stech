from __future__ import annotations

from typing import Any

import httpx

from stech_mcp.services.product_work_dispatcher import RetryableWorkError


class ResearchImagesHandler:
    """Map image research results to Product Work queue outcomes."""

    def __init__(
        self,
        service: Any,
        *,
        candidate_import_service: Any | None = None,
        auto_import_exact: bool = False,
        trusted_domains: tuple[str, ...] = (),
    ) -> None:
        self.service = service
        self.candidate_import_service = candidate_import_service
        self.auto_import_exact = bool(auto_import_exact)
        self.trusted_domains = tuple(
            str(value or "").strip().lower().lstrip(".")
            for value in trusted_domains
            if str(value or "").strip()
        )

    def _trusted_domain(self, domain: Any) -> bool:
        host = str(domain or "").strip().lower().lstrip(".")
        if not host:
            return False
        return any(host == allowed or host.endswith("." + allowed) for allowed in self.trusted_domains)

    @staticmethod
    def _strict_candidate(candidate: dict[str, Any]) -> bool:
        return (
            str(candidate.get("partnumber_match") or "").strip().upper() == "EXACT"
            and str(candidate.get("variant_match") or "UNKNOWN").strip().upper() != "MISMATCH"
            and float(candidate.get("confidence_score") or 0) >= 95
        )

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
            imported: list[dict[str, Any]] = []
            import_errors: list[str] = []
            if (
                self.auto_import_exact
                and self.candidate_import_service is not None
                and self.trusted_domains
            ):
                for candidate in list(result.get("candidates") or []):
                    if not isinstance(candidate, dict):
                        continue
                    if not self._strict_candidate(candidate):
                        continue
                    if not self._trusted_domain(candidate.get("source_domain")):
                        continue
                    candidate_id = candidate.get("product_image_candidate_id") or candidate.get("candidate_id")
                    if candidate_id in (None, ""):
                        continue
                    try:
                        imported.append(
                            self.candidate_import_service.import_candidate(int(candidate_id))
                        )
                    except Exception as exc:
                        import_errors.append(f"{candidate_id}: {type(exc).__name__}: {exc}")

                if imported:
                    try:
                        refreshed = self.service.readiness_service.get(
                            partnumber,
                            category_code=category_code,
                            channel_code="MASTER",
                        )
                    except Exception as exc:
                        refreshed = {"state": "UNKNOWN", "error": f"{type(exc).__name__}: {exc}"}
                    refreshed_state = str(refreshed.get("state") or "").strip().upper()
                    if refreshed_state == "READY":
                        return {
                            "status": "COMPLETED",
                            "current_step": "trusted exact images auto-imported",
                            "imported_count": len(imported),
                            "import_errors": import_errors,
                        }
                    return {
                        "status": "PARTIAL",
                        "current_step": "trusted exact images partially auto-imported",
                        "error_code": "IMAGE_SET_STILL_INCOMPLETE",
                        "error_detail": (
                            f"imported={len(imported)}; remaining_state={refreshed_state}; "
                            f"errors={len(import_errors)}"
                        ),
                    }

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