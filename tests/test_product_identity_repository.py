from stech_mcp.db.product_identity_repository import ProductIdentityRepository


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.description = [
            ("producto_distribuidor_id",),
            ("distribuidor_codigo",),
            ("codigo_externo",),
            ("part_number",),
            ("ean",),
            ("upc",),
            ("mini_codigo",),
            ("marca",),
            ("nombre",),
            ("identity_status",),
            ("identity_confidence",),
            ("identity_source",),
        ]
        self.calls = []
        self.rowcount = 0

    def execute(self, sql, *params):
        self.calls.append((sql, params))
        if sql.lstrip().upper().startswith("UPDATE"):
            self.rowcount = 2
        return self

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, rows):
        self.cursor_obj = FakeCursor(rows)
        self.commits = 0
        self.rollbacks = 0
        self.closed = 0

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed += 1


def test_list_missing_identifiers_is_keyset_paginated_and_uses_operational_table():
    rows = [
        (11, "DELTRON", "A", "PN1", None, None, "M1", "LENOVO", "P1", None, None, None),
        (12, "DELTRON", "B", "PN2", None, "036000291452", "M2", "LENOVO", "P2", None, None, None),
        (13, "DELTRON", "C", "PN3", None, None, "M3", "LENOVO", "P3", None, None, None),
    ]
    connection = FakeConnection(rows)
    repo = ProductIdentityRepository(lambda: connection)

    result = repo.list_missing_identifiers(after_id=10, limit=2, distributor="deltron")

    assert [row["producto_distribuidor_id"] for row in result["products"]] == [11, 12]
    assert result["has_more"] is True
    assert result["next_after_id"] == 12
    sql, params = connection.cursor_obj.calls[0]
    upper = sql.upper()
    assert "PRD_PRODUCTO_DISTRIBUIDOR" in upper
    assert "HST_PRODUCTO_OBSERVACION" not in upper
    assert "PRODUCTO_DISTRIBUIDOR_ID > ?" in upper
    assert params == (10, "DELTRON")


def test_promote_missing_identifier_updates_only_identity_columns():
    connection = FakeConnection([])
    repo = ProductIdentityRepository(lambda: connection)

    changed = repo.promote_missing_identifier(
        partnumber="EP-T2510NBEGWW",
        target_field="ean",
        value="8806094899528",
        confidence=80,
        source="STECH_MCP_VERIFIED:EAN:123",
    )

    assert changed == 2
    sql, params = connection.cursor_obj.calls[0]
    upper = sql.upper()
    assert "UPDATE DBO.PRD_PRODUCTO_DISTRIBUIDOR" in upper
    assert "EAN = ?" in upper
    assert "STOCK" not in upper
    assert "HST_" not in upper
    assert "WHERE PART_NUMBER = ?" in upper
    assert params[-1] == "EP-T2510NBEGWW"
    assert connection.commits == 1
