from types import SimpleNamespace

from stech_mcp.services.source_document_service import SourceDocumentService


class FakeHttp:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def fetch(self, url):
        self.calls.append(url)
        return self.response


class FakeDocumentRepository:
    def __init__(self):
        self.by_sha = {}
        self.matches = []
        self.next_id = 1

    def upsert_by_hash(self, **kwargs):
        sha = kwargs["sha256"]
        if sha in self.by_sha:
            return self.by_sha[sha]
        result = {
            "source_document_id": self.next_id,
            "sha256": sha,
            "url": kwargs["url"],
            "document_type": kwargs["document_type"],
            "title": kwargs.get("title"),
            "content_type": kwargs.get("content_type"),
            "content_length": kwargs.get("content_length"),
            "extracted_text": kwargs.get("extracted_text"),
            "pages": kwargs.get("pages") or [],
        }
        self.next_id += 1
        self.by_sha[sha] = result
        return result

    def add_match(self, document_id, **kwargs):
        self.matches.append((document_id, kwargs))


class FakePage:
    def __init__(self, text):
        self._text = text

    def extract_text(self):
        return self._text


class FakePdf:
    pages = [
        FakePage("Cover page"),
        FakePage("PN1 Bluetooth 5.4 and IP67"),
    ]


def test_pdf_is_extracted_per_page_and_same_hash_reuses_document():
    http = FakeHttp(SimpleNamespace(
        content=b"%PDF-fake-same-content",
        content_type="application/pdf",
        final_url="https://brand.example/spec.pdf",
        content_length=22,
    ))
    repo = FakeDocumentRepository()
    service = SourceDocumentService(http_client=http, document_repository=repo, pdf_reader_factory=lambda stream: FakePdf())

    first = service.ingest("https://brand.example/spec.pdf", "PN1", "OFFICIAL_DOCUMENT")
    second = service.ingest("https://brand.example/spec-copy.pdf", "PN1", "OFFICIAL_DOCUMENT")

    assert first["sha256"] == second["sha256"]
    assert first["document_id"] == second["document_id"] == 1
    assert first["pages"][1]["text"] == "PN1 Bluetooth 5.4 and IP67"
    assert first["matched_pages"] == [2]
    assert repo.matches[0][1]["match_type"] == "EXACT_PN"
    assert repo.matches[0][1]["confidence"] == "A2"


def test_html_extraction_ignores_script_and_keeps_visible_exact_pn_text():
    html = b"""<html><head><title>PN2 Specs</title><script>bad secret PN2</script></head>
    <body><h1>Official PN2</h1><p>Bluetooth 5.3</p><style>.x{display:none}</style></body></html>"""
    http = FakeHttp(SimpleNamespace(
        content=html,
        content_type="text/html; charset=utf-8",
        final_url="https://brand.example/pn2",
        content_length=len(html),
    ))
    repo = FakeDocumentRepository()
    service = SourceDocumentService(http_client=http, document_repository=repo)

    result = service.ingest("https://brand.example/pn2", "PN2", "MANUFACTURER")

    assert "Official PN2" in result["text"]
    assert "Bluetooth 5.3" in result["text"]
    assert "bad secret" not in result["text"]
    assert "display:none" not in result["text"]
    assert result["matched_pages"] == [1]
    assert repo.matches[0][1]["confidence"] == "A1"
