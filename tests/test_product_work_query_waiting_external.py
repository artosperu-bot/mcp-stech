from __future__ import annotations

import json

from stech_mcp.db.product_work_query_repository import ProductWorkQueryRepository


class Cursor:
    description = [
        ("item_id",), ("job_id",), ("work_type",), ("partnumber",),
        ("category_code",), ("channel_code",), ("context_hash",),
        ("input_json",), ("status",), ("created_at",),
    ]

    def __init__(self):
        self.sql = ""

    def execute(self, sql, *params):
        self.sql = sql
        return self

    def fetchall(self):
        return [(
            1234, 140, "RESEARCH_IMAGES", "910-006862", None, None,
            "a1b2c3d4e5f67890", json.dumps({"requested_fields": ["images"]}),
            "WAITING_EXTERNAL_RESEARCH", None,
        )]


class Connection:
    def __init__(self):
        self.cursor_value = Cursor()

    def cursor(self):
        return self.cursor_value

    def close(self):
        pass


def test_list_waiting_external_filters_waiting_state_and_decodes_input_json():
    connection = Connection()
    repo = ProductWorkQueryRepository(lambda: connection)

    rows = repo.list_waiting_external(limit=10)

    assert "WAITING_EXTERNAL_RESEARCH" in connection.cursor_value.sql
    assert "TOP (10)" in connection.cursor_value.sql
    assert rows[0]["item_id"] == 1234
    assert rows[0]["input"] == {"requested_fields": ["images"]}
