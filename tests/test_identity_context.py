from stech_mcp.services.identity_context import build_identity_context


def test_build_identity_context_uses_existing_laptop_facts_without_guessing():
    context = build_identity_context(
        {
            "part_number": "83LY00J9LM",
            "marca": "Lenovo",
            "modelo": "IdeaPad Slim 3",
            "nombre": "Lenovo IdeaPad Slim 3 Intel Core i5 16GB 512GB",
            "categoria": "LAPTOP",
            "ean": None,
            "upc": None,
            "atributos_json": {
                "procesador": "Intel Core i5-13420H",
                "ram_gb": 16,
                "storage_gb": 512,
                "storage_type": "SSD",
                "screen_inches": 15.6,
                "color": "Gris",
                "operating_system": "Sin sistema operativo",
            },
        }
    )

    assert context == {
        "brand": "LENOVO",
        "part_number": "83LY00J9LM",
        "model": "IdeaPad Slim 3",
        "category": "LAPTOP",
        "title": "Lenovo IdeaPad Slim 3 Intel Core i5 16GB 512GB",
        "processor": "Intel Core i5-13420H",
        "ram_gb": 16,
        "storage_gb": 512,
        "storage_type": "SSD",
        "screen_inches": 15.6,
        "gpu": None,
        "color": "Gris",
        "operating_system": "Sin sistema operativo",
        "existing_ean": None,
        "existing_upc": None,
        "existing_gtin": None,
    }


def test_build_identity_context_tolerates_json_string_and_missing_optional_fields():
    context = build_identity_context(
        {
            "part_number": "82YU00XYLM",
            "marca": "LENOVO",
            "atributos_json": '{"procesador":"AMD Ryzen 5","ram_gb":8}',
        }
    )

    assert context["brand"] == "LENOVO"
    assert context["part_number"] == "82YU00XYLM"
    assert context["processor"] == "AMD Ryzen 5"
    assert context["ram_gb"] == 8
    assert context["storage_gb"] is None
