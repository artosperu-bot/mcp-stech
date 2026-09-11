from __future__ import annotations

from stech_mcp.domain.product_schema import CategoryAttribute
from stech_mcp.services.product_technical_status import ProductTechnicalStatusService


class FakeProductRepository:
    def get_by_partnumber(self, partnumber):
        assert partnumber == "PN1"
        return {
            "partnumber": "PN1",
            "category_code": "portable_speaker",
            "nombre": "Parlante portátil de prueba",
            "price": 99,
            "stock": 8,
            "ip_rating": "IP67",
        }


class FakeEnrichmentRepository:
    def get_approved(self, partnumber, field_codes=None):
        assert partnumber == "PN1"
        assert field_codes is None
        return [
            {
                "field_code": "bluetooth_version",
                "value_text": "5.4",
                "value_number": None,
                "unit": None,
                "confidence_grade": "A1",
            },
            {
                "field_code": "ip_rating",
                "value_text": "IP68",
                "value_number": None,
                "unit": None,
                "confidence_grade": "A1",
            },
        ]


class FakeSchemaRepository:
    def get_category_schema(self, category_code):
        assert category_code == "PORTABLE_SPEAKER"
        return [
            CategoryAttribute("PORTABLE_SPEAKER", "speaker_power_w", "REQUIRED", 10, "NUMBER", "W", True, "EXACT_PN_ONLY"),
            CategoryAttribute("PORTABLE_SPEAKER", "bluetooth_version", "REQUIRED", 20, "TEXT", None, False, "EXACT_PN_ONLY"),
            CategoryAttribute("PORTABLE_SPEAKER", "ip_rating", "REQUIRED", 30, "TEXT", None, False, "EXACT_PN_ONLY"),
            CategoryAttribute("PORTABLE_SPEAKER", "box_contents", "RECOMMENDED", 40, "LIST", None, False, "EXACT_PN_ONLY"),
        ]


def test_status_returns_only_missing_technical_fields_and_approved_overrides_raw():
    service = ProductTechnicalStatusService(
        product_repository=FakeProductRepository(),
        enrichment_repository=FakeEnrichmentRepository(),
        schema_repository=FakeSchemaRepository(),
    )

    result = service.get(" pn1 ")

    assert result["partnumber"] == "PN1"
    assert result["category_code"] == "PORTABLE_SPEAKER"
    assert result["known_fields"]["bluetooth_version"] == "5.4"
    assert result["known_fields"]["ip_rating"] == "IP68"
    assert "speaker_power_w" in result["missing_required"]
    assert "box_contents" in result["missing_recommended"]
    assert "price" not in result["known_fields"]
    assert "stock" not in result["known_fields"]
    assert "price" not in result["missing_required"]
    assert "stock" not in result["missing_required"]
    assert result["conflicts"] == []
    assert result["completion_pct"] == 50
    assert result["missing_identity"] == ["ean", "upc", "gtin"]


def test_status_reuses_approved_barcode_identity_and_keeps_technical_score_unchanged():
    class BarcodeEnrichmentRepository(FakeEnrichmentRepository):
        def get_approved(self, partnumber, field_codes=None):
            rows = super().get_approved(partnumber, field_codes)
            return [
                *rows,
                {
                    "field_code": "ean",
                    "value_text": "0197528523880",
                    "value_number": None,
                    "unit": None,
                    "confidence_grade": "A1",
                },
            ]

    service = ProductTechnicalStatusService(
        product_repository=FakeProductRepository(),
        enrichment_repository=BarcodeEnrichmentRepository(),
        schema_repository=FakeSchemaRepository(),
    )

    result = service.get("PN1")

    assert result["known_fields"]["ean"] == "0197528523880"
    assert result["identity"]["ean"] == "0197528523880"
    assert result["missing_identity"] == []
    assert result["completion_pct"] == 50


def test_status_uses_direct_product_barcode_before_researching_identity():
    class ProductWithUpc(FakeProductRepository):
        def get_by_partnumber(self, partnumber):
            product = super().get_by_partnumber(partnumber)
            product["upc"] = "740617352214"
            return product

    service = ProductTechnicalStatusService(
        product_repository=ProductWithUpc(),
        enrichment_repository=FakeEnrichmentRepository(),
        schema_repository=FakeSchemaRepository(),
    )

    result = service.get("PN1")

    assert result["identity"]["upc"] == "740617352214"
    assert result["known_fields"]["upc"] == "740617352214"
    assert result["missing_identity"] == []
    assert result["completion_pct"] == 50


def test_status_raises_when_product_does_not_exist():
    class MissingProductRepository:
        def get_by_partnumber(self, partnumber):
            return None

    service = ProductTechnicalStatusService(
        product_repository=MissingProductRepository(),
        enrichment_repository=FakeEnrichmentRepository(),
        schema_repository=FakeSchemaRepository(),
    )

    try:
        service.get("MISSING")
    except LookupError as exc:
        assert "MISSING" in str(exc)
    else:
        raise AssertionError("expected LookupError")
