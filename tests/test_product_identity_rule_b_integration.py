from stech_mcp.services.product_identity_research import ProductIdentityResearchService
from stech_mcp.services.research.search_provider import SearchResult


VALID_UPC = "740617352214"


class Products:
    def get_by_partnumber(self, pn):
        return {"part_number": "PN1", "marca": "LENOVO", "ean": None, "upc": None} if pn == "PN1" else None


class Enrichments:
    def get_approved(self, pn, field_codes=None):
        return []


class Search:
    def __init__(self):
        self.calls = []

    def search(self, query, domains=(), limit=5):
        domains = tuple(domains)
        self.calls.append((query, domains, limit))
        if "deltron.com.pe" in domains:
            return [SearchResult("Deltron PN1", "https://www.deltron.com.pe/pn1", "PN1 UPC")]
        return []


class RetailSearch:
    def __init__(self):
        self.calls = []

    def search(self, query, domains=(), limit=5):
        domains = tuple(domains)
        self.calls.append((query, domains, limit))
        if "ripley.com.pe" in domains:
            return [SearchResult("Ripley PN1", "https://simple.ripley.com.pe/pn1", "PN1 UPC")]
        return []


class Sources:
    def ingest(self, url, partnumber, source_type):
        confidence = {
            "AUTHORIZED_DISTRIBUTOR": "B",
            "TRUSTED_RETAILER": "C",
        }.get(source_type, "A1")
        return {
            "url": url,
            "source_type": source_type,
            "confidence_rank": confidence,
            "title": "Source",
            "pages": [{"page": 1, "text": f"PN1 UPC: {VALID_UPC}"}],
        }


class Extractor:
    def extract(self, doc, fields, pn):
        return [{
            "field_code": "upc",
            "raw_value": VALID_UPC,
            "normalized_value": VALID_UPC,
            "canonical_gtin": VALID_UPC.zfill(14),
            "unit": None,
            "source_type": doc["source_type"],
            "source_name": "Source",
            "source_url": doc["url"],
            "source_partnumber": pn,
            "evidence_text": f"PN1 UPC: {VALID_UPC}",
            "page_number": 1,
            "confidence_rank": doc["confidence_rank"],
            "status": "PENDING",
        }]


class Candidates:
    def __init__(self):
        self.rows = []

    def add(self, **row):
        saved = {"product_fact_candidate_id": len(self.rows) + 1, **row}
        self.rows.append(saved)
        return saved


class PromotionMustNotRun:
    def evaluate_and_promote(self, pn, candidates):
        raise AssertionError("non-consensus candidate must not reach FactPromotionService")


class Audit:
    def add_audit_event(self, **kwargs):
        pass


def build(search_provider):
    candidates = Candidates()
    service = ProductIdentityResearchService(
        product_repository=Products(),
        enrichment_repository=Enrichments(),
        candidate_repository=candidates,
        promotion_service=PromotionMustNotRun(),
        search_provider=search_provider,
        source_document_service=Sources(),
        fact_extractor=Extractor(),
        audit_repository=Audit(),
    )
    return service, candidates


def test_single_authorized_distributor_stays_candidate_and_exposes_code_without_promotion():
    service, candidates = build(Search())

    result = service.research("PN1")

    assert result["state"] == "PARTIAL"
    assert result["decision"] == "CANDIDATE"
    assert result["candidate_fields"] == {"upc": [VALID_UPC]}
    assert result["verified_fields"] == {}
    assert candidates.rows


def test_trusted_retailer_result_is_retained_as_candidate_but_never_promoted():
    search = RetailSearch()
    service, candidates = build(search)

    result = service.research("PN1")

    assert result["state"] == "PARTIAL"
    assert result["decision"] == "CANDIDATE"
    assert result["candidate_fields"] == {"upc": [VALID_UPC]}
    assert result["verified_fields"] == {}
    assert any(row["source_type"] == "TRUSTED_RETAILER" for row in candidates.rows)
    assert any("ripley.com.pe" in domains for _, domains, _ in search.calls)
