from stech_mcp.db.enrichment_repository import EnrichmentRepository


class FakeCursor:
    def __init__(self, rows=None, one=None):
        self.rows = rows or []
        self.one = one
        self.description = [
            ("enrichment_id",),
            ("partnumber",),
            ("field_code",),
            ("value_text",),
            ("value_number",),
            ("unit",),
            ("method",),
            ("confidence_grade",),
            ("is_approved",),
            ("created_at",),
            ("updated_at",),
        ]
        self.last_sql = ""
        self.last_params = ()
        self.executions = []

    def execute(self, sql, *params):
        self.last_sql = sql
        self.last_params = params
        self.executions.append((sql, params))
        return self

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.one


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_obj = cursor
        self.closed = False
        self.committed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


def test_get_approved_filters_by_partnumber_and_approved_only():
    rows = [
        (1, "82YU00XYLM", "package_weight_g", None, 2180, "g", "VERIFIED", "A1", True, None, None),
    ]
    cursor = FakeCursor(rows=rows)
    conn = FakeConnection(cursor)
    repo = EnrichmentRepository(lambda: conn)

    result = repo.get_approved("82YU00XYLM")

    assert result[0]["partnumber"] == "82YU00XYLM"
    assert result[0]["is_approved"] is True
    assert "partnumber = ?" in cursor.last_sql
    assert "is_approved = 1" in cursor.last_sql
    assert "82YU00XYLM" not in cursor.last_sql
    assert cursor.last_params == ("82YU00XYLM",)
    assert conn.closed is True


def test_get_approved_field_filter_uses_only_placeholders():
    cursor = FakeCursor(rows=[])
    conn = FakeConnection(cursor)
    repo = EnrichmentRepository(lambda: conn)

    repo.get_approved("82YU00XYLM", ["package_width_cm", "package_weight_g"])

    assert "field_code IN (?,?)" in cursor.last_sql
    assert "package_width_cm" not in cursor.last_sql
    assert cursor.last_params == ("82YU00XYLM", "package_width_cm", "package_weight_g")


def test_upsert_uses_parameters_not_interpolated_sql():
    cursor = FakeCursor(one=(10,))
    conn = FakeConnection(cursor)
    repo = EnrichmentRepository(lambda: conn)

    result = repo.upsert(
        partnumber="82YU00XYLM",
        field_code="package_weight_g",
        value_number=2180,
        unit="g",
        method="VERIFIED",
        confidence_grade="A1",
        is_approved=True,
    )

    sql = "\n".join(statement for statement, _ in cursor.executions)
    assert "82YU00XYLM" not in sql
    assert cursor.executions[0][1][0] == "82YU00XYLM"
    assert result["enrichment_id"] == 10
    assert conn.committed is True
    assert conn.closed is True


def test_upsert_preserves_approved_manual_value_by_default():
    cursor = FakeCursor(one=(7, "MANUAL", True))
    conn = FakeConnection(cursor)
    repo = EnrichmentRepository(lambda: conn)

    result = repo.upsert(
        partnumber="82YU00XYLM",
        field_code="package_weight_g",
        value_number=2500,
        unit="g",
        method="ESTIMATED",
        confidence_grade="E",
        is_approved=False,
    )

    assert result["enrichment_id"] == 7
    assert result["preserved_manual"] is True
    assert len(cursor.executions) == 1
    assert conn.committed is False
    assert conn.closed is True


def test_add_evidence_inserts_with_parameters():
    cursor = FakeCursor(one=(99,))
    conn = FakeConnection(cursor)
    repo = EnrichmentRepository(lambda: conn)

    result = repo.add_evidence(
        enrichment_id=10,
        source_url="https://psref.lenovo.com/example",
        source_domain="psref.lenovo.com",
        source_type="OFFICIAL_DOCUMENT",
        source_partnumber="82YU00XYLM",
        evidence_text="Package weight 2.18 kg",
        rank_score=100,
    )

    assert "psref.lenovo.com" not in cursor.last_sql
    assert cursor.last_params[0] == 10
    assert result["evidence_id"] == 99
    assert conn.committed is True
    assert conn.closed is True
