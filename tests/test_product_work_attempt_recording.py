from __future__ import annotations

from stech_mcp.db.product_work_execution_repository import ProductWorkExecutionRepository


class FakeCursor:
    def __init__(self):
        self.executions: list[tuple[str, tuple]] = []
        self._last_sql = ""

    def execute(self, sql, *params):
        self._last_sql = str(sql)
        self.executions.append((self._last_sql, params))
        return self

    def fetchone(self):
        upper = self._last_sql.upper()
        if "UPDATE DBO.PRODUCT_WORK_ITEM" in upper:
            return (2,)
        if "INSERT INTO DBO.PRODUCT_WORK_ATTEMPT" in upper:
            return (44, 2)
        return None


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


def test_record_attempt_start_records_claimed_attempt_without_incrementing_again():
    cursor = FakeCursor()
    conn = FakeConnection(cursor)
    repo = ProductWorkExecutionRepository(lambda: conn)
    item = {
        "item_id": 7379,
        "job_id": 174,
        "partnumber": "981-000014",
        "attempt_count": 2,
        "max_attempts": 3,
    }

    result = repo.record_attempt_start(item, "worker-2")

    assert result == {"attempt_id": 44, "attempt_number": 2}
    sql = "\n".join(text.upper() for text, _ in cursor.executions)
    assert "ATTEMPT_COUNT = ATTEMPT_COUNT + 1" not in sql
    assert len(cursor.executions) == 1
    assert cursor.executions[0][1] == (174, 7379, 2, "worker-2")
    assert conn.committed is True
    assert conn.closed is True
