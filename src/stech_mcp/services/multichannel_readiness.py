from __future__ import annotations

from typing import Any, Callable

from stech_mcp.services.marketplace_preview import build_marketplace_preview


PreviewBuilder = Callable[..., dict[str, Any]]


def _preview_status(preview: dict[str, Any]) -> dict[str, Any]:
    fields = list(preview.get("fields") or [])
    total = len(fields)
    missing = [
        field
        for field in fields
        if str(field.get("status") or "").strip().upper()
        in {"RESEARCH_REQUIRED", "MARKETPLACE_INPUT"}
    ]
    completion = round(((total - len(missing)) / total) * 100) if total else 0
    return {
        "state": "READY" if not missing else "INCOMPLETE",
        "completion_pct": completion,
        "field_count": total,
        "missing_count": len(missing),
        "missing_fields": [
            str(field.get("field") or field.get("field_name") or "").strip()
            for field in missing
        ],
    }


class MultichannelReadinessService:
    """Read-only channel readiness calculated from one canonical product master."""

    def __init__(
        self,
        *,
        product_repository: Any,
        enrichment_repository: Any,
        technical_status_service: Any,
        preview_builder: PreviewBuilder = build_marketplace_preview,
    ) -> None:
        self.product_repository = product_repository
        self.enrichment_repository = enrichment_repository
        self.technical_status_service = technical_status_service
        self.preview_builder = preview_builder

    def get(self, partnumber: str) -> dict[str, Any]:
        pn = str(partnumber or "").strip().upper()
        if not pn:
            raise ValueError("partnumber is required")
        product = self.product_repository.get_by_partnumber(pn)
        if product is None:
            raise LookupError(f"product not found: {pn}")

        technical = self.technical_status_service.get(pn)
        category = str(technical.get("category_code") or "").strip().upper()
        enrichments = self.enrichment_repository.get_approved(pn)
        channels: dict[str, dict[str, Any]] = {}

        for marketplace in ("COOLBOX", "FALABELLA"):
            try:
                preview = self.preview_builder(
                    product=product,
                    marketplace=marketplace,
                    category=category,
                    package=None,
                    enrichments=enrichments,
                    image_urls=[],
                    marketplace_inputs={},
                )
            except ValueError:
                channels[marketplace] = {
                    "state": "NOT_CONFIGURED",
                    "completion_pct": 0,
                    "field_count": 0,
                    "missing_count": 0,
                    "missing_fields": [],
                }
            else:
                channels[marketplace] = _preview_status(preview)

        technical_completion = int(technical.get("completion_pct") or 0)
        technical_missing = [
            *(technical.get("missing_required") or []),
            *(technical.get("missing_recommended") or []),
        ]
        channels["VTEX"] = {
            "state": "READY" if not technical_missing else "INCOMPLETE",
            "completion_pct": technical_completion,
            "field_count": len(technical.get("known_fields") or {}) + len(technical_missing),
            "missing_count": len(technical_missing),
            "missing_fields": list(technical_missing),
        }

        return {
            "partnumber": pn,
            "category_code": category,
            "technical_completion_pct": technical_completion,
            "channels": channels,
        }
