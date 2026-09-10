from __future__ import annotations

import json
from typing import Any, Callable, Iterable

from stech_mcp.domain.product_loader_models import ITEM_STATES, JOB_STATES, normalize_partnumber


def _row_to_dict(cursor: Any, row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    columns = [item[0] for item in (cursor.description or [])]
    return dict(zip(columns, row))


def _rows_to_dicts(cursor: Any, rows: list[Any]) -> list[dict[str, Any]]:
    columns = [item[0] for item in (cursor.description or [])]
    return [dict(zip(columns, row)) for row in rows]


def _decode_item(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if item is None:
        return None
    out = dict(item)
    raw = out.pop("input_json", None)
    try:
        out["input"] = json.loads(raw) if raw else {}
    except (TypeError, json.JSONDecodeError):
        out["input"] = {}
    out["item_id"] = out.get("product_loader_job_item_id")
    return out


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

    def get_item(self, item_id: int) -> dict[str, Any] | None:
        connection = self.connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT
                    product_loader_job_item_id, product_loader_job_id, row_number,
                    partnumber, input_json, status, current_step, retry_count,
                    product_id_vtex, sku_id_vtex, product_ref_id_vtex, sku_ref_id_vtex,
                    last_error_code, last_error_detail, claimed_at, completed_at,
                    created_at, updated_at
                FROM dbo.product_loader_job_item
                WHERE product_loader_job_item_id = ?
                """,
                int(item_id),
            )
            return _decode_item(_row_to_dict(cursor, cursor.fetchone()))
        finally:
            connection.close()

    def claim_item(self, item_id: int, expected_states: Iterable[str]) -> bool:
        allowed = {str(value or "").strip().upper() for value in expected_states}
        if not allowed:
            return False
        connection = self.connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT status
                FROM dbo.product_loader_job_item WITH (UPDLOCK, HOLDLOCK)
                WHERE product_loader_job_item_id = ?
                """,
                int(item_id),
            )
            row = cursor.fetchone()
            if row is None or str(row[0] or "").strip().upper() not in allowed:
                if hasattr(connection, "rollback"):
                    connection.rollback()
                return False
            cursor.execute(
                """
                UPDATE dbo.product_loader_job_item
                SET claimed_at = SYSUTCDATETIME(), updated_at = SYSUTCDATETIME()
                WHERE product_loader_job_item_id = ?
                """,
                int(item_id),
            )
            connection.commit()
            return True
        except Exception:
            if hasattr(connection, "rollback"):
                connection.rollback()
            raise
        finally:
            connection.close()

    def update_item(
        self,
        item_id: int,
        *,
        status: str,
        current_step: str | None = None,
        product_id_vtex: int | None = None,
        sku_id_vtex: int | None = None,
        product_ref_id_vtex: str | None = None,
        sku_ref_id_vtex: str | None = None,
        last_error_code: str | None = None,
        last_error_detail: str | None = None,
        completed: bool = False,
    ) -> dict[str, Any]:
        state = str(status or "").strip().upper()
        if state not in ITEM_STATES:
            raise ValueError(f"invalid item status: {state}")
        connection = self.connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                UPDATE dbo.product_loader_job_item
                SET status = ?,
                    current_step = ?,
                    product_id_vtex = COALESCE(?, product_id_vtex),
                    sku_id_vtex = COALESCE(?, sku_id_vtex),
                    product_ref_id_vtex = COALESCE(?, product_ref_id_vtex),
                    sku_ref_id_vtex = COALESCE(?, sku_ref_id_vtex),
                    last_error_code = ?,
                    last_error_detail = ?,
                    completed_at = CASE WHEN ? = 1 THEN SYSUTCDATETIME() ELSE completed_at END,
                    updated_at = SYSUTCDATETIME()
                WHERE product_loader_job_item_id = ?
                """,
                state,
                str(current_step or state),
                product_id_vtex,
                sku_id_vtex,
                product_ref_id_vtex,
                sku_ref_id_vtex,
                last_error_code,
                last_error_detail,
                1 if completed else 0,
                int(item_id),
            )
            connection.commit()
            cursor.execute(
                """
                SELECT
                    product_loader_job_item_id, product_loader_job_id, row_number,
                    partnumber, input_json, status, current_step, retry_count,
                    product_id_vtex, sku_id_vtex, product_ref_id_vtex, sku_ref_id_vtex,
                    last_error_code, last_error_detail, claimed_at, completed_at,
                    created_at, updated_at
                FROM dbo.product_loader_job_item
                WHERE product_loader_job_item_id = ?
                """,
                int(item_id),
            )
            item = _decode_item(_row_to_dict(cursor, cursor.fetchone()))
            if item is None:
                raise ValueError("job item not found")
            return item
        except Exception:
            if hasattr(connection, "rollback"):
                connection.rollback()
            raise
        finally:
            connection.close()

    def append_event(
        self,
        *,
        job_id: int,
        item_id: int | None,
        partnumber: str | None,
        event_type: str,
        status: str | None = None,
        detail: dict[str, Any] | None = None,
        actor_source: str = "MCP",
    ) -> None:
        detail_json = json.dumps(detail or {}, ensure_ascii=False, separators=(",", ":"), default=str)
        connection = self.connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                INSERT dbo.product_loader_job_event (
                    product_loader_job_id, product_loader_job_item_id, partnumber,
                    event_type, actor_source, status, detail_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                int(job_id),
                int(item_id) if item_id is not None else None,
                normalize_partnumber(partnumber or "") or None,
                str(event_type or "").strip().upper(),
                str(actor_source or "MCP").strip() or "MCP",
                str(status or "").strip().upper() or None,
                detail_json,
            )
            connection.commit()
        except Exception:
            if hasattr(connection, "rollback"):
                connection.rollback()
            raise
        finally:
            connection.close()

    def reset_item_for_retry(self, item_id: int) -> dict[str, Any]:
        connection = self.connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                UPDATE dbo.product_loader_job_item
                SET status = N'PENDING', current_step = NULL,
                    retry_count = retry_count + 1,
                    last_error_code = NULL, last_error_detail = NULL,
                    claimed_at = NULL, completed_at = NULL,
                    updated_at = SYSUTCDATETIME()
                WHERE product_loader_job_item_id = ?
                """,
                int(item_id),
            )
            connection.commit()
        except Exception:
            if hasattr(connection, "rollback"):
                connection.rollback()
            raise
        finally:
            connection.close()
        item = self.get_item(int(item_id))
        if item is None:
            raise ValueError("job item not found")
        return item

    def list_resumable_items(self) -> list[dict[str, Any]]:
        connection = self.connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT
                    i.product_loader_job_item_id, i.product_loader_job_id, i.row_number,
                    i.partnumber, i.input_json, i.status, i.current_step, i.retry_count,
                    i.product_id_vtex, i.sku_id_vtex, i.product_ref_id_vtex, i.sku_ref_id_vtex,
                    i.last_error_code, i.last_error_detail, i.claimed_at, i.completed_at,
                    i.created_at, i.updated_at
                FROM dbo.product_loader_job_item i
                INNER JOIN dbo.product_loader_job j
                    ON j.product_loader_job_id = i.product_loader_job_id
                WHERE i.status IN (
                    N'PENDING', N'VALIDATING', N'PREPARING', N'IMAGES_LOCAL',
                    N'VTEX_CHECK', N'VTEX_CREATE_PRODUCT', N'VTEX_CREATE_SKU',
                    N'VTEX_IMAGES', N'VERIFYING'
                )
                  AND j.status NOT IN (N'COMPLETED', N'FAILED', N'CANCELLED')
                ORDER BY i.product_loader_job_id, i.row_number, i.product_loader_job_item_id
                """
            )
            return [_decode_item(row) for row in _rows_to_dicts(cursor, list(cursor.fetchall()))]
        finally:
            connection.close()

    def set_job_status(self, job_id: int, status: str) -> None:
        state = str(status or "").strip().upper()
        if state not in JOB_STATES:
            raise ValueError(f"invalid job status: {state}")
        connection = self.connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                UPDATE dbo.product_loader_job
                SET status = ?,
                    started_at = CASE WHEN ? = N'RUNNING' AND started_at IS NULL THEN SYSUTCDATETIME() ELSE started_at END,
                    finished_at = CASE WHEN ? IN (N'COMPLETED', N'PARTIAL', N'FAILED', N'CANCELLED') THEN SYSUTCDATETIME() ELSE finished_at END,
                    updated_at = SYSUTCDATETIME()
                WHERE product_loader_job_id = ?
                """,
                state,
                state,
                state,
                int(job_id),
            )
            connection.commit()
        except Exception:
            if hasattr(connection, "rollback"):
                connection.rollback()
            raise
        finally:
            connection.close()

    def refresh_job_summary(self, job_id: int) -> dict[str, int]:
        connection = self.connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT
                    COUNT(*) AS total_items,
                    SUM(CASE WHEN status = N'COMPLETED' THEN 1 ELSE 0 END) AS completed_items,
                    SUM(CASE WHEN status IN (N'RESEARCH_REQUIRED', N'REVIEW_REQUIRED') THEN 1 ELSE 0 END) AS review_items,
                    SUM(CASE WHEN status = N'BLOCKED' THEN 1 ELSE 0 END) AS blocked_items,
                    SUM(CASE WHEN status = N'FAILED' THEN 1 ELSE 0 END) AS failed_items
                FROM dbo.product_loader_job_item
                WHERE product_loader_job_id = ?
                """,
                int(job_id),
            )
            row = cursor.fetchone() or (0, 0, 0, 0, 0)
            summary = {
                "total_items": int(row[0] or 0),
                "completed_items": int(row[1] or 0),
                "review_items": int(row[2] or 0),
                "blocked_items": int(row[3] or 0),
                "failed_items": int(row[4] or 0),
            }
            cursor.execute(
                """
                UPDATE dbo.product_loader_job
                SET total_items = ?, completed_items = ?, review_items = ?,
                    blocked_items = ?, failed_items = ?, updated_at = SYSUTCDATETIME()
                WHERE product_loader_job_id = ?
                """,
                summary["total_items"],
                summary["completed_items"],
                summary["review_items"],
                summary["blocked_items"],
                summary["failed_items"],
                int(job_id),
            )
            connection.commit()
            return summary
        except Exception:
            if hasattr(connection, "rollback"):
                connection.rollback()
            raise
        finally:
            connection.close()

    def list_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        bounded = max(1, min(int(limit), 500))
        connection = self.connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT TOP ({bounded})
                    product_loader_job_id, source_name, channel, actor_source,
                    status, total_items, completed_items, review_items,
                    blocked_items, failed_items, created_at, started_at,
                    finished_at, updated_at
                FROM dbo.product_loader_job
                ORDER BY product_loader_job_id DESC
                """
            )
            jobs = _rows_to_dicts(cursor, list(cursor.fetchall()))
            if not jobs:
                return []

            job_ids = [int(job["product_loader_job_id"]) for job in jobs]
            placeholders = ",".join("?" for _ in job_ids)
            cursor.execute(
                f"""
                SELECT
                    product_loader_job_item_id, product_loader_job_id, row_number,
                    partnumber, status, last_error_code, last_error_detail,
                    created_at, updated_at
                FROM dbo.product_loader_job_item
                WHERE product_loader_job_id IN ({placeholders})
                ORDER BY product_loader_job_id DESC, row_number, product_loader_job_item_id
                """,
                *job_ids,
            )
            item_rows = _rows_to_dicts(cursor, list(cursor.fetchall()))
            items_by_job: dict[int, list[dict[str, Any]]] = {job_id: [] for job_id in job_ids}
            for row in item_rows:
                job_id = int(row.get("product_loader_job_id"))
                items_by_job.setdefault(job_id, []).append(
                    {
                        "item_id": row.get("product_loader_job_item_id"),
                        "row_number": row.get("row_number"),
                        "partnumber": normalize_partnumber(row.get("partnumber")),
                        "status": row.get("status"),
                        "last_error_code": row.get("last_error_code"),
                        "last_error_detail": row.get("last_error_detail"),
                        "created_at": row.get("created_at"),
                        "updated_at": row.get("updated_at"),
                    }
                )

            result: list[dict[str, Any]] = []
            for job in jobs:
                job_id = int(job.get("product_loader_job_id"))
                result.append(
                    {
                        **job,
                        "job_id": job_id,
                        "items": items_by_job.get(job_id, []),
                    }
                )
            return result
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
                    status, total_items, completed_items, review_items,
                    blocked_items, failed_items, created_at, started_at,
                    finished_at, updated_at
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
                    partnumber, input_json, status, current_step, retry_count,
                    product_id_vtex, sku_id_vtex, product_ref_id_vtex, sku_ref_id_vtex,
                    last_error_code, last_error_detail, claimed_at, completed_at,
                    created_at, updated_at
                FROM dbo.product_loader_job_item
                WHERE product_loader_job_id = ?
                ORDER BY row_number, product_loader_job_item_id
                """,
                parsed_job_id,
            )
            items = [_decode_item(row) for row in _rows_to_dicts(cursor, list(cursor.fetchall()))]

            cursor.execute(
                """
                SELECT
                    product_loader_job_event_id, product_loader_job_id,
                    product_loader_job_item_id, partnumber, event_type,
                    actor_source, status, detail_json, created_at
                FROM dbo.product_loader_job_event
                WHERE product_loader_job_id = ?
                ORDER BY product_loader_job_event_id
                """,
                parsed_job_id,
            )
            events = _rows_to_dicts(cursor, list(cursor.fetchall()))
            for event in events:
                raw = event.pop("detail_json", None)
                try:
                    event["detail"] = json.loads(raw) if raw else {}
                except (TypeError, json.JSONDecodeError):
                    event["detail"] = {}

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
