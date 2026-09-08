from __future__ import annotations

from stech_mcp.db.product_work_repository import ProductWorkRepository


class FakeCursor:
    def __init__(self, *, fetchone_values=None, fetchall_values=None):
        self.fetchone_values = list(fetchone_values or [])
        self.fetchall_values = list(fetchall_values or [])
        self.executions: list[tuple[str, tuple]] = []
        self.description = []

    def execute(self, sql, *params):
        self.executions.append((sql, params))
        upper = sql.upper()
        if "OUTPUT" in upper and "INSERTED.PRODUCT_WORK_ITEM_ID" in upper:
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

    def fetchall(self):
        return self.fetchall_values.pop(0) if self.fetchall_values else []


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_obj = cursor
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def test_claim_next_uses_atomic_sql_locks_priority_and_lease():
    row = (
        101, 41, "ENRICH_TECHNICAL", "PN1", "LAPTOP", None,
        "a" * 64, '{"partnumber":"PN1"}', "QUEUED", None,
        0, 100, 0, 3, None, "worker-a", None,
    )
    cursor = FakeCursor(fetchone_values=[row])
    conn = FakeConnection(cursor)
    repo = ProductWorkRepository(lambda: conn)

    item = repo.claim_next("worker-a", lease_seconds=120)

    assert item is not None
    assert item["item_id"] == 101
    assert item["partnumber"] == "PN1"
    assert item["input"]["partnumber"] == "PN1"
    sql = "\n".join(text.upper() for text, _ in cursor.executions)
    assert "UPDLOCK" in sql
    assert "READPAST" in sql
    assert "ROWLOCK" in sql
    assert "PRIORITY DESC" in sql
    assert "CLAIM_EXPIRES_AT" in sql
    assert "FAILED_RETRYABLE" in sql
    assert conn.committed is True
    assert conn.closed is True


def test_claim_next_returns_none_when_no_work_is_available():
    cursor = FakeCursor(fetchone_values=[None])
    conn = FakeConnection(cursor)
    repo = ProductWorkRepository(lambda: conn)

    assert repo.claim_next("worker-a", lease_seconds=120) is None
    assert conn.committed is True
    assert conn.closed is True
