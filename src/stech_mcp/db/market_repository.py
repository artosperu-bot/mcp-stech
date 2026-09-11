from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any


_MATCH_STATUSES = {"VERIFIED", "PROBABLE", "REVIEW", "REJECTED"}
_MATCH_METHODS = {"PN_EXACT", "EAN_EXACT", "UPC_EXACT", "MODEL_EXACT", "MANUAL", "OTHER"}
_STOCK_STATES = {"IN_STOCK", "LOW_STOCK", "OUT_OF_STOCK", "UNKNOWN"}
_SOURCE_METHODS = {"API", "COLLECTOR", "WEB_RESEARCH", "MANUAL", "IMPORT"}
_STRATEGIES = {"BALANCED", "MARGIN", "VOLUME", "CLEARANCE"}
_ACTIONS = {
    "COMPRAR", "PUBLICAR", "SUBIR_STOCK", "BAJAR_PRECIO", "SUBIR_PRECIO",
    "MANTENER", "LIQUIDAR", "NO_COMPETIR", "REVISAR_PROVEEDOR", "INVESTIGAR",
}


def _text(value: Any, *, upper: bool = False) -> str:
    result = str(value or "").strip()
    return result.upper() if upper else result


def _utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _score(value: Any, name: str) -> Decimal | None:
    if value is None:
        return None
    result = Decimal(str(value))
    if result < 0 or result > 100:
        raise ValueError(f"{name} must be between 0 and 100")
    return result


class MarketRepository:
    def __init__(self, connection_factory: Callable[[], Any]):
        self._connection_factory = connection_factory

    @staticmethod
    def _row_to_dict(cursor: Any, row: Any) -> dict[str, Any] | None:
        if row is None:
            return None
        columns = [str(column[0]) for column in cursor.description]
        result = dict(zip(columns, row, strict=False))
        for key in ("evidence_json", "reason_codes_json"):
            raw = result.get(key)
            if isinstance(raw, str) and raw:
                try:
                    result[key.removesuffix("_json")] = json.loads(raw)
                except json.JSONDecodeError:
                    result[key.removesuffix("_json")] = None
        return result

    @classmethod
    def _rows_to_dicts(cls, cursor: Any, rows: list[Any]) -> list[dict[str, Any]]:
        return [item for row in rows if (item := cls._row_to_dict(cursor, row)) is not None]

    @staticmethod
    def _close(connection: Any) -> None:
        close = getattr(connection, "close", None)
        if callable(close):
            close()

    @staticmethod
    def _rollback(connection: Any) -> None:
        rollback = getattr(connection, "rollback", None)
        if callable(rollback):
            rollback()

    def upsert_listing(
        self,
        *,
        source_code: str,
        external_listing_id: str | None = None,
        seller_name: str | None = None,
        external_sku: str | None = None,
        title: str | None = None,
        url: str | None = None,
        currency: str = "PEN",
        is_stech: bool = False,
        seen_at: datetime | None = None,
    ) -> dict[str, Any]:
        source = _text(source_code, upper=True)
        if not source:
            raise ValueError("source_code is required")
        listing_key = _text(external_listing_id)
        normalized_url = _text(url)
        if not listing_key:
            if not normalized_url:
                raise ValueError("external_listing_id or url is required")
            listing_key = "URL:" + hashlib.sha256(
                f"{source}|{_text(seller_name, upper=True)}|{normalized_url}".encode("utf-8")
            ).hexdigest()
        curr = _text(currency, upper=True)
        if len(curr) != 3:
            raise ValueError("currency must be a 3-letter code")
        observed = _utc(seen_at)

        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
MERGE dbo.market_listing AS target
USING (SELECT ? AS source_code, ? AS external_listing_id) AS source
ON target.source_code = source.source_code
AND target.external_listing_id = source.external_listing_id
WHEN MATCHED THEN UPDATE SET
    seller_name = ?, external_sku = ?, title = ?, url = ?, currency = ?, is_stech = ?,
    last_seen_at = ?, updated_at = SYSUTCDATETIME()
