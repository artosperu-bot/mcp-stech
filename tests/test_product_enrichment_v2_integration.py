from __future__ import annotations

import copy

import pytest

from stech_mcp.domain.product_schema import CategoryAttribute
from stech_mcp.http.source_client import SourceResponse
from stech_mcp.services.deltron_fact_adapter import DeltronFactAdapter
from stech_mcp.services.fact_extractor import FactExtractor
from stech_mcp.services.fact_promotion import FactPromotionService
from stech_mcp.services.product_enrichment_engine import ProductEnrichmentEngine
from stech_mcp.services.product_field_verification import ProductFieldVerificationService
from stech_mcp.services.product_technical_status import ProductTechnicalStatusService
from stech_mcp.services.research.research_planner import ResearchPlanner
from stech_mcp.services.research.search_provider import SearchResult
from stech_mcp.services.source_document_service import SourceDocumentService


class MemoryProductRepository:
    def __init__(self, products):
        self.products = products

    def get_by_partnumber(self, partnumber):
        return self.products.get(partnumber)


class MemorySchemaRepository:
    def __init__(self, schemas):
        self.schemas = schemas

    def get_category_schema(self, category_code):
        return list(self.schemas.get(category_code, ()))


class MemoryEnrichmentRepository:
    def __init__(self):
        self.rows = {}
        self.evidence = []
        self.next_id = 1

    def get_approved(self, partnumber, field_codes=None):
        rows = [row for (pn, _), row in self.rows.items() if pn == partnumber and row["is_approved"]]
        if field_codes:
            wanted = set(field_codes)
            rows = [row for row in rows if row["field_code"] in wanted]
        return [dict(row) for row in rows]

    def upsert(self, *, partnumber, field_code, value_text=None, value_number=None, unit=None, method, confidence_grade, is_approved=False, allow_manual_override=False):
        key = (partnumber, field_code)
        existing = self.rows.get(key)
        if existing and existing["method"] == "MANUAL" and existing["is_approved"] and not allow_manual_override:
            return {"enrichment_id": existing["enrichment_id"], "partnumber": partnumber, "field_code": field_code, "preserved_manual": True}
        enrichment_id = existing["enrichment_id"] if existing else self.next_id
        if existing is None:
            self.next_id += 1
        self.rows[key] = {
            "enrichment_id": enrichment_id,
            "partnumber": partnumber,
            "field_code": field_code,
            "value_text": value_text,
            "value_number": value_number,
            "unit": unit,
            "method": method,
            "confidence_grade": confidence_grade,
            "is_approved": bool(is_approved),
        }
        return {"enrichment_id": enrichment_id, "partnumber": partnumber, "field_code": field_code, "preserved_manual": False}

    def add_evidence(self, **kwargs):
        row = {"evidence_id": len(self.evidence) + 1, **kwargs}
        self.evidence.append(row)
        return row


class MemoryCandidateRepository:
    def __init__(self):
        self.rows = []

    def add(self, **kwargs):
        row = {"product_fact_candidate_id": len(self.rows) + 1, **kwargs}
        self.rows.append(row)
        return dict(row)

    def update_state(self, candidate_id, state):
        for row in self.rows:
            if row["product_fact_candidate_id"] == candidate_id:
                row["state"] = state
                return
        raise LookupError(candidate_id)

    def list_for_product(self, partnumber):
        return [dict(row) for row in self.rows if row["partnumber"] == partnumber]


class MemoryDocumentRepository:
    def __init__(self):
        self.by_hash = {}
        self.matches = []
        self.next_id = 1

    def upsert_by_hash(self, *, sha256, url, document_type, title=None, content_type=None, content_length=None, extracted_text=None, pages=None):
        if sha256 in self.by_hash:
            return dict(self.by_hash[sha256])
        row = {
            "source_document_id": self.next_id,
            "sha256": sha256,
            "url": url,
            "document_type": document_type,
            "title": title,
            "content_type": content_type,
            "content_length": content_length,
            "extracted_text": extracted_text,
            "pages": list(pages or []),
        }
        self.next_id += 1
        self.by_hash[sha256] = row
        return dict(row)

    def add_match(self, document_id, *, partnumber, match_type, pages, confidence):
        self.matches.append({
            "document_id": document_id,
            "partnumber": partnumber,
            "match_type": match_type,
            "pages": list(pages or []),
            "confidence": confidence,
        })


