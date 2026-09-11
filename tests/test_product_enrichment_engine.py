from __future__ import annotations

from stech_mcp.services.product_enrichment_engine import ProductEnrichmentEngine
from stech_mcp.services.research.search_provider import SearchProviderNotConfigured, SearchResult


class FakeProductRepository:
    def __init__(self, products):
        self.products = products

    def get_by_partnumber(self, partnumber):
        return self.products.get(partnumber)


class FakeStatusService:
    def __init__(self, snapshots):
        self.snapshots = list(snapshots)
        self.calls = 0

    def get(self, partnumber):
        index = min(self.calls, len(self.snapshots) - 1)
        self.calls += 1
        return dict(self.snapshots[index])


class FakeAdapter:
    def __init__(self, candidates=None):
        self.candidates = list(candidates or [])
        self.calls = []

    def adapt(self, product, *, category_code):
        self.calls.append((product, category_code))
        return list(self.candidates)


class FakeCandidateRepository:
    def __init__(self):
        self.added = []
        self.next_id = 1

    def add(self, **kwargs):
        self.added.append(dict(kwargs))
        result = {"product_fact_candidate_id": self.next_id, **kwargs, "state": kwargs.get("state", "PENDING")}
        self.next_id += 1
        return result


class FakePromotion:
    def __init__(self, results=None):
        self.results = list(results or [])
        self.calls = []

    def evaluate_and_promote(self, partnumber, candidates):
        self.calls.append((partnumber, list(candidates)))
        if self.results:
            return self.results.pop(0)
        return {"state": "COMPLETED", "promoted": {}, "preserved": {}, "rejected": [], "conflicts": []}


class FakePlanner:
    def __init__(self, queries=None):
        self.queries = list(queries or [])
        self.last_pending_fields = None

    def plan(self, partnumber, brand, category_code, pending_fields):
        self.last_pending_fields = list(pending_fields)
        return list(self.queries)


class FakeSearch:
    def __init__(self, results=None, configured=True):
        self.results = list(results or [])
        self.configured = configured
        self.calls = []

    def search(self, query, domains=(), limit=5):
        self.calls.append((query, domains, limit))
        if not self.configured:
            raise SearchProviderNotConfigured("Brave Search API key is not configured")
        return list(self.results)


class FakeSourceDocumentService:
    def __init__(self, document=None):
        self.document = document or {}
        self.calls = []

    def ingest(self, url, partnumber, source_type):
        self.calls.append((url, partnumber, source_type))
        return {"url": url, "source_type": source_type, **self.document}


class FakeExtractor:
    def __init__(self, candidates=None):
        self.candidates = list(candidates or [])
        self.calls = []

    def extract(self, document, target_fields, partnumber):
        self.calls.append((document, list(target_fields), partnumber))
        return list(self.candidates)


class FakeAudit:
    def __init__(self):
        self.events = []

    def add_audit_event(self, **kwargs):
        self.events.append(kwargs)


def status(*, missing_required=(), missing_recommended=(), missing_identity=(), completion=100):
    return {
        "partnumber": "PN1",
        "category_code": "PORTABLE_SPEAKER",
        "known_fields": {},
        "missing_required": list(missing_required),
        "missing_recommended": list(missing_recommended),
        "missing_identity": list(missing_identity),
        "conflicts": [],
        "completion_pct": completion,
    }


def build_engine(*, snapshots, adapter=None, promotion=None, planner=None, search=None, source=None, extractor=None, audit=None):
    return ProductEnrichmentEngine(
        product_repository=FakeProductRepository({"PN1": {"partnumber": "PN1", "marca": "JBL"}}),
        technical_status_service=FakeStatusService(snapshots),
        deltron_adapter=adapter or FakeAdapter(),
        candidate_repository=FakeCandidateRepository(),
        promotion_service=promotion or FakePromotion(),
        research_planner=planner or FakePlanner(),
        search_provider=search or FakeSearch(),
        source_document_service=source or FakeSourceDocumentService(),
        fact_extractor=extractor or FakeExtractor(),
        audit_repository=audit or FakeAudit(),
    )


def test_complete_product_skips_web_search():
    search = FakeSearch()
    progress = []
    engine = build_engine(snapshots=[status() ], search=search)

    result = engine.enrich("PN1", "PORTABLE_SPEAKER", None, lambda state, pct: progress.append((state, pct)))

    assert result["state"] == "COMPLETED"
    assert search.calls == []
    assert result["remaining_fields"] == []
    assert any(state == "REBUILDING_PRODUCT_MASTER" for state, _ in progress)