WHEN NOT MATCHED THEN INSERT(
    source_code, seller_name, external_listing_id, external_sku, title, url, currency,
    is_stech, first_seen_at, last_seen_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
OUTPUT INSERTED.market_listing_id, INSERTED.source_code, INSERTED.seller_name,
       INSERTED.external_listing_id, INSERTED.external_sku, INSERTED.title,
       INSERTED.url, INSERTED.currency, INSERTED.is_stech,
       INSERTED.first_seen_at, INSERTED.last_seen_at;
""",
                source,
                listing_key,
                seller_name,
                external_sku,
                title,
                normalized_url or None,
                curr,
                bool(is_stech),
                observed,
                source,
                seller_name,
                listing_key,
                external_sku,
                title,
                normalized_url or None,
                curr,
                bool(is_stech),
                observed,
                observed,
            )
            result = self._row_to_dict(cursor, cursor.fetchone())
            if result is None:
                raise RuntimeError("market listing upsert returned no row")
            connection.commit()
            return result
        except Exception:
            self._rollback(connection)
            raise
        finally:
            self._close(connection)

    def upsert_product_match(
        self,
        *,
        market_listing_id: int,
        partnumber: str,
        match_status: str,
        match_method: str,
        confidence_score: Decimal | float | int,
        evidence: dict[str, Any] | None = None,
        verified_by: str | None = None,
        verified_at: datetime | None = None,
    ) -> dict[str, Any]:
        pn = _text(partnumber, upper=True)
        status = _text(match_status, upper=True)
        method = _text(match_method, upper=True)
        confidence = _score(confidence_score, "confidence_score")
        if not pn:
            raise ValueError("partnumber is required")
        if status not in _MATCH_STATUSES:
            raise ValueError("invalid match_status")
        if method not in _MATCH_METHODS:
            raise ValueError("invalid match_method")
        evidence_json = json.dumps(evidence or {}, ensure_ascii=False, separators=(",", ":"))
        verified_time = _utc(verified_at) if status == "VERIFIED" else None

        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
MERGE dbo.market_product_match AS target
USING (SELECT ? AS market_listing_id, ? AS partnumber) AS source
ON target.market_listing_id = source.market_listing_id AND target.partnumber = source.partnumber
WHEN MATCHED THEN UPDATE SET
    match_status = ?, match_method = ?, confidence_score = ?, evidence_json = ?,
    verified_by = ?, verified_at = ?, updated_at = SYSUTCDATETIME()
WHEN NOT MATCHED THEN INSERT(
    market_listing_id, partnumber, match_status, match_method, confidence_score,
    evidence_json, verified_by, verified_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
OUTPUT INSERTED.market_product_match_id, INSERTED.market_listing_id, INSERTED.partnumber,
       INSERTED.match_status, INSERTED.match_method, INSERTED.confidence_score,
       INSERTED.evidence_json, INSERTED.verified_by, INSERTED.verified_at;
""",
                int(market_listing_id), pn,
                status, method, confidence, evidence_json, verified_by, verified_time,
                int(market_listing_id), pn, status, method, confidence, evidence_json, verified_by, verified_time,
            )
            result = self._row_to_dict(cursor, cursor.fetchone())
            if result is None:
                raise RuntimeError("market product match upsert returned no row")
            connection.commit()
            return result
        except Exception:
            self._rollback(connection)
            raise
        finally:
            self._close(connection)

    def insert_observation(
        self,
        *,
        market_listing_id: int,
        observed_at: datetime,
        price_regular: Decimal | None = None,
        price_offer: Decimal | None = None,
        price_effective: Decimal | None = None,
        stock_qty: Decimal | None = None,
        stock_state: str = "UNKNOWN",
        promotion_text: str | None = None,
        promotion_type: str | None = None,
        shipping_price: Decimal | None = None,
        seller_count: int | None = None,
        ranking_position: int | None = None,
        source_method: str = "MANUAL",
        source_observation_key: str | None = None,
        raw_fingerprint: str | None = None,
        data_quality_score: Decimal | float | int | None = None,
    ) -> dict[str, Any]:
        stock = _text(stock_state, upper=True)
        method = _text(source_method, upper=True)
        source_key = _text(source_observation_key)
        fingerprint = _text(raw_fingerprint, upper=False).lower()
        quality = _score(data_quality_score, "data_quality_score")
        if stock not in _STOCK_STATES:
            raise ValueError("invalid stock_state")
        if method not in _SOURCE_METHODS:
            raise ValueError("invalid source_method")
        if not source_key and not fingerprint:
            raise ValueError("source_observation_key or raw_fingerprint is required")
        if fingerprint and len(fingerprint) != 64:
            raise ValueError("raw_fingerprint must be a SHA-256 hex digest")
        observed = _utc(observed_at)

        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            if source_key:
                cursor.execute(
                    """
SELECT market_observation_id
FROM dbo.market_observation
WHERE market_listing_id = ? AND source_observation_key = ?;
""",
                    int(market_listing_id), source_key,
                )
            else:
                cursor.execute(
                    """
SELECT market_observation_id
FROM dbo.market_observation
WHERE market_listing_id = ? AND observed_at = ? AND raw_fingerprint = ?;
""",
                    int(market_listing_id), observed, fingerprint,
                )
            existing = cursor.fetchone()
            if existing is not None:
                return {"market_observation_id": int(existing[0]), "inserted": False}

            cursor.execute(
                """
INSERT INTO dbo.market_observation(
    market_listing_id, observed_at, price_regular, price_offer, price_effective,
    stock_qty, stock_state, promotion_text, promotion_type, shipping_price,
    seller_count, source_observation_key, ranking_position, source_method,
    raw_fingerprint, data_quality_score
)
OUTPUT INSERTED.market_observation_id
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
""",
                int(market_listing_id),
                observed,
                price_regular,
                price_offer,
                price_effective,
                stock_qty,
                stock,
                promotion_text,
                promotion_type,
                shipping_price,
                int(seller_count) if seller_count is not None else None,
                source_key or None,
                int(ranking_position) if ranking_position is not None else None,
                method,
                fingerprint or None,
                quality,
            )
            inserted = cursor.fetchone()
            if inserted is None:
                raise RuntimeError("market observation insert returned no id")
            connection.commit()
            return {"market_observation_id": int(inserted[0]), "inserted": True}
        except Exception:
            self._rollback(connection)
            raise
        finally:
            self._close(connection)

    def insert_supplier_observation(
        self,
        *,
        supplier_code: str,
        partnumber: str,
        observed_at: datetime,
        currency: str,
        source_method: str,
        source_key: str,
        cost_usd: Decimal | None = None,
        cost_pen: Decimal | None = None,
        stock_qty: Decimal | None = None,
        stock_state: str = "UNKNOWN",
        warehouse_code: str | None = None,
        tax_included: bool = False,
        data_quality_score: Decimal | float | int | None = None,
    ) -> dict[str, Any]:
        supplier = _text(supplier_code, upper=True)
        pn = _text(partnumber, upper=True)
        curr = _text(currency, upper=True)
        method = _text(source_method, upper=True)
        key = _text(source_key)
        stock = _text(stock_state, upper=True)
        quality = _score(data_quality_score, "data_quality_score")
        if not supplier or not pn or not key:
            raise ValueError("supplier_code, partnumber and source_key are required")
        if len(curr) != 3:
            raise ValueError("currency must be a 3-letter code")
        if method not in _SOURCE_METHODS:
            raise ValueError("invalid source_method")
        if stock not in _STOCK_STATES:
            raise ValueError("invalid stock_state")

        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT supplier_observation_id FROM dbo.supplier_observation WHERE supplier_code = ? AND source_key = ?;",
                supplier, key,
            )
            existing = cursor.fetchone()
            if existing is not None:
                return {"supplier_observation_id": int(existing[0]), "inserted": False}
            cursor.execute(
                """
INSERT INTO dbo.supplier_observation(
    supplier_code, partnumber, observed_at, cost_usd, cost_pen, stock_qty,
    stock_state, warehouse_code, currency, tax_included, source_method,
    source_key, data_quality_score
)
OUTPUT INSERTED.supplier_observation_id
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
""",
                supplier, pn, _utc(observed_at), cost_usd, cost_pen, stock_qty,
                stock, warehouse_code, curr, bool(tax_included), method, key, quality,
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("supplier observation insert returned no id")
            connection.commit()
            return {"supplier_observation_id": int(row[0]), "inserted": True}
        except Exception:
            self._rollback(connection)
            raise
        finally:
            self._close(connection)

    def get_verified_competitors(self, partnumber: str, channel: str | None = None) -> list[dict[str, Any]]:
        pn = _text(partnumber, upper=True)
        channel_code = _text(channel, upper=True) or None
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
SELECT
    l.market_listing_id, l.source_code, l.seller_name, l.external_listing_id,
    o.price_effective, o.stock_state, o.observed_at, o.data_quality_score
FROM dbo.market_listing l
INNER JOIN dbo.market_product_match m ON m.market_listing_id = l.market_listing_id
CROSS APPLY (
    SELECT TOP (1) mo.price_effective, mo.stock_state, mo.observed_at, mo.data_quality_score
    FROM dbo.market_observation mo
    WHERE mo.market_listing_id = l.market_listing_id
    ORDER BY mo.observed_at DESC, mo.market_observation_id DESC
) o
WHERE m.partnumber = ?
  AND m.match_status = 'VERIFIED'
  AND l.is_stech = 0
  AND (? IS NULL OR l.source_code = ?)
ORDER BY o.price_effective, l.source_code, l.seller_name;
""",
                pn, channel_code, channel_code,
            )
            return self._rows_to_dicts(cursor, cursor.fetchall())
        finally:
            self._close(connection)

    def get_price_history(self, partnumber: str, channel: str | None = None, days: int = 30) -> list[dict[str, Any]]:
        safe_days = max(1, min(int(days), 3650))
        cutoff = datetime.now(timezone.utc) - timedelta(days=safe_days)
        pn = _text(partnumber, upper=True)
        channel_code = _text(channel, upper=True) or None
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
SELECT l.market_listing_id, l.source_code, l.seller_name, l.external_listing_id,
       o.observed_at, o.price_regular, o.price_offer, o.price_effective,
       o.stock_qty, o.stock_state, o.promotion_text, o.promotion_type,
       o.shipping_price, o.seller_count, o.ranking_position, o.data_quality_score
FROM dbo.market_observation o
INNER JOIN dbo.market_listing l ON l.market_listing_id = o.market_listing_id
INNER JOIN dbo.market_product_match m ON m.market_listing_id = l.market_listing_id
WHERE m.partnumber = ?
  AND m.match_status = 'VERIFIED'
  AND o.observed_at >= ?
  AND (? IS NULL OR l.source_code = ?)
ORDER BY o.observed_at, l.market_listing_id;
""",
                pn, cutoff, channel_code, channel_code,
            )
            return self._rows_to_dicts(cursor, cursor.fetchall())
        finally:
            self._close(connection)

    def get_supplier_history(self, partnumber: str, supplier: str | None = None, days: int = 90) -> list[dict[str, Any]]:
        safe_days = max(1, min(int(days), 3650))
        cutoff = datetime.now(timezone.utc) - timedelta(days=safe_days)
        pn = _text(partnumber, upper=True)
        supplier_code = _text(supplier, upper=True) or None
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
SELECT supplier_observation_id, supplier_code, partnumber, observed_at,
       cost_usd, cost_pen, stock_qty, stock_state, warehouse_code, currency,
       tax_included, source_method, data_quality_score