class FakeHttp:
    def __init__(self, content_by_url):
        self.content_by_url = content_by_url
        self.calls = []

    def fetch(self, url):
        self.calls.append(url)
        content = self.content_by_url[url].encode("utf-8")
        return SourceResponse(
            content=content,
            content_type="text/html; charset=utf-8",
            final_url=url,
            content_length=len(content),
        )


class FakeSearch:
    def __init__(self, urls_by_partnumber):
        self.urls_by_partnumber = urls_by_partnumber
        self.calls = []

    def search(self, query, domains=(), limit=5):
        self.calls.append({"query": query, "domains": tuple(domains), "limit": limit})
        for partnumber, urls in self.urls_by_partnumber.items():
            if partnumber in query:
                return [SearchResult(title="Official", url=url, description="official specifications") for url in urls]
        return []


class Audit:
    def __init__(self):
        self.events = []

    def add_audit_event(self, **kwargs):
        self.events.append(kwargs)


def schema(category, field_code, value_type="TEXT", *, variant_sensitive=False):
    return CategoryAttribute(
        category_code=category,
        field_code=field_code,
        requirement="REQUIRED",
        ordinal=1,
        value_type=value_type,
        unit=None,
        variant_sensitive=variant_sensitive,
        reuse_policy="EXACT_PN_ONLY" if variant_sensitive else "SAME_CHASSIS_ALLOWED",
    )


def build_engine(product, category_schema, source_texts, urls):
    product_repository = MemoryProductRepository({product["part_number"]: product})
    enrichment_repository = MemoryEnrichmentRepository()
    schema_repository = MemorySchemaRepository({product["category_code"]: [category_schema]})
    technical_status = ProductTechnicalStatusService(
        product_repository=product_repository,
        enrichment_repository=enrichment_repository,
        schema_repository=schema_repository,
    )
    candidates = MemoryCandidateRepository()
    verification = ProductFieldVerificationService(enrichment_repository)
    promotion = FactPromotionService(
        verification_service=verification,
        enrichment_repository=enrichment_repository,
        candidate_repository=candidates,
    )
    documents = MemoryDocumentRepository()
    http = FakeHttp(source_texts)
    source_service = SourceDocumentService(document_repository=documents, http_client=http)
    search = FakeSearch({product["part_number"]: urls})
    audit = Audit()
    engine = ProductEnrichmentEngine(
        product_repository=product_repository,
        technical_status_service=technical_status,
        deltron_adapter=DeltronFactAdapter(),
        candidate_repository=candidates,
        promotion_service=promotion,
        research_planner=ResearchPlanner(),
        search_provider=search,
        source_document_service=source_service,
        fact_extractor=FactExtractor(),
        audit_repository=audit,
    )
    return engine, technical_status, enrichment_repository, candidates, documents, search, audit


