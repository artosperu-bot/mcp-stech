from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from statistics import median
from typing import Any, Callable

from stech_mcp.domain.market_math import calculate_floor_price, calculate_profit, summarize_series
from stech_mcp.domain.market_models import DEFAULT_OPPORTUNITY_WEIGHTS
from stech_mcp.domain.opportunity_score import gate_action, score_confidence, score_opportunity, score_risk


_VALID_STRATEGIES = {"BALANCED", "MARGIN", "VOLUME", "CLEARANCE"}


def _d(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _age_days(now: datetime, observed_at: Any) -> float | None:
    if not isinstance(observed_at, datetime):
        return None
    return max(0.0, (_utc(now) - _utc(observed_at)).total_seconds() / 86400.0)


def _freshness_score(age_days: float | None) -> float:
    if age_days is None:
        return 0.0
    if age_days <= 1:
        return 100.0
    if age_days <= 3:
        return 90.0
    if age_days <= 7:
        return 75.0
    if age_days <= 14:
        return 55.0
    if age_days <= 30:
        return 35.0
    return 10.0


def _bounded(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


class MarketIntelligenceService:
    def __init__(
        self,
        *,
        market_repository: Any,
        product_repository: Any,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.market_repository = market_repository
        self.product_repository = product_repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _normalize_partnumber(partnumber: str) -> str:
        normalized = str(partnumber or "").strip().upper()
        if not normalized:
            raise ValueError("partnumber is required")
        return normalized

    @staticmethod
    def _normalize_channel(channel: str | None) -> str | None:
        normalized = str(channel or "").strip().upper()
        return normalized or None

    @staticmethod
    def _product_brand(product: dict[str, Any]) -> str | None:
        for key in ("brand", "marca", "marca_nombre"):
            value = str(product.get(key) or "").strip().upper()
            if value:
                return value
        return None

    @staticmethod
    def _product_category(product: dict[str, Any]) -> str | None:
        for key in ("category_code", "categoria", "categoria_nombre", "rubro", "familia"):
            value = str(product.get(key) or "").strip().upper()
            if value:
                return value
        return None

    def _get_product(self, partnumber: str) -> tuple[str, dict[str, Any] | None]:
        pn = self._normalize_partnumber(partnumber)
        return pn, self.product_repository.get_by_partnumber(pn)

    def competitors_get(self, partnumber: str, channel: str | None = None) -> dict[str, Any]:
        pn, product = self._get_product(partnumber)
        if product is None:
            return {"found": False, "partnumber": pn, "reason": "product_not_found"}
        rows = self.market_repository.get_verified_competitors(pn, channel=self._normalize_channel(channel))
        return {
            "found": True,
            "partnumber": pn,
            "channel": self._normalize_channel(channel),
            "count": len(rows),
            "competitors": rows,
            "verified_only": True,
            "as_of": self.clock(),
        }

    def price_history(self, partnumber: str, channel: str | None = None, days: int = 30) -> dict[str, Any]:
        pn, product = self._get_product(partnumber)
        if product is None:
            return {"found": False, "partnumber": pn, "reason": "product_not_found"}
        safe_days = max(1, min(int(days), 3650))
        rows = self.market_repository.get_price_history(pn, channel=self._normalize_channel(channel), days=safe_days)
        return {
            "found": True,
            "partnumber": pn,
            "channel": self._normalize_channel(channel),
            "days": safe_days,
            "count": len(rows),
            "observations": rows,
            "as_of": self.clock(),
        }

    def variations_get(
        self,
        partnumber: str,
        channel: str | None = None,
        *,
        windows: tuple[int, ...] = (1, 7, 30, 90),
    ) -> dict[str, Any]:
        pn, product = self._get_product(partnumber)
        if product is None:
            return {"found": False, "partnumber": pn, "reason": "product_not_found"}
        clean_windows = tuple(sorted({max(1, min(int(day), 3650)) for day in windows})) or (30,)
        rows = self.market_repository.get_price_history(
            pn,
            channel=self._normalize_channel(channel),
            days=max(clean_windows),
        )
        grouped: dict[Any, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[row.get("market_listing_id")].append(row)

        listings = []
        for listing_id, observations in grouped.items():
            first = observations[0]
            listings.append(
                {
                    "market_listing_id": listing_id,
                    "source_code": first.get("source_code"),
                    "seller_name": first.get("seller_name"),
                    "summary": summarize_series(
                        observations,
                        as_of=self.clock(),
                        windows=clean_windows,
                    ),
                }
            )
        listings.sort(key=lambda item: (str(item.get("source_code") or ""), str(item.get("seller_name") or ""), str(item.get("market_listing_id") or "")))
        return {
            "found": True,
            "partnumber": pn,
            "channel": self._normalize_channel(channel),
            "windows": list(clean_windows),
            "listing_count": len(listings),
            "observation_count": len(rows),
            "listings": listings,
            "as_of": self.clock(),
        }

    def _supplier_context(self, partnumber: str) -> dict[str, Any] | None:
        rows = self.market_repository.get_supplier_history(partnumber, days=90)
        if not rows:
            return None
        now = self.clock()
        latest_by_supplier: dict[str, dict[str, Any]] = {}
        for row in sorted(rows, key=lambda item: item.get("observed_at") or datetime.min.replace(tzinfo=timezone.utc), reverse=True):
            supplier = str(row.get("supplier_code") or "UNKNOWN").upper()
            latest_by_supplier.setdefault(supplier, row)

        candidates: list[dict[str, Any]] = []
        for supplier, row in latest_by_supplier.items():
            cost_pen = _d(row.get("cost_pen"))
            cost_usd = _d(row.get("cost_usd"))
            tax_included = bool(row.get("tax_included"))
            fx = None
            if cost_pen is not None:
                effective_cost = cost_pen if tax_included else cost_pen * Decimal("1.18")
            elif cost_usd is not None:
                fx_row = self.market_repository.get_latest_fx_rate("USD", "PEN", as_of=now)
                fx = _d((fx_row or {}).get("rate"))
                if fx is None:
                    continue
                effective_cost = cost_usd * fx
                if not tax_included:
                    effective_cost *= Decimal("1.18")
            else:
                continue
            candidates.append(
                {
                    "supplier_code": supplier,
                    "cost_pen": effective_cost.quantize(Decimal("0.0001")),
                    "raw": row,
                    "fx_rate": fx,
                    "age_days": _age_days(now, row.get("observed_at")),
                }
            )
        if not candidates:
            return None
        in_stock = [item for item in candidates if str(item["raw"].get("stock_state") or "").upper() in {"IN_STOCK", "LOW_STOCK"}]
        pool = in_stock or candidates
        return min(pool, key=lambda item: item["cost_pen"])

    def _commercial_context(self, partnumber: str, channel: str) -> dict[str, Any] | None:
        product = self.product_repository.get_by_partnumber(partnumber)
        if product is None:
            return None
        category = self._product_category(product)
        brand = self._product_brand(product)
        now = self.clock()
        policy = self.market_repository.get_pricing_policy(
            channel,
            category=category,
            brand=brand,
            as_of=now,
        )
        fee_rule = self.market_repository.get_fee_rule(channel, category=category, as_of=now)
        supplier = self._supplier_context(partnumber)
        competitors = self.market_repository.get_verified_competitors(partnumber, channel=channel)
        history = self.market_repository.get_price_history(partnumber, channel=channel, days=90)
        internal = self.market_repository.get_internal_signal(partnumber, as_of=now)
        return {
            "product": product,
            "category": category,
            "brand": brand,
            "policy": policy,
            "fee_rule": fee_rule,
            "supplier": supplier,
            "competitors": competitors,
            "history": history,
            "internal": internal,
            "as_of": now,
        }

    @staticmethod
    def _shipping_cost(fee_rule: dict[str, Any], sale_price: Decimal) -> Decimal:
        shipping = _d(fee_rule.get("shipping_cost_pen")) or Decimal("0")
        threshold = _d(fee_rule.get("free_shipping_threshold_pen"))
        absorbs = bool(fee_rule.get("seller_absorbs_shipping_above_threshold"))
        if threshold is not None and sale_price >= threshold and not absorbs:
            return Decimal("0")
        return shipping

    def profit_simulate(
        self,
        partnumber: str,
        channel: str,
        sale_price_pen: Decimal | float | int,
        *,
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        pn, product = self._get_product(partnumber)
        market = self._normalize_channel(channel)
        if product is None:
            return {"found": False, "partnumber": pn, "reason": "product_not_found"}
        if market is None:
            raise ValueError("channel is required")
        context = self._commercial_context(pn, market)
        assert context is not None
        overrides = overrides or {}
        supplier = context["supplier"]
        fee = context["fee_rule"]
        reasons: list[str] = []
        cost_pen = _d(overrides.get("product_cost_pen"))
        cost_source = "OVERRIDE" if cost_pen is not None else None
        if cost_pen is None and supplier is not None:
            cost_pen = supplier["cost_pen"]
            cost_source = supplier["supplier_code"]
        if cost_pen is None:
            reasons.append("SUPPLIER_COST_MISSING")
        if fee is None and not any(key in overrides for key in ("commission_pct", "payment_fee_pct", "fixed_fee_pen", "shipping_cost_pen")):
            reasons.append("CHANNEL_FEE_RULE_MISSING")
        if reasons:
            return {
                "found": True,
                "partnumber": pn,
                "channel": market,
                "simulated": False,
                "reason_codes": reasons,
            }

        fee = fee or {}
        sale_price = _d(sale_price_pen)
        if sale_price is None:
            raise ValueError("sale_price_pen is required")
        commission = _d(overrides.get("commission_pct"))
        if commission is None:
            commission = _d(fee.get("commission_pct")) or Decimal("0")
        payment_fee = _d(overrides.get("payment_fee_pct"))
        if payment_fee is None:
            payment_fee = _d(fee.get("payment_fee_pct")) or Decimal("0")
        fixed_fee = _d(overrides.get("fixed_fee_pen"))
        if fixed_fee is None:
            fixed_fee = _d(fee.get("fixed_fee_pen")) or Decimal("0")
        shipping = _d(overrides.get("shipping_cost_pen"))
        if shipping is None:
            shipping = self._shipping_cost(fee, sale_price)
        other_cost = _d(overrides.get("other_cost_pen")) or Decimal("0")
        breakdown = calculate_profit(
            sale_price_pen=sale_price,
            product_cost_pen=cost_pen,
            commission_pct=commission,
            payment_fee_pct=payment_fee,
            fixed_fee_pen=fixed_fee,
            shipping_cost_pen=shipping,
            other_cost_pen=other_cost,
        )
        return {
            "found": True,
            "partnumber": pn,
            "channel": market,
            "simulated": True,
            "cost_source": cost_source,
            "breakdown": breakdown,
            "fee_rule_id": fee.get("fee_rule_id"),
            "as_of": context["as_of"],
            "reason_codes": [],
        }

    def _confidence(self, context: dict[str, Any]) -> float:
        now = context["as_of"]
        competitors = context["competitors"]
        history = context["history"]
        supplier = context["supplier"]
        internal = context["internal"]
        competitor_age = min(
            (_age_days(now, row.get("observed_at")) for row in competitors),
            default=None,
        )
        supplier_age = supplier.get("age_days") if supplier else None
        present = [
            bool(context.get("policy")),
            bool(context.get("fee_rule")),
            bool(supplier),
            bool(competitors),
            bool(history),
            bool(internal),
        ]
        observed_input_pct = sum(1 for value in present if value) / len(present) * 100.0
        return score_confidence(
            {
                "identity_verified": True,
                "supplier_freshness": _freshness_score(supplier_age),
                "competitor_freshness": _freshness_score(competitor_age),
                "competitor_count": len(competitors),
                "history_depth": len(history),
                "internal_signal_quality": 100 if internal else 0,
                "observed_input_pct": observed_input_pct,
            }
        )

    @staticmethod
    def _price_war(history: list[dict[str, Any]]) -> bool:
        grouped: dict[Any, list[dict[str, Any]]] = defaultdict(list)
        for row in history:
            grouped[row.get("market_listing_id")].append(row)
        drops = 0
        for rows in grouped.values():
            ordered = sorted(rows, key=lambda item: item.get("observed_at") or datetime.min.replace(tzinfo=timezone.utc))
            previous = None
            for row in ordered:
                price = _d(row.get("price_effective"))
                if price is None:
                    continue
                if previous is not None and price < previous:
                    drops += 1
                previous = price
        return drops >= 3

    def _risk(self, context: dict[str, Any], floor_price: Decimal | None = None) -> float:
        history = context["history"]
        competitors = context["competitors"]
        now = context["as_of"]
        supplier = context["supplier"]
        internal = context["internal"] or {}
        grouped: dict[Any, list[dict[str, Any]]] = defaultdict(list)
        for row in history:
            grouped[row.get("market_listing_id")].append(row)
        summaries = [summarize_series(rows, as_of=now) for rows in grouped.values()]
        volatility = max((float(summary["volatility_pct"] or 0) for summary in summaries), default=0.0)
        latest_age = min((_age_days(now, row.get("observed_at")) for row in competitors), default=None)
        prices = [_d(row.get("price_effective")) for row in competitors]
        clean_prices = [price for price in prices if price is not None and price > 0]
        market_min = min(clean_prices) if clean_prices else None

        if floor_price is not None and market_min is not None and market_min > 0:
            headroom = (market_min - floor_price) / market_min
            margin_risk = _bounded(100.0 - float(headroom) * 1000.0)
        else:
            margin_risk = 50.0
        supplier_state = str(((supplier or {}).get("raw") or {}).get("stock_state") or "UNKNOWN").upper()
        supplier_risk = 0.0 if supplier_state == "IN_STOCK" else 30.0 if supplier_state == "LOW_STOCK" else 70.0 if supplier_state == "UNKNOWN" else 100.0
        decline = 0.0
        for summary in summaries:
            delta = summary.get("change_from_previous_pct")
            if delta is not None and delta < 0:
                decline = max(decline, min(100.0, abs(float(delta)) * 1000.0))
        staleness = 100.0 if latest_age is None else _bounded(latest_age / 14.0 * 100.0)
        aging = _bounded(float(internal.get("inventory_age_days") or 0) / 180.0 * 100.0)
        return score_risk(
            {
                "margin_headroom_score": margin_risk,
                "price_volatility_score": _bounded(volatility * 1000.0),
                "price_war": self._price_war(history),
                "supplier_risk_score": supplier_risk,
                "market_decline_score": decline,
                "seller_pressure_score": _bounded(len(competitors) * 10.0),
                "staleness_score": staleness,
                "inventory_aging_score": aging,
            }
        )

    def data_quality(self, partnumber: str, channel: str | None = None) -> dict[str, Any]:
        pn, product = self._get_product(partnumber)
        if product is None:
            return {"found": False, "partnumber": pn, "reason": "product_not_found"}
        market = self._normalize_channel(channel)
        if market is None:
            competitors = self.market_repository.get_verified_competitors(pn, channel=None)
            history = self.market_repository.get_price_history(pn, channel=None, days=90)
            supplier = self._supplier_context(pn)
            internal = self.market_repository.get_internal_signal(pn, as_of=self.clock())
            context = {
                "competitors": competitors,
                "history": history,
                "supplier": supplier,
                "internal": internal,
                "policy": None,
                "fee_rule": None,
                "as_of": self.clock(),
            }
        else:
            context = self._commercial_context(pn, market)
            assert context is not None
        return {
            "found": True,
            "partnumber": pn,
            "channel": market,
            "confidence_score": self._confidence(context),
            "verified_competitor_count": len(context["competitors"]),
            "history_depth": len(context["history"]),
            "supplier_available": bool(context["supplier"]),
            "internal_signal_available": bool(context["internal"]),
            "as_of": context["as_of"],
        }

    def recommended_price(self, partnumber: str, channel: str, *, strategy: str = "BALANCED") -> dict[str, Any]:
        pn, product = self._get_product(partnumber)
        market = self._normalize_channel(channel)
        if product is None:
            return {"found": False, "partnumber": pn, "reason": "product_not_found"}
        if market is None:
            raise ValueError("channel is required")
        strategy_code = str(strategy or "BALANCED").strip().upper()
        if strategy_code not in _VALID_STRATEGIES:
            raise ValueError("invalid strategy")
        context = self._commercial_context(pn, market)
        assert context is not None
        policy = context["policy"]
        fee = context["fee_rule"]
        supplier = context["supplier"]
        missing = []
        if policy is None:
            missing.append("PRICING_POLICY_MISSING")
        if fee is None:
            missing.append("CHANNEL_FEE_RULE_MISSING")
        if supplier is None:
            missing.append("SUPPLIER_COST_MISSING")
        confidence = self._confidence(context)
        if missing:
            return {
                "found": True,
                "partnumber": pn,
                "channel": market,
                "action_code": "INVESTIGAR",
                "strategy": strategy_code,
                "confidence_score": confidence,
                "risk_score": 100.0,
                "reason_codes": missing,
                "recommended_price_pen": None,
                "floor_price_pen": None,
                "market_min_price_pen": None,
                "market_median_price_pen": None,
                "expected_profit_pen": None,
                "expected_margin_pct": None,
                "exceptional_margin": False,
                "as_of": context["as_of"],
            }

        cost_pen = supplier["cost_pen"]
        commission = _d(fee.get("commission_pct")) or Decimal("0")
        payment_fee = _d(fee.get("payment_fee_pct")) or Decimal("0")
        fixed_fee = _d(fee.get("fixed_fee_pen")) or Decimal("0")
        minimum_margin = _d(policy.get("minimum_margin_pct")) or Decimal("0")
        minimum_contribution = _d(policy.get("minimum_contribution_pen")) or Decimal("0")
        undercut = _d(policy.get("undercut_amount_pen")) or Decimal("1")
        # Floor shipping uses the configured seller-borne cost. If a threshold can
        # remove seller cost, using the non-discounted shipping amount is conservative.
        normal_shipping = _d(fee.get("shipping_cost_pen")) or Decimal("0")
        floor_price = calculate_floor_price(
            product_cost_pen=cost_pen,
            commission_pct=commission,
            payment_fee_pct=payment_fee,
            fixed_fee_pen=fixed_fee,
            shipping_cost_pen=normal_shipping,
            minimum_margin_pct=minimum_margin,
            minimum_contribution_pen=minimum_contribution,
        )

        prices = sorted(
            price
            for row in context["competitors"]
            if (price := _d(row.get("price_effective"))) is not None and price > 0
        )
        market_min = min(prices) if prices else None
        market_median = Decimal(str(median(prices))) if prices else None
        reasons: list[str] = []
        exceptional = False

        if strategy_code != "CLEARANCE" and market_min is not None and market_min < floor_price:
            target = floor_price
            action = "NO_COMPETIR"
            reasons.append("MARKET_BELOW_FLOOR")
        elif not prices:
            target = floor_price
            action = "INVESTIGAR"
            reasons.append("NO_VERIFIED_COMPETITOR_PRICE")
        elif strategy_code == "CLEARANCE":
            target = max(Decimal("0.01"), market_min - undercut)
            exceptional = target < floor_price
            if exceptional:
                reasons.append("CLEARANCE_BELOW_NORMAL_FLOOR")
            action = "LIQUIDAR" if _d((context["internal"] or {}).get("own_stock_qty")) not in (None, Decimal("0")) else "PUBLICAR"
        elif strategy_code == "VOLUME":
            target = max(floor_price, market_min - undercut)
            action = "MANTENER"
        elif strategy_code == "MARGIN":
            target = max(floor_price, market_median or market_min)
            action = "MANTENER"
        else:
            competitive_band = market_min + ((market_median or market_min) - market_min) * Decimal("0.25")
            target = max(floor_price, competitive_band)
            action = "MANTENER"

        target = target.quantize(Decimal("0.0001"))
        own_price = _d((context["internal"] or {}).get("own_sale_price_pen"))
        if action not in {"NO_COMPETIR", "INVESTIGAR", "LIQUIDAR", "PUBLICAR"}:
            if own_price is None:
                action = "PUBLICAR"
                reasons.append("NO_STECH_PRICE")
            elif target < own_price - Decimal("1"):
                action = "BAJAR_PRECIO"
            elif target > own_price + Decimal("1"):
                action = "SUBIR_PRECIO"
            else:
                action = "MANTENER"

        shipping = self._shipping_cost(fee, target)
        expected = calculate_profit(
            sale_price_pen=target,
            product_cost_pen=cost_pen,
            commission_pct=commission,
            payment_fee_pct=payment_fee,
            fixed_fee_pen=fixed_fee,
            shipping_cost_pen=shipping,
        )
        risk = self._risk(context, floor_price=floor_price)
        gated_action = gate_action(action, confidence, risk)
        if gated_action != action:
            reasons.append("ACTION_GATED_BY_CONFIDENCE_OR_RISK")
        return {
            "found": True,
            "partnumber": pn,
            "channel": market,
            "action_code": gated_action,
            "raw_action_code": action,
            "strategy": strategy_code,
            "recommended_price_pen": target,
            "floor_price_pen": floor_price,
            "market_min_price_pen": market_min,
            "market_median_price_pen": market_median,
            "expected_profit_pen": expected["contribution_pen"],
            "expected_margin_pct": expected["margin_pct"],
            "cost_pen": cost_pen,
            "cost_source": supplier["supplier_code"],
            "confidence_score": confidence,
            "risk_score": risk,
            "reason_codes": reasons,
            "exceptional_margin": exceptional,
            "as_of": context["as_of"],
        }

    def risk_analyze(self, partnumber: str, channel: str | None = None) -> dict[str, Any]:
        pn, product = self._get_product(partnumber)
        if product is None:
            return {"found": False, "partnumber": pn, "reason": "product_not_found"}
        market = self._normalize_channel(channel)
        if market is None:
            competitors = self.market_repository.get_verified_competitors(pn, channel=None)
            history = self.market_repository.get_price_history(pn, channel=None, days=90)
            context = {
                "competitors": competitors,
                "history": history,
                "supplier": self._supplier_context(pn),
                "internal": self.market_repository.get_internal_signal(pn, as_of=self.clock()),
                "as_of": self.clock(),
            }
            floor = None
        else:
            context = self._commercial_context(pn, market)
            assert context is not None
            pricing = self.recommended_price(pn, market)
            floor = pricing.get("floor_price_pen")
        risk = self._risk(context, floor_price=floor)
        reasons = []
        if self._price_war(context["history"]):
            reasons.append("PRICE_WAR_SIGNAL")
        if risk >= 70:
            reasons.append("HIGH_MARKET_RISK")
        return {
            "found": True,
            "partnumber": pn,
            "channel": market,
            "risk_score": risk,
            "reason_codes": reasons,
            "as_of": context["as_of"],
        }

    def product_analyze(self, partnumber: str, channel: str | None = None) -> dict[str, Any]:
        pn, product = self._get_product(partnumber)
        if product is None:
            return {"found": False, "partnumber": pn, "reason": "product_not_found"}
        market = self._normalize_channel(channel)
        if market is None:
            quality = self.data_quality(pn)
            risk = self.risk_analyze(pn)
            return {
                "found": True,
                "partnumber": pn,
                "channel": None,
                "action_code": "INVESTIGAR",
                "opportunity_score": None,
                "confidence_score": quality["confidence_score"],
                "risk_score": risk["risk_score"],
                "reason_codes": ["CHANNEL_REQUIRED_FOR_PRICING"],
                "as_of": self.clock(),
            }

        context = self._commercial_context(pn, market)
        assert context is not None
        pricing = self.recommended_price(pn, market)
        internal = context["internal"] or {}
        supplier = context["supplier"]
        expected_margin = _d(pricing.get("expected_margin_pct"))
        profitability = None if expected_margin is None else _bounded(float(expected_margin) * 500.0)
        market_min = _d(pricing.get("market_min_price_pen"))
        floor = _d(pricing.get("floor_price_pen"))
        competitiveness = None
        if market_min is not None and floor is not None and market_min > 0:
            competitiveness = 100.0 if floor <= market_min else _bounded(100.0 - float((floor - market_min) / market_min) * 1000.0)
        supplier_availability = None
        if supplier is not None:
            state = str(supplier["raw"].get("stock_state") or "UNKNOWN").upper()
            supplier_availability = {"IN_STOCK": 100.0, "LOW_STOCK": 65.0, "UNKNOWN": 40.0, "OUT_OF_STOCK": 0.0}.get(state, 40.0)
        sales_30d = _d(internal.get("sales_units_30d"))
        demand_rotation = None if sales_30d is None else _bounded(float(sales_30d) * 10.0)
        risk = float(pricing.get("risk_score") or 100.0)
        market_stability = _bounded(100.0 - risk)
        inventory_pressure = None
        own_stock = _d(internal.get("own_stock_qty"))
        if own_stock is not None:
            aging = float(internal.get("inventory_age_days") or 0)
            no_sale = float(internal.get("days_since_last_sale") or 0)
            inventory_pressure = _bounded(min(100.0, aging / 1.8 + no_sale)) if own_stock > 0 else 0.0
        score = score_opportunity(
            {
                "profitability": profitability,
                "competitiveness": competitiveness,
                "supplier_availability": supplier_availability,
                "demand_rotation": demand_rotation,
                "market_stability": market_stability,
                "inventory_pressure": inventory_pressure,
            },
            DEFAULT_OPPORTUNITY_WEIGHTS,
        )
        result = {
            **pricing,
            "opportunity_score": score["opportunity_score"],
            "opportunity_coverage_pct": score["coverage_pct"],
            "signals": {
                "profitability": profitability,
                "competitiveness": competitiveness,
                "supplier_availability": supplier_availability,
                "demand_rotation": demand_rotation,
                "market_stability": market_stability,
                "inventory_pressure": inventory_pressure,
            },
        }
        payload = {
            key: value
            for key, value in result.items()
            if key not in {"as_of"}
        }
        fingerprint = hashlib.sha256(json.dumps(payload, default=str, sort_keys=True).encode("utf-8")).hexdigest()
        try:
            self.market_repository.save_recommendation_snapshot(
                {
                    "partnumber": pn,
                    "channel_code": market,
                    "calculated_at": result["as_of"],
                    "action_code": result["action_code"],
                    "opportunity_score": result["opportunity_score"],
                    "confidence_score": result["confidence_score"],
                    "risk_score": result["risk_score"],
                    "recommended_price_pen": result.get("recommended_price_pen"),
                    "floor_price_pen": result.get("floor_price_pen"),
                    "market_min_price_pen": result.get("market_min_price_pen"),
                    "market_median_price_pen": result.get("market_median_price_pen"),
                    "expected_profit_pen": result.get("expected_profit_pen"),
                    "expected_margin_pct": result.get("expected_margin_pct"),
                    "reason_codes": result.get("reason_codes") or [],
                    "input_fingerprint": fingerprint,
                }
            )
        except (AttributeError, NotImplementedError):
            pass
        result["input_fingerprint"] = fingerprint
        return result
