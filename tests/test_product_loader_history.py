from __future__ import annotations

from datetime import datetime, timezone

from stech_mcp.db.product_loader_repository import ProductLoaderRepository


class FakeCursor:
    def __init__(self):
        self.description = []
        self.executions: list[tuple[str, tuple]] = []
        self._rows = []

    def execute(self, sql, *params):
        self.executions.append((sql, params))
        if "FROM dbo.product_loader_job\n" in sql and "ORDER BY product_loader_job_id DESC" in sql:
            self.description = [
                ("product_loader_job_id",),
                ("source_name",),
                ("channel",),
                ("actor_source",),
                ("status",),
                ("total_items",),
                ("completed_items",),
                ("review_items",),
                ("blocked_items",),
                ("failed_items",),
                ("created_at",),
                ("started_at",),
                ("finished_at",),
                ("updated_at",),
            ]
            ts = datetime(2026, 9, 10, 14, 30, tzinfo=timezone.utc)
            self._rows = [
                (42, "carga-42.xlsx", "VTEX", "SCR_UI", "COMPLETED", 2, 2, 0, 0, 0, ts, ts, ts, ts),
                (41, "carga-41.xlsx", "VTEX", "SCR_UI", "PARTIAL", 2, 1, 0, 0, 1, ts, ts, ts, ts),
            ]
        elif "FROM dbo.product_loader_job_item" in sql and "WHERE product_loader_job_id IN" in sql:
            self.description = [
                ("product_loader_job_item_id",),
                ("product_loader_job_id",),
                ("row_number",),
                ("partnumber",),
                ("status",),
                ("last_error_code",),
                ("last_error_detail",),
                ("created_at",),
                ("updated_at",),
            ]
            ts = datetime(2026, 9, 10, 14, 31, tzinfo=timezone.utc)
            self._rows = [
                (102, 42, 3, " 83gw005fld ", "COMPLETED", None, None, ts, ts),
                (101, 42, 2, " 82yu00xylm ", "COMPLETED", None, None, ts, ts),
                (99, 41, 2, "OLD-PN", "FAILED", "SOURCE_NOT_FOUND", "No encontrado", ts, ts),
            ]
        else:
            raise AssertionError(f"unexpected SQL: {sql}")
        return self

    def fetchall(self):
        rows = list(self._rows)
        self._rows = []
        return rows


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_obj = cursor
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def close(self):
        self.closed = True


def test_list_jobs_returns_newest_jobs_with_exact_persisted_items():
    cursor = FakeCursor()
    conn = FakeConnection(cursor)
    repo = ProductLoaderRepository(lambda: conn)

    result = repo.list_jobs(limit=2)

    assert [job["job_id"] for job in result] == [42, 41]
    assert result[0]["source_name"] == "carga-42.xlsx"
    assert result[0]["items"] == [
        {
            "item_id": 101,
            "row_number": 2,
            "partnumber": "82YU00XYLM",
            "status": "COMPLETED",
            "last_error_code": None,
            "last_error_detail": None,
            "created_at": result[0]["items"][0]["created_at"],
            "updated_at": result[0]["items"][0]["updated_at"],
        },
        {
            "item_id": 102,
            "row_number": 3,
            "partnumber": "83GW005FLD",
            "status": "COMPLETED",
            "last_error_code": None,
            "last_error_detail": None,
            "created_at": result[0]["items"][1]["created_at"],
            "updated_at": result[0]["items"][1]["updated_at"],
        },
    ]
    assert result[1]["items"][0]["last_error_code"] == "SOURCE_NOT_FOUND"
    assert conn.closed is True


def test_list_jobs_clamps_limit_before_interpolating_top():
    cursor = FakeCursor()
    conn = FakeConnection(cursor)
    repo = ProductLoaderRepository(lambda: conn)

    repo.list_jobs(limit=999999)

    jobs_sql, jobs_params = cursor.executions[0]
    assert "TOP (500)" in jobs_sql
    assert jobs_params == ()
