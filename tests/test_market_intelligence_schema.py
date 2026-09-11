from pathlib import Path


def test_market_intelligence_migration_contains_required_objects():
    sql = Path("sql/010_market_intelligence_v1.sql").read_text(encoding="utf-8")
    for name in (
        "market_listing",
        "market_product_match",
        "market_observation",
        "supplier_observation",
        "market_pricing_policy",
        "market_channel_fee_rule",
        "market_fx_rate",
        "market_internal_signal",
        "market_recommendation_snapshot",
    ):
        assert f"dbo.{name}" in sql

    assert "VERIFIED" in sql
    assert "confidence_score" in sql
    assert "source_observation_key" in sql
    assert "minimum_margin_pct" in sql
    assert "minimum_contribution_pen" in sql


def test_market_intelligence_migration_is_additive_and_idempotent():
    sql = Path("sql/010_market_intelligence_v1.sql").read_text(encoding="utf-8").upper()
    assert "IF OBJECT_ID" in sql
    assert "DROP TABLE" not in sql
    assert "TRUNCATE TABLE" not in sql
    assert "DELETE FROM" not in sql
