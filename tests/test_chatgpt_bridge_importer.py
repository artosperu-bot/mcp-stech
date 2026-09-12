from __future__ import annotations

from datetime import datetime, timezone

import pytest

from stech_mcp.chatgpt_bridge.contracts import ResearchRequestV1, ResearchResultV1
from stech_mcp.chatgpt_bridge.importer import BridgeResultImporter


class ImageRepo:
    def __init__(self):
        self.rows = []

    def add_candidate(self, **kwargs):
        key = (kwargs["partnumber"], kwargs["source_url"])
        for row in self.rows:
            if (row["partnumber"], row["source_url"]) == key:
                return row
        row = {"product_image_candidate_id": len(self.rows) + 1, "state": "PENDING", **kwargs}
        self.rows.append(row)
        return row


class FactRepo:
    def __init__(self):
        self.rows = []

    def list_for_product(self, partnumber):
        return [row for row in self.rows if row["partnumber"] == partnumber]

    def add(self, **kwargs):
        row = {"product_fact_candidate_id": len(self.rows) + 1, "state": "PENDING", **kwargs}
        self.rows.append(row)
        return row


class WorkRepo:
    def __init__(self):
        self.transitions = []
        self.retries = []

    def transition_item(self, item_id, **kwargs):
        self.transitions.append((item_id, kwargs))
        return {"item_id": item_id, **kwargs}

    def schedule_retry(self, item_id, **kwargs):
        self.retries.append((item_id, kwargs))
        return {"item_id": item_id, "status": "FAILED_RETRYABLE", **kwargs}


class SchemaField:
    def __init__(self, field_code):
        self.field_code = field_code


class SchemaRepo:
    def get_category_schema(self, category_code):
        if category_code == "LAPTOP":
            return [SchemaField("ram_gb"), SchemaField("storage_gb")]
        return []


def request(work_type="RESEARCH_IMAGES", category_code=None):
    fields = {
        "RESEARCH_IMAGES": ["images"],
        "RESEARCH_IDENTITY": ["ean", "upc", "gtin"],
        "ENRICH_TECHNICAL": ["ram_gb"],
    }[work_type]
    return ResearchRequestV1.model_validate(
        {
            "request_id": "rw_1234_a1b2c3d4e5f6",
            "created_at": datetime(2026, 9, 11, 22, 30, tzinfo=timezone.utc),
            "product_work_item_id": 1234,
            "product_work_job_id": 140,
            "work_type": work_type,
            "partnumber": "PN1",
            "brand": "BRAND",
            "category_code": category_code,
            "requested_fields": fields,
            "research_policy": {},
        }
    )


def result(work_type="RESEARCH_IMAGES", status="EVIDENCE_FOUND", **overrides):
    payload = {
        "request_id": "rw_1234_a1b2c3d4e5f6",
        "partnumber": "PN1",
        "work_type": work_type,
        "researched_at": datetime(2026, 9, 11, 22, 40, tzinfo=timezone.utc),
        "status": status,
        "sources": [],
        "image_candidates": [],
        "identity_candidates": [],
        "technical_candidates": [],
        "notes": "",
    }
    payload.update(overrides)
    return ResearchResultV1.model_validate(payload)


def importer():
    image_repo = ImageRepo()
    fact_repo = FactRepo()
    work_repo = WorkRepo()
    service = BridgeResultImporter(
        image_candidate_repository=image_repo,
        fact_candidate_repository=fact_repo,
        work_repository=work_repo,
        schema_repository=SchemaRepo(),
    )
    return service, image_repo, fact_repo, work_repo


def test_rejects_result_that_does_not_match_request_identity():
    service, image_repo, fact_repo, work_repo = importer()
    bad = result().model_copy(update={"partnumber": "OTHER"})
    with pytest.raises(ValueError, match="partnumber"):
        service.import_result(request(), bad)
    assert image_repo.rows == []
    assert work_repo.transitions == []


