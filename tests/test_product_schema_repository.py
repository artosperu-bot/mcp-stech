from __future__ import annotations

from stech_mcp.db.product_schema_repository import ProductSchemaRepository


class FakeCursor:
    def __init__(self, rows):
        self.rows = list(rows)
        self.executions = []
        self.description = [
            ("category_code",),
            ("field_code",),
            ("requirement",),
            ("ordinal",),
            ("value_type",),
            ("unit",),
            ("variant_sensitive",),
            ("reuse_policy",),
        ]

    def execute(self, sql, *params):
        self.executions.append((sql, params))
        return self

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_obj = cursor
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def close(self):
        self.closed = True


def test_repository_returns_fields_in_ordinal_order_and_normalizes_category():
    cursor = FakeCursor([
        ("PORTABLE_SPEAKER", "speaker_power_w", "REQUIRED", 10, "NUMBER", "W", True, "EXACT_PN_ONLY"),
        ("PORTABLE_SPEAKER", "bluetooth_version", "REQUIRED", 20, "TEXT", None, False, "EXACT_PN_ONLY"),
        ("PORTABLE_SPEAKER", "box_contents", "RECOMMENDED", 90, "TEXT", None, False, "EXACT_PN_ONLY"),
    ])
    connection = FakeConnection(cursor)
    repo = ProductSchemaRepository(lambda: connection)

    schema = repo.get_category_schema(" portable speaker ")

    assert [item.field_code for item in schema] == [
        "speaker_power_w",
        "bluetooth_version",
        "box_contents",
    ]
    assert [item.field_code for item in schema if item.requirement == "REQUIRED"] == [
        "speaker_power_w",
        "bluetooth_version",
    ]
    assert cursor.executions[0][1] == ("PORTABLE_SPEAKER",)
    assert "ORDER BY ca.ordinal" in cursor.executions[0][0]
    assert connection.closed is True


def test_repository_returns_empty_list_for_category_without_schema():
    cursor = FakeCursor([])
    connection = FakeConnection(cursor)
    repo = ProductSchemaRepository(lambda: connection)

    assert repo.get_category_schema("UNKNOWN") == []
    assert connection.closed is True
