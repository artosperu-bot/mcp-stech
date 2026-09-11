from pathlib import Path

from stech_mcp.tools.market_intelligence import register_market_intelligence_tools


REQUIRED_TOOLS = {
    "market_observation_ingest",
    "market_supplier_observation_ingest",
    "market_internal_signal_ingest",
    "market_product_match_upsert",
    "market_pricing_policy_get",
    "market_pricing_policy_upsert",
    "market_channel_fee_rule_get",
    "market_channel_fee_rule_upsert",
    "market_competitors_get",
    "market_price_history",
    "market_variations_get",
    "market_data_quality",
    "market_profit_simulate",
    "market_recommended_price",
    "market_product_analyze",
    "market_risk_analyze",
    "market_opportunities_find",
    "market_assortment_gaps",
    "market_supplier_opportunities",
    "market_channel_opportunities",
    "market_strategy",
    "market_weekly_actions",
}


class FakeMcp:
    def __init__(self):
        self.names = []

    def tool(self):
        def decorator(func):
            self.names.append(func.__name__)
            return func
        return decorator


class Stub:
    def __getattr__(self, name):
        def method(*args, **kwargs):
            return {"method": name, "args": args, "kwargs": kwargs}
        return method


def test_all_market_intelligence_tools_register_additively():
    mcp = FakeMcp()
    namespace = Stub()
    registered = register_market_intelligence_tools(
        mcp,
        market_repository=Stub(),
        market_service=Stub(),
        opportunity_service=Stub(),
        namespace=namespace,
    )

    assert set(registered) == REQUIRED_TOOLS
    assert set(mcp.names) == REQUIRED_TOOLS


def test_authoritative_server_wires_market_intelligence_additively():
    source = Path("src/stech_mcp/server_authoritative.py").read_text(encoding="utf-8")
    assert "MarketRepository" in source
    assert "MarketIntelligenceService" in source
    assert "MarketOpportunityService" in source
    assert "register_market_intelligence_tools" in source
    assert "market_intelligence_tools" in source


def test_market_tools_do_not_expose_operational_marketplace_writes():
    source = Path("src/stech_mcp/tools/market_intelligence.py").read_text(encoding="utf-8")
    forbidden = (
        "market_price_update",
        "market_stock_update",
        "marketplace_publish",
        "market_purchase_execute",
    )
    for name in forbidden:
        assert name not in source
