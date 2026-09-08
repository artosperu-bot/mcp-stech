from __future__ import annotations

from stech_mcp.db.source_document_repository import SourceDocumentRepository


class FakeDatabase:
    def __init__(self):
        self.documents = {}
        self.matches = []
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
        if upper.startswith("SELECT SOURCE_DOCUMENT_ID") and "WHERE SHA256" in upper:
            sha = params[0]
            self.description = [
                ("source_document_id",), ("sha256",), ("url",), ("document_type",),
                ("title",), ("content_type",), ("content_length",), ("extracted_text",),
                ("page_text_json",), ("downloaded_at",),
            ]
            self.current = self.db.documents.get(sha)
        elif upper.startswith("INSERT INTO DBO.SOURCE_DOCUMENT"):
            sha, url, document_type, title, content_type, content_length, extracted_text, page_text_json = params
            doc_id = self.db.next_id
            self.db.next_id += 1
            row = (doc_id, sha, url, document_type, title, content_type, content_length, extracted_text, page_text_json, None)
            self.db.documents[sha] = row
            self.current = (doc_id,)
            self.description = [("source_document_id",)]
        elif upper.startswith("MERGE DBO.SOURCE_DOCUMENT_MATCH"):
            self.db.matches.append(params)
            self.current = None
        else:
            raise AssertionError(f"unexpected SQL: {sql}")
        return self

    def fetchone(self):
        return self.current


class FakeConnection:
    def __init__(self, db):
        self.db = db
        self.cursor_obj = FakeCursor(db)
        self.commits = 0
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        self.closed = True


def test_same_sha_reuses_document_even_when_url_changes():
    db = FakeDatabase()
    repo = SourceDocumentRepository(db.connect)

    first = repo.upsert_by_hash(sha256="abc", url="https://example/a.pdf", document_type="PDF")
    second = repo.upsert_by_hash(sha256="abc", url="https://example/copy.pdf", document_type="PDF")

    assert first["source_document_id"] == second["source_document_id"] == 1
    assert len(db.documents) == 1
    assert second["url"] == "https://example/a.pdf"


def test_document_match_persists_exact_product_pages_and_confidence():
    db = FakeDatabase()
    repo = SourceDocumentRepository(db.connect)
    document = repo.upsert_by_hash(sha256="abc", url="https://example/spec.pdf", document_type="PDF")

    repo.add_match(
        document["source_document_id"],
        partnumber="PN1",
        match_type="EXACT_PN",
        pages=[1, 3],
        confidence="A2",
    )

    assert len(db.matches) == 1
    params = db.matches[0]
    assert params[0] == 1
    assert params[1] == "PN1"
    assert params[2] == "EXACT_PN"
    assert params[3] == "[1,3]"
    assert params[4] == "A2"