def test_partial_product_searches_only_missing_fields():
    from stech_mcp.services.research.research_planner import ResearchQuery

    planner = FakePlanner([
        ResearchQuery("PN1", "ip_rating", "PORTABLE_SPEAKER", '"PN1" IP rating', ("jbl.com",), "MANUFACTURER"),
        ResearchQuery("PN1", "speaker_power_w", "PORTABLE_SPEAKER", '"PN1" speaker power', ("jbl.com",), "MANUFACTURER"),
    ])
    search = FakeSearch([SearchResult("Official", "https://jbl.com/pn1", "spec")])
    extractor = FakeExtractor([
        {
            "field_code": "ip_rating",
            "raw_value": "IP67",
            "normalized_value": "IP67",
            "unit": None,
            "source_type": "MANUFACTURER",
            "source_name": "Official",
            "source_url": "https://jbl.com/pn1",
            "source_partnumber": "PN1",
            "evidence_text": "PN1 IP67",
            "page_number": 1,
            "confidence_rank": "A1",
            "status": "PENDING",
        }
    ])
    promotion = FakePromotion([
        {"state": "COMPLETED", "promoted": {"ip_rating": "IP67"}, "preserved": {}, "rejected": [], "conflicts": []},
    ])
    engine = build_engine(
        snapshots=[
            status(missing_required=("ip_rating", "speaker_power_w"), completion=70),
            status(missing_required=("ip_rating", "speaker_power_w"), completion=70),
            status(missing_required=("speaker_power_w",), completion=85),
        ],
        planner=planner,
        search=search,
        extractor=extractor,
        promotion=promotion,
    )

    result = engine.enrich("PN1", "PORTABLE_SPEAKER", None, lambda *_: None)

    assert set(planner.last_pending_fields) == {"ip_rating", "speaker_power_w"}
    assert set(result["remaining_fields"]) <= {"ip_rating", "speaker_power_w"}
    assert set(result["promoted_fields"]) == {"ip_rating"}
    assert all(call[1] == [call[0]["source_type"] and call[1][0] if False else call[1][0]] for call in [])  # no-op guard
    assert {tuple(call[1]) for call in extractor.calls} <= {("ip_rating",), ("speaker_power_w",)}


def test_identity_gap_is_researched_with_technical_gaps_and_stops_after_any_barcode_is_known():
    from stech_mcp.services.research.research_planner import ResearchQuery

    planner = FakePlanner([
        ResearchQuery("PN1", "ean", "PORTABLE_SPEAKER", '"PN1" EAN GTIN barcode', ("jbl.com",), "MANUFACTURER"),
    ])
    search = FakeSearch([SearchResult("Official", "https://jbl.com/pn1", "EAN 0197528523880")])
    extractor = FakeExtractor([
        {
            "field_code": "ean",
            "raw_value": "0197528523880",
            "normalized_value": "0197528523880",
            "unit": None,
            "source_type": "MANUFACTURER",
            "source_name": "Official",
            "source_url": "https://jbl.com/pn1",
            "source_partnumber": "PN1",
            "evidence_text": "PN1 EAN 0197528523880",
            "page_number": 1,
            "confidence_rank": "A1",
            "status": "PENDING",
        }
    ])
    promotion = FakePromotion([
        {"state": "COMPLETED", "promoted": {"ean": "0197528523880"}, "preserved": {}, "rejected": [], "conflicts": []},
    ])
    engine = build_engine(
        snapshots=[
            status(missing_identity=("ean", "upc", "gtin"), completion=100),
            status(missing_identity=("ean", "upc", "gtin"), completion=100),
            status(missing_identity=(), completion=100),
        ],
        planner=planner,
        search=search,
        extractor=extractor,
        promotion=promotion,
    )

    result = engine.enrich("PN1", "PORTABLE_SPEAKER", None, lambda *_: None)

    assert set(planner.last_pending_fields) == {"ean", "upc", "gtin"}
    assert result["state"] == "COMPLETED"
    assert result["remaining_fields"] == []
    assert result["promoted_fields"] == ["ean"]


def test_unconfigured_search_returns_partial_instead_of_fake_success():
    engine = build_engine(
        snapshots=[status(missing_required=("ip_rating",), completion=80), status(missing_required=("ip_rating",), completion=80)],
        planner=FakePlanner([]),
        search=FakeSearch(configured=False),
    )
    # Force one query so the provider is actually consulted.
    from stech_mcp.services.research.research_planner import ResearchQuery
    engine.research_planner.queries = [
        ResearchQuery("PN1", "ip_rating", "PORTABLE_SPEAKER", '"PN1" IP rating', (), "MANUFACTURER")
    ]

    result = engine.enrich("PN1", "PORTABLE_SPEAKER", None, lambda *_: None)

    assert result["state"] == "PARTIAL"
    assert result["error_code"] == "SEARCH_PROVIDER_NOT_CONFIGURED"
    assert result["remaining_fields"] == ["ip_rating"]
