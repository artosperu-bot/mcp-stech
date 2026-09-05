from stech_mcp.domain.source_policy import Evidence, choose_best_evidence, can_use_same_chassis


def test_official_exact_sku_wins_over_retailer():
    official = Evidence(
        value="16GB LPDDR5-5500",
        source_type="OFFICIAL_DOCUMENT",
        confidence_grade="A2",
        source_partnumber="82YU00XYLM",
    )
    retailer = Evidence(
        value="16GB LPDDR5-4800",
        source_type="TRUSTED_RETAILER",
        confidence_grade="C",
        source_partnumber="82YU00XYLM",
    )

    assert choose_best_evidence([retailer, official]) == official


def test_same_chassis_is_not_allowed_for_variant_specific_fields():
    for field_code in ["ram", "ssd", "cpu", "operating_system", "color"]:
        assert can_use_same_chassis(field_code) is False


def test_same_chassis_is_allowed_for_structural_fields():
    for field_code in ["device_width", "device_depth", "ports", "keyboard_layout", "package_width"]:
        assert can_use_same_chassis(field_code) is True
