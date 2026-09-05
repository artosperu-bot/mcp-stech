from __future__ import annotations

from collections.abc import Callable
from typing import Any


class ProductIdentityRepository:
    """Controlled read/write access to product identity only.

    The repository intentionally targets dbo.PRD_PRODUCTO_DISTRIBUIDOR and does
    not touch stock, prices, observations, or movement history.
    """

    def __init__(self, connection_factory: Callable[[], Any]):
        self._connection_factory = connection_factory

    @staticmethod
    def _rows_to_dicts(cursor: Any, rows: list[Any]) -> list[dict[str, Any]]:
        columns = [item[0] for item in (cursor.description or [])]
        return [dict(zip(columns, row, strict=False)) for row in rows]

    def list_missing_identifiers(
        self,
        *,
        after_id: int = 0,
        limit: int = 100,
        distributor: str | None = None,
    ) -> dict[str, Any]:
        after = max(0, int(after_id or 0))
        page_size = max(1, min(int(limit or 100), 500))
        fetch_size = page_size + 1
        where = [
            "p.activo = 1",
            "p.producto_distribuidor_id > ?",
            "NULLIF(LTRIM(RTRIM(p.part_number)), '') IS NOT NULL",
            "(NULLIF(LTRIM(RTRIM(p.ean)), '') IS NULL OR NULLIF(LTRIM(RTRIM(p.upc)), '') IS NULL)",
        ]
        params: list[Any] = [after]
        if distributor:
            where.append("d.codigo = ?")
            params.append(str(distributor).strip().upper())

        sql = f"""
        SELECT TOP ({fetch_size})
            p.producto_distribuidor_id,
            d.codigo AS distribuidor_codigo,
            p.codigo_externo,
            p.part_number,
            p.ean,
            p.upc,
            p.mini_codigo,
            p.marca,
            p.nombre,
            p.identity_status,
            p.identity_confidence,
            p.identity_source
        FROM dbo.PRD_PRODUCTO_DISTRIBUIDOR p
        JOIN dbo.DST_DISTRIBUIDOR d ON d.distribuidor_id = p.distribuidor_id
        WHERE {' AND '.join(where)}
        ORDER BY p.producto_distribuidor_id
        """

        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(sql, *params)
            rows = self._rows_to_dicts(cursor, list(cursor.fetchall()))
            has_more = len(rows) > page_size
            page = rows[:page_size]
            next_after_id = int(page[-1]["producto_distribuidor_id"]) if page else after
            return {
                "products": page,
                "count": len(page),
                "has_more": has_more,
                "next_after_id": next_after_id,
            }
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()

    def partnumber_collision_stats(self, partnumbers: list[str]) -> dict[str, dict[str, Any]]:
        normalized = sorted({str(value or "").strip().upper() for value in partnumbers if str(value or "").strip()})
        if not normalized:
            return {}
        placeholders = ",".join("?" for _ in normalized)
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT
                    UPPER(LTRIM(RTRIM(p.part_number))) AS part_number,
                    COUNT_BIG(*) AS active_row_count,
                    COUNT(DISTINCT COALESCE(NULLIF(UPPER(LTRIM(RTRIM(p.marca))), ''), '<EMPTY>')) AS active_brand_count
                FROM dbo.PRD_PRODUCTO_DISTRIBUIDOR p
                WHERE p.activo = 1
                  AND UPPER(LTRIM(RTRIM(p.part_number))) IN ({placeholders})
                GROUP BY UPPER(LTRIM(RTRIM(p.part_number)))
                """,
                *normalized,
            )
            rows = list(cursor.fetchall())
            return {
                str(row[0]).upper(): {
                    "active_row_count": int(row[1]),
                    "active_brand_count": int(row[2]),
                }
                for row in rows
            }
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()

    def list_by_partnumber(self, partnumber: str) -> list[dict[str, Any]]:
        pn = str(partnumber or "").strip().upper()
        if not pn:
            raise ValueError("partnumber is required")

        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT
                    p.producto_distribuidor_id,
                    d.codigo AS distribuidor_codigo,
                    p.codigo_externo,
                    p.part_number,
                    p.ean,
                    p.upc,
                    p.mini_codigo,
                    p.marca,
                    p.nombre,
                    p.identity_status,
                    p.identity_confidence,
                    p.identity_source
                FROM dbo.PRD_PRODUCTO_DISTRIBUIDOR p
                JOIN dbo.DST_DISTRIBUIDOR d ON d.distribuidor_id = p.distribuidor_id
                WHERE p.activo = 1 AND p.part_number = ?
                ORDER BY p.producto_distribuidor_id
                """,
                pn,
            )
            return self._rows_to_dicts(cursor, list(cursor.fetchall()))
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()

    def promote_missing_identifier(
        self,
        *,
        partnumber: str,
        target_field: str,
        value: str,
        confidence: int,
        source: str,
    ) -> int:
        pn = str(partnumber or "").strip().upper()
        field = str(target_field or "").strip().lower()
        if not pn:
            raise ValueError("partnumber is required")
        if field not in {"ean", "upc"}:
            raise ValueError("target_field must be ean or upc")
        numeric_confidence = max(0, min(int(confidence), 100))
        source_text = str(source or "").strip()
        if not source_text:
            raise ValueError("source is required")

        sql = f"""
        UPDATE dbo.PRD_PRODUCTO_DISTRIBUIDOR
        SET {field} = ?,
            identity_status = CASE
                WHEN ? >= ISNULL(identity_confidence, 0) THEN 'VALIDADO_DETALLE'
                ELSE identity_status
            END,
            identity_confidence = CASE
                WHEN ? > ISNULL(identity_confidence, 0) THEN ?
                ELSE identity_confidence
            END,
            identity_source = CASE
                WHEN ? >= ISNULL(identity_confidence, 0) THEN ?
                ELSE identity_source
            END,
            updated_at = SYSDATETIME()
        WHERE part_number = ?
          AND activo = 1
          AND NULLIF(LTRIM(RTRIM({field})), '') IS NULL
        """

        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                sql,
                value,
                numeric_confidence,
                numeric_confidence,
                numeric_confidence,
                numeric_confidence,
                source_text,
                pn,
            )
            changed = int(getattr(cursor, "rowcount", 0) or 0)
            connection.commit()
            return changed
        except Exception:
            rollback = getattr(connection, "rollback", None)
            if callable(rollback):
                rollback()
            raise
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()
