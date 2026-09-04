from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any


class PackagingRuleRepository:
    def __init__(self, connection_factory: Callable[[], Any]):
        self._connection_factory = connection_factory

    def match(self, category_code: str, screen_inches: Decimal) -> dict[str, Any] | None:
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT TOP (1) rule_code, category_code, screen_min_inches, screen_max_inches, "
                "width_cm, length_cm, height_cm, weight_g, priority, enabled, source_code "
                "FROM dbo.packaging_rule "
                "WHERE enabled = 1 "
                "AND category_code = ? "
                "AND (screen_min_inches IS NULL OR ? >= screen_min_inches) "
                "AND (screen_max_inches IS NULL OR ? < screen_max_inches) "
                "ORDER BY priority ASC, rule_code ASC;",
                category_code.strip().upper(),
                screen_inches,
                screen_inches,
            )
            row = cursor.fetchone()
            if row is None:
                return None
            columns = [column[0] for column in cursor.description]
            return dict(zip(columns, row, strict=False))
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()