FROM dbo.supplier_observation
WHERE partnumber = ? AND observed_at >= ?
  AND (? IS NULL OR supplier_code = ?)
ORDER BY observed_at, supplier_code;
""",
                pn, cutoff, supplier_code, supplier_code,
            )
            return self._rows_to_dicts(cursor, cursor.fetchall())
        finally:
            self._close(connection)

    def get_pricing_policy(
        self,
        channel: str,
        *,
        category: str | None = None,
        brand: str | None = None,
        as_of: datetime | None = None,
    ) -> dict[str, Any] | None:
        channel_code = _text(channel, upper=True)
        category_code = _text(category, upper=True) or None
        brand_code = _text(brand, upper=True) or None
        instant = _utc(as_of)
        if not channel_code:
            raise ValueError("channel is required")
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
SELECT TOP (1)
    policy_id, channel_code, category_code, brand, minimum_margin_pct,
    minimum_contribution_pen, undercut_amount_pen, strategy
FROM dbo.market_pricing_policy
WHERE channel_code = ?
  AND is_active = 1
  AND effective_from <= ?
  AND (effective_to IS NULL OR effective_to > ?)
  AND (category_code IS NULL OR category_code = ?)
  AND (brand IS NULL OR brand = ?)
ORDER BY
    CASE WHEN brand = ? THEN 1 ELSE 0 END DESC,
    CASE WHEN category_code = ? THEN 1 ELSE 0 END DESC,
    effective_from DESC, policy_id DESC;
""",
                channel_code, instant, instant, category_code, brand_code,
                brand_code, category_code,
            )
            return self._row_to_dict(cursor, cursor.fetchone())
        finally:
            self._close(connection)

    def upsert_pricing_policy(
        self,
        *,
        channel_code: str,
        effective_from: datetime,
        minimum_margin_pct: Decimal,
        minimum_contribution_pen: Decimal,
        category_code: str | None = None,
        brand: str | None = None,
        stech_margin_pct: Decimal | None = None,
        undercut_amount_pen: Decimal = Decimal("1"),
        strategy: str = "BALANCED",
        effective_to: datetime | None = None,
        is_active: bool = True,
    ) -> dict[str, Any]:
        channel = _text(channel_code, upper=True)
        category = _text(category_code, upper=True) or None
        brand_name = _text(brand, upper=True) or None
        strategy_code = _text(strategy, upper=True)
        if not channel:
            raise ValueError("channel_code is required")
        if strategy_code not in _STRATEGIES:
            raise ValueError("invalid strategy")
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
INSERT INTO dbo.market_pricing_policy(
    channel_code, category_code, brand, stech_margin_pct, minimum_margin_pct,
    minimum_contribution_pen, undercut_amount_pen, strategy,
    effective_from, effective_to, is_active
)
OUTPUT INSERTED.policy_id, INSERTED.channel_code, INSERTED.category_code, INSERTED.brand,
       INSERTED.minimum_margin_pct, INSERTED.minimum_contribution_pen,
       INSERTED.undercut_amount_pen, INSERTED.strategy
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
""",
                channel, category, brand_name, stech_margin_pct, minimum_margin_pct,
                minimum_contribution_pen, undercut_amount_pen, strategy_code,
                _utc(effective_from), _utc(effective_to) if effective_to else None, bool(is_active),
            )
            result = self._row_to_dict(cursor, cursor.fetchone())
            if result is None:
                raise RuntimeError("pricing policy insert returned no row")
            connection.commit()
            return result
        except Exception:
            self._rollback(connection)
            raise
        finally:
            self._close(connection)

    def get_fee_rule(
        self,
        channel: str,
        *,
        category: str | None = None,
        as_of: datetime | None = None,
    ) -> dict[str, Any] | None:
        channel_code = _text(channel, upper=True)
        category_code = _text(category, upper=True) or None
        instant = _utc(as_of)
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
SELECT TOP (1) fee_rule_id, channel_code, category_code, commission_pct,
       fixed_fee_pen, payment_fee_pct, shipping_cost_pen,
       free_shipping_threshold_pen, seller_absorbs_shipping_above_threshold
FROM dbo.market_channel_fee_rule
WHERE channel_code = ? AND is_active = 1
  AND effective_from <= ? AND (effective_to IS NULL OR effective_to > ?)
  AND (category_code IS NULL OR category_code = ?)
ORDER BY CASE WHEN category_code = ? THEN 1 ELSE 0 END DESC,
         effective_from DESC, fee_rule_id DESC;
""",
                channel_code, instant, instant, category_code, category_code,
            )
            return self._row_to_dict(cursor, cursor.fetchone())
        finally:
            self._close(connection)

    def upsert_fee_rule(
        self,
        *,
        channel_code: str,
        effective_from: datetime,
        commission_pct: Decimal = Decimal("0"),
        fixed_fee_pen: Decimal = Decimal("0"),
        payment_fee_pct: Decimal = Decimal("0"),
        shipping_cost_pen: Decimal | None = None,
        free_shipping_threshold_pen: Decimal | None = None,
        seller_absorbs_shipping_above_threshold: bool = False,
        category_code: str | None = None,
        effective_to: datetime | None = None,
        is_active: bool = True,
    ) -> dict[str, Any]:
        channel = _text(channel_code, upper=True)
        if not channel:
            raise ValueError("channel_code is required")
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
INSERT INTO dbo.market_channel_fee_rule(
    channel_code, category_code, commission_pct, fixed_fee_pen, payment_fee_pct,
    shipping_cost_pen, free_shipping_threshold_pen,
    seller_absorbs_shipping_above_threshold, effective_from, effective_to, is_active
)
OUTPUT INSERTED.fee_rule_id, INSERTED.channel_code, INSERTED.category_code,
       INSERTED.commission_pct, INSERTED.fixed_fee_pen, INSERTED.payment_fee_pct,
       INSERTED.shipping_cost_pen, INSERTED.free_shipping_threshold_pen,
       INSERTED.seller_absorbs_shipping_above_threshold
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
""",
                channel, _text(category_code, upper=True) or None, commission_pct,
                fixed_fee_pen, payment_fee_pct, shipping_cost_pen,
                free_shipping_threshold_pen, bool(seller_absorbs_shipping_above_threshold),
                _utc(effective_from), _utc(effective_to) if effective_to else None, bool(is_active),
            )
            result = self._row_to_dict(cursor, cursor.fetchone())
            if result is None:
                raise RuntimeError("fee rule insert returned no row")
            connection.commit()
            return result
        except Exception:
            self._rollback(connection)
            raise
        finally:
            self._close(connection)

    def get_latest_fx_rate(
        self,
        base_currency: str = "USD",
        quote_currency: str = "PEN",
        *,
        as_of: datetime | None = None,
    ) -> dict[str, Any] | None:
        instant = _utc(as_of)
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
SELECT TOP (1) market_fx_rate_id, rate_date, base_currency, quote_currency,
       rate, source_code, observed_at
FROM dbo.market_fx_rate
WHERE base_currency = ? AND quote_currency = ? AND rate_date <= CAST(? AS date)
ORDER BY rate_date DESC, observed_at DESC, market_fx_rate_id DESC;
""",
                _text(base_currency, upper=True), _text(quote_currency, upper=True), instant,
            )
            return self._row_to_dict(cursor, cursor.fetchone())
        finally:
            self._close(connection)

    def get_internal_signal(self, partnumber: str, as_of: datetime | None = None) -> dict[str, Any] | None:
        pn = _text(partnumber, upper=True)
        instant = _utc(as_of)
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
SELECT TOP (1) market_internal_signal_id, partnumber, observed_at, own_stock_qty,
       sales_units_7d, sales_units_30d, sales_units_90d, days_since_last_sale,
       inventory_age_days, own_sale_price_pen, source_code
