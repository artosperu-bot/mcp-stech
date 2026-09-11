from __future__ import annotations

from collections.abc import Callable
from typing import Any


class DeltronSpecificationRepository:
    """Read structured Deltron technical specifications from DB_DISTRIBUIDORES."""

    def __init__(self, connection_factory: Callable[[], Any]) -> None:
        self._connection_factory = connection_factory

    @staticmethod
    def _row_to_dict(cursor: Any, row: Any) -> dict[str, Any]:
        columns = [item[0] for item in cursor.description]
        return dict(zip(columns, row, strict=False))

    def list_for_product(self, producto_distribuidor_id: int) -> list[dict[str, Any]]:
        product_id = int(producto_distribuidor_id)
        if product_id <= 0:
            raise ValueError("producto_distribuidor_id must be greater than zero")

        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
SELECT *
FROM dbo.PRD_DELTRON_ESPECIFICACION
WHERE producto_distribuidor_id = ?
ORDER BY orden_seccion, orden_atributo, orden, especificacion_id
""",
                product_id,
            )
            return [self._row_to_dict(cursor, row) for row in cursor.fetchall()]
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()
