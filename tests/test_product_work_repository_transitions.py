from __future__ import annotations

import pytest

from stech_mcp.db.product_work_repository import ProductWorkRepository


class FakeCursor:
    def __init__(self, fetchone_values=None):
        self.fetchone_values = list(fetchone_values or [])
        self.executions = []
        self.description = []

    def execute(self, sql, *params):
        self.executions.append((sql, params))
        upper = sql.upper()
        if "SELECT STATUS" in upper:
            self.description = [("status",)]
        elif "OUTPUT INSERTED.PRODUCT_WORK_ITEM_ID" in upper:
            self.description = [
                ("product_work_item_id",), ("product_work_job_id",), ("work_type",),
                ("partnumber",), ("category_code",), ("channel_code",),
                ("context_hash",), ("input_json",), ("status",), ("current_step",),
                ("progress_pct",), ("priority",), ("attempt_count",), ("max_attempts",),
                ("next_attempt_at",), ("claimed_by",), ("claim_expires_at",),
            ]
        return self

    def fetchone(self):
        return self.fetchone_values.pop(0) if self.fetchone_values else None


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_obj = cursor
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self): return self.cursor_obj
    def commit(self): self.committed = True
    def rollback(self): self.rolled_back = True
    def close(self): self.closed = True


def test_invalid_terminal_transition_is_rejected_without_update():
    cursor = FakeCursor(fetchone_values=[("COMPLETED",)])
    conn = FakeConnection(cursor)
    repo = ProductWorkRepository(lambda: conn)

    with pytest.raises(ValueError, match="invalid transition"):
        repo.transition_item(10, status="QUEUED", current_step="retry")

    updates = [sql for sql, _ in cursor.executions if sql.lstrip().upper().startswith("UPDATE")]
    assert updates == []
    assert conn.rolled_back is True
    assert conn.closed is True


def test_retry_scheduling_clears_claim_and_increments_attempt_count():
    row = (
        10, 3, "ENRICH_TECHNICAL", "PN1", "LAPTOP", None,
        "b" * 64, '{"partnumber":"PN1"}', "FAILED_RETRYABLE", "retry scheduled",
        30, 50, 1, 3, None, None, None,
    )
    cursor = FakeCursor(fetchone_values=[row])
    conn = FakeConnection(cursor)
    repo = ProductWorkRepository(lambda: conn)

    item = repo.schedule_retry(
        10,
        error_code="TEMPORARY_SOURCE_ERROR",
        error_detail="timeout",
        delay_seconds=60,
    )

    assert item["status"] == "FAILED_RETRYABLE"
    sql = "\n".join(text.upper() for text, _ in cursor.executions)
    assert "ATTEMPT_COUNT = ATTEMPT_COUNT + 1" in sql
    assert "NEXT_ATTEMPT_AT" in sql
    assert "CLAIMED_BY = NULL" in sql
    assert "CLAIM_EXPIRES_AT = NULL" in sql
    assert conn.committed is True
