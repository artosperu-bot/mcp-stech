import json

import pytest

from stech_mcp.services.marketplace_preview import build_marketplace_preview


def _product():
    return {
        "part_number": "82YU00XYLM",
        "upc": "197528523880",
        "marca": "LENOVO",
        "nombre": 'Notebook Lenovo V15 G4 AMN, 15.6" FHD TN, AMD Ryzen 5 7520U, 16GB LPDDR5-4800.',
        "atributos_json": json.dumps(
            {
                "especificaciones": {
                    "MODELO": "V15 G4 AMN",
                    "PANTALLA": "15.6 PULG TN LED FHD RESOLUCION 1920 x 1080",
                    "CPU": "AMD RYZEN 5 7520U",
                    "PESO": "1.65 KG",
                }
            }
        ),
    }


def test_generic_preview_routes_coolbox_laptop():
    result = build_marketplace_preview(
        product=_product(),
        marketplace="coolbox",
        category="laptop",
        package=None,
    )

    assert result["marketplace"] == "COOLBOX"
    assert result["category"] == "LAPTOP"
    assert result["template"] == "Laptops-All in one"
    assert result["field_count"] == 81


def test_generic_preview_rejects_unknown_marketplace():
    with pytest.raises(ValueError, match="unsupported marketplace/category"):
        build_marketplace_preview(
            product=_product(), marketplace="UNKNOWN", category="LAPTOP"
        )