def test_imports_image_candidate_and_moves_item_to_review_required():
    service, image_repo, _, work_repo = importer()
    response = result(
        image_candidates=[
            {
                "image_url": "https://brand.example/pn1.jpg",
                "page_url": "https://brand.example/pn1",
                "title": "PN1 image",
                "width": 1200,
                "height": 1200,
                "exact_partnumber_match": True,
            }
        ]
    )

    outcome = service.import_result(request(), response)

    assert outcome["status"] == "REVIEW_REQUIRED"
    assert len(image_repo.rows) == 1
    assert image_repo.rows[0]["source_type"] == "CHATGPT_WEB_IMAGE"
    assert image_repo.rows[0]["partnumber_match"] == "EXACT"
    assert work_repo.transitions[-1][1]["status"] == "REVIEW_REQUIRED"


def test_importing_same_image_result_twice_does_not_duplicate_candidate():
    service, image_repo, _, _ = importer()
    response = result(
        image_candidates=[
            {
                "image_url": "https://brand.example/pn1.jpg",
                "page_url": "https://brand.example/pn1",
                "exact_partnumber_match": True,
            }
        ]
    )
    service.import_result(request(), response)
    service.import_result(request(), response)
    assert len(image_repo.rows) == 1


def test_no_verified_evidence_is_terminal_only_after_real_external_result():
    service, _, _, work_repo = importer()
    outcome = service.import_result(request(), result(status="NO_VERIFIED_EVIDENCE"))
    assert outcome["status"] == "NO_DATA_FOUND"
    assert work_repo.transitions[-1][1]["status"] == "NO_DATA_FOUND"


def test_temporary_external_error_schedules_retry_instead_of_no_data():
    service, _, _, work_repo = importer()
    outcome = service.import_result(request(), result(status="TEMPORARY_RESEARCH_ERROR"))
    assert outcome["status"] == "FAILED_RETRYABLE"
    assert len(work_repo.retries) == 1
    assert work_repo.transitions == []


def test_identity_import_revalidates_checksum_before_persisting():
    service, _, fact_repo, work_repo = importer()
    valid = result(
        work_type="RESEARCH_IDENTITY",
        identity_candidates=[
            {
                "identifier_type": "UPC",
                "value": "740617352214",
                "label": "UPC",
                "page_url": "https://brand.example/pn1",
                "source_domain": "brand.example",
                "source_type": "OFFICIAL",
                "exact_partnumber_match": True,
                "evidence_text": "PN1 UPC 740617352214",
            }
        ],
    )
    outcome = service.import_result(request("RESEARCH_IDENTITY"), valid)
    assert len(fact_repo.rows) == 1
    assert fact_repo.rows[0]["field_code"] == "upc"
    assert outcome["status"] == "REVIEW_REQUIRED"
    assert work_repo.transitions[-1][1]["status"] == "REVIEW_REQUIRED"

    invalid = valid.model_copy(
        update={
            "identity_candidates": [
                valid.identity_candidates[0].model_copy(update={"value": "740617352215"})
            ]
        }
    )
    with pytest.raises(ValueError, match="checksum"):
        service.import_result(request("RESEARCH_IDENTITY"), invalid)
    assert len(fact_repo.rows) == 1


def test_technical_import_rejects_field_outside_resolved_schema():
    service, _, fact_repo, _ = importer()
    response = result(
        work_type="ENRICH_TECHNICAL",
        technical_candidates=[
            {
                "field_name": "price",
                "value": 999,
                "page_url": "https://brand.example/pn1",
                "source_domain": "brand.example",
                "source_type": "OFFICIAL",
                "exact_partnumber_match": True,
                "evidence_text": "price 999",
            }
        ],
    )
    with pytest.raises(ValueError, match="schema"):
        service.import_result(request("ENRICH_TECHNICAL", category_code="LAPTOP"), response)
    assert fact_repo.rows == []
