from stech_mcp.db.deltron_specification_repository import DeltronSpecificationRepository


_COLUMNS = [
    "especificacion_id",
    "producto_distribuidor_id",
    "seccion",
    "atributo_original",
    "valor_original",
    "atributo_normalizado",
    "valor_normalizado",
    "unidad",
    "orden",
    "estado_validacion",
    "observacion",
    "fuente_id",
    "fecha_captura",
    "seccion_normalizada",
    "orden_seccion",
    "orden_atributo",
    "estado_normalizacion",
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
                633,
                1162,
                "MEMORIA",
                "CAPACIDAD",
                "16 GB",
                "CAPACIDAD",
                16,
                "GB",
                8,
                "POR_VALIDAR",
                None,
                None,
                "2026-09-02 14:41:01",
                "MEMORIA",
                6,
                1,
                "NORMALIZADO_EXPLICITO",
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


def test_list_for_product_reads_structured_deltron_specification_table():
    conn = FakeConnection()
    repo = DeltronSpecificationRepository(lambda: conn)

    rows = repo.list_for_product(1162)

    normalized_sql = " ".join(conn.cursor_obj.sql.split()).lower()
    assert "dbo.prd_deltron_especificacion" in normalized_sql
    assert "producto_distribuidor_id = ?" in normalized_sql
    assert conn.cursor_obj.params == (1162,)
    assert "1162" not in conn.cursor_obj.sql
    assert "order by orden_seccion, orden_atributo, orden, especificacion_id" in normalized_sql
    assert rows[0]["seccion"] == "MEMORIA"
    assert rows[0]["atributo_original"] == "CAPACIDAD"
    assert rows[0]["valor_original"] == "16 GB"
    assert rows[0]["valor_normalizado"] == 16
    assert rows[0]["unidad"] == "GB"
    assert conn.closed is True
