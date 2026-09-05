from __future__ import annotations

from collections.abc import Callable
from typing import Any


class ProductIdentityResearchRepository:
    def __init__(self, connection_factory: Callable[[], Any]):
        self._connection_factory = connection_factory

    @staticmethod
    def _row_to_dict(cursor: Any, row: Any) -> dict[str, Any] | None:
        if row is None:
            return None
        columns = [item[0] for item in (cursor.description or [])]
        return dict(zip(columns, row, strict=False))

    @staticmethod
    def _rows_to_dicts(cursor: Any, rows: list[Any]) -> list[dict[str, Any]]:
        columns = [item[0] for item in (cursor.description or [])]
        return [dict(zip(columns, row, strict=False)) for row in rows]

    def get_for_product_ids(self, product_ids: list[int]) -> dict[tuple[int, str], dict[str, Any]]:
        ids = sorted({int(value) for value in product_ids if int(value) > 0})
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT
                    research_id, producto_distribuidor_id, partnumber, identifier_type,
                    status, attempt_count, value_text, confidence_grade, source_type,
                    source_url, source_partnumber, evidence_text, note, last_error,
                    actor_source, created_at, updated_at
                FROM dbo.product_identity_research
                WHERE producto_distribuidor_id IN ({placeholders})
                """,
                *ids,
            )
            rows = self._rows_to_dicts(cursor, list(cursor.fetchall()))
            return {
                (int(row["producto_distribuidor_id"]), str(row["identifier_type"]).upper()): row
                for row in rows
            }
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()

    def upsert(
        self,
        *,
        producto_distribuidor_id: int,
        partnumber: str,
        identifier_type: str,
        status: str,
        value_text: str | None = None,
        confidence_grade: str | None = None,
        source_type: str | None = None,
        source_url: str | None = None,
        source_partnumber: str | None = None,
        evidence_text: str | None = None,
        note: str | None = None,
        last_error: str | None = None,
        actor_source: str | None = None,
        increment_attempt: bool = True,
    ) -> dict[str, Any]:
        product_id = int(producto_distribuidor_id)
        pn = str(partnumber or "").strip().upper()
        kind = str(identifier_type or "").strip().upper()
        state = str(status or "").strip().upper()
        if product_id <= 0:
            raise ValueError("producto_distribuidor_id must be positive")
        if not pn:
            raise ValueError("partnumber is required")
        if kind not in {"EAN", "UPC", "GTIN"}:
            raise ValueError("identifier_type must be EAN, UPC or GTIN")
        if state not in {
            "PENDING",
            "RESEARCHING",
            "VERIFIED",
            "PROMOTED",
            "NO_ENCONTRADO",
            "RESEARCH_REQUIRED",
            "CONFLICTO",
            "INVALID_IDENTITY",
            "ERROR",
        }:
            raise ValueError("unsupported research status")

        attempt_delta = 1 if increment_attempt else 0
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                MERGE dbo.product_identity_research AS target
                USING (
                    SELECT ? AS producto_distribuidor_id, ? AS identifier_type
                ) AS source
                ON target.producto_distribuidor_id = source.producto_distribuidor_id
                   AND target.identifier_type = source.identifier_type
                WHEN MATCHED THEN UPDATE SET
                    partnumber = ?,
                    status = ?,
                    attempt_count = target.attempt_count + ?,
                    value_text = ?,
                    confidence_grade = ?,
                    source_type = ?,
                    source_url = ?,
                    source_partnumber = ?,
                    evidence_text = ?,
                    note = ?,
                    last_error = ?,
                    actor_source = ?,
                    updated_at = SYSUTCDATETIME()
                WHEN NOT MATCHED THEN INSERT (
                    producto_distribuidor_id, partnumber, identifier_type, status,
                    attempt_count, value_text, confidence_grade, source_type, source_url,
                    source_partnumber, evidence_text, note, last_error, actor_source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                OUTPUT inserted.research_id;
                """,
                product_id,
                kind,
                pn,
                state,
                attempt_delta,
                value_text,
                confidence_grade,
                source_type,
                source_url,
                source_partnumber,
                evidence_text,
                note,
                last_error,
                actor_source,
                product_id,
                pn,
                kind,
                state,
                attempt_delta,
                value_text,
                confidence_grade,
                source_type,
                source_url,
                source_partnumber,
                evidence_text,
                note,
                last_error,
                actor_source,
            )
            inserted = cursor.fetchone()
            if inserted is None:
                raise RuntimeError("research upsert did not return research_id")
            connection.commit()

            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT TOP (1)
                    research_id, producto_distribuidor_id, partnumber, identifier_type,
                    status, attempt_count, value_text, confidence_grade, source_type,
                    source_url, source_partnumber, evidence_text, note, last_error,
                    actor_source, created_at, updated_at
                FROM dbo.product_identity_research
                WHERE producto_distribuidor_id = ? AND identifier_type = ?
                """,
                product_id,
                kind,
            )
            row = self._row_to_dict(cursor, cursor.fetchone())
            if row is None:
                raise RuntimeError("research upsert could not be re-read")
            return row
        except Exception:
            rollback = getattr(connection, "rollback", None)
            if callable(rollback):
                rollback()
            raise
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()

    def summary(self, partnumber: str | None = None) -> dict[str, Any]:
        pn = str(partnumber or "").strip().upper() or None
        where = " WHERE partnumber = ?" if pn else ""
        params = (pn,) if pn else ()
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT status, COUNT_BIG(*) AS item_count
                FROM dbo.product_identity_research
                """ + where + " GROUP BY status ORDER BY status",
                *params,
            )
            status_rows = list(cursor.fetchall())
            by_status = {str(row[0]): int(row[1]) for row in status_rows}

            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT identifier_type, COUNT_BIG(*) AS item_count
                FROM dbo.product_identity_research
                """ + where + " GROUP BY identifier_type ORDER BY identifier_type",
                *params,
            )
            type_rows = list(cursor.fetchall())
            by_identifier = {str(row[0]): int(row[1]) for row in type_rows}
            return {
                "partnumber": pn,
                "total": sum(by_status.values()),
                "by_status": by_status,
                "by_identifier": by_identifier,
            }
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()
