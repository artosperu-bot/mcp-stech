from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

_SAFE_VIEW = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$")


class ProductRepository:
    def __init__(self, connection_factory: Callable[[], Any], *, view_name: str = "dbo.V_MCP_PRODUCTO") -> None:
        if not _SAFE_VIEW.fullmatch(view_name):
            raise ValueError("Unsafe view name")
        self._connection_factory = connection_factory
        self._view_name = view_name

    def get_by_partnumber(self, partnumber: str) -> dict[str, Any] | None:
        if not partnumber or not partnumber.strip():
            raise ValueError("partnumber is required")

        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            sql = f"SELECT TOP (1) * FROM {self._view_name} WHERE partnumber = ?"
            cursor.execute(sql, partnumber.strip())
            row = cursor.fetchone()
            if row is None:
                return None

            columns = [item[0] for item in cursor.description]
            return dict(zip(columns, row, strict=False))
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()
