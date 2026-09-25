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
