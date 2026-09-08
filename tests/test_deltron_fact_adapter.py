from stech_mcp.services.deltron_fact_adapter import DeltronFactAdapter


def test_adapter_excludes_commercial_fields_and_maps_portable_speaker_specs():
    adapter = DeltronFactAdapter()
    candidates = adapter.adapt(
        {
            "partnumber": "PN1",
            "precio": "99.00",
            "stock": 12,
            "atributos_json": {
                "especificaciones": {
                    "Bluetooth": "Bluetooth 5.4",
                    "Potencia": "30 W RMS",
                    "Protección": "IP67 waterproof",
                }
            },
        },
        category_code="PORTABLE_SPEAKER",
    )

    fields = {candidate["field_code"] for candidate in candidates}
    assert fields == {"bluetooth_version", "speaker_power_w", "ip_rating"}
    assert "price" not in fields
    assert "precio" not in fields
    assert "stock" not in fields

    bluetooth = next(x for x in candidates if x["field_code"] == "bluetooth_version")
    assert bluetooth["normalized_value"] == "5.4"
    assert bluetooth["source_type"] == "AUTHORIZED_DISTRIBUTOR"
    assert bluetooth["source_name"] == "DELTRON"
    assert bluetooth["source_partnumber"] == "PN1"
    assert bluetooth["confidence_rank"] == "B"


def test_adapter_accepts_json_string_and_rejects_ambiguous_values():
    adapter = DeltronFactAdapter()
    product = {
        "part_number": "PN2",
        "atributos_json": '{"especificaciones":{"Bluetooth":"Bluetooth","Potencia":"30"}}',
    }

    assert adapter.adapt(product, category_code="PORTABLE_SPEAKER") == []


def test_adapter_maps_headphone_and_laptop_aliases_without_marketplace_fields():
    adapter = DeltronFactAdapter()
    headphones = adapter.adapt(
        {
            "partnumber": "HP1",
            "atributos_json": {
                "especificaciones": {
                    "Driver": "40 mm",
                    "Bluetooth": "5.3",
                    "Autonomía": "50 horas",
                }
            },
        },
        category_code="HEADPHONES",
    )
    laptop = adapter.adapt(
        {
            "partnumber": "LT1",
            "atributos_json": {
                "especificaciones": {
                    "CPU": "Intel Core i5-13420H",
                    "Memoria RAM": "16 GB DDR5",
                    "SSD": "512 GB SSD",
                    "Resolución": "1920 x 1080",
                }
            },
        },
        category_code="LAPTOP",
    )

    assert {x["field_code"] for x in headphones} == {
        "driver_size_mm",
        "bluetooth_version",
        "battery_runtime_hours",
    }
    assert {x["field_code"] for x in laptop} == {
        "cpu_model",
        "ram_gb",
        "storage_gb",
        "resolution",
    }
