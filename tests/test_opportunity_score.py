from stech_mcp.domain.opportunity_score import gate_action, score_confidence, score_opportunity, score_risk


def test_unknown_factor_is_renormalized_not_scored_zero():
    result = score_opportunity(
        {"profitability": 80, "demand": None},
        {"profitability": 30, "demand": 15},
    )
    assert result["opportunity_score"] == 80.0
    assert round(result["coverage_pct"], 2) == 66.67


def test_opportunity_score_uses_available_weighted_factors():
    result = score_opportunity(
        {"profitability": 90, "competitiveness": 70, "supplier": 50},
        {"profitability": 30, "competitiveness": 20, "supplier": 10},
    )
    assert result["opportunity_score"] == 76.67
    assert result["coverage_pct"] == 100.0


def test_confidence_rewards_fresh_exact_and_deep_data():
    score = score_confidence(
        {
            "identity_verified": True,
            "supplier_freshness": 100,
            "competitor_freshness": 90,
            "competitor_count": 4,
            "history_depth": 20,
            "internal_signal_quality": 80,
            "observed_input_pct": 95,
        }
    )
    assert 80 <= score <= 100


def test_risk_increases_with_price_war_stale_data_and_thin_margin():
    score = score_risk(
        {
            "margin_headroom_score": 90,
            "price_volatility_score": 80,
            "price_war": True,
            "supplier_risk_score": 60,
            "market_decline_score": 70,
            "seller_pressure_score": 80,
            "staleness_score": 90,
            "inventory_aging_score": 50,
        }
    )
    assert score >= 70


def test_strong_actions_are_downgraded_when_confidence_is_low_or_risk_high():
    for action in ("COMPRAR", "SUBIR_STOCK", "BAJAR_PRECIO", "SUBIR_PRECIO", "LIQUIDAR", "PUBLICAR"):
        assert gate_action(action, confidence_score=55, risk_score=20) == "INVESTIGAR"
        assert gate_action(action, confidence_score=90, risk_score=80) == "INVESTIGAR"


def test_non_destructive_actions_survive_confidence_gate():
    assert gate_action("MANTENER", confidence_score=30, risk_score=90) == "MANTENER"
    assert gate_action("NO_COMPETIR", confidence_score=30, risk_score=90) == "NO_COMPETIR"
    assert gate_action("REVISAR_PROVEEDOR", confidence_score=30, risk_score=90) == "REVISAR_PROVEEDOR"