FROM dbo.market_internal_signal
WHERE partnumber = ? AND observed_at <= ?
ORDER BY observed_at DESC, market_internal_signal_id DESC;
""",
                pn, instant,
            )
            return self._row_to_dict(cursor, cursor.fetchone())
        finally:
            self._close(connection)

    def upsert_internal_signal(
        self,
        *,
        partnumber: str,
        observed_at: datetime,
        source_code: str,
        source_key: str,
        own_stock_qty: Decimal | None = None,
        sales_units_7d: Decimal | None = None,
        sales_units_30d: Decimal | None = None,
        sales_units_90d: Decimal | None = None,
        days_since_last_sale: int | None = None,
        inventory_age_days: int | None = None,
        own_sale_price_pen: Decimal | None = None,
    ) -> dict[str, Any]:
        pn = _text(partnumber, upper=True)
        source = _text(source_code, upper=True)
        key = _text(source_key)
        if not pn or not source or not key:
            raise ValueError("partnumber, source_code and source_key are required")
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT market_internal_signal_id FROM dbo.market_internal_signal WHERE source_code = ? AND source_key = ?;",
                source, key,
            )
            existing = cursor.fetchone()
            if existing is not None:
                return {"market_internal_signal_id": int(existing[0]), "inserted": False}
            cursor.execute(
                """
