from __future__ import annotations

from typing import Any


class ProductWorkspaceV2Service:
    """Channel-neutral Product Workspace read model composed from authoritative services."""

    def __init__(
        self,
        *,
        product_repository: Any,
        technical_status_service: Any,
        image_readiness_service: Any,
        image_candidate_repository: Any,
        fact_candidate_repository: Any,
        work_repository: Any,
        deltron_specification_repository: Any | None = None,
    ) -> None:
        self.product_repository = product_repository
        self.technical_status_service = technical_status_service
        self.image_readiness_service = image_readiness_service
        self.image_candidate_repository = image_candidate_repository
        self.fact_candidate_repository = fact_candidate_repository
        self.work_repository = work_repository
        self.deltron_specification_repository = deltron_specification_repository

    @staticmethod
    def _fallback_category(product: dict[str, Any]) -> str | None:
        for key in ("category_code", "categoria", "subcategoria", "familia", "tipo_producto"):
            value = str(product.get(key) or "").strip().upper()
            if value:
                return value
        return None

    def _deltron_specifications(self, product: dict[str, Any]) -> list[dict[str, Any]]:
        if self.deltron_specification_repository is None:
            return []
        product_id = product.get("producto_distribuidor_id")
        if product_id in (None, ""):
            return []
        try:
            product_id_int = int(product_id)
        except (TypeError, ValueError):
            return []
        if product_id_int <= 0:
            return []
        return list(self.deltron_specification_repository.list_for_product(product_id_int))

    def get(self, partnumber: str) -> dict[str, Any]:
        pn = str(partnumber or "").strip().upper()
        if not pn:
            raise ValueError("partnumber is required")
        product = self.product_repository.get_by_partnumber(pn)
        if product is None:
            return {"found": False, "partnumber": pn}

        deltron_specifications = self._deltron_specifications(product)

        try:
            technical = self.technical_status_service.get(pn)
        except LookupError as exc:
            category = self._fallback_category(product)
            technical = {
                "partnumber": pn,
                "category_code": category,
                "state": "NOT_CONFIGURED",
                "known_fields": {},
                "field_sources": {},
                "missing_required": [],
                "missing_recommended": [],
                "conflicts": [],
                "completion_pct": 0,
                "reason": str(exc),
            }
        else:
            category = str(technical.get("category_code") or "").strip().upper() or None

        image_readiness = self.image_readiness_service.get(
            pn,
            category_code=category,
            channel_code="MASTER",
        )
        image_candidates = list(self.image_candidate_repository.list_for_product(pn))
        fact_candidates = list(self.fact_candidate_repository.list_for_product(pn))
        jobs = list(self.work_repository.list_for_product(pn, limit=20))
        conflicts = [
            row
            for row in fact_candidates
            if str(row.get("state") or "").strip().upper() == "CONFLICT"
        ]

        master = {
            "partnumber": pn,
            "producto_distribuidor_id": product.get("producto_distribuidor_id"),
            "brand": product.get("marca") or product.get("brand"),
            "model": product.get("modelo") or product.get("model"),
            "name": product.get("nombre") or product.get("name") or product.get("product_name"),
            "ean": product.get("ean"),
            "upc": product.get("upc"),
            "mini_codigo": product.get("mini_codigo") or product.get("minicodigo"),
            "category_code": category,
            "distributor": product.get("distribuidor") or product.get("distributor"),
        }
        return {
            "found": True,
            "partnumber": pn,
            "master": master,
            "technical": technical,
            "deltron_specifications": {
                "source": "dbo.PRD_DELTRON_ESPECIFICACION",
                "count": len(deltron_specifications),
                "items": deltron_specifications,
            },
            "images": {
                "readiness": image_readiness,
                "candidate_count": len(image_candidates),
                "candidates": image_candidates,
            },
            "evidence": {
                "candidate_count": len(fact_candidates),
                "conflict_count": len(conflicts),
                "candidates": fact_candidates,
            },
            "jobs": jobs,
            "channels": {},
        }