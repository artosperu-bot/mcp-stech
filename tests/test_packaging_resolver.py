from decimal import Decimal

from stech_mcp.domain.packaging_resolver import resolve_package


class EmptyEnrichmentRepo:
    def get_approved(self, partnumber, field_codes=None):
        return []


class OfficialPackageRepo:
    def get_approved(self, partnumber, field_codes=None):
        values = {
            "package_width_cm": Decimal("31.0"),
            "package_length_cm": Decimal("50.5"),
            "package_height_cm": Decimal("7.2"),
            "package_weight_g": Decimal("2180"),
        }
        return [
            {
                "partnumber": partnumber,
                "field_code": field_code,
                "value_text": None,
                "value_number": value,
                "unit": "g" if field_code == "package_weight_g" else "cm",
                "method": "VERIFIED",
                "confidence_grade": "A1",
                "is_approved": True,
            }
            for field_code, value in values.items()
        ]


class PartialOfficialRepo:
    def get_approved(self, partnumber, field_codes=None):
        return [
            {
                "partnumber": partnumber,
                "field_code": "package_weight_g",
                "value_text": None,
                "value_number": Decimal("2180"),
                "unit": "g",
                "method": "VERIFIED",
                "confidence_grade": "A1",
                "is_approved": True,
            }
        ]


class RuleRepo:
    def match(self, category_code, screen_inches):
        return {
            "rule_code": "LAPTOP_15_X_DEFAULT",
            "category_code": category_code,
            "screen_min_inches": Decimal("15.00"),
            "screen_max_inches": Decimal("16.00"),
            "width_cm": Decimal("33.00"),
            "length_cm": Decimal("54.00"),
            "height_cm": Decimal("7.00"),
            "weight_g": 2500,
            "priority": 100,
            "enabled": True,
            "source_code": "REGLA_STECH_EMPAQUE",
        }


def test_resolver_uses_estimated_rule_when_no_official_package_exists():
    result = resolve_package(
        partnumber="82YU00XYLM",
        category_code="LAPTOP",
        screen_inches=Decimal("15.6"),
        enrichment_repository=EmptyEnrichmentRepo(),
        packaging_rule_repository=RuleRepo(),
    )

    assert result == {
        "width_cm": Decimal("33.00"),
        "length_cm": Decimal("54.00"),
        "height_cm": Decimal("7.00"),
        "weight_g": 2500,
        "status": "ESTIMATED",
        "method": "ESTIMATED",
        "source": "REGLA_STECH_EMPAQUE",
        "rule_code": "LAPTOP_15_X_DEFAULT",
        "confidence_grade": "E",
    }


def test_resolver_prefers_approved_official_package_over_rule():
    result = resolve_package(
        partnumber="82YU00XYLM",
        category_code="LAPTOP",
        screen_inches=Decimal("15.6"),
        enrichment_repository=OfficialPackageRepo(),
        packaging_rule_repository=RuleRepo(),
    )

    assert result["weight_g"] == 2180
    assert result["width_cm"] == Decimal("31.0")
    assert result["length_cm"] == Decimal("50.5")
    assert result["height_cm"] == Decimal("7.2")
    assert result["method"] == "VERIFIED"
    assert result["status"] == "VERIFIED"
    assert result["confidence_grade"] == "A1"
    assert result["rule_code"] is None


def test_partial_official_package_does_not_mix_with_estimated_rule():
    result = resolve_package(
        partnumber="82YU00XYLM",
        category_code="LAPTOP",
        screen_inches=Decimal("15.6"),
        enrichment_repository=PartialOfficialRepo(),
        packaging_rule_repository=RuleRepo(),
    )

    assert result["weight_g"] == 2500
    assert result["width_cm"] == Decimal("33.00")
    assert result["method"] == "ESTIMATED"
    assert result["rule_code"] == "LAPTOP_15_X_DEFAULT"
