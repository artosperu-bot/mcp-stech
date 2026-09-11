from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from stech_mcp.domain.market_math import (
    calculate_floor_price,
    calculate_profit,
    percent_change,
    summarize_series,
)


def test_profit_returns_full_contribution_breakdown():
    result = calculate_profit(
        sale_price_pen=Decimal("1500"),
        product_cost_pen=Decimal("1000"),
        commission_pct=Decimal("0.10"),
        payment_fee_pct=Decimal("0.02"),
        fixed_fee_pen=Decimal("5"),
        shipping_cost_pen=Decimal("20"),
    )

    assert result["commission_pen"] == Decimal("150.0000")
    assert result["payment_fee_pen"] == Decimal("30.0000")
    assert result["contribution_pen"] == Decimal("295.0000")
    assert result["margin_pct"] == Decimal("0.1966666667")


def test_floor_price_satisfies_margin_and_minimum_contribution():
    floor = calculate_floor_price(
        product_cost_pen=Decimal("1000"),
        commission_pct=Decimal("0.10"),
        payment_fee_pct=Decimal("0.02"),
        fixed_fee_pen=Decimal("5"),
        shipping_cost_pen=Decimal("20"),
        minimum_margin_pct=Decimal("0.15"),
        minimum_contribution_pen=Decimal("100"),
    )
    result = calculate_profit(
        sale_price_pen=floor,
        product_cost_pen=Decimal("1000"),
        commission_pct=Decimal("0.10"),
        payment_fee_pct=Decimal("0.02"),
        fixed_fee_pen=Decimal("5"),
        shipping_cost_pen=Decimal("20"),
    )
    assert result["margin_pct"] >= Decimal("0.15")
    assert result["contribution_pen"] >= Decimal("100")


def test_percent_change_handles_zero_and_negative_values_safely():
    assert percent_change(Decimal("100"), Decimal("120")) == Decimal("0.2000000000")
    assert percent_change(Decimal("0"), Decimal("10")) is None
    assert percent_change(None, Decimal("10")) is None


def test_summarize_series_returns_window_variations_and_statistics():
    as_of = datetime(2026, 9, 10, 12, tzinfo=timezone.utc)
    rows = [
        {"observed_at": as_of - timedelta(days=40), "price_effective": Decimal("1800")},
        {"observed_at": as_of - timedelta(days=20), "price_effective": Decimal("1700")},
        {"observed_at": as_of - timedelta(days=5), "price_effective": Decimal("1600")},
        {"observed_at": as_of - timedelta(hours=2), "price_effective": Decimal("1500")},
    ]

    result = summarize_series(rows, as_of=as_of, windows=(1, 7, 30, 90))

    assert result["count"] == 4
    assert result["current"] == Decimal("1500")
    assert result["previous"] == Decimal("1600")
    assert result["change_from_previous_pct"] == Decimal("-0.0625000000")
    assert result["min"] == Decimal("1500")
    assert result["max"] == Decimal("1800")
    assert result["median"] == Decimal("1650")
    assert result["windows"]["7d"]["reference"] == Decimal("1600")
    assert result["windows"]["30d"]["reference"] == Decimal("1700")


def test_summarize_series_handles_no_prices():
    result = summarize_series([], as_of=datetime.now(timezone.utc))
    assert result["count"] == 0
    assert result["current"] is None
    assert result["volatility_pct"] is None


def test_profit_rejects_non_positive_sale_price():
    with pytest.raises(ValueError, match="sale_price_pen"):
        calculate_profit(
            sale_price_pen=Decimal("0"),
            product_cost_pen=Decimal("1000"),
            commission_pct=Decimal("0.10"),
            payment_fee_pct=Decimal("0.02"),
            fixed_fee_pen=Decimal("0"),
            shipping_cost_pen=Decimal("0"),
        )
