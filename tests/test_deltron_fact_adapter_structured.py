from stech_mcp.services.deltron_fact_adapter import DeltronFactAdapter


def _row(section, attribute, value, normalized=None, unit=None):
    return {
        "seccion": section,
        "atributo_original": attribute,
        "valor_original": value,
        "valor_normalizado": normalized,
        "unidad": unit,
    }


def test_adapter_maps_structured_laptop_specs_by_section_and_attribute():
    adapter = DeltronFactAdapter()
    candidates = adapter.adapt(
        {"partnumber": "82YU00XYLM"},
        category_code="LAPTOP",
        specifications=[
            _row("CPU", "ESPECIFICACION", "AMD RYZEN 5 7520U 2.80 / 4.30 GHZ"),
            _row("MEMORIA", "CAPACIDAD", "16 GB", 16, "GB"),
            _row("ALMACENAMIENTO", "CAPACIDAD", "512 GB", 512, "GB"),
            _row("ALMACENAMIENTO", "TIPO", "SSD M.2"),
            _row("PANTALLA", "ESPECIFICACION", "15.6 PULG TN LED FHD RESOLUCION MAXIMA 1920 x 1080"),
            _row("CONECTIVIDAD", "WIRELESS", "802.11AX 2x2 Wi-Fi 6"),
            _row("CONECTIVIDAD", "BLUETOOTH", "5.1"),
            _row("BATERIA", "CAPACIDAD", "38 WH", 38, "Wh"),
            _row("PESO", "ESPECIFICACION", "1.65 KG", 1.65, "kg"),
            _row("SISTEMA OPERATIVO", "VERSION", "NO INCLUYE SISTEMA OPERATIVO"),
        ],
    )

    by_field = {item["field_code"]: item for item in candidates}
    assert by_field["cpu_model"]["normalized_value"].startswith("AMD RYZEN 5 7520U")
    assert by_field["ram_gb"]["normalized_value"] == 16
    assert by_field["storage_gb"]["normalized_value"] == 512
    assert by_field["storage_type"]["normalized_value"] == "SSD"
    assert by_field["screen_inches"]["normalized_value"] == 15.6
    assert by_field["resolution"]["normalized_value"] == "1920x1080"
    assert by_field["wifi"]["normalized_value"] == "802.11AX 2x2 Wi-Fi 6"
    assert by_field["bluetooth_version"]["normalized_value"] == "5.1"
    assert by_field["battery_wh"]["normalized_value"] == 38
    assert by_field["weight_kg"]["normalized_value"] == 1.65
    assert by_field["os_name"]["normalized_value"] == "NO INCLUYE SISTEMA OPERATIVO"
    assert all(item["source_name"] == "DELTRON" for item in candidates)


def test_adapter_ignores_legacy_atributos_json_without_structured_specs():
    adapter = DeltronFactAdapter()
    product = {
        "part_number": "PN2",
        "atributos_json": {"especificaciones": {"CPU": "OLD VALUE", "Memoria RAM": "64 GB"}},
    }

    assert adapter.adapt(product, category_code="LAPTOP", specifications=[]) == []
