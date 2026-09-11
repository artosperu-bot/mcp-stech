from stech_mcp.services.multichannel_readiness import MultichannelReadinessService


class FakeProductRepository:
    def get_by_partnumber(self, partnumber):
        return {"part_number": partnumber, "marca": "LENOVO", "nombre": "Laptop Test"}


class FakeEnrichmentRepository:
    def get_approved(self, partnumber):
        return []


class FakeTechnicalStatus:
    def get(self, partnumber):
        return {
            "partnumber": partnumber,
            "category_code": "LAPTOP",
            "completion_pct": 80,
            "missing_required": ["battery_wh"],
            "missing_recommended": [],
        }


def fake_preview_builder(*, product, marketplace, category, **kwargs):
    del product, category, kwargs
    if marketplace == "COOLBOX":
        return {
            "fields": [
                {"field": "A", "status": "VERIFIED"},
                {"field": "B", "status": "VERIFIED"},
                {"field": "C", "status": "VERIFIED"},
                {"field": "D", "status": "RESEARCH_REQUIRED"},
            ]
        }
    if marketplace == "FALABELLA":
        return {
            "fields": [
                {"field": "A", "status": "VERIFIED"},
                {"field": "B", "status": "MARKETPLACE_INPUT"},
            ]
        }
    raise ValueError("unsupported")


def test_same_master_has_independent_channel_readiness():
    service = MultichannelReadinessService(
        product_repository=FakeProductRepository(),
        enrichment_repository=FakeEnrichmentRepository(),
        technical_status_service=FakeTechnicalStatus(),
        preview_builder=fake_preview_builder,
    )

    result = service.get("PN1")

    assert set(result["channels"]) >= {"FALABELLA", "COOLBOX", "VTEX"}
    assert result["channels"]["COOLBOX"]["completion_pct"] == 75
    assert result["channels"]["FALABELLA"]["completion_pct"] == 50
    assert result["channels"]["VTEX"]["completion_pct"] == 80
    assert result["channels"]["FALABELLA"]["completion_pct"] != result["channels"]["COOLBOX"]["completion_pct"]
