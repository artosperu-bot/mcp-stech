from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from stech_mcp.services.market_opportunities import MarketOpportunityService


NOW = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)


class FakeProductRepository:
    def get_by_partnumber(self, partnumber):
        return {
            "part_number": partnumber,
            "partnumber": partnumber,
            "marca": "LENOVO",
            "categoria": "LAPTOP",
        }


class FakeMarketRepository:
    def list_candidate_partnumbers(self, channel=None, limit=100):
        return ["A", "B", "C"][:limit]

    def list_supplier_partnumbers(self, supplier=None, limit=100):
        return ["A", "B", "C"][:limit]

    def get_internal_signal(self, partnumber, as_of=None):
        return {
            "A": {"own_stock_qty": Decimal("0"), "sales_units_30d": Decimal("5"), "own_sale_price_pen": None},
            "B": {"own_stock_qty": Decimal("1"), "sales_units_30d": Decimal("4"), "own_sale_price_pen": Decimal("1500")},
            "C": {"own_stock_qty": Decimal("0"), "sales_units_30d": Decimal("3"), "own_sale_price_pen": None},
        }[partnumber]

    def get_supplier_history(self, partnumber, supplier=None, days=90):
        values = {
            "A": (Decimal("950"), Decimal("900")),
            "B": (Decimal("1000"), Decimal("1000")),
            "C": (Decimal("750"), Decimal("700")),
        }[partnumber]
        return [
            {"partnumber": partnumber, "supplier_code": supplier or "DELTRON", "observed_at": NOW, "cost_pen": values[0], "stock_state": "IN_STOCK", "stock_qty": Decimal("10")},
            {"partnumber": partnumber, "supplier_code": supplier or "DELTRON", "observed_at": NOW, "cost_pen": values[1], "stock_state": "IN_STOCK", "stock_qty": Decimal("10")},
        ]


class FakeMarketService:
    def product_analyze(self, partnumber, channel=None):
        return {
            "A": {
                "found": True, "partnumber": "A", "channel": channel,
                "action_code": "INVESTIGAR", "raw_action_code": "COMPRAR",
                "opportunity_score": 95.0, "confidence_score": 55.0, "risk_score": 20.0,
                "expected_profit_pen": Decimal("300"), "expected_margin_pct": Decimal("0.20"),
                "cost_pen": Decimal("900"), "reason_codes": ["ACTION_GATED_BY_CONFIDENCE_OR_RISK"],
            },
            "B": {
                "found": True, "partnumber": "B", "channel": channel,
                "action_code": "COMPRAR", "raw_action_code": "COMPRAR",
                "opportunity_score": 85.0, "confidence_score": 92.0, "risk_score": 25.0,
                "expected_profit_pen": Decimal("250"), "expected_margin_pct": Decimal("0.18"),
                "cost_pen": Decimal("1000"), "reason_codes": [],
            },
            "C": {
                "found": True, "partnumber": "C", "channel": channel,
                "action_code": "COMPRAR", "raw_action_code": "COMPRAR",
                "opportunity_score": 78.0, "confidence_score": 88.0, "risk_score": 30.0,
                "expected_profit_pen": Decimal("160"), "expected_margin_pct": Decimal("0.16"),
                "cost_pen": Decimal("700"), "reason_codes": [],
            },
        }[partnumber]


def build_service():
    return MarketOpportunityService(
        market_service=FakeMarketService(),
        market_repository=FakeMarketRepository(),
        product_repository=FakeProductRepository(),
        clock=lambda: NOW,
    )


def test_gated_investigation_does_not_outrank_actionable_purchase():
    result = build_service().opportunities_find(channel="FALABELLA", category="LAPTOP", limit=10)

    assert [item["partnumber"] for item in result["opportunities"]][:2] == ["B", "C"]
    assert result["opportunities"][-1]["partnumber"] == "A"
    assert result["opportunities"][-1]["action_code"] == "INVESTIGAR"


def test_budget_strategy_never_exceeds_budget_and_skips_low_confidence_purchase():
    result = build_service().strategy(channel="FALABELLA", category="LAPTOP", budget_pen=Decimal("1500"), limit=10)

    assert result["allocated_budget_pen"] <= Decimal("1500")
    assert result["unallocated_budget_pen"] == Decimal("500")
    assert [item["partnumber"] for item in result["purchases"]] == ["B"]
    assert result["purchases"][0]["quantity"] == 1
    assert all(item["partnumber"] != "A" for item in result["purchases"])


def test_negative_contribution_is_never_allocated():
    service = build_service()
    original = service.market_service.product_analyze

    def analyze(partnumber, channel=None):
        result = original(partnumber, channel)
        if partnumber == "B":
            result = {**result, "expected_profit_pen": Decimal("-10")}
        return result

    service.market_service.product_analyze = analyze
    result = service.strategy(channel="FALABELLA", category="LAPTOP", budget_pen=Decimal("1500"), limit=10)

    assert all(item["partnumber"] != "B" for item in result["purchases"])


def test_assortment_gap_detects_no_own_listing_price():
    result = build_service().assortment_gaps(channel="FALABELLA", category="LAPTOP", limit=10)
    assert {item["partnumber"] for item in result["gaps"]} == {"A", "C"}
    assert all("NO_STECH_LISTING" in item["reason_codes"] for item in result["gaps"])


def test_supplier_opportunity_reports_cost_drop_and_stock():
    result = build_service().supplier_opportunities(supplier="DELTRON", category="LAPTOP", limit=10)
    item = next(item for item in result["opportunities"] if item["partnumber"] == "C")
    assert item["latest_cost_pen"] == Decimal("700")
    assert item["cost_change_pen"] == Decimal("-50")
    assert "SUPPLIER_COST_DROP" in item["reason_codes"]
    assert "SUPPLIER_IN_STOCK" in item["reason_codes"]
