from decimal import Decimal

from stech_mcp.domain.packaging_rules import estimate_package_weight, validate_package_dimensions


def test_estimates_normal_15_6_package_weight_from_device_weight():
    result = estimate_package_weight(
        screen_inches=Decimal("15.6"),
        device_weight_kg=Decimal("1.65"),
        is_gaming=False,
    )

    assert result == Decimal("2.35")


def test_estimates_normal_16_package_weight_from_device_weight():
    result = estimate_package_weight(
        screen_inches=Decimal("16"),
        device_weight_kg=Decimal("1.90"),
        is_gaming=False,
    )

    assert result == Decimal("2.70")


def test_rejects_package_dimensions_not_larger_than_device():
    valid, reasons = validate_package_dimensions(
        device_width_cm=Decimal("35.92"),
        device_depth_cm=Decimal("23.58"),
        device_height_cm=Decimal("1.83"),
        package_width_cm=Decimal("35.92"),
        package_length_cm=Decimal("23.58"),
        package_height_cm=Decimal("1.83"),
    )

    assert valid is False
    assert "package_not_larger_than_device" in reasons
