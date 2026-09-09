from stech_mcp.tools.product_research import register_product_research_tools


class FakeMcp:
    def tool(self):
        def decorator(func):
            return func
        return decorator


class FakeStatus:
    def get(self, partnumber):
        return {
            "partnumber": partnumber,
            "category_code": "PORTABLE_SPEAKER",
            "missing_required": ["ip_rating"],
            "missing_recommended": ["speaker_power_w"],
        }


class FakeProducts:
    def get_by_partnumber(self, partnumber):
        return {"part_number": partnumber, "marca": "JBL"}


class FakePlanner:
    def plan(self, partnumber, brand, category_code, pending_fields):
        return [
            type("Q", (), {
                "partnumber": partnumber,
                "field_code": field,
                "category_code": category_code,
                "query": f'"{partnumber}" {field}',
                "domains": ("jbl.com",),
                "stage": "MANUFACTURER",
            })()
            for field in pending_fields
        ]


class FakeDocuments:
    def ingest(self, url, partnumber, source_type):
        return {
            "document_id": 1,
            "url": url,
            "source_type": source_type,
            "confidence_rank": "A1",
            "pages": [{"page": 1, "text": f"{partnumber} IP67"}],
        }


class FakeExtractor:
    def extract(self, document, target_fields, partnumber):
        del document
        return [
            {
                "field_code": target_fields[0],
                "raw_value": "IP67",
                "normalized_value": "IP67",
                "unit": None,
                "source_type": "MANUFACTURER",
                "source_name": "Official",
                "source_url": "https://jbl.com/pn1",
                "source_partnumber": partnumber,
                "evidence_text": f"{partnumber} IP67",
                "page_number": 1,
                "confidence_rank": "A1",
            }
        ]


class FakeCandidates:
    def __init__(self):
        self.rows = []

    def add(self, **kwargs):
        row = {"product_fact_candidate_id": len(self.rows) + 1, **kwargs}
        self.rows.append(row)
        return row

    def list_for_product(self, partnumber):
        return [row for row in self.rows if row["partnumber"] == partnumber]


class FakePromotion:
    def __init__(self):
        self.calls = []

    def evaluate_and_promote(self, partnumber, candidates):
        self.calls.append((partnumber, list(candidates)))
        return {"state": "COMPLETED", "promoted": {candidates[0]["field_code"]: candidates[0]["normalized_value"]}, "conflicts": [], "rejected": [], "preserved": {}}


class FakeReadiness:
    def get(self, partnumber):
        return {"partnumber": partnumber, "channels": {"VTEX": {"completion_pct": 80}}}


def build_tools():
    promotion = FakePromotion()
    candidates = FakeCandidates()
    tools = register_product_research_tools(
        FakeMcp(),
        product_repository=FakeProducts(),
        technical_status_service=FakeStatus(),
        research_planner=FakePlanner(),
        source_document_service=FakeDocuments(),
        fact_extractor=FakeExtractor(),
        candidate_repository=candidates,
        promotion_service=promotion,
        multichannel_readiness_service=FakeReadiness(),
    )
    return tools, candidates, promotion


def test_research_audit_tools_registered():
    tools, _, _ = build_tools()
    required = {
        "product_technical_missing_list",
        "product_research_plan",
        "product_source_ingest",
        "product_fact_candidates",
        "product_fact_promote",
        "product_fact_promote_batch",
        "product_channel_readiness",
    }
    assert required <= set(tools)


def test_source_ingest_creates_candidate_then_promotion_uses_service():
    tools, candidates, promotion = build_tools()

    ingested = tools["product_source_ingest"](
        "PN1",
        "https://jbl.com/pn1",
        "MANUFACTURER",
        ["ip_rating"],
    )
    promoted = tools["product_fact_promote"]("PN1", ["ip_rating"])

    assert ingested["candidate_count"] == 1
    assert candidates.rows[0]["state"] == "PENDING"
    assert promoted["promoted"]["ip_rating"] == "IP67"
    assert len(promotion.calls) == 1
