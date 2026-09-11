from stech_mcp.db.product_image_candidate_repository import ProductImageCandidateRepository


class Cursor:
    def __init__(self):
        self.executions = []
        self.description = []
        self._fetchone = None
        self._fetchall = []

    def execute(self, sql, *params):
        self.executions.append((sql, params))
        upper = sql.upper()
        if "OUTPUT INSERTED.PRODUCT_IMAGE_CANDIDATE_ID" in upper:
            self._fetchone = (7,)
        elif "FROM DBO.PRODUCT_IMAGE_CANDIDATE" in upper and "WHERE PRODUCT_IMAGE_CANDIDATE_ID = ?" in upper:
            self.description = [("product_image_candidate_id",), ("partnumber",), ("state",), ("source_url",)]
            self._fetchone = (7, "ABC-123", "PENDING", "https://example.com/a.jpg")
        elif "FROM DBO.PRODUCT_IMAGE_CANDIDATE" in upper:
            self.description = [("product_image_candidate_id",), ("partnumber",), ("state",), ("source_url",)]
            self._fetchall = [(7, "ABC-123", "PENDING", "https://example.com/a.jpg")]
        return self

    def fetchone(self):
        return self._fetchone

    def fetchall(self):
        return self._fetchall


class Conn:
    def __init__(self):
        self.cur = Cursor()
        self.commits = 0
        self.rollbacks = 0
        self.closed = 0

    def cursor(self):
        return self.cur

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed += 1


def test_add_candidate_normalizes_partnumber_and_parameterizes_values():
    conn = Conn()
    repo = ProductImageCandidateRepository(lambda: conn)
    row = repo.add_candidate(
        partnumber=" abc-123 ",
        source_type="OFFICIAL",
        source_url="https://example.com/a.jpg",
        source_domain="example.com",
        title="ABC-123 front",
        partnumber_match="EXACT",
        variant_match="UNKNOWN",
        confidence_score=95,
        evidence={"query": "ABC-123"},
    )
    assert row["partnumber"] == "ABC-123"
    insert = [item for item in conn.cur.executions if "INSERT DBO.PRODUCT_IMAGE_CANDIDATE" in item[0].upper()][0]
    assert "?" in insert[0]
    assert "https://example.com/a.jpg" not in insert[0]
    assert "ABC-123" in insert[1]
    assert conn.commits == 1


def test_list_and_state_validation():
    conn = Conn()
    repo = ProductImageCandidateRepository(lambda: conn)
    rows = repo.list_for_product(" abc-123 ")
    assert rows[0]["partnumber"] == "ABC-123"

    try:
        repo.set_state(7, "NOT_A_STATE")
    except ValueError as exc:
        assert "invalid candidate state" in str(exc)
    else:
        raise AssertionError("expected ValueError")