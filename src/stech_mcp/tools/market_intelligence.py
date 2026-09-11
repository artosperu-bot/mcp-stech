from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _datetime(value: str | datetime | None, *, required: bool = False) -> datetime | None:
    if value is None or value == "":
        if required:
            raise ValueError("datetime value is required")
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def register_market_intelligence_tools(
    mcp: Any,
    *,
    market_repository: Any,
    market_service: Any,
    opportunity_service: Any,
    namespace: Any | None = None,
) -> dict[str, Any]:
    """Register additive Market Intelligence V1 tools.

    Write tools only persist intelligence inputs/policies. None of these tools
    update operational marketplace prices, stock, product activation or orders.
    """

    @mcp.tool()
    def market_observation_ingest(
        source_code: str,
        external_listing_id: str,
        observed_at: str,
        source_method: str,
        source_observation_key: str,
        seller_name: str | None = None,
        external_sku: str | None = None,
        title: str | None = None,
        url: str | None = None,
        currency: str = "PEN",
        is_stech: bool = False,
        price_regular: float | None = None,
        price_offer: float | None = None,
        price_effective: float | None = None,
        stock_qty: float | None = None,
        stock_state: str = "UNKNOWN",
        promotion_text: str | None = None,
        promotion_type: str | None = None,
        shipping_price: float | None = None,
        seller_count: int | None = None,
        ranking_position: int | None = None,
        raw_fingerprint: str | None = None,
        data_quality_score: float | None = None,
    ) -> dict[str, Any]:
        """Append one competitor/own listing observation to immutable market history."""
        instant = _datetime(observed_at, required=True)
        assert instant is not None
        listing = market_repository.upsert_listing(
            source_code=source_code,
            external_listing_id=external_listing_id,
            seller_name=seller_name,
            external_sku=external_sku,
            title=title,
            url=url,
            currency=currency,
            is_stech=is_stech,
            seen_at=instant,
        )
        observation = market_repository.insert_observation(
            market_listing_id=int(listing["market_listing_id"]),
            observed_at=instant,
            price_regular=price_regular,
            price_offer=price_offer,
            price_effective=price_effective,
            stock_qty=stock_qty,
            stock_state=stock_state,
            promotion_text=promotion_text,
            promotion_type=promotion_type,
            shipping_price=shipping_price,
            seller_count=seller_count,
            ranking_position=ranking_position,
            source_method=source_method,
            source_observation_key=source_observation_key,
            raw_fingerprint=raw_fingerprint,
            data_quality_score=data_quality_score,
        )
        return {"listing": listing, "observation": observation}

    @mcp.tool()
    def market_supplier_observation_ingest(
        supplier_code: str,
        partnumber: str,
        observed_at: str,
        currency: str,
        source_method: str,
        source_key: str,
        cost_usd: float | None = None,
        cost_pen: float | None = None,
        stock_qty: float | None = None,
        stock_state: str = "UNKNOWN",
        warehouse_code: str | None = None,
        tax_included: bool = False,
        data_quality_score: float | None = None,
    ) -> dict[str, Any]:
        """Append an immutable supplier cost/stock observation."""
        instant = _datetime(observed_at, required=True)
        assert instant is not None
        return market_repository.insert_supplier_observation(
            supplier_code=supplier_code,
            partnumber=partnumber,
            observed_at=instant,
            currency=currency,
            source_method=source_method,
            source_key=source_key,
            cost_usd=cost_usd,
            cost_pen=cost_pen,
            stock_qty=stock_qty,
            stock_state=stock_state,
            warehouse_code=warehouse_code,
            tax_included=tax_included,
            data_quality_score=data_quality_score,
        )

    @mcp.tool()
    def market_internal_signal_ingest(
        partnumber: str,
        observed_at: str,
        source_code: str,
        source_key: str,
        own_stock_qty: float | None = None,
        sales_units_7d: float | None = None,
        sales_units_30d: float | None = None,
        sales_units_90d: float | None = None,
        days_since_last_sale: int | None = None,
        inventory_age_days: int | None = None,
        own_sale_price_pen: float | None = None,
    ) -> dict[str, Any]:
        """Persist an ERP/internal stock-sales snapshot used by opportunity scoring."""
        instant = _datetime(observed_at, required=True)
        assert instant is not None
        return market_repository.upsert_internal_signal(
            partnumber=partnumber,
            observed_at=instant,
            source_code=source_code,
            source_key=source_key,
            own_stock_qty=own_stock_qty,
            sales_units_7d=sales_units_7d,
            sales_units_30d=sales_units_30d,
            sales_units_90d=sales_units_90d,
            days_since_last_sale=days_since_last_sale,
            inventory_age_days=inventory_age_days,
            own_sale_price_pen=own_sale_price_pen,
        )

    @mcp.tool()
    def market_product_match_upsert(
        market_listing_id: int,
        partnumber: str,
        match_status: str,
        match_method: str,
        confidence_score: float,
        evidence: dict[str, Any] | None = None,
        verified_by: str | None = None,
        verified_at: str | None = None,
    ) -> dict[str, Any]:
        """Map an external listing to an exact S-TECH PN; only VERIFIED drives pricing."""
        return market_repository.upsert_product_match(
            market_listing_id=market_listing_id,
            partnumber=partnumber,
            match_status=match_status,
            match_method=match_method,
            confidence_score=confidence_score,
            evidence=evidence,
            verified_by=verified_by,
            verified_at=_datetime(verified_at),
        )

    @mcp.tool()
    def market_pricing_policy_get(
        channel: str,
        category: str | None = None,
        brand: str | None = None,
        as_of: str | None = None,
    ) -> dict[str, Any]:
        """Resolve the effective S-TECH pricing policy by channel/category/brand."""
        row = market_repository.get_pricing_policy(
            channel,
            category=category,
            brand=brand,
            as_of=_datetime(as_of),
        )
        return {"found": row is not None, "policy": row}

    @mcp.tool()
    def market_pricing_policy_upsert(
        channel_code: str,
        effective_from: str,
        minimum_margin_pct: float,
        minimum_contribution_pen: float,
        category_code: str | None = None,
        brand: str | None = None,
        stech_margin_pct: float | None = None,
        undercut_amount_pen: float = 1.0,
        strategy: str = "BALANCED",
        effective_to: str | None = None,
        is_active: bool = True,
    ) -> dict[str, Any]:
        """Add an effective-dated pricing policy; this does not update marketplace prices."""
        start = _datetime(effective_from, required=True)
        assert start is not None
        return market_repository.upsert_pricing_policy(
            channel_code=channel_code,
            effective_from=start,
            minimum_margin_pct=minimum_margin_pct,
            minimum_contribution_pen=minimum_contribution_pen,
            category_code=category_code,
            brand=brand,
            stech_margin_pct=stech_margin_pct,
            undercut_amount_pen=undercut_amount_pen,
            strategy=strategy,
            effective_to=_datetime(effective_to),
            is_active=is_active,
        )

    @mcp.tool()
    def market_channel_fee_rule_get(
        channel: str,
        category: str | None = None,
        as_of: str | None = None,
    ) -> dict[str, Any]:
        """Resolve the effective commission/payment/shipping fee rule for a channel."""
        row = market_repository.get_fee_rule(channel, category=category, as_of=_datetime(as_of))
        return {"found": row is not None, "fee_rule": row}

    @mcp.tool()
    def market_channel_fee_rule_upsert(
        channel_code: str,
        effective_from: str,
        commission_pct: float = 0.0,
        fixed_fee_pen: float = 0.0,
        payment_fee_pct: float = 0.0,
        shipping_cost_pen: float | None = None,
        free_shipping_threshold_pen: float | None = None,
        seller_absorbs_shipping_above_threshold: bool = False,
        category_code: str | None = None,
        effective_to: str | None = None,
        is_active: bool = True,
    ) -> dict[str, Any]:
        """Add an effective-dated channel fee rule for profitability simulation."""
        start = _datetime(effective_from, required=True)
        assert start is not None
        return market_repository.upsert_fee_rule(
            channel_code=channel_code,
            effective_from=start,
            commission_pct=commission_pct,
            fixed_fee_pen=fixed_fee_pen,
            payment_fee_pct=payment_fee_pct,
            shipping_cost_pen=shipping_cost_pen,
            free_shipping_threshold_pen=free_shipping_threshold_pen,
            seller_absorbs_shipping_above_threshold=seller_absorbs_shipping_above_threshold,
            category_code=category_code,
            effective_to=_datetime(effective_to),
            is_active=is_active,
        )

    @mcp.tool()
    def market_competitors_get(partnumber: str, channel: str | None = None) -> dict[str, Any]:
        """Return current VERIFIED competitors for an exact Part Number."""
        return market_service.competitors_get(partnumber, channel)

    @mcp.tool()
    def market_price_history(partnumber: str, channel: str | None = None, days: int = 30) -> dict[str, Any]:
        """Return immutable price/stock/promotion history for VERIFIED listings."""
        return market_service.price_history(partnumber, channel, days=days)

    @mcp.tool()
    def market_variations_get(
        partnumber: str,
        channel: str | None = None,
        windows: list[int] | None = None,
    ) -> dict[str, Any]:
        """Calculate previous, 1/7/30/90-day and statistical price variations per listing."""
        return market_service.variations_get(
            partnumber,
            channel,
            windows=tuple(windows or [1, 7, 30, 90]),
        )

    @mcp.tool()
    def market_data_quality(partnumber: str, channel: str | None = None) -> dict[str, Any]:
        """Return confidence/freshness/depth metrics separately from opportunity score."""
        return market_service.data_quality(partnumber, channel)

    @mcp.tool()
    def market_profit_simulate(
        partnumber: str,
        channel: str,
        sale_price_pen: float,
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Simulate contribution and margin using effective supplier cost and channel fees."""
        return market_service.profit_simulate(
            partnumber,
            channel,
            sale_price_pen,
            overrides=overrides,
        )

    @mcp.tool()
    def market_recommended_price(
        partnumber: str,
        channel: str,
        strategy: str = "BALANCED",
    ) -> dict[str, Any]:
        """Recommend an auditable price without writing it to any marketplace."""
        return market_service.recommended_price(partnumber, channel, strategy=strategy)

    @mcp.tool()
    def market_product_analyze(partnumber: str, channel: str | None = None) -> dict[str, Any]:
        """Return full Opportunity/Confidence/Risk analysis and recommended commercial action."""
        return market_service.product_analyze(partnumber, channel)

    @mcp.tool()
    def market_risk_analyze(partnumber: str, channel: str | None = None) -> dict[str, Any]:
        """Analyze price war, volatility, stale data, supplier and inventory risks."""
        return market_service.risk_analyze(partnumber, channel)

    @mcp.tool()
    def market_opportunities_find(
        channel: str | None = None,
        category: str | None = None,
        limit: int = 30,
    ) -> dict[str, Any]:
        """Rank actionable commercial opportunities before low-confidence investigations."""
        return opportunity_service.opportunities_find(channel=channel, category=category, limit=limit)

    @mcp.tool()
    def market_assortment_gaps(
        channel: str | None = None,
        category: str | None = None,
        limit: int = 30,
    ) -> dict[str, Any]:
        """Find exact-PN market products with no current S-TECH listing/price signal."""
        return opportunity_service.assortment_gaps(channel=channel, category=category, limit=limit)

    @mcp.tool()
    def market_supplier_opportunities(
        supplier: str | None = None,
        category: str | None = None,
        limit: int = 30,
    ) -> dict[str, Any]:
        """Find supplier cost drops and available-stock opportunities."""
        return opportunity_service.supplier_opportunities(supplier=supplier, category=category, limit=limit)

    @mcp.tool()
    def market_channel_opportunities(
        channel: str,
        category: str | None = None,
        limit: int = 30,
    ) -> dict[str, Any]:
        """Rank opportunities for one sales channel."""
        return opportunity_service.channel_opportunities(channel, category=category, limit=limit)

    @mcp.tool()
    def market_strategy(
        channel: str | None = None,
        category: str | None = None,
        budget_pen: float | None = None,
        limit: int = 30,
    ) -> dict[str, Any]:
        """Build a budget-safe portfolio strategy; returns recommendations only."""
        return opportunity_service.strategy(
            channel=channel,
            category=category,
            budget_pen=budget_pen,
            limit=limit,
        )

    @mcp.tool()
    def market_weekly_actions(
        channel: str | None = None,
        category: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Return prioritized commercial actions grouped by action code."""
        return opportunity_service.weekly_actions(channel=channel, category=category, limit=limit)

    registered = {
        "market_observation_ingest": market_observation_ingest,
        "market_supplier_observation_ingest": market_supplier_observation_ingest,
        "market_internal_signal_ingest": market_internal_signal_ingest,
        "market_product_match_upsert": market_product_match_upsert,
        "market_pricing_policy_get": market_pricing_policy_get,
        "market_pricing_policy_upsert": market_pricing_policy_upsert,
        "market_channel_fee_rule_get": market_channel_fee_rule_get,
        "market_channel_fee_rule_upsert": market_channel_fee_rule_upsert,
        "market_competitors_get": market_competitors_get,
        "market_price_history": market_price_history,
        "market_variations_get": market_variations_get,
        "market_data_quality": market_data_quality,
        "market_profit_simulate": market_profit_simulate,
        "market_recommended_price": market_recommended_price,
        "market_product_analyze": market_product_analyze,
        "market_risk_analyze": market_risk_analyze,
        "market_opportunities_find": market_opportunities_find,
        "market_assortment_gaps": market_assortment_gaps,
        "market_supplier_opportunities": market_supplier_opportunities,
        "market_channel_opportunities": market_channel_opportunities,
        "market_strategy": market_strategy,
        "market_weekly_actions": market_weekly_actions,
    }
    if namespace is not None:
        for name, func in registered.items():
            setattr(namespace, name, func)
    return registered
