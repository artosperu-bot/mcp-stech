from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from stech_mcp.services.market_intelligence import MarketIntelligenceService


NOW = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)


class FakeProductRepository:
    def get_by_partnumber(self, partnumber):
        if partnumber == "MISSING":
            return None
        return {
            "part_number": partnumber,
            "partnumber": partnumber,
            "marca": "LENOVO",
            "categoria": "LAPTOP",
            "nombre": "Laptop Lenovo",
        }


class FakeMarketRepository:
    def __init__(self, competitor_prices=(Decimal("1500"), Decimal("1600"))):
        self.competitor_prices = list(competitor_prices)
        self.saved = []

    def get_verified_competitors(self, partnumber, channel=None):
        return [
            {
                "market_listing_id": index + 1,
                "source_code": channel or "FALABELLA",
                "seller_name": f"SELLER {index + 1}",
                "price_effective": price,
                "stock_state": "IN_STOCK",
                "observed_at": NOW - timedelta(hours=index + 1),
                "data_quality_score": Decimal("95"),
            }
            for index, price in enumerate(self.competitor_prices)
        ]

    def get_price_history(self, partnumber, channel=None, days=30):
        return [
            {
                "market_listing_id": 1,
                "source_code": channel or "FALABELLA",
                "seller_name": "SELLER 1",
                "observed_at": NOW - timedelta(days=5),
                "price_effective": Decimal("1600"),
                "stock_state": "IN_STOCK",
                "data_quality_score": Decimal("90"),
            },
            {
                "market_listing_id": 1,
                "source_code": channel or "FALABELLA",
                "seller_name": "SELLER 1",
                "observed_at": NOW - timedelta(hours=1),
                "price_effective": self.competitor_prices[0],
                "stock_state": "IN_STOCK",
                "data_quality_score": Decimal("95"),
            },
        ]

    def get_supplier_history(self, partnumber, supplier=None, days=90):
        return [
            {
                "supplier_code": "DELTRON",
                "partnumber": partnumber,
                "observed_at": NOW - timedelta(hours=2),
                "cost_pen": Decimal("1000"),
                "cost_usd": None,
                "currency": "PEN",
                "tax_included": True,
                "stock_qty": Decimal("20"),
                "stock_state": "IN_STOCK",
                "data_quality_score": Decimal("100"),
            }
        ]

    def get_pricing_policy(self, channel, category=None, brand=None, as_of=None):
        return {
            "policy_id": 1,
            "channel_code": channel,
            "category_code": category,
            "brand": brand,
            "minimum_margin_pct": Decimal("0.15"),
            "minimum_contribution_pen": Decimal("100"),
            "undercut_amount_pen": Decimal("1"),
            "strategy": "BALANCED",
        }

    def get_fee_rule(self, channel, category=None, as_of=None):
        return {
            "fee_rule_id": 1,
            "channel_code": channel,
            "category_code": category,
            "commission_pct": Decimal("0.10"),
            "fixed_fee_pen": Decimal("5"),
            "payment_fee_pct": Decimal("0.02"),
            "shipping_cost_pen": Decimal("20"),
            "free_shipping_threshold_pen": None,
            "seller_absorbs_shipping_above_threshold": False,
        }

    def get_latest_fx_rate(self, base_currency="USD", quote_currency="PEN", as_of=None):
        return {"rate": Decimal("3.50"), "observed_at": NOW}

    def get_internal_signal(self, partnumber, as_of=None):
        return {
            "partnumber": partnumber,
            "observed_at": NOW - timedelta(hours=3),
            "own_stock_qty": Decimal("5"),
            "sales_units_7d": Decimal("2"),
            "sales_units_30d": Decimal("8"),
            "sales_units_90d": Decimal("18"),
            "days_since_last_sale": 1,
            "inventory_age_days": 25,
            "own_sale_price_pen": Decimal("1550"),
            "source_code": "ERP",
        }

    def save_recommendation_snapshot(self, snapshot):
        self.saved.append(snapshot)


def build_service(prices=(Decimal("1500"), Decimal("1600"))):
    return MarketIntelligenceService(
        market_repository=FakeMarketRepository(prices),
        product_repository=FakeProductRepository(),
        clock=lambda: NOW,
    )


def test_profit_simulate_uses_configured_channel_fees():
    result = build_service().profit_simulate("82YU00XYLM", "FALABELLA", Decimal("1500"))

    assert result["found"] is True
    assert result["cost_source"] == "DELTRON"
    assert result["breakdown"]["contribution_pen"] == Decimal("295.0000")
    assert result["breakdown"]["margin_pct"] == Decimal("0.1966666667")


def test_variations_are_calculated_per_listing_not_mixed_between_sellers():
    result = build_service().variations_get("82YU00XYLM", "FALABELLA", windows=(1, 7, 30))

    assert result["found"] is True
    listing = result["listings"][0]
    assert listing["market_listing_id"] == 1
    assert listing["summary"]["previous"] == Decimal("1600")
    assert listing["summary"]["current"] == Decimal("1500")
    assert listing["summary"]["change_from_previous_pct"] == Decimal("-0.0625000000")


def test_recommended_price_never_breaks_floor_in_balanced_strategy():
    result = build_service().recommended_price("82YU00XYLM", "FALABELLA", strategy="BALANCED")

    assert result["recommended_price_pen"] >= result["floor_price_pen"]
    assert result["expected_margin_pct"] >= Decimal("0.15")


def test_market_below_floor_returns_no_competir():
    result = build_service((Decimal("1300"), Decimal("1350"))).recommended_price(
        "82YU00XYLM", "FALABELLA"
    )

    assert result["action_code"] == "NO_COMPETIR"
    assert "MARKET_BELOW_FLOOR" in result["reason_codes"]
    assert result["floor_price_pen"] > result["market_min_price_pen"]


def test_clearance_can_cross_normal_floor_but_marks_exception_explicitly():
    result = build_service((Decimal("1300"), Decimal("1350"))).recommended_price(
        "82YU00XYLM", "FALABELLA", strategy="CLEARANCE"
    )

    assert result["recommended_price_pen"] < result["floor_price_pen"]
    assert "CLEARANCE_BELOW_NORMAL_FLOOR" in result["reason_codes"]
    assert result["exceptional_margin"] is True


def test_missing_product_is_explicit_not_inferred():
    result = build_service().product_analyze("MISSING", "FALABELLA")
    assert result == {"found": False, "partnumber": "MISSING", "reason": "product_not_found"}
