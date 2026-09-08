from stech_mcp.db.deltron_image_repository import DeltronImageRepository


_COLUMNS = [
    "imagen_id",
    "producto_distribuidor_id",
    "orden_imagen",
    "url_origen",
    "ruta_relativa",
    "ruta_actual",
    "nombre_archivo",
    "part_number_snapshot",
    "modelo_snapshot",
    "marca_snapshot",
    "ancho_px",
    "alto_px",
    "megapixeles",
    "tamano_bytes",
    "formato",
    "hash_sha256",
    "calidad",
    "estado_descarga",
    "estado_archivo",
    "ruta_papelera",
    "fecha_descarga",
    "fecha_verificacion",
    "fecha_eliminacion",
    "ultimo_error",
    "created_at",
    "updated_at",
    "categoria_snapshot",
    "subcategoria_snapshot",
]


class FakeCursor:
    def __init__(self):
        self.sql = None
        self.params = None
        self.description = [(name,) for name in _COLUMNS]

    def execute(self, sql, *params):
        self.sql = sql
        self.params = params
        return self

    def fetchall(self):
        return [
            (
                395,
                1343,
                8,
                "https://imagenes.deltron.com.pe/images/productos/carrusel/NBLEN82XQ00LYLM/x.jpg",
                r"LENOVO\COMPUTADORAS_NOTEBOOK\82XQ00LYLM\x.jpg",
                r"C:\STECH_IMAGENES\LENOVO\COMPUTADORAS_NOTEBOOK\82XQ00LYLM\x.jpg",
                "x.jpg",
                "82XQ00LYLM",
                "V15",
                "LENOVO",
                1200,
                1200,
                1.44,
                345678,
                "jpg",
                "a" * 64,
                "ALTA",
                "OK",
                "ACTIVO",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                "COMPUTADORAS",
                "NOTEBOOK",
            )
        ]


class FakeConnection:
    def __init__(self):
        self.cursor_obj = FakeCursor()
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def close(self):
        self.closed = True


def test_list_for_product_uses_real_table_and_parameterized_product_id():
    conn = FakeConnection()
    repo = DeltronImageRepository(lambda: conn)

    rows = repo.list_for_product(1343)

    assert "dbo.PRD_DELTRON_IMAGEN" in conn.cursor_obj.sql
    assert "producto_distribuidor_id = ?" in conn.cursor_obj.sql
    assert conn.cursor_obj.params == (1343,)
    assert "1343" not in conn.cursor_obj.sql
    assert rows[0]["imagen_id"] == 395
    assert rows[0]["part_number_snapshot"] == "82XQ00LYLM"
    assert rows[0]["url_origen"].startswith("https://imagenes.deltron.com.pe/")
    assert conn.closed is True


def test_list_for_product_orders_by_declared_image_order_then_id():
    conn = FakeConnection()
    repo = DeltronImageRepository(lambda: conn)

    repo.list_for_product(1343)

    normalized_sql = " ".join(conn.cursor_obj.sql.split()).lower()
    assert "order by orden_imagen asc, imagen_id asc" in normalized_sql