@pytest.mark.parametrize(
    "product,category_schema,url,text,expected",
    [
        (
            {"part_number": "LAP-1", "category_code": "LAPTOP", "marca": "LENOVO", "nombre": "Laptop", "precio_usd_sin_igv": 499.0, "stock_valor": 7},
            schema("LAPTOP", "ram_gb", "NUMBER", variant_sensitive=True),
            "https://lenovo.example/lap-1",
            "<html><body>LAP-1 RAM: 16 GB</body></html>",
            16.0,
        ),
        (
            {"part_number": "SPK-1", "category_code": "PORTABLE_SPEAKER", "marca": "JBL", "nombre": "Parlante", "precio_usd_sin_igv": 99.0, "stock_valor": 12},
            schema("PORTABLE_SPEAKER", "ip_rating"),
            "https://jbl.example/spk-1",
            "<html><body>SPK-1 protection IP67</body></html>",
            "IP67",
        ),
        (
            {"part_number": "HP-1", "category_code": "HEADPHONES", "marca": "LOGITECH", "nombre": "Audifono", "precio_usd_sin_igv": 75.0, "stock_valor": 5},
            schema("HEADPHONES", "driver_size_mm", "NUMBER"),
            "https://logitech.example/hp-1",
            "<html><body>HP-1 driver: 40 mm</body></html>",
            40.0,
        ),
    ],
)
def test_three_categories_research_only_missing_fields_and_preserve_price_stock(product, category_schema, url, text, expected):
    original = copy.deepcopy(product)
    engine, technical, enrichments, candidates, _, search, audit = build_engine(
        product,
        category_schema,
        {url: text},
        [url],
    )

    result = engine.enrich(product["part_number"], product["category_code"], None, lambda *_: None)

    assert result["state"] == "COMPLETED"
    assert result["remaining_fields"] == []
    assert result["promoted_fields"] == [category_schema.field_code]
    assert technical.get(product["part_number"])["completion_pct"] == 100
    assert enrichments.get_approved(product["part_number"])[0]["field_code"] == category_schema.field_code
    assert candidates.rows[0]["state"] == "PROMOTED"
    assert all(category_schema.field_code.replace("_", " ").split()[0].lower() in call["query"].lower() or category_schema.field_code in call["query"] for call in search.calls)
    assert product["precio_usd_sin_igv"] == original["precio_usd_sin_igv"]
    assert product["stock_valor"] == original["stock_valor"]
    assert audit.events[-1]["event_type"] == "TECHNICAL_ENRICHMENT_V2"


def test_wrong_partnumber_cannot_promote_variant_sensitive_fact():
    product = {"part_number": "LAP-EXACT", "category_code": "LAPTOP", "marca": "LENOVO", "nombre": "Laptop", "precio_usd_sin_igv": 700.0, "stock_valor": 2}
    field = schema("LAPTOP", "ram_gb", "NUMBER", variant_sensitive=True)
    url = "https://lenovo.example/wrong"
    engine, technical, enrichments, candidates, _, _, _ = build_engine(
        product,
        field,
        {url: "<html><body>OTHER-PN RAM: 32 GB</body></html>"},
        [url],
    )

    result = engine.enrich("LAP-EXACT", "LAPTOP", None, lambda *_: None)

    assert result["state"] == "PARTIAL"
    assert technical.get("LAP-EXACT")["completion_pct"] == 0
    assert enrichments.get_approved("LAP-EXACT") == []
    assert candidates.rows[0]["state"] == "REJECTED"


def test_equal_strength_conflicting_sources_are_preserved_for_review():
    product = {"part_number": "SPK-CONFLICT", "category_code": "PORTABLE_SPEAKER", "marca": "JBL", "nombre": "Parlante", "precio_usd_sin_igv": 120.0, "stock_valor": 4}
    field = schema("PORTABLE_SPEAKER", "ip_rating")
    urls = ["https://jbl.example/a", "https://jbl.example/b"]
    engine, _, _, candidates, _, _, _ = build_engine(
        product,
        field,
        {
            urls[0]: "<html><body>SPK-CONFLICT IP67</body></html>",
            urls[1]: "<html><body>SPK-CONFLICT IP68</body></html>",
        },
        urls,
    )

    result = engine.enrich("SPK-CONFLICT", "PORTABLE_SPEAKER", None, lambda *_: None)

    assert result["state"] == "REVIEW_REQUIRED"
    assert result["conflicts"][0]["field_code"] == "ip_rating"
    assert {row["state"] for row in candidates.rows} == {"CONFLICT"}


def test_same_document_bytes_are_reused_by_sha_across_urls():
    repository = MemoryDocumentRepository()
    content = "<html><body>PN-CACHE IP67</body></html>"
    http = FakeHttp({
        "https://brand.example/a": content,
        "https://brand.example/copy": content,
    })
    service = SourceDocumentService(document_repository=repository, http_client=http)

    first = service.ingest("https://brand.example/a", "PN-CACHE", "MANUFACTURER")
    second = service.ingest("https://brand.example/copy", "PN-CACHE", "MANUFACTURER")

    assert first["sha256"] == second["sha256"]
    assert first["document_id"] == second["document_id"]
    assert len(repository.by_hash) == 1
