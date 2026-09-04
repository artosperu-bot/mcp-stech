from stech_mcp.db.product_repository import ProductRepository


class FakeCursor:
    def __init__(self, *, many=False):
        self.sql = None
        self.params = None
        self.description = [
            ("producto_distribuidor_id",),
            ("part_number",),
            ("marca",),
            ("nombre",),
            ("stock_valor",),
            ("precio_usd_sin_igv",),
        ]
        self.many = many

    def execute(self, sql, *params):
        self.sql = sql
        self.params = params
        return self

    def fetchone(self):
        return (101, "82YU00XYLM", "LENOVO", "Lenovo V15 G4 AMN", 7, 420.50)

    def fetchall(self):
        if not self.many:
            return []
        return [
            (101, "82YU00XYLM", "LENOVO", "Lenovo V15 G4 AMN", 7, 420.50),
            (102, "82XQ00N6LM", "LENOVO", "Lenovo IdeaPad", 3, 510.00),
        ]


class FakeConnection:
    def __init__(self, *, many=False):
        self.cursor_obj = FakeCursor(many=many)
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def close(self):
        self.closed = True


def test_product_get_uses_real_v8_part_number_column_and_parameters():
    conn = FakeConnection()
    repo = ProductRepository(lambda: conn, view_name="dbo.V_PRD_PRODUCTO_ACTUAL")
    result = repo.get_by_partnumber("82YU00XYLM'; DROP TABLE X;--")

    assert "part_number = ?" in conn.cursor_obj.sql
    assert "DROP TABLE" not in conn.cursor_obj.sql
    assert conn.cursor_obj.params == ("82YU00XYLM'; DROP TABLE X;--",)
    assert result["marca"] == "LENOVO"
    assert result["partnumber"] == "82YU00XYLM"
    assert result["part_number"] == "82YU00XYLM"
    assert conn.closed is True


def test_product_search_uses_v8_identifiers_and_limit():
    conn = FakeConnection(many=True)
    repo = ProductRepository(lambda: conn, view_name="dbo.V_PRD_PRODUCTO_ACTUAL")

    rows = repo.search("82YU", limit=20)

    assert "part_number LIKE ?" in conn.cursor_obj.sql
    assert "ean LIKE ?" in conn.cursor_obj.sql
    assert "upc LIKE ?" in conn.cursor_obj.sql
    assert "mini_codigo LIKE ?" in conn.cursor_obj.sql
    assert "codigo_externo LIKE ?" in conn.cursor_obj.sql
    assert "nombre LIKE ?" in conn.cursor_obj.sql
    assert "TOP (20)" in conn.cursor_obj.sql
    assert rows[0]["partnumber"] == "82YU00XYLM"
    assert len(rows) == 2
    assert conn.closed is True


def test_rejects_unsafe_view_name():
    try:
        ProductRepository(lambda: FakeConnection(), view_name="dbo.V_PRD_PRODUCTO_ACTUAL; DROP TABLE X")
    except ValueError as exc:
        assert "unsafe view name" in str(exc).lower()
    else:
        raise AssertionError("unsafe view name should be rejected")
