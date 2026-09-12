from types import SimpleNamespace

import pytest

from stech_mcp.chatgpt_bridge.contracts import ResearchRequestV1, ResearchResultV1, TechnicalCandidateV1
from stech_mcp.chatgpt_bridge.importer import BridgeResultImporter
from stech_mcp.services.handlers.enrich_technical import EnrichTechnicalHandler


class CategorylessEngine:
    def enrich(self, partnumber, category_code, requested_fields, progress):
        raise LookupError(f"technical category not found: {partnumber}")


class FakeWorkRepository:
    def __init__(self):
        self.transitions = []

    def transition_item(self, item_id, **kwargs):
        self.transitions.append((item_id, kwargs))
        return {"item_id": item_id, **kwargs}


class FakeFactRepository:
    def __init__(self):
        self.rows = []

    def list_for_product(self, partnumber):
        return list(self.rows)

    def add(self, **kwargs):
        self.rows.append(dict(kwargs))
        return dict(kwargs)


class FakeImageRepository:
    def add_candidate(self, **kwargs):
        return kwargs


class EmptySchemaRepository:
    def get_category_schema(self, category_code):
        return []


def test_categoryless_manual_pn_with_requested_fields_hands_off_to_external_research():
    handler = EnrichTechnicalHandler(CategorylessEngine(), external_research_enabled=True)
    item = {
        "partnumber": "DUAL-RTX5060-O8G",
        "work_type": "ENRICH_TECHNICAL",
        "input": {
            "requested_fields": ["Memoria gráfica", "Tipo de memoria"],
            "scope": "TEMPLATE_SMART_COMPLETE",
        },
    }

    out = handler(item, lambda *_args: None)

    assert out["status"] == "WAITING_EXTERNAL_RESEARCH"
    assert out["error_code"] == "EXTERNAL_RESEARCH_REQUIRED"


def test_bridge_accepts_requested_fields_as_whitelist_when_category_schema_is_unknown():
    facts = FakeFactRepository()
    work = FakeWorkRepository()
    importer = BridgeResultImporter(
        image_candidate_repository=FakeImageRepository(),
        fact_candidate_repository=facts,
        work_repository=work,
        schema_repository=EmptySchemaRepository(),
    )
    request = ResearchRequestV1(
        request_id="rw_123456_abcdef",
        created_at="2026-09-12T20:00:00Z",
        product_work_item_id=123456,
        product_work_job_id=654321,
        work_type="ENRICH_TECHNICAL",
        partnumber="DUAL-RTX5060-O8G",
        category_code=None,
        requested_fields=["Memoria gráfica", "Tipo de memoria"],
    )
    result = ResearchResultV1(
        request_id=request.request_id,
        partnumber=request.partnumber,
        work_type=request.work_type,
        researched_at="2026-09-12T21:00:00Z",
        status="EVIDENCE_FOUND",
        technical_candidates=[
            TechnicalCandidateV1(
                field_name="Memoria gráfica",
                value="8 GB",
                page_url="https://example.com/product",
                source_domain="example.com",
                source_type="OFFICIAL",
                exact_partnumber_match=True,
                evidence_text="Exact PN technical specification",
            )
        ],
    )

    out = importer.import_result(request, result)

    assert out["status"] == "REVIEW_REQUIRED"
    assert out["imported"] == 1
    assert facts.rows[0]["field_code"] == "memoria_grafica"


def test_bridge_rejects_unsolicited_field_when_only_requested_fields_define_scope():
    facts = FakeFactRepository()
    importer = BridgeResultImporter(
        image_candidate_repository=FakeImageRepository(),
        fact_candidate_repository=facts,
        work_repository=FakeWorkRepository(),
        schema_repository=EmptySchemaRepository(),
    )
    request = ResearchRequestV1(
        request_id="rw_223456_abcdef",
        created_at="2026-09-12T20:00:00Z",
        product_work_item_id=223456,
        product_work_job_id=754321,
        work_type="ENRICH_TECHNICAL",
        partnumber="DUAL-RTX5060-O8G",
        category_code=None,
        requested_fields=["Memoria gráfica"],
    )
    result = ResearchResultV1(
        request_id=request.request_id,
        partnumber=request.partnumber,
        work_type=request.work_type,
        researched_at="2026-09-12T21:00:00Z",
        status="EVIDENCE_FOUND",
        technical_candidates=[
            TechnicalCandidateV1(
                field_name="Color",
                value="Negro",
                page_url="https://example.com/product",
                source_domain="example.com",
                source_type="OFFICIAL",
                exact_partnumber_match=True,
                evidence_text="Exact PN",
            )
        ],
    )

    with pytest.raises(ValueError, match="outside requested technical fields"):
        importer.import_result(request, result)
