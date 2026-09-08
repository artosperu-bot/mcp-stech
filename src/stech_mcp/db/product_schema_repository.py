from __future__ import annotations

from collections.abc import Callable
from typing import Any

from stech_mcp.domain.product_schema import CategoryAttribute, normalize_category_code


class ProductSchemaRepository:
    def __init__(self, connection_factory: Callable[[], Any]):
        self._connection_factory = connection_factory

    def get_category_schema(self, category_code: str) -> list[CategoryAttribute]:
        normalized = normalize_category_code(category_code)
        if not normalized:
            return []

        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
SELECT
    ca.category_code,
    ca.field_code,
    ca.requirement,
    ca.ordinal,
    d.value_type,
    d.unit,
    d.variant_sensitive,
    d.reuse_policy
FROM dbo.category_attribute ca
INNER JOIN dbo.product_attribute_definition d
    ON d.field_code = ca.field_code
WHERE ca.category_code = ?
  AND ca.active = 1
  AND d.enabled = 1
ORDER BY ca.ordinal, ca.field_code;
""",
                normalized,
            )
            return [
                CategoryAttribute(
                    category_code=row[0],
                    field_code=row[1],
                    requirement=row[2],
                    ordinal=row[3],
                    value_type=row[4],
                    unit=row[5],
                    variant_sensitive=bool(row[6]),
                    reuse_policy=row[7],
                )
                for row in cursor.fetchall()
            ]
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()
