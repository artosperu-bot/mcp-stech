from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_FLOOR
from typing import Any, Callable


_ACTION_PRIORITY = {
    "COMPRAR": 0,
    "SUBIR_STOCK": 1,
    "PUBLICAR": 2,
    "BAJAR_PRECIO": 3,
    "SUBIR_PRECIO": 4,
    "LIQUIDAR": 5,
    "MANTENER": 6,
    "REVISAR_PROVEEDOR": 7,
    "NO_COMPETIR": 8,
    "INVESTIGAR": 9,
}


def _d(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MarketOpportunityService:
    """Portfolio-level market intelligence built on product-level analysis.

    V1 only returns recommendations. It never writes operational stock, price,
    purchases or marketplace listings.
    """

    def __init__(
        self,
        *,
        market_service: Any,
        market_repository: Any,
        product_repository: Any,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.market_service = market_service
        self.market_repository = market_repository
        self.product_repository = product_repository
        self.clock = clock or _utc_now

    @staticmethod
    def _channel(value: str | None) -> str | None:
        normalized = str(value or "").strip().upper()
        return normalized or None

    @staticmethod
    def _category(value: str | None) -> str | None:
        normalized = str(value or "").strip().upper()
        return normalized or None

    @staticmethod
    def _supplier(value: str | None) -> str | None:
        normalized = str(value or "").strip().upper()
        return normalized or None

    @staticmethod
    def _safe_limit(limit: int, *, maximum: int = 100) -> int:
        return max(1, min(int(limit), maximum))

    @staticmethod
    def _product_category(product: dict[str, Any] | None) -> str | None:
        if not product:
            return None
        for key in ("category_code", "categoria", "categoria_nombre", "rubro", "familia"):
            value = str(product.get(key) or "").strip().upper()
            if value:
                return value
        return None

    def _matches_category(self, partnumber: str, category: str | None) -> bool:
        if category is None:
            return True
        product = self.product_repository.get_by_partnumber(partnumber)
        return self._product_category(product) == category

    def _candidate_partnumbers(
        self,
        *,
        channel: str | None,
        category: str | None,
        limit: int,
    ) -> list[str]:
        fetch_limit = min(max(limit * 5, 25), 500)
        rows = self.market_repository.list_candidate_partnumbers(channel=channel, limit=fetch_limit)
        result: list[str] = []
        seen: set[str] = set()
        for value in rows:
            pn = str(value or "").strip().upper()
            if not pn or pn in seen or not self._matches_category(pn, category):
                continue
            seen.add(pn)
            result.append(pn)
            if len(result) >= fetch_limit:
                break
        return result

    @staticmethod
    def _sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
        action = str(item.get("action_code") or "INVESTIGAR").upper()
        opportunity = float(item.get("opportunity_score") or 0.0)
        confidence = float(item.get("confidence_score") or 0.0)
        profit = float(_d(item.get("expected_profit_pen")) or Decimal("0"))
        return (
            _ACTION_PRIORITY.get(action, 99),
            -opportunity,
            -confidence,
            -profit,
            str(item.get("partnumber") or ""),
        )

    def opportunities_find(
        self,
        *,
        channel: str | None = None,
        category: str | None = None,
        limit: int = 30,
    ) -> dict[str, Any]:
        market = self._channel(channel)
        category_code = self._category(category)
        safe_limit = self._safe_limit(limit)
        partnumbers = self._candidate_partnumbers(
            channel=market,
            category=category_code,
            limit=safe_limit,
        )
        opportunities: list[dict[str, Any]] = []
        for pn in partnumbers:
            result = self.market_service.product_analyze(pn, market)
            if result.get("found") is False:
                continue
            opportunities.append(result)
        opportunities.sort(key=self._sort_key)
        opportunities = opportunities[:safe_limit]
        return {
            "channel": market,
            "category": category_code,
            "count": len(opportunities),
            "opportunities": opportunities,
            "as_of": self.clock(),
        }

    def assortment_gaps(
        self,
        *,
        channel: str | None = None,
        category: str | None = None,
        limit: int = 30,
    ) -> dict[str, Any]:
        market = self._channel(channel)
        category_code = self._category(category)
        safe_limit = self._safe_limit(limit)
        partnumbers = self._candidate_partnumbers(
            channel=market,
            category=category_code,
            limit=safe_limit * 2,
        )
        gaps: list[dict[str, Any]] = []
        for pn in partnumbers:
            signal = self.market_repository.get_internal_signal(pn, as_of=self.clock())
            own_price = _d((signal or {}).get("own_sale_price_pen"))
            if own_price is not None:
                continue
            analysis = self.market_service.product_analyze(pn, market)
            if analysis.get("found") is False:
                continue
            reasons = list(analysis.get("reason_codes") or [])
            if "NO_STECH_LISTING" not in reasons:
                reasons.append("NO_STECH_LISTING")
            gaps.append({**analysis, "reason_codes": reasons})
        gaps.sort(key=self._sort_key)
        gaps = gaps[:safe_limit]
        return {
            "channel": market,
            "category": category_code,
            "count": len(gaps),
            "gaps": gaps,
            "as_of": self.clock(),
        }

    def _supplier_partnumbers(self, *, supplier: str | None, category: str | None, limit: int) -> list[str]:
        fetch_limit = min(max(limit * 5, 25), 500)
        lister = getattr(self.market_repository, "list_supplier_partnumbers", None)
        if callable(lister):
            rows = lister(supplier=supplier, limit=fetch_limit)
        else:
            # Compatibility fallback for deployments before the supplier-index
            # query is installed. It intentionally narrows coverage rather than
            # inventing supplier products.
            rows = self.market_repository.list_candidate_partnumbers(channel=None, limit=fetch_limit)
        result: list[str] = []
        seen: set[str] = set()
        for value in rows:
            pn = str(value or "").strip().upper()
            if not pn or pn in seen or not self._matches_category(pn, category):
                continue
            seen.add(pn)
            result.append(pn)
        return result

    def supplier_opportunities(
        self,
        *,
        supplier: str | None = None,
        category: str | None = None,
        limit: int = 30,
    ) -> dict[str, Any]:
        supplier_code = self._supplier(supplier)
        category_code = self._category(category)
        safe_limit = self._safe_limit(limit)
        partnumbers = self._supplier_partnumbers(
            supplier=supplier_code,
            category=category_code,
            limit=safe_limit,
        )
        opportunities: list[dict[str, Any]] = []
        for pn in partnumbers:
            rows = self.market_repository.get_supplier_history(pn, supplier=supplier_code, days=90)
            if not rows:
                continue
            # Stable sort preserves repository order for equal timestamps. The
            # repository returns chronological history, so the last row is current.
            ordered = sorted(
                rows,
                key=lambda row: row.get("observed_at") or datetime.min.replace(tzinfo=timezone.utc),
            )
            latest = ordered[-1]
            previous = ordered[-2] if len(ordered) > 1 else None
            latest_cost = _d(latest.get("cost_pen"))
            previous_cost = _d((previous or {}).get("cost_pen"))
            change = (
                latest_cost - previous_cost
                if latest_cost is not None and previous_cost is not None
                else None
            )
            reasons: list[str] = []
            if change is not None and change < 0:
                reasons.append("SUPPLIER_COST_DROP")
            elif change is not None and change > 0:
                reasons.append("SUPPLIER_COST_INCREASE")
            stock_state = str(latest.get("stock_state") or "UNKNOWN").upper()
            if stock_state in {"IN_STOCK", "LOW_STOCK"}:
                reasons.append("SUPPLIER_IN_STOCK")
            elif stock_state == "OUT_OF_STOCK":
                reasons.append("SUPPLIER_OUT_OF_STOCK")
            opportunities.append(
                {
                    "partnumber": pn,
                    "supplier_code": str(latest.get("supplier_code") or supplier_code or "").upper() or None,
                    "latest_cost_pen": latest_cost,
                    "previous_cost_pen": previous_cost,
                    "cost_change_pen": change,
                    "stock_qty": _d(latest.get("stock_qty")),
                    "stock_state": stock_state,
                    "reason_codes": reasons,
                    "observed_at": latest.get("observed_at"),
                }
            )
        opportunities.sort(
            key=lambda item: (
                0 if "SUPPLIER_COST_DROP" in item["reason_codes"] else 1,
                item["latest_cost_pen"] if item["latest_cost_pen"] is not None else Decimal("Infinity"),
                item["partnumber"],
            )
        )
        opportunities = opportunities[:safe_limit]
        return {
            "supplier": supplier_code,
            "category": category_code,
            "count": len(opportunities),
            "opportunities": opportunities,
            "as_of": self.clock(),
        }

    def channel_opportunities(
        self,
        channel: str,
        *,
        category: str | None = None,
        limit: int = 30,
    ) -> dict[str, Any]:
        market = self._channel(channel)
        if market is None:
            raise ValueError("channel is required")
        return self.opportunities_find(channel=market, category=category, limit=limit)

    def strategy(
        self,
        *,
        channel: str | None = None,
        category: str | None = None,
        budget_pen: Decimal | float | int | None = None,
        limit: int = 30,
    ) -> dict[str, Any]:
        market = self._channel(channel)
        category_code = self._category(category)
        safe_limit = self._safe_limit(limit)
        opportunity_result = self.opportunities_find(
            channel=market,
            category=category_code,
            limit=safe_limit,
        )
        actions = opportunity_result["opportunities"]
        if budget_pen is None:
            return {
                "channel": market,
                "category": category_code,
                "budget_pen": None,
                "allocated_budget_pen": None,
                "unallocated_budget_pen": None,
                "purchases": [],
                "actions": actions,
                "as_of": self.clock(),
            }

        budget = _d(budget_pen)
        if budget is None or budget < 0:
            raise ValueError("budget_pen must be zero or greater")
        remaining = budget
        purchases: list[dict[str, Any]] = []
        allocated = Decimal("0")

        for item in actions:
            action = str(item.get("action_code") or "").upper()
            confidence = float(item.get("confidence_score") or 0.0)
            risk = float(item.get("risk_score") or 100.0)
            contribution = _d(item.get("expected_profit_pen"))
            unit_cost = _d(item.get("cost_pen"))
            if action not in {"COMPRAR", "SUBIR_STOCK"}:
                continue
            if confidence < 70.0 or risk > 65.0:
                continue
            if contribution is None or contribution <= 0 or unit_cost is None or unit_cost <= 0:
                continue
            affordable = int((remaining / unit_cost).to_integral_value(rounding=ROUND_FLOOR))
            if affordable <= 0:
                continue

            signal = self.market_repository.get_internal_signal(item["partnumber"], as_of=self.clock()) or {}
            sales_30d = _d(signal.get("sales_units_30d"))
            desired = max(1, int(sales_30d or Decimal("1")))

            supplier_rows = self.market_repository.get_supplier_history(item["partnumber"], days=30)
            supplier_stock: int | None = None
            if supplier_rows:
                latest_supplier = sorted(
                    supplier_rows,
                    key=lambda row: row.get("observed_at") or datetime.min.replace(tzinfo=timezone.utc),
                )[-1]
                stock_qty = _d(latest_supplier.get("stock_qty"))
                if stock_qty is not None:
                    supplier_stock = max(0, int(stock_qty))
            quantity = min(affordable, desired, supplier_stock if supplier_stock is not None else affordable)
            if quantity <= 0:
                continue
            investment = unit_cost * quantity
            total_contribution = contribution * quantity
            purchases.append(
                {
                    "partnumber": item["partnumber"],
                    "action_code": action,
                    "quantity": quantity,
                    "unit_cost_pen": unit_cost,
                    "investment_pen": investment,
                    "expected_unit_contribution_pen": contribution,
                    "expected_total_contribution_pen": total_contribution,
                    "opportunity_score": item.get("opportunity_score"),
                    "confidence_score": confidence,
                    "risk_score": risk,
                }
            )
            allocated += investment
            remaining -= investment

        return {
            "channel": market,
            "category": category_code,
            "budget_pen": budget,
            "allocated_budget_pen": allocated,
            "unallocated_budget_pen": remaining,
            "purchases": purchases,
            "actions": actions,
            "as_of": self.clock(),
        }

    def weekly_actions(
        self,
        *,
        channel: str | None = None,
        category: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        result = self.opportunities_find(
            channel=channel,
            category=category,
            limit=self._safe_limit(limit, maximum=200),
        )
        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in result["opportunities"]:
            action = str(item.get("action_code") or "INVESTIGAR").upper()
            grouped.setdefault(action, []).append(item)
        return {
            "channel": result["channel"],
            "category": result["category"],
            "count": result["count"],
            "actions": result["opportunities"],
            "by_action": grouped,
            "as_of": self.clock(),
        }
