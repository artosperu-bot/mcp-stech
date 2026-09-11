from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from stech_mcp.db.market_repository import MarketRepository


class FakeDatabase:
    def __init__(self):
        self.observations: dict[tuple[int, str], int] = {}
        self.next_observation_id = 1
        self.executed: list[tuple[str, tuple]] = []

    def connect(self):
        return FakeConnection(self)


class FakeCursor:
    def __init__(self, db: FakeDatabase):
        self.db = db
        self.current = None
        self.rows = []
        self.description = []

    def execute(self, sql, *params):
        normalized = " ".join(sql.upper().split())
        self.db.executed.append((normalized, params))
        self.current = None
        self.rows = []

        if normalized.startswith("SELECT MARKET_OBSERVATION_ID") and "SOURCE_OBSERVATION_KEY" in normalized:
            key = (int(params[0]), str(params[1]))
            existing = self.db.observations.get(key)
            self.current = (existing,) if existing is not None else None
            self.description = [("market_observation_id",)]
        elif normalized.startswith("INSERT INTO DBO.MARKET_OBSERVATION"):
            listing_id = int(params[0])
            source_key = str(params[11]) if params[11] is not None else ""
            observation_id = self.db.next_observation_id
            self.db.next_observation_id += 1
            if source_key:
                self.db.observations[(listing_id, source_key)] = observation_id
            self.current = (observation_id,)
            self.description = [("market_observation_id",)]
        elif "FROM DBO.MARKET_LISTING L" in normalized and "MARKET_PRODUCT_MATCH" in normalized:
            assert "M.MATCH_STATUS = 'VERIFIED'" in normalized
            self.description = [
                ("market_listing_id",), ("source_code",), ("seller_name",),
                ("external_listing_id",), ("price_effective",), ("stock_state",),
                ("observed_at",), ("data_quality_score",),
            ]
            self.rows = [
                (7, "FALABELLA", "SELLER A", "ABC", Decimal("1499"), "IN_STOCK", datetime(2026, 9, 10, tzinfo=timezone.utc), Decimal("90")),
            ]
        elif "FROM DBO.MARKET_PRICING_POLICY" in normalized:
            assert "ORDER BY" in normalized
            assert "CASE WHEN BRAND = ?" in normalized
            assert "CASE WHEN CATEGORY_CODE = ?" in normalized
            self.description = [
                ("policy_id",), ("channel_code",), ("category_code",), ("brand",),
                ("minimum_margin_pct",), ("minimum_contribution_pen",),
                ("undercut_amount_pen",), ("strategy",),
            ]
            self.current = (3, "FALABELLA", "LAPTOP", "LENOVO", Decimal("0.12"), Decimal("80"), Decimal("1"), "BALANCED")
        else:
            raise AssertionError(f"unexpected SQL: {sql}")
        return self

    def fetchone(self):
        return self.current

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, db: FakeDatabase):
        self.cursor_obj = FakeCursor(db)
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def test_observation_ingestion_is_idempotent_by_source_key():
    db = FakeDatabase()
    repo = MarketRepository(db.connect)
    payload = dict(
        market_listing_id=12,
        observed_at=datetime(2026, 9, 10, 12, tzinfo=timezone.utc),
        price_regular=Decimal("1599"),
        price_offer=Decimal("1499"),
        price_effective=Decimal("1499"),
        stock_qty=Decimal("5"),
        stock_state="IN_STOCK",
        promotion_text="Oferta",
        promotion_type="SALE",
        shipping_price=Decimal("0"),
        seller_count=3,
        ranking_position=1,
        source_method="API",
        source_observation_key="falabella:abc:20260910T1200",
        raw_fingerprint="a" * 64,
        data_quality_score=Decimal("95"),
    )

    first = repo.insert_observation(**payload)
    second = repo.insert_observation(**payload)

    assert first["market_observation_id"] == second["market_observation_id"] == 1
    assert first["inserted"] is True
    assert second["inserted"] is False
    inserts = [sql for sql, _ in db.executed if sql.startswith("INSERT INTO DBO.MARKET_OBSERVATION")]
    assert len(inserts) == 1


def test_competitor_query_uses_only_verified_product_matches():
    db = FakeDatabase()
    repo = MarketRepository(db.connect)

    rows = repo.get_verified_competitors("82yu00xylm", channel="falabella")

    assert len(rows) == 1
    assert rows[0]["source_code"] == "FALABELLA"
    assert rows[0]["price_effective"] == Decimal("1499")


def test_policy_lookup_prefers_brand_then_category_specificity():
    db = FakeDatabase()
    repo = MarketRepository(db.connect)

    policy = repo.get_pricing_policy(
        "falabella",
        category="laptop",
        brand="lenovo",
        as_of=datetime(2026, 9, 10, tzinfo=timezone.utc),
    )

    assert policy is not None
    assert policy["policy_id"] == 3
    assert policy["brand"] == "LENOVO"
    assert policy["category_code"] == "LAPTOP"
