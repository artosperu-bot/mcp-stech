from __future__ import annotations

from typing import Any, Callable


class ProductWorkQueryRepository:
    def __init__(self, connection_factory: Callable[[], Any]):
        self.connection_factory = connection_factory

    def list_for_product(self, partnumber: str, *, limit: int = 20) -> list[dict[str, Any]]:
        pn = str(partnumber or "").strip().upper()
        bounded = max(1, min(int(limit), 100))
        connection = self.connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT TOP ({bounded})
                    i.product_work_item_id AS item_id,
                    i.product_work_job_id AS job_id,
                    i.work_type,
                    i.partnumber,
                    i.category_code,
                    i.channel_code,
                    i.status,
                    i.current_step,
                    i.progress_pct,
                    i.priority,
                    i.attempt_count,
                    i.max_attempts,
                    i.last_error_code,
                    i.last_error_detail,
                    i.created_at,
                    i.updated_at,
                    i.completed_at,
                    j.source_name,
                    j.actor_source
                FROM dbo.product_work_item i
                JOIN dbo.product_work_job j
                  ON j.product_work_job_id = i.product_work_job_id
                WHERE i.partnumber = ?
                ORDER BY i.product_work_item_id DESC
                """,
                pn,
            )
            columns = [item[0] for item in (cursor.description or [])]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()
