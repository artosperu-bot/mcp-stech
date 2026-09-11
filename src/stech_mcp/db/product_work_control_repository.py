from __future__ import annotations

import json
from typing import Any

from stech_mcp.db.product_work_repository import ProductWorkRepository


class ProductWorkControlRepository(ProductWorkRepository):
    def create_job(
        self,
        *,
        work_type: str,
        source_name: str,
        actor_source: str,
        priority: int,
        max_attempts: int,
        items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        conn = self.connection_factory()
        try:
            cur = conn.cursor()
            cur.execute(
                """
INSERT INTO dbo.product_work_job(work_type, source_name, actor_source, status, priority)
OUTPUT INSERTED.product_work_job_id
VALUES (?, ?, ?, N'PENDING', ?);
""",
                work_type, source_name, actor_source, int(priority),
            )
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("failed to create product work job")
            job_id = int(row[0])
            result_items: list[dict[str, Any]] = []
            queued = 0

            for item in items:
                payload = dict(item)
                context_hash = str(payload.pop("context_hash"))
                pn = str(payload.get("partnumber") or "").strip().upper()
                category = payload.get("category_code")
                channel = payload.get("channel_code")
                row_number = payload.get("row_number")
                cur.execute(
                    """
INSERT INTO dbo.product_work_item(
    product_work_job_id, work_type, partnumber, category_code, channel_code,
    source_row_number, context_hash, input_json, status, priority, max_attempts
)
OUTPUT INSERTED.product_work_item_id
SELECT ?, ?, ?, ?, ?, ?, ?, ?, N'QUEUED', ?, ?
WHERE NOT EXISTS (
    SELECT 1
    FROM dbo.product_work_item WITH (UPDLOCK, HOLDLOCK)
    WHERE active_work_key = CONVERT(NVARCHAR(260), ? + N'|' + ?)
);
""",
                    job_id,
                    work_type,
                    pn,
                    category,
                    channel,
                    row_number,
                    context_hash,
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    int(priority),
                    int(max_attempts),
                    pn,
                    context_hash,
                )
                inserted = cur.fetchone()
                if inserted is None:
                    result_items.append({"partnumber": pn, "state": "ALREADY_ACTIVE"})
                    continue
                queued += 1
                result_items.append({
                    "item_id": int(inserted[0]),
                    "partnumber": pn,
                    "state": "QUEUED",
                    "input": payload,
                })

            status = "PENDING" if queued else "COMPLETED"
            cur.execute(
                """
UPDATE dbo.product_work_job
SET total_items = ?, status = ?,
    finished_at = CASE WHEN ? = 0 THEN SYSUTCDATETIME() ELSE NULL END,
    updated_at = SYSUTCDATETIME()
WHERE product_work_job_id = ?;
""",
                queued, status, queued, job_id,
            )
            conn.commit()
            return {
                "job_id": job_id,
                "status": status,
                "total_items": queued,
                "requested_items": len(items),
                "items": result_items,
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_job(self, job_id: int) -> dict[str, Any] | None:
        conn = self.connection_factory()
        try:
            cur = conn.cursor()
            cur.execute(
                """
SELECT product_work_job_id, work_type, source_name, actor_source, status, priority,
       total_items, completed_items, review_items, failed_items,
       created_at, started_at, finished_at, updated_at
FROM dbo.product_work_job
WHERE product_work_job_id = ?;
""",
                int(job_id),
            )
            job_row = cur.fetchone()
            job = self._row_dict(cur, job_row)
            if job is None:
                return None
            cur.execute(
                """
SELECT product_work_item_id, product_work_job_id, work_type, partnumber,
       category_code, channel_code, status, current_step, progress_pct, priority,
       attempt_count, max_attempts, next_attempt_at, claimed_by, claim_expires_at,
       last_error_code, last_error_detail, created_at, updated_at, completed_at
FROM dbo.product_work_item
WHERE product_work_job_id = ?
ORDER BY product_work_item_id;
""",
                int(job_id),
            )
            rows = [self._row_dict(cur, row) for row in cur.fetchall()]
            job["job_id"] = job["product_work_job_id"]
            job["items"] = [
                {**row, "item_id": row["product_work_item_id"]}
                for row in rows if row is not None
            ]
            return job
        finally:
            conn.close()

    def list_jobs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        conn = self.connection_factory()
        try:
            cur = conn.cursor()
            cur.execute(
                """
SELECT TOP (?) product_work_job_id, work_type, source_name, actor_source, status,
       priority, total_items, completed_items, review_items, failed_items,
       created_at, started_at, finished_at, updated_at
FROM dbo.product_work_job
ORDER BY product_work_job_id DESC;
""",
                int(limit),
            )
            result = []
            for row in cur.fetchall():
                item = self._row_dict(cur, row)
                if item is not None:
                    item["job_id"] = item["product_work_job_id"]
                    result.append(item)
            return result
        finally:
            conn.close()

    def retry_item(self, item_id: int) -> dict[str, Any]:
        conn = self.connection_factory()
        try:
            cur = conn.cursor()
            cur.execute(
                """
UPDATE dbo.product_work_item
SET status = N'QUEUED', current_step = N'manual retry', progress_pct = 0,
    next_attempt_at = NULL, claimed_by = NULL, claimed_at = NULL,
    claim_expires_at = NULL, last_error_code = NULL, last_error_detail = NULL,
    completed_at = NULL,
    max_attempts = CASE WHEN attempt_count >= max_attempts THEN attempt_count + 1 ELSE max_attempts END,
    updated_at = SYSUTCDATETIME()
OUTPUT INSERTED.product_work_item_id, INSERTED.partnumber, INSERTED.status
WHERE product_work_item_id = ?
  AND status IN (N'FAILED_RETRYABLE', N'FAILED', N'PARTIAL', N'REVIEW_REQUIRED', N'NO_DATA_FOUND');
""",
                int(item_id),
            )
            row = cur.fetchone()
            if row is None:
                raise ValueError("item cannot be retried in its current state")
            conn.commit()
            return {"item_id": int(row[0]), "partnumber": row[1], "status": row[2]}
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def cancel_item(self, item_id: int) -> dict[str, Any]:
        conn = self.connection_factory()
        try:
            cur = conn.cursor()
            cur.execute(
                """
UPDATE dbo.product_work_item
SET status = N'CANCELLED', current_step = N'cancelled',
    claimed_by = NULL, claimed_at = NULL, claim_expires_at = NULL,
    completed_at = SYSUTCDATETIME(), updated_at = SYSUTCDATETIME()
OUTPUT INSERTED.product_work_item_id, INSERTED.partnumber, INSERTED.status
WHERE product_work_item_id = ?
  AND status NOT IN (N'COMPLETED', N'CANCELLED');
""",
                int(item_id),
            )
            row = cur.fetchone()
            if row is None:
                raise ValueError("item cannot be cancelled in its current state")
            conn.commit()
            return {"item_id": int(row[0]), "partnumber": row[1], "status": row[2]}
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
