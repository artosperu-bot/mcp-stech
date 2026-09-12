from stech_mcp.domain.derived_fact import DerivedFact
from stech_mcp.services.product_data_readiness import ProductDataReadinessService


def _product():
    return {
        "partnumber": "PN1",
        "brand": "LENOVO",
        "name": "Laptop Lenovo",
        "price": None,
        "stock": None,
    }


def test_product_is_listo_without_price_stock_or_package_data():
    result = ProductDataReadinessService().evaluate(
        product=_product(),
        technical={
            "state": "READY",
            "known_fields": {"cpu_model": "Ryzen 5", "ram_gb": 16},
            "missing_required": [],
            "conflicts": [],
        },
    )

    assert result["product_data_status"] == "LISTO"
    assert result["missing_required"] == []
    assert "price" not in result["missing_required"]
    assert "stock" not in result["missing_required"]
    assert "package_weight_g" not in result["missing_required"]


def test_missing_required_product_fact_is_incompleto():
    result = ProductDataReadinessService().evaluate(
        product=_product(),
        technical={
            "known_fields": {"ram_gb": 16},
            "missing_required": ["cpu_model"],
            "conflicts": [],
        },
    )

    assert result["product_data_status"] == "INCOMPLETO"
    assert result["missing_required"] == ["cpu_model"]


def test_strong_open_conflict_requires_review():
    result = ProductDataReadinessService().evaluate(
        product=_product(),
        technical={
            "known_fields": {"ram_gb": 16},
            "missing_required": [],
            "conflicts": ["ram_gb"],
        },
    )

    assert result["product_data_status"] == "REVIEW_REQUIRED"
    assert result["conflicts"] == ["ram_gb"]


def test_valid_derived_fact_can_satisfy_required_product_field():
    derived = DerivedFact(
        field_code="gama",
        value="Media",
        rule_code="LAPTOP_GAMA_V1",
        rule_version=1,
        inputs={"cpu_model": "Ryzen 5"},
        confidence=0.85,
        explanation="regla",
        derived_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )
    result = ProductDataReadinessService().evaluate(
        product=_product(),
        technical={
            "known_fields": {"ram_gb": 16},
            "missing_required": ["gama"],
            "conflicts": [],
        },
        derived_facts={"gama": derived},
    )

    assert result["product_data_status"] == "LISTO"
    assert result["derived_fields"] == ["gama"]


def test_missing_core_identity_blocks_product_listo():
    product = _product()
    product["brand"] = None

    result = ProductDataReadinessService().evaluate(
        product=product,
        technical={"known_fields": {}, "missing_required": [], "conflicts": []},
    )

    assert result["product_data_status"] == "INCOMPLETO"
    assert result["missing_identity"] == ["brand"]
