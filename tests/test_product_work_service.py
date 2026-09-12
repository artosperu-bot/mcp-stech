from __future__ import annotations

import pytest

from stech_mcp.services.product_work_service import ProductWorkService


class FakeRepository:
    def __init__(self):
        self.created = None

    def create_job(self, **kwargs):
        self.created = kwargs
        return {
            "job_id": 77,
            "status": "PENDING",
            "total_items": len(kwargs["items"]),
            "items": kwargs["items"],
        }


def test_create_enrichment_job_dedupes_and_strips_commercial_fields():
    repo = FakeRepository()
    service = ProductWorkService(repo, max_attempts=4)

    result = service.create_job(
        rows=[
            {
                "partnumber": " pn1 ",
                "category_code": "laptop",
                "row_number": 3,
                "price": 99,
                "stock": 8,
                "cost": 70,
                "promotion_start": "2026-09-01",
                "source_context": {"template": "X"},
            },
            {"partnumber": "PN1", "stock": 2},
        ],
        work_type="ENRICH_TECHNICAL",
        source_name="PRODUCT_WORKBENCH",
        actor_source="SCR_UI",
        priority=50,
    )

    assert result["total_items"] == 1
    assert repo.created["max_attempts"] == 4
    item = repo.created["items"][0]
    assert item["partnumber"] == "PN1"
    assert item["category_code"] == "LAPTOP"
    assert item["row_number"] == 3
    assert "price" not in item
    assert "stock" not in item
    assert "cost" not in item
    assert "promotion_start" not in item


def test_create_identity_job_keeps_only_selected_unique_batch_and_safe_identity_context():
    repo = FakeRepository()
    service = ProductWorkService(repo)

    result = service.create_job(
        rows=[
            {
                "partnumber": " pn1 ",
                "requested_fields": ["ean", "upc", "gtin"],
                "price": 99,
                "stock": 8,
                "cost": 70,
                "promotion_start": "2026-09-01",
                "category_code": "LAPTOP",
            },
            {"partnumber": "PN1", "stock": 2},
            {"partnumber": "pn2", "requested_fields": ["ean", "upc", "gtin"], "publish": True},
        ],
        work_type="RESEARCH_IDENTITY",
        source_name="V8_SELECTED_IDENTITY",
        actor_source="SCR_UI",
        priority=70,
    )

    assert result["total_items"] == 2
    assert repo.created["work_type"] == "RESEARCH_IDENTITY"
    assert [item["partnumber"] for item in repo.created["items"]] == ["PN1", "PN2"]
    assert repo.created["items"] == [
        {"partnumber": "PN1", "requested_fields": ["ean", "upc", "gtin"], "context_hash": repo.created["items"][0]["context_hash"]},
        {"partnumber": "PN2", "requested_fields": ["ean", "upc", "gtin"], "context_hash": repo.created["items"][1]["context_hash"]},
    ]
    forbidden = {"price", "stock", "cost", "promotion_start", "publish", "category_code", "channel_code"}
    assert all(not (forbidden & set(item)) for item in repo.created["items"])


def test_service_rejects_invalid_max_attempts():
    with pytest.raises(ValueError, match="max_attempts"):
        ProductWorkService(FakeRepository(), max_attempts=0)
    with pytest.raises(ValueError, match="max_attempts"):
        ProductWorkService(FakeRepository(), max_attempts=11)


def test_create_job_rejects_invalid_priority_or_work_type():
    service = ProductWorkService(FakeRepository())
    with pytest.raises(ValueError, match="priority"):
        service.create_job(rows=[{"partnumber": "PN1"}], work_type="ENRICH_TECHNICAL", source_name="X", actor_source="Y", priority=101)
    with pytest.raises(ValueError, match="work_type"):
        service.create_job(rows=[{"partnumber": "PN1"}], work_type="VTEX_CREATE_SKU", source_name="X", actor_source="Y", priority=50)
