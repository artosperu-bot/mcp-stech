from __future__ import annotations

from typing import Any


class ProductImageResearchService:
    """Find missing-image candidates without publishing or auto-approving them."""

    def __init__(
        self,
        *,
        product_repository: Any,
        local_image_sync_service: Any,
        readiness_service: Any,
        candidate_repository: Any,
        search_provider: Any,
    ) -> None:
        self.product_repository = product_repository
        self.local_image_sync_service = local_image_sync_service
        self.readiness_service = readiness_service
        self.candidate_repository = candidate_repository
        self.search_provider = search_provider

    @staticmethod
    def _exact_pn_match(partnumber: str, *values: Any) -> bool:
        target = str(partnumber or "").strip().upper()
        return bool(target and any(target in str(value or "").upper() for value in values))

    def research(
        self,
        partnumber: str,
        category_code: str | None = None,
        target_count: int | None = None,
    ) -> dict[str, Any]:
        pn = str(partnumber or "").strip().upper()
        if not pn:
            raise ValueError("partnumber is required")
        product = self.product_repository.get_by_partnumber(pn)
        if product is None:
            raise LookupError(f"product not found: {pn}")

        before = self.readiness_service.get(
            pn,
            category_code=category_code,
            channel_code="MASTER",
        )

        # First reuse exact images already present on PC020. The readiness check
        # also sees eligible Deltron rows, so external search is a true fallback.
        self.local_image_sync_service.sync(pn)
        current = self.readiness_service.get(
            pn,
            category_code=category_code,
            channel_code="MASTER",
        )
        if str(current.get("state") or "").upper() == "READY":
            return {
                "found": True,
                "partnumber": pn,
                "state": "READY",
                "source": "EXISTING",
                "readiness": current,
                "candidate_count": 0,
                "candidates": [],
            }

        desired = max(
            int(
                target_count
                or current.get("recommended_min")
                or before.get("recommended_min")
                or 4
            ),
            1,
        )
        brand = str(product.get("marca") or product.get("brand") or "").strip()
        model = str(product.get("modelo") or product.get("model") or "").strip()
        query = " ".join(value for value in (pn, brand, model, "product images") if value)
        results = self.search_provider.search(query, count=min(max(desired * 2, 5), 20))

        saved: list[dict[str, Any]] = []
        for result in results:
            exact = self._exact_pn_match(
                pn,
                result.title,
                result.page_url,
                result.image_url,
            )
            candidate = self.candidate_repository.add_candidate(
                partnumber=pn,
                source_type="WEB_IMAGE",
                source_url=result.image_url,
                source_domain=result.source_domain,
                source_page_url=result.page_url,
                title=result.title,
                thumbnail_url=result.thumbnail_url,
                image_width_px=result.width,
                image_height_px=result.height,
                exactness_policy="EXACT_PN_REQUIRED" if exact else "MANUAL_REVIEW",
                partnumber_match="EXACT" if exact else "UNKNOWN",
                variant_match="UNKNOWN",
                confidence_score=95 if exact else 60,
                evidence={
                    "query": query,
                    "title": result.title,
                    "page_url": result.page_url,
                },
            )
            saved.append(candidate)

        return {
            "found": True,
            "partnumber": pn,
            "state": "REVIEW_REQUIRED" if saved else "NO_DATA_FOUND",
            "source": "WEB" if saved else "NONE",
            "readiness": current,
            "query": query,
            "candidate_count": len(saved),
            "candidates": saved,
        }