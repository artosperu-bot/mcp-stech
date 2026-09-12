from stech_mcp.domain.derived_fact import DerivedFact
from stech_mcp.services.description_builder import DescriptionBuilder


def test_laptop_description_uses_verified_facts_and_exact_identity():
    builder = DescriptionBuilder()
    facts = {
        "brand": "LENOVO",
        "model": "V15 G4 AMN",
        "cpu_model": "AMD Ryzen 5 7520U",
        "ram_gb": 16,
        "storage_gb": 512,
        "storage_type": "SSD NVMe",
        "screen_inches": 15.6,
        "resolution": "1920x1080",
        "gpu_model": "AMD Radeon 610M",
        "wifi": "Wi-Fi 6",
        "bluetooth_version": "5.1",
        "weight_kg": 1.65,
        "os_name": "Sin sistema operativo",
        "ean": "0197528523880",
    }

    text = builder.build(
        "82YU00XYLM",
        "LAPTOP",
        facts,
        derived_facts={},
        max_chars=3000,
    )

    assert "AMD Ryzen 5 7520U" in text
    assert "16 GB" in text
    assert "512 GB" in text
    assert "15.6" in text
    assert "1920x1080" in text
    assert "Sin sistema operativo" in text
    assert "Part Number: 82YU00XYLM" in text
    assert "EAN: 0197528523880" in text


def test_description_omits_unknown_specs_and_unsupported_marketing_claims():
    text = DescriptionBuilder().build(
        "PN1",
        "LAPTOP",
        {
            "brand": "LENOVO",
            "model": "V15",
            "cpu_model": "Intel Core i3-1315U",
            "ram_gb": 8,
            "gpu_model": None,
            "warranty": None,
        },
        derived_facts={},
        max_chars=1000,
    )

    assert "garantía" not in text.casefold()
    assert "ultrapotente" not in text.casefold()
    assert "el mejor" not in text.casefold()
    assert "None" not in text


def test_description_preserves_identity_footer_when_body_is_truncated():
    facts = {
        "brand": "LENOVO",
        "model": "V15 G4 AMN",
        "cpu_model": "AMD Ryzen 5 7520U",
        "ram_gb": 16,
        "storage_gb": 512,
        "screen_inches": 15.6,
        "resolution": "1920x1080",
        "wifi": "Wi-Fi 6",
        "bluetooth_version": "5.1",
        "battery_wh": 38,
        "weight_kg": 1.65,
        "ean": "0197528523880",
    }

    text = DescriptionBuilder().build(
        "82YU00XYLM",
        "LAPTOP",
        facts,
        derived_facts={},
        max_chars=320,
    )

    assert len(text) <= 320
    assert "Part Number: 82YU00XYLM" in text
    assert "EAN: 0197528523880" in text


def test_smartphone_description_is_category_aware():
    text = DescriptionBuilder().build(
        "ARMOR25TPRO",
        "SMARTPHONE",
        {
            "brand": "ULEFONE",
            "model": "Armor 25T Pro",
            "chipset": "MediaTek Dimensity 6300",
            "ram_gb": 6,
            "storage_gb": 256,
            "screen_inches": 6.78,
            "battery_mah": 6500,
            "network": "5G",
            "ip_rating": "IP68/IP69K",
        },
        derived_facts={},
        max_chars=1500,
    )

    assert "MediaTek Dimensity 6300" in text
    assert "6500 mAh" in text
    assert "5G" in text
    assert "IP68/IP69K" in text
    assert "Part Number: ARMOR25TPRO" in text


def test_same_inputs_generate_same_description():
    builder = DescriptionBuilder()
    facts = {
        "brand": "LENOVO",
        "model": "V15",
        "cpu_model": "AMD Ryzen 5 7520U",
        "ram_gb": 16,
        "storage_gb": 512,
    }

    first = builder.build("PN1", "LAPTOP", facts, derived_facts={}, max_chars=1200)
    second = builder.build("PN1", "LAPTOP", facts, derived_facts={}, max_chars=1200)

    assert first == second
