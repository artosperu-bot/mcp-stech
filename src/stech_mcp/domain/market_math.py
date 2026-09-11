from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP, localcontext
from statistics import median
from typing import Any, Iterable

_MONEY = Decimal("0.0001")
_RATIO = Decimal("0.0000000001")


def _d(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY, rounding=ROUND_HALF_UP)


def _ratio(value: Decimal) -> Decimal:
    return value.quantize(_RATIO, rounding=ROUND_HALF_UP)


def percent_change(previous: Decimal | None, current: Decimal | None) -> Decimal | None:
    previous = _d(previous)
    current = _d(current)
    if previous is None or current is None or previous == 0:
        return None
    return _ratio((current - previous) / previous)


def calculate_profit(
    *,
    sale_price_pen: Decimal,
    product_cost_pen: Decimal,
    commission_pct: Decimal,
    payment_fee_pct: Decimal,
    fixed_fee_pen: Decimal,
    shipping_cost_pen: Decimal,
    other_cost_pen: Decimal = Decimal("0"),
) -> dict[str, Decimal]:
    sale_price_pen = _d(sale_price_pen) or Decimal("0")
    if sale_price_pen <= 0:
        raise ValueError("sale_price_pen must be greater than zero")

    product_cost_pen = _d(product_cost_pen) or Decimal("0")
    commission_pct = _d(commission_pct) or Decimal("0")
    payment_fee_pct = _d(payment_fee_pct) or Decimal("0")
    fixed_fee_pen = _d(fixed_fee_pen) or Decimal("0")
    shipping_cost_pen = _d(shipping_cost_pen) or Decimal("0")
    other_cost_pen = _d(other_cost_pen) or Decimal("0")

    commission_pen = _money(sale_price_pen * commission_pct)
    payment_fee_pen = _money(sale_price_pen * payment_fee_pct)
    contribution_pen = _money(
        sale_price_pen
        - product_cost_pen
        - commission_pen
        - payment_fee_pen
        - fixed_fee_pen
        - shipping_cost_pen
        - other_cost_pen
    )
    margin_pct = _ratio(contribution_pen / sale_price_pen)

    return {
        "sale_price_pen": _money(sale_price_pen),
        "product_cost_pen": _money(product_cost_pen),
        "commission_pen": commission_pen,
        "payment_fee_pen": payment_fee_pen,
        "fixed_fee_pen": _money(fixed_fee_pen),
        "shipping_cost_pen": _money(shipping_cost_pen),
        "other_cost_pen": _money(other_cost_pen),
        "contribution_pen": contribution_pen,
        "margin_pct": margin_pct,
    }


def calculate_floor_price(
    *,
    product_cost_pen: Decimal,
    commission_pct: Decimal,
    payment_fee_pct: Decimal,
    fixed_fee_pen: Decimal,
    shipping_cost_pen: Decimal,
    minimum_margin_pct: Decimal,
    minimum_contribution_pen: Decimal,
    other_cost_pen: Decimal = Decimal("0"),
) -> Decimal:
    product_cost_pen = _d(product_cost_pen) or Decimal("0")
    commission_pct = _d(commission_pct) or Decimal("0")
    payment_fee_pct = _d(payment_fee_pct) or Decimal("0")
    fixed_fee_pen = _d(fixed_fee_pen) or Decimal("0")
    shipping_cost_pen = _d(shipping_cost_pen) or Decimal("0")
    minimum_margin_pct = _d(minimum_margin_pct) or Decimal("0")
    minimum_contribution_pen = _d(minimum_contribution_pen) or Decimal("0")
    other_cost_pen = _d(other_cost_pen) or Decimal("0")

    variable_rate = commission_pct + payment_fee_pct
    fixed_cost = product_cost_pen + fixed_fee_pen + shipping_cost_pen + other_cost_pen
    margin_denominator = Decimal("1") - variable_rate - minimum_margin_pct
    contribution_denominator = Decimal("1") - variable_rate
    if margin_denominator <= 0 or contribution_denominator <= 0:
        raise ValueError("fees and minimum margin leave no feasible sale price")

    margin_floor = fixed_cost / margin_denominator
    contribution_floor = (fixed_cost + minimum_contribution_pen) / contribution_denominator
    raw = max(margin_floor, contribution_floor)
    return raw.quantize(_MONEY, rounding=ROUND_CEILING)


def _normalize_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    raise ValueError("observed_at must be datetime")


def _stddev_population(values: list[Decimal]) -> Decimal:
    if len(values) < 2:
        return Decimal("0")
    with localcontext() as ctx:
        ctx.prec = 28
        mean_value = sum(values, Decimal("0")) / Decimal(len(values))
        variance = sum(((value - mean_value) ** 2 for value in values), Decimal("0")) / Decimal(len(values))
        return variance.sqrt()


def summarize_series(
    observations: Iterable[dict[str, Any]],
    *,
    as_of: datetime,
    windows: tuple[int, ...] = (1, 7, 30, 90),
    value_key: str = "price_effective",
) -> dict[str, Any]:
    as_of = _normalize_time(as_of)
    rows: list[tuple[datetime, Decimal]] = []
    for row in observations:
        value = _d(row.get(value_key))
        observed_at = row.get("observed_at")
        if value is None or observed_at is None:
            continue
        observed_dt = _normalize_time(observed_at)
        if observed_dt <= as_of:
            rows.append((observed_dt, value))
    rows.sort(key=lambda item: item[0])

    if not rows:
        return {
            "count": 0,
            "current": None,
            "previous": None,
            "change_from_previous_abs": None,
            "change_from_previous_pct": None,
            "min": None,
            "max": None,
            "mean": None,
            "median": None,
            "volatility_pct": None,
            "days_since_last_change": None,
            "windows": {f"{day}d": {"reference": None, "change_abs": None, "change_pct": None} for day in windows},
        }

    values = [value for _, value in rows]
    current = values[-1]
    previous = values[-2] if len(values) > 1 else None
    mean_value = sum(values, Decimal("0")) / Decimal(len(values))
    median_value = Decimal(str(median(values)))
    volatility_pct = None if mean_value == 0 else _ratio(_stddev_population(values) / mean_value)

    last_change_at = rows[-1][0]
    for index in range(len(rows) - 2, -1, -1):
        if rows[index][1] != current:
            last_change_at = rows[index + 1][0]
            break
    days_since_last_change = Decimal(str((as_of - last_change_at).total_seconds() / 86400)).quantize(Decimal("0.01"))

    window_result: dict[str, Any] = {}
    for day in windows:
        cutoff = as_of - timedelta(days=day)
        candidates = [(dt, value) for dt, value in rows if dt >= cutoff]
        reference = candidates[0][1] if candidates else None
        window_result[f"{day}d"] = {
            "reference": reference,
            "change_abs": _money(current - reference) if reference is not None else None,
            "change_pct": percent_change(reference, current) if reference is not None else None,
        }

    return {
        "count": len(rows),
        "current": current,
        "previous": previous,
        "change_from_previous_abs": _money(current - previous) if previous is not None else None,
        "change_from_previous_pct": percent_change(previous, current),
        "min": min(values),
        "max": max(values),
        "mean": _money(mean_value),
        "median": median_value,
        "volatility_pct": volatility_pct,
        "days_since_last_change": days_since_last_change,
        "windows": window_result,
    }
