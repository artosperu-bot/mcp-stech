from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

_SAFE_VIEW = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$")


class ProductRepository:
    """Lectura segura del catálogo operativo V8.

    El contrato real de scr/v8-identity es dbo.V_PRD_PRODUCTO_ACTUAL y usa
    `part_number`, `mini_codigo`, `codigo_externo`, EAN/UPC, stock y precio.
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
        # Alias estable del MCP sin perder el nombre SQL real.
        if product.get("part_number") is not None:
            product["partnumber"] = product["part_number"]
        if product.get("mini_codigo") is not None:
            product["minicodigo"] = product["mini_codigo"]
        return product

    def get_by_partnumber(self, partnumber: str) -> dict[str, Any] | None:
        if not partnumber or not partnumber.strip():
            raise ValueError("partnumber is required")

        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            sql = f"SELECT TOP (1) * FROM {self._view_name} WHERE part_number = ?"
            cursor.execute(sql, partnumber.strip())
            row = cursor.fetchone()
            if row is None:
                return None
            return self._row_to_dict(cursor, row)
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
