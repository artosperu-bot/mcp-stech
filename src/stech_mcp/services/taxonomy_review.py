from __future__ import annotations

from typing import Any


class TaxonomyReviewService:
    """Review-first taxonomy workflow for cases not resolved by V8 CAT_V2."""

    def __init__(self, repository: Any) -> None:
        self.repository = repository

    def sync(self, *, limit: int = 1000, distributor: str | None = None) -> dict[str, Any]:
        result = self.repository.sync_missing(limit=limit, distributor=distributor)
        pending_count = self.repository.count_reviews(status="PENDING")
        pending_sample = self.repository.list_reviews(status="PENDING", limit=50)
        return {
            **result,
            "pending_count": pending_count,
            "pending_sample_count": len(pending_sample),
            "pending_sample": pending_sample,
        }

    def missing(self, *, limit: int = 100, distributor: str | None = None) -> dict[str, Any]:
        rows = self.repository.list_missing(limit=limit, distributor=distributor)
        return {"count": len(rows), "products": rows}

    def catalog(self, *, limit: int = 1000) -> dict[str, Any]:
        rows = self.repository.taxonomy_catalog(limit=limit)
        categories = sorted({str(row.get("category") or "").strip() for row in rows if row.get("category")})
        return {
            "pair_count": len(rows),
            "category_count": len(categories),
            "categories": categories,
            "pairs": rows,
        }

    def list(self, *, status: str | None = "PENDING", limit: int = 100) -> dict[str, Any]:
        rows = self.repository.list_reviews(status=status, limit=limit)
        return {"status": status, "count": len(rows), "reviews": rows}

    def get(self, review_id: int) -> dict[str, Any]:
        row = self.repository.get_review(int(review_id))
        return {"found": row is not None, "review": row}

    def propose(
        self,
        review_id: int,
        *,
        category: str,
        subcategory: str,
        confidence: str,
        reason: str,
        evidence: list[str] | None,
        proposed_by: str,
    ) -> dict[str, Any]:
        row = self.repository.propose(
            int(review_id),
            category=category,
            subcategory=subcategory,
            confidence=confidence,
            reason=reason,
            evidence=evidence,
            proposed_by=proposed_by,
        )
        return {"proposed": True, "review": row}

    @staticmethod
    def _review_ids(values: list[int], *, max_items: int = 500) -> list[int]:
        rows: list[int] = []
        seen: set[int] = set()
        for raw in list(values or [])[:max_items]:
            review_id = int(raw)
            if review_id <= 0 or review_id in seen:
                continue
            seen.add(review_id)
            rows.append(review_id)
        if not rows:
            raise ValueError("at least one valid review_id is required")
        return rows

    def propose_batch(
        self,
        items: list[dict[str, Any]],
        *,
        proposed_by: str = "CHATGPT",
    ) -> dict[str, Any]:
        rows = list(items or [])
        if not rows:
            raise ValueError("items are required")
        if len(rows) > 500:
            raise ValueError("maximum 500 taxonomy proposals per batch")
        results: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        seen: set[int] = set()
        for raw in rows:
            try:
                review_id = int(raw.get("review_id"))
                if review_id <= 0:
                    raise ValueError("review_id must be positive")
                if review_id in seen:
                    raise ValueError("duplicate review_id")
                seen.add(review_id)
                result = self.propose(
                    review_id,
                    category=str(raw.get("category") or ""),
                    subcategory=str(raw.get("subcategory") or ""),
                    confidence=str(raw.get("confidence") or "MEDIA"),
                    reason=str(raw.get("reason") or ""),
                    evidence=list(raw.get("evidence") or []),
                    proposed_by=proposed_by,
                )
                results.append(result)
            except Exception as exc:
                errors.append({
                    "review_id": raw.get("review_id"),
                    "error": f"{type(exc).__name__}: {exc}",
                })
        return {
            "requested_count": len(rows),
            "proposed_count": len(results),
            "error_count": len(errors),
            "results": results,
            "errors": errors,
        }

    def approve_batch(
        self,
        review_ids: list[int],
        *,
        approved_by: str,
    ) -> dict[str, Any]:
        ids = self._review_ids(review_ids)
        results: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for review_id in ids:
            try:
                results.append(self.approve(review_id, approved_by=approved_by))
            except Exception as exc:
                errors.append({
                    "review_id": review_id,
                    "error": f"{type(exc).__name__}: {exc}",
                })
        return {
            "requested_count": len(ids),
            "approved_count": len(results),
            "error_count": len(errors),
            "results": results,
            "errors": errors,
        }

    def apply_batch(
        self,
        review_ids: list[int],
        *,
        applied_by: str,
        stop_on_error: bool = False,
    ) -> dict[str, Any]:
        ids = self._review_ids(review_ids)
        results: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for review_id in ids:
            try:
                results.append(self.apply(review_id, applied_by=applied_by))
            except Exception as exc:
                errors.append({
                    "review_id": review_id,
                    "error": f"{type(exc).__name__}: {exc}",
                })
                if stop_on_error:
                    break
        return {
            "requested_count": len(ids),
            "applied_count": len(results),
            "error_count": len(errors),
            "stopped_early": bool(stop_on_error and errors),
            "results": results,
            "errors": errors,
        }

    def approve(self, review_id: int, *, approved_by: str) -> dict[str, Any]:
        return {"approved": True, "review": self.repository.approve(int(review_id), approved_by=approved_by)}

    def reject(self, review_id: int, *, rejected_by: str, reason: str | None = None) -> dict[str, Any]:
        return {
            "rejected": True,
            "review": self.repository.reject(int(review_id), rejected_by=rejected_by, reason=reason),
        }

    def sql_preview(self, review_id: int) -> dict[str, Any]:
        return self.repository.sql_preview(int(review_id))

    def apply(self, review_id: int, *, applied_by: str) -> dict[str, Any]:
        return {"applied": True, "review": self.repository.apply_review(int(review_id), applied_by=applied_by)}
