from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

_SAFE_VIEW = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$")
_HISTORY_VIEW = "dbo.V_HST_PRODUCTO_OBSERVACION_V8"


class ProductRepository:
    """Lectura segura del catálogo operativo V8.

    El contrato real de scr/v8-identity es dbo.V_PRD_PRODUCTO_ACTUAL y usa
    `part_number`, `mini_codigo`, `codigo_externo`, EAN/UPC, stock y precio.
    El histórico append-only se consulta desde V_HST_PRODUCTO_OBSERVACION_V8.
    """

    def __init__(
        self,
        connection_factory: Callable[[], Any],
        *,
        view_name: str = "dbo.V_PRD_PRODUCTO_ACTUAL",
    ) -> None:
        if not _SAFE_VIEW.fullmatch(view_name):
            raise ValueError("Unsafe view name")
        self._connection_factory = connection_factory
        self._view_name = view_name

    @staticmethod
    def _row_to_dict(cursor: Any, row: Any) -> dict[str, Any]:
        columns = [item[0] for item in cursor.description]
        product = dict(zip(columns, row, strict=False))
        # Alias estable del MCP sin perder los nombres SQL reales.
        if product.get("part_number") is not None:
            product["partnumber"] = product["part_number"]
        if product.get("mini_codigo") is not None:
            product["minicodigo"] = product["mini_codigo"]
        return product

    def get_by_partnumber(self, partnumber: str) -> dict[str, Any] | None:
        """Return a deterministic current row for legacy single-product consumers.

        When the same PN exists at multiple distributors, prefer the most recently
        observed row. New multi-distributor consumers should call
        `list_by_partnumber` instead of assuming a PN belongs to only one source.
        """
        if not partnumber or not partnumber.strip():
            raise ValueError("partnumber is required")

        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            sql = f"""SELECT TOP (1) *
FROM {self._view_name}
WHERE part_number = ?
ORDER BY ultima_observacion DESC, producto_distribuidor_id DESC"""
            cursor.execute(sql, partnumber.strip())
            row = cursor.fetchone()
            if row is None:
                return None
            return self._row_to_dict(cursor, row)
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()

    def list_by_partnumber(self, partnumber: str, *, limit: int = 50) -> list[dict[str, Any]]:
        """Return every current distributor row for an exact Part Number."""
        pn = str(partnumber or "").strip()
        if not pn:
            raise ValueError("partnumber is required")
        bounded = max(1, min(int(limit), 200))

        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            sql = f"""SELECT TOP ({bounded}) *
FROM {self._view_name}
WHERE part_number = ?
ORDER BY ultima_observacion DESC, producto_distribuidor_id DESC"""
            cursor.execute(sql, pn)
            return [self._row_to_dict(cursor, row) for row in cursor.fetchall()]
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()

    def search(self, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        query = str(query or "").strip()
        if not query:
            raise ValueError("query is required")
        limit = max(1, min(int(limit), 50))
        like = f"%{query}%"

        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            sql = f"""SELECT TOP ({limit}) *
FROM {self._view_name}
WHERE part_number LIKE ?
   OR ean LIKE ?
   OR upc LIKE ?
   OR mini_codigo LIKE ?
   OR codigo_externo LIKE ?
   OR nombre LIKE ?
ORDER BY ultima_observacion DESC, producto_distribuidor_id DESC"""
            cursor.execute(sql, like, like, like, like, like, like)
            return [self._row_to_dict(cursor, row) for row in cursor.fetchall()]
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()

    def list_for_scan(
        self,
        *,
        after_partnumber: str = "",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Page by unique Part Number and include all current distributor rows.

        Paging raw distributor rows can split one PN across page boundaries and
        skip remaining distributors when the next cursor uses `part_number > ?`.
        This query first selects the next N unique PNs, then returns every row
        for those products.
        """
        after = str(after_partnumber or "").strip().upper()
        bounded = max(1, min(int(limit), 500))
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            if after:
                sql = f"""WITH page_pn AS (
    SELECT DISTINCT TOP ({bounded}) part_number
    FROM {self._view_name}
    WHERE part_number > ?
    ORDER BY part_number
)
SELECT src.*
FROM {self._view_name} AS src
INNER JOIN page_pn AS p ON p.part_number = src.part_number
ORDER BY src.part_number, src.ultima_observacion DESC, src.producto_distribuidor_id DESC"""
                cursor.execute(sql, after)
            else:
                sql = f"""WITH page_pn AS (
    SELECT DISTINCT TOP ({bounded}) part_number
    FROM {self._view_name}
    ORDER BY part_number
)
SELECT src.*
FROM {self._view_name} AS src
INNER JOIN page_pn AS p ON p.part_number = src.part_number
ORDER BY src.part_number, src.ultima_observacion DESC, src.producto_distribuidor_id DESC"""
                cursor.execute(sql)
            return [self._row_to_dict(cursor, row) for row in cursor.fetchall()]
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()

    def history(self, partnumber: str, *, limit: int = 25) -> list[dict[str, Any]]:
        """Devuelve observaciones reales V8; no sintetiza intervalos faltantes."""
        partnumber = str(partnumber or "").strip()
        if not partnumber:
            raise ValueError("partnumber is required")
        limit = max(1, min(int(limit), 200))

        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            sql = f"""SELECT TOP ({limit}) *
FROM {_HISTORY_VIEW}
WHERE part_number = ?
ORDER BY observado_at DESC, observacion_id DESC"""
            cursor.execute(sql, partnumber)
            return [self._row_to_dict(cursor, row) for row in cursor.fetchall()]
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()
