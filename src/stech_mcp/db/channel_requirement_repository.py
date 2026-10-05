from __future__ import annotations

from typing import Any, Callable


class ChannelRequirementRepository:
    def __init__(self, connection_factory: Callable[[], Any]):
        self.connection_factory = connection_factory

    def get(
        self,
        channel_code: str,
        category_code: str,
        version_code: str | None = None,
    ) -> dict[str, Any] | None:
        channel = str(channel_code or "").strip().upper()
        category = str(category_code or "").strip().upper()
        version = str(version_code or "").strip().upper() or None
        if not channel or not category:
            raise ValueError("channel_code and category_code are required")

        connection = self.connection_factory()
        try:
            cursor = connection.cursor()
            if version:
                cursor.execute(
                    """
                    SELECT TOP (1) channel_code, platform_code, template_code,
                           version_code, category_code
                    FROM dbo.V_CHANNEL_REQUIREMENT_V2
                    WHERE channel_code = ? AND category_code = ? AND version_code = ?
                      AND active = 1
                    ORDER BY template_code
                    """,
                    channel,
                    category,
                    version,
                )
            else:
                cursor.execute(
                    """
                    SELECT TOP (1) channel_code, platform_code, template_code,
                           version_code, category_code
                    FROM dbo.V_CHANNEL_REQUIREMENT_V2
                    WHERE channel_code = ? AND category_code = ? AND active = 1
                      AND (valid_from IS NULL OR valid_from <= SYSUTCDATETIME())
                      AND (valid_to IS NULL OR valid_to > SYSUTCDATETIME())
                    ORDER BY COALESCE(valid_from, CONVERT(DATETIME2(0),'19000101')) DESC,
                             version_code DESC, template_code
                    """,
                    channel,
                    category,
                )
            header = cursor.fetchone()
            if header is None:
                return None
            columns = [item[0] for item in (cursor.description or [])]
            head = dict(zip(columns, header))
            cursor.execute(
                """
                SELECT target_field_code, master_field_code, display_name,
                       requirement, data_scope, data_type, unit, excel_column,
                       json_path, allowed_values_json, transform_rule,
                       identifier_role, auto_fill, image_role
                FROM dbo.V_CHANNEL_REQUIREMENT_V2
                WHERE channel_code = ? AND category_code = ?
                  AND template_code = ? AND version_code = ? AND active = 1
                ORDER BY target_field_code
                """,
                channel,
                category,
                head["template_code"],
                head["version_code"],
            )
            field_columns = [item[0] for item in (cursor.description or [])]
            fields = [dict(zip(field_columns, row)) for row in cursor.fetchall()]
            return {**head, "fields": fields}
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()
