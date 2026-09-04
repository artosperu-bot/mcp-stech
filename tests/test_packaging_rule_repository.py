from decimal import Decimal

from stech_mcp.db.packaging_rule_repository import PackagingRuleRepository


class FakeCursor:
    def __init__(self, row):
        self.row = row
        self.sql = ""
        self.params = ()
        self.description = [
            ("rule_code",),
            ("category_code",),
            ("screen_min_inches",),
            ("screen_max_inches",),
            ("width_cm",),
            ("length_cm",),
            ("height_cm",),
            ("weight_g",),
            ("priority",),
            ("enabled",),
            ("source_code",),
        ]

    def execute(self, sql, *params):
        self.sql = sql
        self.params = params
        return self

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, row):
        self.cursor_obj = FakeCursor(row)
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def close(self):
        self.closed = True


def test_15_6_matches_approved_laptop_rule():
    row = (
        "LAPTOP_15_X_DEFAULT", "LAPTOP", Decimal("15.00"), Decimal("16.00"),
        Decimal("33.00"), Decimal("54.00"), Decimal("7.00"), 2500, 100, True,
        "REGLA_STECH_EMPAQUE",
    )
    conn = FakeConnection(row)
    repo = PackagingRuleRepository(lambda: conn)

    rule = repo.match("LAPTOP", Decimal("15.6"))

    assert rule["rule_code"] == "LAPTOP_15_X_DEFAULT"
    assert rule["width_cm"] == Decimal("33.00")
    assert rule["length_cm"] == Decimal("54.00")
    assert rule["height_cm"] == Decimal("7.00")
    assert rule["weight_g"] == 2500
    assert "category_code = ?" in conn.cursor_obj.sql
    assert "? >= screen_min_inches" in conn.cursor_obj.sql
    assert "? < screen_max_inches" in conn.cursor_obj.sql
    assert conn.cursor_obj.params == ("LAPTOP", Decimal("15.6"), Decimal("15.6"))
    assert conn.closed is True


def test_16_0_does_not_match_15_x_rule():
    conn = FakeConnection(None)
    repo = PackagingRuleRepository(lambda: conn)

    assert repo.match("LAPTOP", Decimal("16.0")) is None
    assert conn.cursor_obj.params == ("LAPTOP", Decimal("16.0"), Decimal("16.0"))
    assert conn.closed is True
