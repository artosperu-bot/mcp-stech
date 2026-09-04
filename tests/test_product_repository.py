from stech_mcp.db.product_repository import ProductRepository


class FakeCursor:
    def __init__(self):
        self.sql = None
        self.params = None
        self.description = [("partnumber",), ("marca",), ("nombre",)]

    def execute(self, sql, *params):
        self.sql = sql
        self.params = params
        return self

    def fetchone(self):
        return ("82YU00XYLM", "LENOVO", "Lenovo V15 G4 AMN")


class FakeConnection:
    def __init__(self):
        self.cursor_obj = FakeCursor()

    def cursor(self):
        return self.cursor_obj


def test_product_get_uses_parameter_not_sql_concatenation():
    conn = FakeConnection()
    repo = ProductRepository(lambda: conn, view_name="dbo.V_MCP_PRODUCTO")
    result = repo.get_by_partnumber("82YU00XYLM'; DROP TABLE X;--")

    assert "?" in conn.cursor_obj.sql
    assert "DROP TABLE" not in conn.cursor_obj.sql
    assert conn.cursor_obj.params == ("82YU00XYLM'; DROP TABLE X;--",)
    assert result["marca"] == "LENOVO"


def test_rejects_unsafe_view_name():
    try:
        ProductRepository(lambda: FakeConnection(), view_name="dbo.V_MCP_PRODUCTO; DROP TABLE X")
    except ValueError as exc:
        assert "unsafe view name" in str(exc).lower()
    else:
        raise AssertionError("unsafe view name should be rejected")
