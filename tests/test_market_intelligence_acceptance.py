from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from stech_mcp.db.market_repository import MarketRepository
from stech_mcp.services.market_intelligence import MarketIntelligenceService
from stech_mcp.services.market_opportunities import MarketOpportunityService


NOW = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)


class AcceptanceProducts:
    def get_by_partnumber(self, partnumber):
        return {
            "part_number": partnumber,
            "partnumber": partnumber,
            "marca": "LENOVO",
            "categoria": "LAPTOP",
            "nombre": f"Laptop {partnumber}",
        }


class AcceptanceMarketRepository:
    def __init__(self):
        self.snapshots = []

    def get_verified_competitors(self, partnumber, channel=None):
        return [
            {
                "market_listing_id": 1,
                "source_code": channel or "FALABELLA",
                "seller_name": "COMPETIDOR A",
                "price_effective": Decimal("1549"),
                "stock_state": "IN_STOCK",
                "observed_at": NOW - timedelta(hours=1),
                "data_quality_score": Decimal("95"),
            },
            {
                "market_listing_id": 2,
                "source_code": channel or "FALABELLA",
                "seller_name": "COMPETIDOR B",
                "price_effective": Decimal("1599"),
                "stock_state": "IN_STOCK",
                "observed_at": NOW - timedelta(hours=2),
                "data_quality_score": Decimal("92"),
            },
        ]

    def get_price_history(self, partnumber, channel=None, days=30):
        return [
            {
                "market_listing_id": 1,
                "source_code": channel or "FALABELLA",
                "seller_name": "COMPETIDOR A",
                "observed_at": NOW - timedelta(days=7),
                "price_effective": Decimal("1699"),
                "stock_state": "IN_STOCK",
                "data_quality_score": Decimal("90"),
            },
            {
                "market_listing_id": 1,
                "source_code": channel or "FALABELLA",
                "seller_name": "COMPETIDOR A",
                "observed_at": NOW - timedelta(hours=1),
                "price_effective": Decimal("1549"),
                "stock_state": "IN_STOCK",
                "data_quality_score": Decimal("95"),
            },
            {
                "market_listing_id": 2,
                "source_code": channel or "FALABELLA",
                "seller_name": "COMPETIDOR B",
                "observed_at": NOW - timedelta(days=7),
                "price_effective": Decimal("1649"),
                "stock_state": "IN_STOCK",
                "data_quality_score": Decimal("88"),
            },
            {
                "market_listing_id": 2,
                "source_code": channel or "FALABELLA",
                "seller_name": "COMPETIDOR B",
                "observed_at": NOW - timedelta(hours=2),
                "price_effective": Decimal("1599"),
                "stock_state": "IN_STOCK",
                "data_quality_score": Decimal("92"),
            },
        ]

    def get_supplier_history(self, partnumber, supplier=None, days=90):
        return [
            {
                "supplier_code": supplier or "DELTRON",
                "partnumber": partnumber,
                "observed_at": NOW - timedelta(days=5),
                "cost_pen": Decimal("1020"),
                "cost_usd": None,
                "currency": "PEN",
                "tax_included": True,
                "stock_qty": Decimal("20"),
                "stock_state": "IN_STOCK",
                "data_quality_score": Decimal("100"),
            },
            {
                "supplier_code": supplier or "DELTRON",
                "partnumber": partnumber,
                "observed_at": NOW - timedelta(hours=1),
                "cost_pen": Decimal("980"),
                "cost_usd": None,
                "currency": "PEN",
                "tax_included": True,
                "stock_qty": Decimal("25"),
                "stock_state": "IN_STOCK",
                "data_quality_score": Decimal("100"),
            },
        ]

    def get_pricing_policy(self, channel, category=None, brand=None, as_of=None):
        return {
            "policy_id": 10,
            "channel_code": channel,
            "category_code": category,
            "brand": brand,
            "minimum_margin_pct": Decimal("0.12"),
            "minimum_contribution_pen": Decimal("100"),
            "undercut_amount_pen": Decimal("1"),
            "strategy": "BALANCED",
        }

    def get_fee_rule(self, channel, category=None, as_of=None):
        return {
            "fee_rule_id": 20,
            "channel_code": channel,
            "category_code": category,
            "commission_pct": Decimal("0.08"),
            "fixed_fee_pen": Decimal("0"),
            "payment_fee_pct": Decimal("0.02"),
            "shipping_cost_pen": Decimal("15"),
            "free_shipping_threshold_pen": None,
            "seller_absorbs_shipping_above_threshold": False,
        }

    def get_latest_fx_rate(self, base_currency="USD", quote_currency="PEN", as_of=None):
        return {"rate": Decimal("3.50"), "observed_at": NOW}

    def get_internal_signal(self, partnumber, as_of=None):
        return {
            "partnumber": partnumber,
            "observed_at": NOW - timedelta(hours=1),
            "own_stock_qty": Decimal("3"),
            "sales_units_7d": Decimal("4"),
            "sales_units_30d": Decimal("12"),
            "sales_units_90d": Decimal("30"),
            "days_since_last_sale": 1,
            "inventory_age_days": 20,
            "own_sale_price_pen": Decimal("1699"),
            "source_code": "ERP",
        }

    def list_candidate_partnumbers(self, channel=None, limit=100):
        return ["82YU00XYLM"]

    def list_supplier_partnumbers(self, supplier=None, limit=100):
        return ["82YU00XYLM"]

    def save_recommendation_snapshot(self, snapshot):
        self.snapshots.append(snapshot)


def test_repository_can_discover_supplier_only_products():
    assert hasattr(MarketRepository, "list_supplier_partnumbers")


def test_end_to_end_analysis_sees_price_drop_profit_floor_and_supplier_drop():
    repo = AcceptanceMarketRepository()
    products = AcceptanceProducts()
    market = MarketIntelligenceService(
        market_repository=repo,
        product_repository=products,
        clock=lambda: NOW,
    )
    opportunities = MarketOpportunityService(
        market_service=market,
        market_repository=repo,
        product_repository=products,
        clock=lambda: NOW,
    )

    variations = market.variations_get("82YU00XYLM", "FALABELLA", windows=(7, 30))
    seller_a = next(item for item in variations["listings"] if item["market_listing_id"] == 1)
    assert seller_a["summary"]["current"] == Decimal("1549")
    assert seller_a["summary"]["previous"] == Decimal("1699")
    assert seller_a["summary"]["change_from_previous_pct"] < 0

    simulated = market.profit_simulate("82YU00XYLM", "FALABELLA", Decimal("1549"))
    assert simulated["simulated"] is True
    assert simulated["breakdown"]["contribution_pen"] > 0

    pricing = market.recommended_price("82YU00XYLM", "FALABELLA", strategy="BALANCED")
    assert pricing["recommended_price_pen"] >= pricing["floor_price_pen"]
    assert pricing["expected_margin_pct"] >= Decimal("0.12")

    analyzed = market.product_analyze("82YU00XYLM", "FALABELLA")
    assert 0 <= analyzed["opportunity_score"] <= 100
    assert 0 <= analyzed["confidence_score"] <= 100
    assert 0 <= analyzed["risk_score"] <= 100
    assert repo.snapshots

    supplier = opportunities.supplier_opportunities(supplier="DELTRON", category="LAPTOP")
    item = supplier["opportunities"][0]
    assert item["latest_cost_pen"] == Decimal("980")
    assert item["cost_change_pen"] == Decimal("-40")
    assert "SUPPLIER_COST_DROP" in item["reason_codes"]
