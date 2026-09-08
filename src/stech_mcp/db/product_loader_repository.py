from __future__ import annotations

import json
from typing import Any, Callable

from stech_mcp.domain.product_loader_models import normalize_partnumber


def _row_to_dict(cursor: Any, row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    columns = [item[0] for item in (cursor.description or [])]
    return dict(zip(columns, row))


def _rows_to_dicts(cursor: Any, rows: list[Any]) -> list[dict[str, Any]]:
    columns = [item[0] for item in (cursor.description or [])]
    return [dict(zip(columns, row)) for row in rows]


class ProductLoaderRepository:
    def __init__(self, connection_factory: Callable[[], Any]):
        self.connection_factory = connection_factory

    def create_job(
        self,
        *,
        source_name: str,
        rows: list[dict[str, Any]],
        actor_source: str,
        channel: str,
    ) -> dict[str, Any]:
        source = str(source_name or "").strip()
        actor = str(actor_source or "").strip() or "SCR_UI"
        channel_code = str(channel or "").strip().upper() or "VTEX"
        if not source:
            raise ValueError("source_name is required")
        if not rows:
            raise ValueError("rows are required")

        normalized_rows: list[dict[str, Any]] = []
        seen_rows: set[int] = set()
        for row in rows:
            try:
                row_number = int(row.get("row_number"))
            except (TypeError, ValueError) as exc:
                raise ValueError("row_number must be a positive integer") from exc
            if row_number <= 0:
                raise ValueError("row_number must be a positive integer")
            if row_number in seen_rows:
                raise ValueError("duplicate row_number")
            seen_rows.add(row_number)

            partnumber = normalize_partnumber(row.get("partnumber"))
            if not partnumber:
                raise ValueError("partnumber is required")
            normalized_rows.append({**row, "row_number": row_number, "partnumber": partnumber})

        connection = self.connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                INSERT dbo.product_loader_job (
                    source_name, channel, actor_source, status, total_items
                )
                OUTPUT INSERTED.product_loader_job_id
                VALUES (?, ?, ?, N'PENDING', ?)
                """,
                source,
                channel_code,
                actor,
                len(normalized_rows),
            )
            inserted = cursor.fetchone()
            if not inserted:
                raise RuntimeError("product_loader_job insert did not return an id")
            job_id = int(inserted[0])

            items: list[dict[str, Any]] = []
            for row in normalized_rows:
                input_json = json.dumps(row, ensure_ascii=False, separators=(",", ":"), default=str)
                cursor.execute(
                    """
                    INSERT dbo.product_loader_job_item (
                        product_loader_job_id, row_number, partnumber, input_json, status
                    )
                    OUTPUT INSERTED.product_loader_job_item_id
                    VALUES (?, ?, ?, ?, N'PENDING')
                    """,
                    job_id,
                    row["row_number"],
                    row["partnumber"],
                    input_json,
                )
                inserted_item = cursor.fetchone()
                if not inserted_item:
                    raise RuntimeError("product_loader_job_item insert did not return an id")
                items.append(
                    {
                        "item_id": int(inserted_item[0]),
                        "row_number": row["row_number"],
                        "partnumber": row["partnumber"],
                        "status": "PENDING",
                        "input": row,
                    }
                )

            connection.commit()
            return {
                "job_id": job_id,
                "source_name": source,
                "channel": channel_code,
                "actor_source": actor,
                "status": "PENDING",
                "total_items": len(items),
                "items": items,
            }
        except Exception:
            if hasattr(connection, "rollback"):
                connection.rollback()
            raise
        finally:
            connection.close()

    def get_job(self, job_id: int) -> dict[str, Any] | None:
        parsed_job_id = int(job_id)
        connection = self.connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT
                    product_loader_job_id, source_name, channel, actor_source,
                    status, total_items
                FROM dbo.product_loader_job
                WHERE product_loader_job_id = ?
                """,
                parsed_job_id,
            )
            job = _row_to_dict(cursor, cursor.fetchone())
            if job is None:
                return None

            cursor.execute(
                """
                SELECT
                    product_loader_job_item_id, product_loader_job_id, row_number,
                    partnumber, input_json, status
                FROM dbo.product_loader_job_item
                WHERE product_loader_job_id = ?
                ORDER BY row_number, product_loader_job_item_id
                """,
                parsed_job_id,
            )
            items = _rows_to_dicts(cursor, list(cursor.fetchall()))
            for item in items:
                raw = item.pop("input_json", None)
                try:
                    item["input"] = json.loads(raw) if raw else {}
                except (TypeError, json.JSONDecodeError):
                    item["input"] = {}
                item["item_id"] = item.get("product_loader_job_item_id")

            cursor.execute(
                """
                SELECT
                    product_loader_job_event_id, product_loader_job_id,
                    product_loader_job_item_id, event_type, status
                FROM dbo.product_loader_job_event
                WHERE product_loader_job_id = ?
                ORDER BY product_loader_job_event_id
                """,
                parsed_job_id,
            )
            events = _rows_to_dicts(cursor, list(cursor.fetchall()))

            status_counts = {
                "completed": 0,
                "research_required": 0,
                "review_required": 0,
                "blocked": 0,
                "failed": 0,
            }
            for item in items:
                key = str(item.get("status") or "").strip().lower()
                if key in status_counts:
                    status_counts[key] += 1

            return {
                **job,
                "job_id": job.get("product_loader_job_id"),
                "items": items,
                "events": events,
                "summary": {"total": len(items), **status_counts},
            }
        finally:
            connection.close()