INSERT INTO dbo.market_internal_signal(
    partnumber, observed_at, own_stock_qty, sales_units_7d, sales_units_30d,
    sales_units_90d, days_since_last_sale, inventory_age_days, own_sale_price_pen,
    source_code, source_key
)
OUTPUT INSERTED.market_internal_signal_id
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
""",
                pn, _utc(observed_at), own_stock_qty, sales_units_7d, sales_units_30d,
                sales_units_90d, days_since_last_sale, inventory_age_days,
                own_sale_price_pen, source, key,
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("internal signal insert returned no id")
            connection.commit()
            return {"market_internal_signal_id": int(row[0]), "inserted": True}
        except Exception:
            self._rollback(connection)
            raise
        finally:
            self._close(connection)

    def list_candidate_partnumbers(
        self,
        *,
        channel: str | None = None,
        limit: int = 100,
    ) -> list[str]:
        safe_limit = max(1, min(int(limit), 500))
        channel_code = _text(channel, upper=True) or None
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                f"""
SELECT DISTINCT TOP ({safe_limit}) m.partnumber
FROM dbo.market_product_match m
INNER JOIN dbo.market_listing l ON l.market_listing_id = m.market_listing_id
WHERE m.match_status = 'VERIFIED'
  AND (? IS NULL OR l.source_code = ?)
