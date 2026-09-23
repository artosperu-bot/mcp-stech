from __future__ import annotations

import json

from stech_mcp.db.product_loader_repository import ProductLoaderRepository
from stech_mcp.domain.product_loader_models import (
    ITEM_STATES,
    JOB_STATES,
    TERMINAL_ITEM_STATES,
    normalize_partnumber,
)


class FakeCursor:
    def __init__(self, fetchone_values=None, fetchall_values=None):
        self.fetchone_values = list(fetchone_values or [])
        self.fetchall_values = list(fetchall_values or [])
        self.description = []
        self.executions = []
        self.rowcount = 1

    def execute(self, sql, *params):
        self.executions.append((sql, params))
        if "FROM dbo.product_loader_job\n" in sql and "WHERE product_loader_job_id = ?" in sql:
            self.description = [
                ("product_loader_job_id",), ("source_name",), ("channel",),
                ("actor_source",), ("status",), ("total_items",),
            ]
        elif "FROM dbo.product_loader_job_item" in sql and "ORDER BY row_number" in sql:
            self.description = [
                ("product_loader_job_item_id",), ("product_loader_job_id",),
                ("row_number",), ("partnumber",), ("input_json",), ("status",),
            ]
        elif "FROM dbo.product_loader_job_event" in sql:
            self.description = [
                ("product_loader_job_event_id",), ("product_loader_job_id",),
                ("product_loader_job_item_id",), ("event_type",), ("status",),
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


def test_product_loader_state_contract_and_partnumber_normalization():
    assert normalize_partnumber(" 82yu00xylm ") == "82YU00XYLM"
    assert "RUNNING" in JOB_STATES
    assert "VTEX_CREATE_SKU" in ITEM_STATES
    assert {"COMPLETED", "RESEARCH_REQUIRED", "REVIEW_REQUIRED", "BLOCKED", "FAILED"} <= TERMINAL_ITEM_STATES


def test_create_job_is_parameterized_and_normalizes_rows():
    cursor = FakeCursor(fetchone_values=[(41,), (101,), (102,)])
    conn = FakeConnection(cursor)
    repo = ProductLoaderRepository(lambda: conn)

    result = repo.create_job(
        source_name="carga.xlsx",
        rows=[
            {"row_number": 2, "partnumber": " 82yu00xylm ", "brand": "Lenovo"},
            {"row_number": 3, "partnumber": "83GW005FLD", "brand": "Lenovo"},
        ],
        actor_source="SCR_UI",
        channel="VTEX",
    )

    assert result["job_id"] == 41
    assert result["status"] == "PENDING"
    assert result["total_items"] == 2
    assert [item["partnumber"] for item in result["items"]] == ["82YU00XYLM", "83GW005FLD"]
    assert [item["item_id"] for item in result["items"]] == [101, 102]

    sql_text = "\n".join(sql for sql, _ in cursor.executions)
    assert "82YU00XYLM" not in sql_text
    assert "83GW005FLD" not in sql_text
    assert any("INSERT dbo.product_loader_job (" in sql for sql, _ in cursor.executions)
    item_calls = [(sql, params) for sql, params in cursor.executions if "INSERT dbo.product_loader_job_item (" in sql]
    assert len(item_calls) == 2
    assert item_calls[0][1][1] == 2
    assert item_calls[0][1][2] == "82YU00XYLM"
    assert json.loads(item_calls[0][1][3])["brand"] == "Lenovo"
    assert conn.committed is True
    assert conn.closed is True


def test_create_job_rejects_duplicate_excel_row_numbers_before_writing():
    cursor = FakeCursor()
    conn = FakeConnection(cursor)
    repo = ProductLoaderRepository(lambda: conn)

    try:
        repo.create_job(
            source_name="carga.xlsx",
            rows=[
                {"row_number": 2, "partnumber": "A"},
                {"row_number": 2, "partnumber": "B"},
            ],
            actor_source="SCR_UI",
            channel="VTEX",
        )
    except ValueError as exc:
        assert "row_number" in str(exc)
    else:
        raise AssertionError("duplicate row_number must fail")

    assert cursor.executions == []


def test_get_job_decodes_input_json_and_returns_items_events_and_summary():
    cursor = FakeCursor(
        fetchone_values=[(41, "carga.xlsx", "VTEX", "SCR_UI", "PARTIAL", 2)],
        fetchall_values=[
            [
                (101, 41, 2, "82YU00XYLM", '{"brand":"Lenovo"}', "COMPLETED"),
                (102, 41, 3, "83GW005FLD", '{"brand":"Lenovo"}', "FAILED"),
            ],
            [
                (9001, 41, 101, "ITEM_COMPLETED", "COMPLETED"),
                (9002, 41, 102, "ITEM_FAILED", "FAILED"),
            ],
        ],
    )
    conn = FakeConnection(cursor)
    repo = ProductLoaderRepository(lambda: conn)

    result = repo.get_job(41)

    assert result is not None
    assert result["job_id"] == 41
    assert result["items"][0]["input"]["brand"] == "Lenovo"
    assert result["summary"] == {
        "total": 2,
        "completed": 1,
        "research_required": 0,
        "review_required": 0,
        "blocked": 0,
        "failed": 1,
    }
    assert len(result["events"]) == 2
    assert conn.closed is True
