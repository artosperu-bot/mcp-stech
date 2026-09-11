from stech_mcp.services.product_workspace_v2 import ProductWorkspaceV2Service


class Products:
    def get_by_partnumber(self, pn):
        return {
            "part_number": pn,
            "producto_distribuidor_id": 1162,
            "marca": "LENOVO",
            "nombre": "Notebook Lenovo V15 G4 AMN",
            "familia": "NOTEBOOK",
        }


class Technical:
    def get(self, pn):
        return {
            "partnumber": pn,
            "category_code": "LAPTOP",
            "known_fields": {"ram_gb": 16},
            "field_sources": {"ram_gb": "DELTRON"},
            "missing_required": [],
            "missing_recommended": [],
            "completion_pct": 100,
        }


class Specs:
    def list_for_product(self, product_id):
        assert product_id == 1162
        return [
            {
                "especificacion_id": 633,
                "producto_distribuidor_id": 1162,
                "seccion": "MEMORIA",
                "atributo_original": "CAPACIDAD",
                "valor_original": "16 GB",
                "valor_normalizado": 16,
                "unidad": "GB",
                "orden": 8,
                "estado_validacion": "POR_VALIDAR",
                "seccion_normalizada": "MEMORIA",
                "orden_seccion": 6,
                "orden_atributo": 1,
                "estado_normalizacion": "NORMALIZADO_EXPLICITO",
            }
        ]


class Images:
    def get(self, pn, category_code=None, channel_code=None):
        return {"state": "NO_IMAGES", "image_count": 0, "recommended_min": 4}


class EmptyListRepo:
    def list_for_product(self, pn, limit=20):
        return []


def test_workspace_returns_raw_structured_deltron_specs_for_any_ui_category():
    service = ProductWorkspaceV2Service(
        product_repository=Products(),
        technical_status_service=Technical(),
        image_readiness_service=Images(),
        image_candidate_repository=EmptyListRepo(),
        fact_candidate_repository=EmptyListRepo(),
        work_repository=EmptyListRepo(),
        deltron_specification_repository=Specs(),
    )

    result = service.get("82YU00XYLM")

    assert result["deltron_specifications"]["count"] == 1
    assert result["deltron_specifications"]["source"] == "dbo.PRD_DELTRON_ESPECIFICACION"
    assert result["deltron_specifications"]["items"][0]["seccion"] == "MEMORIA"
    assert result["deltron_specifications"]["items"][0]["valor_original"] == "16 GB"
