from __future__ import annotations

from collections.abc import Callable
from typing import Any


class EnrichmentRepository:
    def __init__(self, connection_factory: Callable[[], Any]):
        self._connection_factory = connection_factory

    @staticmethod
    def _row_to_dict(cursor: Any, row: Any) -> dict[str, Any]:
        columns = [column[0] for column in cursor.description]
        return dict(zip(columns, row, strict=False))

    def get_approved(
        self,
        partnumber: str,
        field_codes: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            sql = (
                "SELECT enrichment_id, partnumber, field_code, value_text, value_number, "
                "unit, method, confidence_grade, is_approved, created_at, updated_at "
                "FROM dbo.product_enrichment "
                "WHERE partnumber = ? AND is_approved = 1"
            )
            params: list[Any] = [partnumber.strip()]
            if field_codes:
                placeholders = ",".join("?" for _ in field_codes)
                sql += f" AND field_code IN ({placeholders})"
                params.extend(field_codes)
            sql += " ORDER BY field_code;"
            cursor.execute(sql, *params)
            return [self._row_to_dict(cursor, row) for row in cursor.fetchall()]
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()

    def upsert(
        self,
        *,
        partnumber: str,
        field_code: str,
        value_text: str | None = None,
        value_number: Any | None = None,
        unit: str | None = None,
        method: str,
        confidence_grade: str,
        is_approved: bool = False,
        allow_manual_override: bool = False,
    ) -> dict[str, Any]:
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            pn = partnumber.strip()
            code = field_code.strip()

            cursor.execute(
                "SELECT enrichment_id, method, is_approved "
                "FROM dbo.product_enrichment "
                "WHERE partnumber = ? AND field_code = ?;",
                pn,
                code,
            )
            existing = cursor.fetchone()
            if (
                existing
                and len(existing) >= 3
                and str(existing[1]).upper() == "MANUAL"
                and bool(existing[2])
                and not allow_manual_override
            ):
                return {
                    "enrichment_id": existing[0],
                    "partnumber": pn,
                    "field_code": code,
                    "preserved_manual": True,
                }

            cursor.execute(
                "MERGE dbo.product_enrichment AS target "
                "USING (SELECT ? AS partnumber, ? AS field_code) AS source "
                "ON target.partnumber = source.partnumber AND target.field_code = source.field_code "
                "WHEN MATCHED THEN UPDATE SET "
                "value_text = ?, value_number = ?, unit = ?, method = ?, confidence_grade = ?, "
                "is_approved = ?, updated_at = SYSUTCDATETIME() "
                "WHEN NOT MATCHED THEN INSERT "
                "(partnumber, field_code, value_text, value_number, unit, method, confidence_grade, is_approved) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "OUTPUT inserted.enrichment_id;",
                pn,
                code,
                value_text,
                value_number,
                unit,
                method,
                confidence_grade,
                bool(is_approved),
                pn,
                code,
                value_text,
                value_number,
                unit,
                method,
                confidence_grade,
                bool(is_approved),
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("enrichment upsert did not return enrichment_id")
            connection.commit()
            return {
                "enrichment_id": row[0],
                "partnumber": pn,
                "field_code": code,
                "preserved_manual": False,
            }
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()

    def add_evidence(
        self,
        *,
        enrichment_id: int,
        source_url: str | None,
        source_domain: str | None,
        source_type: str,
        source_partnumber: str | None,
        evidence_text: str | None,
        rank_score: int,
    ) -> dict[str, Any]:
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                "INSERT dbo.product_evidence "
                "(enrichment_id, source_url, source_domain, source_type, source_partnumber, evidence_text, rank_score) "
                "OUTPUT inserted.evidence_id "
                "VALUES (?, ?, ?, ?, ?, ?, ?);",
                enrichment_id,
                source_url,
                source_domain,
                source_type,
                source_partnumber,
                evidence_text,
                rank_score,
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("evidence insert did not return evidence_id")
            connection.commit()
            return {"evidence_id": row[0], "enrichment_id": enrichment_id}
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()
