from __future__ import annotations

from stech_mcp.db.fact_candidate_repository import FactCandidateRepository


class FakeDatabase:
    def __init__(self):
        self.rows = []
        self.next_id = 1

    def connect(self):
        return FakeConnection(self)


class FakeCursor:
    def __init__(self, db):
        self.db = db
        self.current = None
        self.description = []

    def execute(self, sql, *params):
        upper = " ".join(sql.upper().split())
        if upper.startswith("INSERT INTO DBO.PRODUCT_FACT_CANDIDATE"):
            candidate_id = self.db.next_id
            self.db.next_id += 1
            row = (candidate_id, *params)
            self.db.rows.append(row)
            self.current = (candidate_id,)
            self.description = [("product_fact_candidate_id",)]
        elif upper.startswith("SELECT PRODUCT_FACT_CANDIDATE_ID"):
            partnumber = params[0]
            selected = [row for row in self.db.rows if row[1] == partnumber]
            self.description = [
                ("product_fact_candidate_id",), ("partnumber",), ("field_code",),
                ("raw_value_text",), ("normalized_value_json",), ("unit",),
                ("source_type",), ("source_name",), ("source_url",),
                ("source_partnumber",), ("evidence_text",), ("page_number",),
                ("confidence_rank",), ("state",),
            ]
            self.current = selected
        else:
            raise AssertionError(f"unexpected SQL: {sql}")
        return self

    def fetchone(self):
        return self.current

    def fetchall(self):
        return self.current or []


class FakeConnection:
    def __init__(self, db):
        self.cursor_obj = FakeCursor(db)

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def test_candidates_keep_conflicting_evidence_instead_of_overwriting():
    db = FakeDatabase()
    repo = FactCandidateRepository(db.connect)

    repo.add(
        partnumber="PN1",
        field_code="bluetooth_version",
        raw_value="Bluetooth 5.4",
        normalized_value="5.4",
        source_type="MANUFACTURER",
        source_name="Brand",
        source_url="https://brand.example/pn1",
        source_partnumber="PN1",
        evidence_text="Bluetooth version 5.4",
        page_number=None,
        confidence_rank="A1",
    )
    repo.add(
        partnumber="PN1",
        field_code="bluetooth_version",
        raw_value="Bluetooth 5.3",
        normalized_value="5.3",
        source_type="AUTHORIZED_DISTRIBUTOR",
        source_name="Distributor",
        source_url="https://dist.example/pn1",
        source_partnumber="PN1",
        evidence_text="Bluetooth 5.3",
        page_number=None,
        confidence_rank="B",
    )

    rows = repo.list_for_product("PN1")
    assert len(rows) == 2
    assert {row["normalized_value"] for row in rows} == {"5.4", "5.3"}
    assert {row["confidence_rank"] for row in rows} == {"A1", "B"}
    assert all(row["state"] == "PENDING" for row in rows)


def test_candidate_normalizes_partnumber_field_and_serializes_structured_value():
    db = FakeDatabase()
    repo = FactCandidateRepository(db.connect)

    result = repo.add(
        partnumber=" pn1 ",
        field_code=" Dimensions_MM ",
        raw_value="100 x 80 x 50 mm",
        normalized_value=[100, 80, 50],
        unit="mm",
        source_type="OFFICIAL_DOCUMENT",
        source_name="Brand manual",
        source_url="https://brand.example/manual.pdf",
        source_partnumber="PN1",
        evidence_text="Dimensions 100 x 80 x 50 mm",
        page_number=4,
        confidence_rank="A2",
    )

    assert result["partnumber"] == "PN1"
    assert result["field_code"] == "dimensions_mm"
    row = repo.list_for_product("PN1")[0]
    assert row["normalized_value"] == [100, 80, 50]
    assert row["page_number"] == 4
