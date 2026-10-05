from __future__ import annotations

from typing import Any


class ProductScanner:
    """Detect Product Workspace gaps and enqueue bounded work; never researches directly."""

    def __init__(
        self,
        *,
        product_repository: Any,
        technical_status_service: Any,
        image_readiness_service: Any,
        work_service: Any,
    ) -> None:
        self.product_repository = product_repository
        self.technical_status_service = technical_status_service
        self.image_readiness_service = image_readiness_service
        self.work_service = work_service

    @staticmethod
    def _pn(row: dict[str, Any]) -> str:
        return str(row.get("partnumber") or row.get("part_number") or "").strip().upper()

    @staticmethod
    def _category(row: dict[str, Any]) -> str | None:
        return str(row.get("category_code") or row.get("categoria") or "").strip().upper() or None

    @staticmethod
    def _stock(row: dict[str, Any]) -> float:
        for key in ("stock_total", "stock", "stock_actual"):
            try:
                if row.get(key) is not None:
                    return float(row.get(key) or 0)
            except (TypeError, ValueError):
                pass
        return 0.0

    def scan_once(self, *, limit: int = 100, after_partnumber: str = "") -> dict[str, Any]:
        bounded = max(1, min(int(limit), 500))
        rows = list(
            self.product_repository.list_for_scan(
                after_partnumber=after_partnumber,
                limit=bounded,
            )
        )
        technical_rows: list[dict[str, Any]] = []
        image_rows: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []

        for row in rows:
            pn = self._pn(row)
            if not pn:
                continue
            category = self._category(row)
            stock = self._stock(row)

            try:
                technical = self.technical_status_service.get(pn)
                missing: list[str] = []
                for value in [
                    *(technical.get("missing_required") or []),
                    *(technical.get("missing_recommended") or []),
                ]:
                    code = str(value or "").strip()
                    if code and code not in missing:
                        missing.append(code)
                if missing:
                    technical_rows.append(
                        {
                            "partnumber": pn,
                            "category_code": category,
                            "scope": "MASTER",
                            "requested_fields": missing,
                            "source_context": {"scanner": "MASTER", "stock": stock},
                        }
                    )
            except Exception as exc:
                errors.append({"partnumber": pn, "area": "TECHNICAL", "error": str(exc)})

            try:
                images = self.image_readiness_service.get(
                    pn,
                    category_code=category,
                    channel_code="MASTER",
                )
                if str(images.get("state") or "").upper() != "READY":
                    image_rows.append(
                        {
                            "partnumber": pn,
                            "category_code": category,
                            "scope": "MASTER",
                            "image_target_count": int(images.get("recommended_min") or 4),
                            "source_context": {
                                "scanner": "IMAGES",
                                "stock": stock,
                                "state": images.get("state"),
                            },
                        }
                    )
            except Exception as exc:
                errors.append({"partnumber": pn, "area": "IMAGES", "error": str(exc)})

        technical_created = 0
        image_created = 0
        job_ids: list[int] = []
        if technical_rows:
            priority = 80 if any(float((row.get("source_context") or {}).get("stock") or 0) > 0 for row in technical_rows) else 50
            result = self.work_service.create_job(
                rows=technical_rows,
                work_type="ENRICH_TECHNICAL",
                source_name="BACKGROUND_MASTER_SCAN",
                actor_source="STECH_MCP_SCANNER",
                priority=priority,
            )
            technical_created = int(result.get("total_items") or 0)
            if result.get("job_id") is not None:
                job_ids.append(int(result["job_id"]))

        if image_rows:
            priority = 90 if any(float((row.get("source_context") or {}).get("stock") or 0) > 0 for row in image_rows) else 55
            result = self.work_service.create_job(
                rows=image_rows,
                work_type="RESEARCH_IMAGES",
                source_name="BACKGROUND_MASTER_SCAN",
                actor_source="STECH_MCP_SCANNER",
                priority=priority,
            )
            image_created = int(result.get("total_items") or 0)
            if result.get("job_id") is not None:
                job_ids.append(int(result["job_id"]))

        return {
            "scanned": len(rows),
            "technical_candidates": len(technical_rows),
            "image_candidates": len(image_rows),
            "technical_jobs_created": technical_created,
            "image_jobs_created": image_created,
            "job_ids": job_ids,
            "errors": errors,
            "last_partnumber": self._pn(rows[-1]) if rows else None,
        }