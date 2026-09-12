from __future__ import annotations

from datetime import datetime, timezone
from importlib import import_module, util

import pytest
from pydantic import ValidationError


def contracts_module():
    spec = util.find_spec("stech_mcp.chatgpt_bridge.contracts")
    assert spec is not None, "ChatGPT bridge contracts module must exist"
    module = import_module("stech_mcp.chatgpt_bridge.contracts")
    assert hasattr(module, "ResearchRequestV1")
    assert hasattr(module, "ResearchResultV1")
    return module


def valid_request_payload():
    return {
        "schema_version": 1,
        "request_id": "rw_1234_a1b2c3d4e5f6",
        "created_at": datetime(2026, 9, 11, 22, 30, tzinfo=timezone.utc),
        "product_work_item_id": 1234,
        "product_work_job_id": 140,
        "work_type": "RESEARCH_IMAGES",
        "partnumber": " 910-006862 ",
        "brand": "LOGITECH",
        "model": None,
        "category_code": None,
        "requested_fields": ["images"],
        "research_policy": {
            "exact_partnumber_required": True,
            "prefer_official_sources": True,
            "max_sources": 5,
            "max_candidates": 10,
        },
    }


def valid_result_payload():
    return {
        "schema_version": 1,
        "request_id": "rw_1234_a1b2c3d4e5f6",
        "partnumber": "910-006862",
        "work_type": "RESEARCH_IMAGES",
        "researched_at": datetime(2026, 9, 11, 22, 40, tzinfo=timezone.utc),
        "status": "EVIDENCE_FOUND",
        "sources": [
            {
                "page_url": "https://www.logitech.com/product/910-006862",
                "source_domain": "logitech.com",
                "source_type": "OFFICIAL",
                "title": "Logitech product page",
                "exact_partnumber_match": True,
            }
        ],
        "image_candidates": [
            {
                "image_url": "https://resource.logitech.com/image.jpg",
                "page_url": "https://www.logitech.com/product/910-006862",
                "title": "910-006862 product image",
                "width": 1200,
                "height": 1200,
                "exact_partnumber_match": True,
            }
        ],
        "identity_candidates": [],
        "technical_candidates": [],
        "notes": "",
    }


def test_request_normalizes_partnumber_and_keeps_safe_research_context():
    module = contracts_module()
    request = module.ResearchRequestV1.model_validate(valid_request_payload())
    assert request.partnumber == "910-006862"
    assert request.work_type == "RESEARCH_IMAGES"
    assert request.research_policy.max_candidates == 10


def test_result_accepts_verifiable_image_evidence():
    module = contracts_module()
    result = module.ResearchResultV1.model_validate(valid_result_payload())
    assert result.status == "EVIDENCE_FOUND"
    assert len(result.image_candidates) == 1
    assert result.image_candidates[0].exact_partnumber_match is True


@pytest.mark.parametrize(
    "field,value",
    [
        ("price", 199.90),
        ("stock", 7),
        ("cost", 100),
        ("promotion", "SALE"),
        ("publication", True),
        ("category", "commercial-category"),
        ("vtex_state", "ACTIVE"),
    ],
)
def test_result_rejects_commercial_fields(field, value):
    module = contracts_module()
    payload = valid_result_payload()
    payload[field] = value
    with pytest.raises(ValidationError):
        module.ResearchResultV1.model_validate(payload)


def test_result_rejects_more_than_ten_image_candidates():
    module = contracts_module()
    payload = valid_result_payload()
    payload["image_candidates"] = payload["image_candidates"] * 11
    with pytest.raises(ValidationError):
        module.ResearchResultV1.model_validate(payload)


def test_contract_rejects_invalid_request_id_and_unknown_result_status():
    module = contracts_module()
    request = valid_request_payload()
    request["request_id"] = "../../bad"
    with pytest.raises(ValidationError):
        module.ResearchRequestV1.model_validate(request)

    result = valid_result_payload()
    result["status"] = "MADE_UP"
    with pytest.raises(ValidationError):
        module.ResearchResultV1.model_validate(result)


def test_result_rejects_non_http_evidence_urls():
    module = contracts_module()
    payload = valid_result_payload()
    payload["image_candidates"][0]["image_url"] = "file:///C:/secret.jpg"
    with pytest.raises(ValidationError):
        module.ResearchResultV1.model_validate(payload)
