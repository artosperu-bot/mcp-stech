from stech_mcp.db.product_repository import ProductRepository


class Cursor:
    def __init__(self):
        self.description = [("part_number",), ("stock_total",)]
        self.executions = []

    def execute(self, sql, *params):
        self.executions.append((sql, params))
        return self

    def fetchall(self):
        return [("PN2", 3), ("PN3", 0)]


class Conn:
    def __init__(self):
        self.cur = Cursor()

    def cursor(self):
        return self.cur

    def close(self):
        pass


def test_list_for_scan_uses_stable_partnumber_cursor():
    conn = Conn()
    repo = ProductRepository(lambda: conn)
    rows = repo.list_for_scan(after_partnumber="PN1", limit=25)
    assert [row["partnumber"] for row in rows] == ["PN2", "PN3"]
    sql, params = conn.cur.executions[0]
    assert "part_number > ?" in sql
    assert "ORDER BY part_number" in sql
    assert params == ("PN1",)
