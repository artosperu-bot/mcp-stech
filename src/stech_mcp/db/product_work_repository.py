from __future__ import annotations

import json
from typing import Any, Callable

from stech_mcp.domain.product_work_models import can_transition


ConnectionFactory = Callable[[], Any]


class ProductWorkRepository:
    def __init__(self, connection_factory: ConnectionFactory):
        self.connection_factory = connection_factory

    @staticmethod
    def _row_dict(cursor: Any, row: Any) -> dict[str, Any] | None:
        if row is None:
            return None
        names = [str(col[0]) for col in cursor.description]
        return dict(zip(names, row, strict=False))

    @staticmethod
    def _decode_item(row: dict[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        out = dict(row)
        if "product_work_item_id" in out:
            out["item_id"] = out["product_work_item_id"]
        if "product_work_job_id" in out:
            out["job_id"] = out["product_work_job_id"]
        raw = out.get("input_json")
        if isinstance(raw, str):
            try:
                out["input"] = json.loads(raw)
            except json.JSONDecodeError:
                out["input"] = {}
        elif isinstance(raw, dict):
            out["input"] = raw
        else:
            out["input"] = {}
        return out

    def claim_next(self, worker_id: str, lease_seconds: int = 120) -> dict[str, Any] | None:
        conn = self.connection_factory()
        try:
            cur = conn.cursor()
            cur.execute(
                """
;WITH next_item AS (
    SELECT TOP (1) i.product_work_item_id
    FROM dbo.product_work_item i WITH (UPDLOCK, READPAST, ROWLOCK)
    WHERE i.status IN (N'QUEUED', N'FAILED_RETRYABLE')
      AND (i.next_attempt_at IS NULL OR i.next_attempt_at <= SYSUTCDATETIME())
      AND (i.claim_expires_at IS NULL OR i.claim_expires_at <= SYSUTCDATETIME())
      AND i.attempt_count < i.max_attempts
    ORDER BY i.priority DESC, i.product_work_item_id
)
UPDATE i
SET claimed_by = ?,
    claimed_at = SYSUTCDATETIME(),
    claim_expires_at = DATEADD(SECOND, ?, SYSUTCDATETIME()),
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

    def renew_claim(self, item_id: int, worker_id: str, lease_seconds: int = 120) -> bool:
        conn = self.connection_factory()
        try:
            cur = conn.cursor()
            cur.execute(
                """
UPDATE dbo.product_work_item
SET claim_expires_at = DATEADD(SECOND, ?, SYSUTCDATETIME()),
    updated_at = SYSUTCDATETIME()
WHERE product_work_item_id = ?
  AND claimed_by = ?
  AND claim_expires_at > SYSUTCDATETIME();
""",
                int(lease_seconds), int(item_id), worker_id,
            )
            changed = bool(getattr(cur, "rowcount", 0))
            conn.commit()
            return changed
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def transition_item(
        self,
        item_id: int,
        *,
        status: str,
        current_step: str | None = None,
        progress_pct: int | None = None,
        error_code: str | None = None,
        error_detail: str | None = None,
    ) -> dict[str, Any]:
        target = str(status or "").strip().upper()
        conn = self.connection_factory()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT status FROM dbo.product_work_item WITH (UPDLOCK, ROWLOCK) WHERE product_work_item_id = ?;",
                int(item_id),
            )
            existing = cur.fetchone()
            if existing is None:
                raise LookupError(f"product work item not found: {item_id}")
            current = str(existing[0])
            if not can_transition(current, target):
                raise ValueError(f"invalid transition: {current} -> {target}")

            terminal = target in {"COMPLETED", "PARTIAL", "REVIEW_REQUIRED", "NO_DATA_FOUND", "FAILED", "CANCELLED"}
            cur.execute(
                """
UPDATE dbo.product_work_item
SET status = ?,
    current_step = COALESCE(?, current_step),
    progress_pct = COALESCE(?, progress_pct),
    last_error_code = ?,
    last_error_detail = ?,
    completed_at = CASE WHEN ? = 1 THEN SYSUTCDATETIME() ELSE completed_at END,
    claimed_by = CASE WHEN ? = 1 THEN NULL ELSE claimed_by END,
    claimed_at = CASE WHEN ? = 1 THEN NULL ELSE claimed_at END,
    claim_expires_at = CASE WHEN ? = 1 THEN NULL ELSE claim_expires_at END,
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
WHERE product_work_item_id = ?;
""",
                target,
                current_step,
                progress_pct,
                error_code,
                error_detail,
                int(terminal),
                int(terminal),
                int(terminal),
                int(terminal),
                int(item_id),
            )
            row = self._decode_item(self._row_dict(cur, cur.fetchone()))
            if row is None:
                raise LookupError(f"product work item not found: {item_id}")
            conn.commit()
            return row
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def schedule_retry(
        self,
        item_id: int,
        *,
        error_code: str,
        error_detail: str | None,
        delay_seconds: int,
    ) -> dict[str, Any]:
        conn = self.connection_factory()
        try:
            cur = conn.cursor()
            cur.execute(
                """
UPDATE dbo.product_work_item
SET status = N'FAILED_RETRYABLE',
    current_step = N'retry scheduled',
    attempt_count = attempt_count + 1,
    next_attempt_at = DATEADD(SECOND, ?, SYSUTCDATETIME()),
    claimed_by = NULL,
    claimed_at = NULL,
    claim_expires_at = NULL,
    last_error_code = ?,
    last_error_detail = ?,
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
WHERE product_work_item_id = ?
  AND attempt_count < max_attempts;
""",
                int(delay_seconds), error_code, error_detail, int(item_id),
            )
            row = self._decode_item(self._row_dict(cur, cur.fetchone()))
            if row is None:
                raise ValueError("retry limit reached or item not found")
            conn.commit()
            return row
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def release_expired_claims(self) -> int:
        conn = self.connection_factory()
        try:
            cur = conn.cursor()
            cur.execute(
                """
UPDATE dbo.product_work_item
SET claimed_by = NULL,
    claimed_at = NULL,
    claim_expires_at = NULL,
    updated_at = SYSUTCDATETIME()
WHERE claim_expires_at IS NOT NULL
  AND claim_expires_at <= SYSUTCDATETIME()
  AND status NOT IN (N'COMPLETED', N'PARTIAL', N'REVIEW_REQUIRED', N'NO_DATA_FOUND', N'FAILED', N'CANCELLED');
"""
            )
            count = int(getattr(cur, "rowcount", 0) or 0)
            conn.commit()
            return count
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
