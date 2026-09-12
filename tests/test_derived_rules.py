from stech_mcp.services.derived_rules import DerivedRuleEngine


def test_engine_derives_laptop_gama_with_auditable_metadata():
    result = DerivedRuleEngine().derive(
        "gama",
        "LAPTOP",
        {
            "cpu_model": "AMD Ryzen 5 7520U",
            "ram_gb": 16,
            "storage_gb": 512,
            "gpu_model": "AMD Radeon 610M",
            "resolution": "1920x1080",
        },
        context={"deltron_price_percentile": 0.45},
    )

    assert result is not None
    assert result.value == "Media"
    assert result.rule_code == "LAPTOP_GAMA_V1"
    assert result.rule_version == 1
    assert result.inputs["cpu_model"] == "AMD Ryzen 5 7520U"
    assert result.derived_at.tzinfo is not None
    assert result.explanation


def test_engine_returns_none_for_unsupported_derived_field_or_category():
    engine = DerivedRuleEngine()

    assert engine.derive("gama", "TOASTER", {"cpu_model": "x"}) is None
    assert engine.derive("random_field", "LAPTOP", {"cpu_model": "x"}) is None
