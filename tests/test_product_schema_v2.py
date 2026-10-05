from pathlib import Path

from stech_mcp.domain.product_schema import (
    CategoryAttribute,
    ProductAttributeDefinition,
    normalize_category_code,
)


def test_attribute_schema_sql_contains_initial_categories_and_tables():
    text = Path("sql/007_product_attribute_schema_v2.sql").read_text(encoding="utf-8")
    for value in (
        "product_attribute_definition",
        "category_attribute",
        "LAPTOP",
        "PORTABLE_SPEAKER",
        "HEADPHONES",
    ):
        assert value in text


def test_initial_schema_seed_contains_required_canonical_fields():
    text = Path("sql/007_product_attribute_schema_v2.sql").read_text(encoding="utf-8")
    expected = {
        "cpu_model",
        "ram_gb",
        "storage_gb",
        "speaker_power_w",
        "ip_rating",
        "driver_size_mm",
        "anc",
        "battery_runtime_hours",
    }
    for field_code in expected:
        assert field_code in text
    assert "REQUIRED" in text
    assert "RECOMMENDED" in text
    assert "SAME_CHASSIS_ALLOWED" in text
    assert "EXACT_PN_ONLY" in text


def test_schema_models_normalize_codes_without_marketplace_context():
    definition = ProductAttributeDefinition(
        field_code=" Bluetooth_Version ",
        value_type="text",
        unit=None,
        variant_sensitive=False,
        reuse_policy="exact_pn_only",
    )
    category = CategoryAttribute(
        category_code=" portable_speaker ",
        field_code=" Bluetooth_Version ",
        requirement="required",
        ordinal=20,
        value_type="text",
        unit=None,
        variant_sensitive=False,
        reuse_policy="exact_pn_only",
    )

    assert definition.field_code == "bluetooth_version"
    assert definition.value_type == "TEXT"
    assert definition.reuse_policy == "EXACT_PN_ONLY"
    assert category.category_code == "PORTABLE_SPEAKER"
    assert category.field_code == "bluetooth_version"
    assert category.requirement == "REQUIRED"
    assert normalize_category_code(" portable speaker ") == "PORTABLE_SPEAKER"
