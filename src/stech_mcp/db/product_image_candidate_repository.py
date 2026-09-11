from __future__ import annotations

import json
from typing import Any, Callable

_STATES = {"PENDING", "VERIFIED", "REJECTED", "CONFLICT", "IMPORTED"}


def _row_to_dict(cursor: Any, row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(zip([item[0] for item in (cursor.description or [])], row))


class ProductImageCandidateRepository:
    """Persistence for unapproved image research candidates.

    Candidate discovery is intentionally separate from ``product_image``. A web
    result only becomes a Product Workspace image after explicit verification or
    a later policy-controlled import step.
    """

    def __init__(self, connection_factory: Callable[[], Any]):
        self.connection_factory = connection_factory

    def add_candidate(
        self,
        *,
        partnumber: str,
        source_type: str,
        source_url: str,
        source_domain: str | None = None,
        source_page_url: str | None = None,
        title: str | None = None,
        thumbnail_url: str | None = None,
        image_width_px: int | None = None,
        image_height_px: int | None = None,
        exactness_policy: str = "MANUAL_REVIEW",
        partnumber_match: str = "UNKNOWN",
        variant_match: str = "UNKNOWN",
        confidence_score: float | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        pn = str(partnumber or "").strip().upper()
        if not pn:
            raise ValueError("partnumber is required")
        url = str(source_url or "").strip()
        if not url:
            raise ValueError("source_url is required")

        connection = self.connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                INSERT dbo.product_image_candidate (
                    partnumber, source_type, source_url, source_domain, source_page_url,
                    title, thumbnail_url, image_width_px, image_height_px,
                    exactness_policy, partnumber_match, variant_match, confidence_score,
                    state, evidence_json, discovered_at, updated_at
                )
                OUTPUT INSERTED.product_image_candidate_id
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, N'PENDING', ?, SYSUTCDATETIME(), SYSUTCDATETIME())
                """,
                pn,
                str(source_type or "").strip().upper(),
                url,
                source_domain,
                source_page_url,
                title,
                thumbnail_url,
                image_width_px,
                image_height_px,
                str(exactness_policy or "MANUAL_REVIEW").strip().upper(),
                str(partnumber_match or "UNKNOWN").strip().upper(),
                str(variant_match or "UNKNOWN").strip().upper(),
                confidence_score,
                json.dumps(evidence or {}, ensure_ascii=False, sort_keys=True),
            )
            inserted = cursor.fetchone()
            if not inserted:
                raise RuntimeError("candidate insert did not return id")
            candidate_id = int(inserted[0])
            connection.commit()
            cursor.execute(
                """
                SELECT product_image_candidate_id, partnumber, state, source_url
                FROM dbo.product_image_candidate
                WHERE product_image_candidate_id = ?
                """,
                candidate_id,
            )
            row = _row_to_dict(cursor, cursor.fetchone())
            if row is None:
                raise RuntimeError("candidate could not be read back")
            return row
        except Exception:
            if hasattr(connection, "rollback"):
                connection.rollback()
            raise
        finally:
            if hasattr(connection, "close"):
                connection.close()

    def list_for_product(self, partnumber: str) -> list[dict[str, Any]]:
        pn = str(partnumber or "").strip().upper()
        connection = self.connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT
                    product_image_candidate_id, partnumber, source_type, source_url,
                    source_domain, source_page_url, title, thumbnail_url,
                    image_width_px, image_height_px, exactness_policy,
                    partnumber_match, variant_match, confidence_score, state,
                    evidence_json, discovered_at, updated_at
                FROM dbo.product_image_candidate
                WHERE partnumber = ?
                ORDER BY confidence_score DESC, product_image_candidate_id DESC
                """,
                pn,
            )
            columns = [item[0] for item in (cursor.description or [])]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            if hasattr(connection, "close"):
                connection.close()

    def set_state(self, candidate_id: int, state: str) -> dict[str, Any]:
        normalized = str(state or "").strip().upper()
        if normalized not in _STATES:
            raise ValueError(f"invalid candidate state: {state}")
        connection = self.connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                UPDATE dbo.product_image_candidate
                SET state = ?, updated_at = SYSUTCDATETIME()
                WHERE product_image_candidate_id = ?
                """,
                normalized,
                int(candidate_id),
            )
            connection.commit()
            cursor.execute(
                """
                SELECT product_image_candidate_id, partnumber, state, source_url
                FROM dbo.product_image_candidate
                WHERE product_image_candidate_id = ?
                """,
                int(candidate_id),
            )
            row = _row_to_dict(cursor, cursor.fetchone())
            if row is None:
                raise ValueError("candidate not found")
            return row
        except Exception:
            if hasattr(connection, "rollback"):
                connection.rollback()
            raise
        finally:
            if hasattr(connection, "close"):
                connection.close()