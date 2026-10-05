from stech_mcp.domain.product_schema import CategoryAttribute
from stech_mcp.services.deltron_fact_adapter import DeltronFactAdapter
from stech_mcp.services.product_technical_status import ProductTechnicalStatusService


class Products:
    def get_by_partnumber(self, partnumber):
        assert partnumber == "82YU00XYLM"
        return {
            "partnumber": partnumber,
            "producto_distribuidor_id": 1162,
            "familia": "NOTEBOOK",
            "nombre": "Notebook Lenovo V15 G4 AMN",
            "atributos_json": {"especificaciones": {"CPU": "LEGACY CPU"}},
        }


class Specs:
    def list_for_product(self, product_id):
        assert product_id == 1162
        return [
            {"seccion": "CPU", "atributo_original": "ESPECIFICACION", "valor_original": "AMD RYZEN 5 7520U", "valor_normalizado": None, "unidad": None},
            {"seccion": "MEMORIA", "atributo_original": "CAPACIDAD", "valor_original": "16 GB", "valor_normalizado": 16, "unidad": "GB"},
            {"seccion": "ALMACENAMIENTO", "atributo_original": "CAPACIDAD", "valor_original": "512 GB", "valor_normalizado": 512, "unidad": "GB"},
            {"seccion": "BATERIA", "atributo_original": "CAPACIDAD", "valor_original": "38 WH", "valor_normalizado": 38, "unidad": "Wh"},
        ]


class Enrichments:
    def get_approved(self, partnumber, field_codes=None):
        # Existing enrichment is deliberately different: Deltron remains the
        # authority whenever it already has the exact PN field.
        return [
            {
                "field_code": "cpu_model",
                "value_text": "AMD Ryzen 5 7520U verified external",
                "value_number": None,
                "unit": None,
                "confidence_grade": "A1",
            }
        ]


class Schema:
    def get_category_schema(self, category_code):
        assert category_code == "LAPTOP"
        return [
            CategoryAttribute("LAPTOP", "cpu_model", "REQUIRED", 10, "TEXT", None, True, "EXACT_PN_ONLY"),
            CategoryAttribute("LAPTOP", "ram_gb", "REQUIRED", 20, "NUMBER", "GB", True, "EXACT_PN_ONLY"),
            CategoryAttribute("LAPTOP", "storage_gb", "REQUIRED", 30, "NUMBER", "GB", True, "EXACT_PN_ONLY"),
            CategoryAttribute("LAPTOP", "battery_wh", "RECOMMENDED", 40, "NUMBER", "Wh", True, "EXACT_PN_ONLY"),
        ]


def test_status_uses_structured_deltron_specs_before_research_and_tracks_source():
    service = ProductTechnicalStatusService(
        product_repository=Products(),
        enrichment_repository=Enrichments(),
        schema_repository=Schema(),
        deltron_specification_repository=Specs(),
        deltron_adapter=DeltronFactAdapter(),
    )

    result = service.get("82YU00XYLM")

    assert result["known_fields"]["ram_gb"] == 16
    assert result["known_fields"]["storage_gb"] == 512
    assert result["known_fields"]["battery_wh"] == 38
    assert result["field_sources"]["ram_gb"] == "DELTRON"
    assert result["field_sources"]["storage_gb"] == "DELTRON"
    assert result["field_sources"]["battery_wh"] == "DELTRON"
    assert result["known_fields"]["cpu_model"] == "AMD RYZEN 5 7520U"
    assert result["field_sources"]["cpu_model"] == "DELTRON"
    assert result["missing_required"] == []
    assert result["missing_recommended"] == []
    assert result["completion_pct"] == 100
