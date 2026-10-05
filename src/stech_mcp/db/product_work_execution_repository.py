from __future__ import annotations

import json
from typing import Any

from stech_mcp.db.product_work_control_repository import ProductWorkControlRepository


class ProductWorkExecutionRepository(ProductWorkControlRepository):
    def claim_next(
        self,
        worker_id: str,
        lease_seconds: int = 120,
        allowed_work_types: tuple[str, ...] | list[str] | None = None,
    ) -> dict[str, Any] | None:
        allowed = tuple(
            dict.fromkeys(
                str(value or "").strip().upper()
                for value in (allowed_work_types or ())
                if str(value or "").strip()
            )
        )
        if not allowed:
            return super().claim_next(worker_id, lease_seconds)

        placeholders = ",".join("?" for _ in allowed)
        conn = self.connection_factory()
        try:
            cur = conn.cursor()
            cur.execute(
                f"""
;WITH next_item AS (
    SELECT TOP (1) i.product_work_item_id
    FROM dbo.product_work_item i WITH (UPDLOCK, READPAST, ROWLOCK)
    WHERE i.status IN (N'QUEUED', N'FAILED_RETRYABLE')
      AND i.work_type IN ({placeholders})
      AND (i.next_attempt_at IS NULL OR i.next_attempt_at <= SYSUTCDATETIME())
      AND (i.claim_expires_at IS NULL OR i.claim_expires_at <= SYSUTCDATETIME())
      AND i.attempt_count < i.max_attempts
    ORDER BY i.priority DESC, i.product_work_item_id
)
UPDATE i
SET claimed_by = ?,
    claimed_at = SYSUTCDATETIME(),
    claim_expires_at = DATEADD(SECOND, ?, SYSUTCDATETIME()),
    attempt_count = attempt_count + 1,
    updated_at = SYSUTCDATETIME()
OUTPUT
    INSERTED.product_work_item_id,
    INSERTED.product_work_job_id,
    INSERTED.work_type,
    INSERTED.partnumber,
    INSERTED.category_code,
    INSERTED.channel_code,
    INSERTED.context_hash,
    INSERTED.input_json,
    INSERTED.status,
    INSERTED.current_step,
    INSERTED.progress_pct,
    INSERTED.priority,
    INSERTED.attempt_count,
    INSERTED.max_attempts,
    INSERTED.next_attempt_at,
    INSERTED.claimed_by,
    INSERTED.claim_expires_at
FROM dbo.product_work_item i
JOIN next_item n ON n.product_work_item_id = i.product_work_item_id;
""",
                *allowed,
                worker_id,
                int(lease_seconds),
            )
            row = self._decode_item(self._row_dict(cur, cur.fetchone()))
            conn.commit()
            return row
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_item(self, item_id: int) -> dict[str, Any] | None:
        conn = self.connection_factory()
        try:
            cur = conn.cursor()
            cur.execute(
                """
SELECT product_work_item_id, product_work_job_id, work_type, partnumber,
       category_code, channel_code, context_hash, input_json, status,
       current_step, progress_pct, priority, attempt_count, max_attempts,
       next_attempt_at, claimed_by, claimed_at, claim_expires_at,
       last_error_code, last_error_detail, created_at, updated_at, completed_at
FROM dbo.product_work_item
WHERE product_work_item_id = ?;
""",
                int(item_id),
            )
            return self._decode_item(self._row_dict(cur, cur.fetchone()))
        finally:
            conn.close()

    def record_event(
        self,
        item: dict[str, Any],
        event_type: str,
        *,
        status: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        job_id = int(item.get("job_id") or item.get("product_work_job_id"))
        item_id = int(item.get("item_id") or item.get("product_work_item_id"))
        conn = self.connection_factory()
        try:
            cur = conn.cursor()
            cur.execute(
                """
INSERT INTO dbo.product_work_event(
    product_work_job_id, product_work_item_id, partnumber,
    event_type, actor_source, status, detail_json
)
VALUES (?, ?, ?, ?, N'WORKER', ?, ?);
""",
                job_id,
                item_id,
                str(item.get("partnumber") or ""),
                str(event_type or "WORKER_EVENT").strip().upper(),
                status,
                json.dumps(detail, ensure_ascii=False, separators=(",", ":")) if detail else None,
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def record_attempt_start(self, item: dict[str, Any], worker_id: str) -> dict[str, int]:
        job_id = int(item.get("job_id") or item.get("product_work_job_id"))
        item_id = int(item.get("item_id") or item.get("product_work_item_id"))
        conn = self.connection_factory()
        try:
            cur = conn.cursor()
            cur.execute(
                """
UPDATE dbo.product_work_item WITH (UPDLOCK, ROWLOCK)
SET attempt_count = attempt_count + 1,
    updated_at = SYSUTCDATETIME()
OUTPUT INSERTED.attempt_count
WHERE product_work_item_id = ?
  AND attempt_count < max_attempts;
""",
                item_id,
            )
            attempt_row = cur.fetchone()
            if attempt_row is None:
                raise ValueError("max attempts reached or product work item not found")
            attempt_number = int(attempt_row[0])

            cur.execute(
                """
INSERT INTO dbo.product_work_attempt(
    product_work_job_id, product_work_item_id, attempt_number, worker_id
)
OUTPUT INSERTED.product_work_attempt_id, INSERTED.attempt_number
VALUES (?, ?, ?, ?);
""",
                job_id, item_id, attempt_number, worker_id,
            )
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("failed to record product work attempt")
            conn.commit()
            return {"attempt_id": int(row[0]), "attempt_number": int(row[1])}
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def record_attempt_end(
        self,
        attempt_id: int,
        *,
        outcome_status: str,
        error_code: str | None = None,
        error_detail: str | None = None,
    ) -> None:
        conn = self.connection_factory()
        try:
            cur = conn.cursor()
            cur.execute(
                """
UPDATE dbo.product_work_attempt
SET finished_at = SYSUTCDATETIME(), outcome_status = ?,
    error_code = ?, error_detail = ?
WHERE product_work_attempt_id = ?;
""",
                outcome_status, error_code, error_detail, int(attempt_id),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def refresh_job_summary(self, job_id: int) -> dict[str, Any]:
        conn = self.connection_factory()
        try:
            cur = conn.cursor()
            cur.execute(
                """
SELECT
    COUNT(*) AS total_items,
    SUM(CASE WHEN status = N'COMPLETED' THEN 1 ELSE 0 END) AS completed_items,
    SUM(CASE WHEN status = N'REVIEW_REQUIRED' THEN 1 ELSE 0 END) AS review_items,
    SUM(CASE WHEN status = N'FAILED' THEN 1 ELSE 0 END) AS failed_items,
    SUM(CASE WHEN status IN (N'PARTIAL', N'NO_DATA_FOUND') THEN 1 ELSE 0 END) AS partial_items,
    SUM(CASE WHEN status NOT IN (
        N'COMPLETED', N'PARTIAL', N'REVIEW_REQUIRED', N'NO_DATA_FOUND', N'FAILED', N'CANCELLED'
    ) THEN 1 ELSE 0 END) AS active_items,
    SUM(CASE WHEN status = N'CANCELLED' THEN 1 ELSE 0 END) AS cancelled_items
FROM dbo.product_work_item
WHERE product_work_job_id = ?;
""",
                int(job_id),
            )
            row = cur.fetchone()
            if row is None:
                raise LookupError(f"product work job not found: {job_id}")
            total, completed, review, failed, partial, active, cancelled = [int(value or 0) for value in row]

            if active > 0:
                status = "RUNNING"
            elif total > 0 and completed == total:
                status = "COMPLETED"
            elif total > 0 and cancelled == total:
                status = "CANCELLED"
            elif review > 0:
                status = "WAITING_REVIEW"
            elif total > 0 and failed == total:
                status = "FAILED"
            else:
                status = "PARTIAL"

            cur.execute(
                """
UPDATE dbo.product_work_job
SET status = ?, total_items = ?, completed_items = ?, review_items = ?, failed_items = ?,
    started_at = CASE WHEN started_at IS NULL AND ? = N'RUNNING' THEN SYSUTCDATETIME() ELSE started_at END,
    finished_at = CASE WHEN ? IN (N'COMPLETED', N'PARTIAL', N'FAILED', N'CANCELLED') THEN SYSUTCDATETIME() ELSE NULL END,
    updated_at = SYSUTCDATETIME()
WHERE product_work_job_id = ?;
""",
                status, total, completed, review, failed, status, status, int(job_id),
            )
            conn.commit()
            return {
                "job_id": int(job_id),
                "status": status,
                "total_items": total,
                "completed_items": completed,
                "review_items": review,
                "failed_items": failed,
                "partial_items": partial,
                "cancelled_items": cancelled,
                "active_items": active,
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