ORDER BY m.partnumber;
""",
                channel_code, channel_code,
            )
            return [str(row[0]) for row in cursor.fetchall()]
        finally:
            self._close(connection)

    def save_recommendation_snapshot(self, snapshot: dict[str, Any]) -> None:
        action = _text(snapshot.get("action_code"), upper=True)
        if action not in _ACTIONS:
            raise ValueError("invalid action_code")
        partnumber = _text(snapshot.get("partnumber"), upper=True)
        if not partnumber:
            raise ValueError("partnumber is required")
        reasons = snapshot.get("reason_codes") or []
        reasons_json = json.dumps(reasons, ensure_ascii=False, separators=(",", ":"))
        fingerprint = _text(snapshot.get("input_fingerprint"), upper=False).lower()
        if len(fingerprint) != 64:
            raise ValueError("input_fingerprint must be a SHA-256 hex digest")
        confidence = _score(snapshot.get("confidence_score"), "confidence_score")
        risk = _score(snapshot.get("risk_score"), "risk_score")
        opportunity = _score(snapshot.get("opportunity_score"), "opportunity_score")

        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
IF NOT EXISTS (
    SELECT 1 FROM dbo.market_recommendation_snapshot
    WHERE partnumber = ? AND ((channel_code = ?) OR (channel_code IS NULL AND ? IS NULL))
      AND input_fingerprint = ?
)
INSERT INTO dbo.market_recommendation_snapshot(
    partnumber, channel_code, calculated_at, action_code, opportunity_score,
    confidence_score, risk_score, recommended_price_pen, floor_price_pen,
    market_min_price_pen, market_median_price_pen, expected_profit_pen,
    expected_margin_pct, reason_codes_json, input_fingerprint
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
""",
                partnumber, snapshot.get("channel_code"), snapshot.get("channel_code"), fingerprint,
                partnumber, snapshot.get("channel_code"), _utc(snapshot.get("calculated_at")), action,
                opportunity, confidence, risk, snapshot.get("recommended_price_pen"),
                snapshot.get("floor_price_pen"), snapshot.get("market_min_price_pen"),
                snapshot.get("market_median_price_pen"), snapshot.get("expected_profit_pen"),
                snapshot.get("expected_margin_pct"), reasons_json, fingerprint,
            )
            connection.commit()
        except Exception:
            self._rollback(connection)
            raise
        finally:
            self._close(connection)
