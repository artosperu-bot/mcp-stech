from __future__ import annotations

import json
from typing import Any, Callable

_STATES = {"PENDING", "VERIFIED", "REJECTED", "CONFLICT", "IMPORTED"}


def _row_to_dict(cursor: Any, row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(zip([item[0] for item in (cursor.description or [])], row))


class ProductImageCandidateRepository:
    """Persistence for image research candidates and image requirement policy."""

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
                SELECT TOP (1) product_image_candidate_id
                FROM dbo.product_image_candidate WITH (UPDLOCK, HOLDLOCK)
                WHERE partnumber = ? AND source_url = ?
                """,
                pn,
                url,
            )
            existing = cursor.fetchone()
            if existing is not None:
                candidate_id = int(existing[0])
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
                    raise RuntimeError("existing candidate could not be read back")
                return row

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
            row = self.get_candidate(candidate_id, connection=connection)
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

    def get_candidate(self, candidate_id: int, *, connection: Any | None = None) -> dict[str, Any] | None:
        owned = connection is None
        conn = connection or self.connection_factory()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    product_image_candidate_id, partnumber, source_type, source_url,
                    source_domain, source_page_url, title, thumbnail_url,
                    image_width_px, image_height_px, exactness_policy,
                    partnumber_match, variant_match, confidence_score, state,
                    evidence_json, discovered_at, updated_at
                FROM dbo.product_image_candidate
                WHERE product_image_candidate_id = ?
                """,
                int(candidate_id),
            )
            return _row_to_dict(cursor, cursor.fetchone())
        finally:
            if owned and hasattr(conn, "close"):
                conn.close()

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
            row = self.get_candidate(int(candidate_id), connection=connection)
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

    def get_image_requirement_policy(self, channel_code: str, category_code: str) -> dict[str, Any] | None:
        channel = str(channel_code or "MASTER").strip().upper() or "MASTER"
        category = str(category_code or "DEFAULT").strip().upper() or "DEFAULT"
        connection = self.connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT TOP (1)
                    image_requirement_policy_id, channel_code, category_code, version_code,
                    required_min, recommended_min, require_main, min_width_px,
                    min_height_px, exactness_policy, active, created_at, updated_at
                FROM dbo.image_requirement_policy
                WHERE active = 1
                  AND (
                    (channel_code = ? AND category_code = ?) OR
                    (channel_code = ? AND category_code = N'DEFAULT') OR
                    (channel_code = N'MASTER' AND category_code = ?) OR
                    (channel_code = N'MASTER' AND category_code = N'DEFAULT')
                  )
                ORDER BY
                    CASE
                        WHEN channel_code = ? AND category_code = ? THEN 1
                        WHEN channel_code = ? AND category_code = N'DEFAULT' THEN 2
                        WHEN channel_code = N'MASTER' AND category_code = ? THEN 3
                        ELSE 4
                    END,
                    image_requirement_policy_id DESC
                """,
                channel,
                category,
                channel,
                category,
                channel,
                category,
                channel,
                category,
            )
            return _row_to_dict(cursor, cursor.fetchone())
        finally:
            if hasattr(connection, "close"):
                connection.close()
