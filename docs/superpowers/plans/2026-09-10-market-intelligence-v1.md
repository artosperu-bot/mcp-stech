# Market Intelligence V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an additive, auditable market-intelligence subsystem to STECH MCP for competitor history, supplier history, profitability, price recommendations, opportunity/risk scoring and commercial action recommendations without modifying operational prices, stock or listings.

**Architecture:** Reuse the current V2 layering (`domain` → `db repositories` → `services` → `tools` → additive `server_authoritative.py` wiring). Persist immutable market observations and configurable commercial policies in `STECH_MCP`; read operational product/stock/history from existing repositories where possible. Keep calculations deterministic and return structured reason codes, freshness and confidence separately from opportunity score.

**Tech Stack:** Python 3.11+, MCP server, SQL Server 2019, pyodbc-style repositories, pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-10-market-intelligence-v1-design.md`

## Global Constraints

- Do not create free-form SQL tools.
- Do not modify operational price, stock, category, activation or marketplace listings.
- Historical observations are append-only/idempotent; never overwrite prior market history.
- Only `VERIFIED` product matches may drive automatic price recommendations.
- Opportunity score and confidence score are distinct values.
- `COMPRAR`, `SUBIR_STOCK`, `LIQUIDAR` and price actions remain recommendations only in V1.
- All policy/fee rules are effective-dated and configurable; no hardcoded marketplace commissions.
- Unknown factors do not count as zero; scoring renormalizes available weights and lowers confidence.
- Strong actions require minimum confidence 70 and maximum risk 65; otherwise downgrade to `INVESTIGAR`.

---

### Task 1: SQL schema and migration contract

**Files:**
- Create: `sql/010_market_intelligence_v1.sql`
- Create: `tests/test_market_intelligence_schema.py`

**Interfaces:**
- Produces tables: `market_listing`, `market_product_match`, `market_observation`, `supplier_observation`, `market_pricing_policy`, `market_channel_fee_rule`, `market_fx_rate`, `market_internal_signal`, `market_recommendation_snapshot`.
- Produces indexes for `(market_listing_id, observed_at)`, `(partnumber, observed_at)`, current active policy lookup and recommendation history.

- [ ] **Step 1: Write the failing schema test**

```python
from pathlib import Path


def test_market_intelligence_migration_contains_required_objects():
    sql = Path("sql/010_market_intelligence_v1.sql").read_text(encoding="utf-8")
    for name in (
        "market_listing",
        "market_product_match",
        "market_observation",
        "supplier_observation",
        "market_pricing_policy",
        "market_channel_fee_rule",
        "market_fx_rate",
        "market_internal_signal",
        "market_recommendation_snapshot",
    ):
        assert f"dbo.{name}" in sql
    assert "VERIFIED" in sql
    assert "confidence_score" in sql
```

- [ ] **Step 2: Run CI and verify RED**

Expected: failure because `sql/010_market_intelligence_v1.sql` does not exist.

- [ ] **Step 3: Add idempotent SQL Server migration**

Use `IF OBJECT_ID(...) IS NULL CREATE TABLE ...` and `IF NOT EXISTS (...) CREATE INDEX ...`. Use `datetime2(3)` in UTC-style timestamps, decimal monetary fields, check constraints for score ranges 0..100 and match/action enums, and unique keys for idempotent ingestion keys.

- [ ] **Step 4: Run CI and verify GREEN**

Expected: schema test passes and existing migration tests remain green.

- [ ] **Step 5: Commit**

```bash
git add sql/010_market_intelligence_v1.sql tests/test_market_intelligence_schema.py
git commit -m "feat: add market intelligence schema"
```

---

### Task 2: Deterministic market math and scoring domain

**Files:**
- Create: `src/stech_mcp/domain/market_models.py`
- Create: `src/stech_mcp/domain/market_math.py`
- Create: `src/stech_mcp/domain/opportunity_score.py`
- Create: `tests/test_market_math.py`
- Create: `tests/test_opportunity_score.py`

**Interfaces:**
- Produces `calculate_profit(sale_price_pen: Decimal, product_cost_pen: Decimal, commission_pct: Decimal, payment_fee_pct: Decimal, fixed_fee_pen: Decimal, shipping_cost_pen: Decimal, other_cost_pen: Decimal = Decimal("0")) -> dict[str, Decimal]`.
- Produces `calculate_floor_price(...) -> Decimal` satisfying both minimum margin and minimum contribution.
- Produces `summarize_series(observations: list[dict], as_of: datetime) -> dict` with previous/1d/7d/30d/90d deltas, min/max/mean/median, volatility, last-change age and observation count.
- Produces `score_opportunity(factors: dict[str, float | None], weights: dict[str, float]) -> dict[str, float]` and `score_confidence(inputs: dict[str, float | bool | None]) -> float`.
- Produces `gate_action(action_code: str, confidence_score: float, risk_score: float) -> str`.

- [ ] **Step 1: Write failing tests for financial math and score renormalization**

```python
from decimal import Decimal
from stech_mcp.domain.market_math import calculate_profit
from stech_mcp.domain.opportunity_score import score_opportunity, gate_action


def test_profit_returns_full_contribution_breakdown():
    result = calculate_profit(
        sale_price_pen=Decimal("1500"), product_cost_pen=Decimal("1000"),
        commission_pct=Decimal("0.10"), payment_fee_pct=Decimal("0.02"),
        fixed_fee_pen=Decimal("5"), shipping_cost_pen=Decimal("20"),
    )
    assert result["contribution_pen"] == Decimal("295")
    assert result["margin_pct"] == Decimal("0.1966666667")


def test_unknown_factor_is_renormalized_not_scored_zero():
    result = score_opportunity({"profitability": 80, "demand": None}, {"profitability": 30, "demand": 15})
    assert result["opportunity_score"] == 80
    assert result["coverage_pct"] < 100


def test_strong_action_is_downgraded_when_confidence_is_low():
    assert gate_action("COMPRAR", 55, 20) == "INVESTIGAR"
```

- [ ] **Step 2: Run CI and verify RED**

Expected: imports fail because new domain modules do not exist.

- [ ] **Step 3: Implement minimal Decimal-safe calculations and scoring**

Keep calculations pure: no repository access, no network access and no hardcoded marketplace values.

- [ ] **Step 4: Add tests for floor price, percent change, empty history, one-point history, volatility and risk gating**

- [ ] **Step 5: Run CI and verify GREEN**

- [ ] **Step 6: Commit**

```bash
git add src/stech_mcp/domain/market_models.py src/stech_mcp/domain/market_math.py src/stech_mcp/domain/opportunity_score.py tests/test_market_math.py tests/test_opportunity_score.py
git commit -m "feat: add market intelligence domain math"
```

---

### Task 3: Market repository and immutable ingestion

**Files:**
- Create: `src/stech_mcp/db/market_repository.py`
- Create: `tests/test_market_repository.py`

**Interfaces:**
- `MarketRepository(connection_factory)`
- `upsert_listing(...) -> dict`
- `upsert_product_match(...) -> dict`
- `insert_observation(...) -> dict` idempotent by `source_observation_key` or fingerprint key.
- `insert_supplier_observation(...) -> dict`
- `get_verified_competitors(partnumber, channel=None) -> list[dict]`
- `get_price_history(partnumber, channel=None, days=30) -> list[dict]`
- `get_supplier_history(partnumber, supplier=None, days=90) -> list[dict]`
- `get_pricing_policy(channel, category=None, brand=None, as_of=None) -> dict | None`
- `upsert_pricing_policy(...) -> dict`
- `get_fee_rule(...) -> dict | None`
- `upsert_fee_rule(...) -> dict`
- `get_internal_signal(partnumber, as_of=None) -> dict | None`
- `upsert_internal_signal(...) -> dict`
- `save_recommendation_snapshot(snapshot: dict) -> None`

- [ ] **Step 1: Write failing repository tests using the project fake-connection pattern**

Test that duplicate observation keys do not create a second row, policy selection prefers channel+category+brand over less-specific rules, and competitor queries require `VERIFIED` matches.

- [ ] **Step 2: Run CI and verify RED**

- [ ] **Step 3: Implement parametrized repository methods**

Follow existing repository cursor/row normalization conventions. Validate table identifiers internally; callers only pass values, never SQL fragments.

- [ ] **Step 4: Run focused repository tests and full CI**

- [ ] **Step 5: Commit**

```bash
git add src/stech_mcp/db/market_repository.py tests/test_market_repository.py
git commit -m "feat: persist market intelligence observations"
```

---

### Task 4: Product-level analysis, variations and pricing service

**Files:**
- Create: `src/stech_mcp/services/market_intelligence.py`
- Create: `tests/test_market_intelligence_service.py`

**Interfaces:**
- `MarketIntelligenceService(market_repository, product_repository)`
- `competitors_get(partnumber, channel=None) -> dict`
- `price_history(partnumber, channel=None, days=30) -> dict`
- `variations_get(partnumber, channel=None, windows=(1,7,30,90)) -> dict`
- `data_quality(partnumber, channel=None) -> dict`
- `profit_simulate(partnumber, channel, sale_price_pen, overrides=None) -> dict`
- `recommended_price(partnumber, channel, strategy="BALANCED") -> dict`
- `product_analyze(partnumber, channel=None) -> dict`
- `risk_analyze(partnumber, channel=None) -> dict`

- [ ] **Step 1: Write failing tests for verified-only competitor analysis and price recommendation floor**

```python
def test_recommended_price_never_breaks_floor_in_balanced_strategy(service):
    result = service.recommended_price("82YU00XYLM", "FALABELLA", strategy="BALANCED")
    assert result["recommended_price_pen"] >= result["floor_price_pen"]


def test_market_below_floor_returns_no_competir_precio(service):
    result = service.recommended_price("82YU00XYLM", "FALABELLA")
    assert result["action_code"] == "NO_COMPETIR"
    assert "MARKET_BELOW_FLOOR" in result["reason_codes"]
```

- [ ] **Step 2: Run CI and verify RED**

- [ ] **Step 3: Implement analysis pipeline**

Resolve product identity, policy, fees, latest supplier cost/FX, verified competitor history and internal signal. Return `as_of`, freshness, observation counts, score inputs and structured reasons. Do not silently invent missing values.

- [ ] **Step 4: Implement strategies**

`BALANCED`: target a competitive percentile while preserving floor. `MARGIN`: prefer market median/upper competitive band. `VOLUME`: approach verified market minimum without breaking floor. `CLEARANCE`: may go below normal floor only when explicitly requested and must expose exceptional margin/loss flags.

- [ ] **Step 5: Add tests for stale data, no competitors, own price materially below market, clearance exception and price-war signal**

- [ ] **Step 6: Run full CI and verify GREEN**

- [ ] **Step 7: Commit**

```bash
git add src/stech_mcp/services/market_intelligence.py tests/test_market_intelligence_service.py
git commit -m "feat: analyze market pricing and risk"
```

---

### Task 5: Opportunity discovery and portfolio strategy

**Files:**
- Create: `src/stech_mcp/services/market_opportunities.py`
- Create: `tests/test_market_opportunities.py`

**Interfaces:**
- `MarketOpportunityService(market_service, market_repository, product_repository)`
- `opportunities_find(channel=None, category=None, limit=30) -> dict`
- `assortment_gaps(channel=None, category=None, limit=30) -> dict`
- `supplier_opportunities(supplier=None, category=None, limit=30) -> dict`
- `channel_opportunities(channel, category=None, limit=30) -> dict`
- `strategy(channel=None, category=None, budget_pen=None, limit=30) -> dict`
- `weekly_actions(channel=None, category=None, limit=50) -> dict`

- [ ] **Step 1: Write failing tests for ordering, confidence gating and budget allocation**

A product with higher opportunity but confidence below 70 must rank as `INVESTIGAR`, not `COMPRAR`. Budget allocation must never exceed `budget_pen`, must use positive contribution products only and return unallocated budget.

- [ ] **Step 2: Run CI and verify RED**

- [ ] **Step 3: Implement candidate ranking**

Use deterministic sort keys: gated action priority, opportunity desc, confidence desc, expected contribution desc, partnumber asc. Limit values to safe caps.

- [ ] **Step 4: Implement assortment/supplier/channel gap reason codes**

Examples: `NO_STECH_LISTING`, `FEW_VERIFIED_COMPETITORS`, `SUPPLIER_COST_DROP`, `SUPPLIER_IN_STOCK`, `OWN_STOCK_AGING`, `NO_SALES_90D`, `MARKET_STOCKOUT`, `GOOD_MARGIN_SPACE`.

- [ ] **Step 5: Run full CI and verify GREEN**

- [ ] **Step 6: Commit**

```bash
git add src/stech_mcp/services/market_opportunities.py tests/test_market_opportunities.py
git commit -m "feat: rank market opportunities and strategy"
```

---

### Task 6: MCP tools and authoritative runtime wiring

**Files:**
- Create: `src/stech_mcp/tools/market_intelligence.py`
- Modify: `src/stech_mcp/server_authoritative.py`
- Create: `tests/test_server_market_intelligence_tools.py`

**Interfaces:**
- Register tools exactly: `market_observation_ingest`, `market_product_match_upsert`, `market_pricing_policy_get`, `market_pricing_policy_upsert`, `market_channel_fee_rule_get`, `market_channel_fee_rule_upsert`, `market_competitors_get`, `market_price_history`, `market_variations_get`, `market_data_quality`, `market_profit_simulate`, `market_recommended_price`, `market_product_analyze`, `market_risk_analyze`, `market_opportunities_find`, `market_assortment_gaps`, `market_supplier_opportunities`, `market_channel_opportunities`, `market_strategy`, `market_weekly_actions`.

- [ ] **Step 1: Write failing smoke test for required tool names**

```python
def test_market_tools_are_registered():
    source = Path("src/stech_mcp/tools/market_intelligence.py").read_text(encoding="utf-8")
    for tool in ("market_product_analyze", "market_recommended_price", "market_strategy", "market_weekly_actions"):
        assert tool in source
```

- [ ] **Step 2: Run CI and verify RED**

- [ ] **Step 3: Implement registration function and runtime wiring**

Instantiate `MarketRepository`, `MarketIntelligenceService` and `MarketOpportunityService` from `_server.mcp_connection_factory` and `_server.product_repository`, then register tools additively in `server_authoritative.py`. Tool write methods must validate enums, percentages, limits, timestamps and required source keys.

- [ ] **Step 4: Add smoke tests proving existing tools remain registered**

- [ ] **Step 5: Run full CI and verify GREEN**

- [ ] **Step 6: Commit**

```bash
git add src/stech_mcp/tools/market_intelligence.py src/stech_mcp/server_authoritative.py tests/test_server_market_intelligence_tools.py
git commit -m "feat: expose market intelligence MCP tools"
```

---

### Task 7: Documentation and end-to-end acceptance

**Files:**
- Modify: `README.md`
- Create: `docs/MARKET_INTELLIGENCE_V1.md`
- Create: `tests/test_market_intelligence_acceptance.py`

**Interfaces:**
- Acceptance sequence: ingest listing → verified match → multiple observations → configure policy/fees → analyze product → obtain variations/risk/recommended price → list portfolio opportunity.

- [ ] **Step 1: Write failing acceptance test with in-memory/fake repositories**

The test must prove that a competitor price drop is visible in variations, profit simulation uses configured fees, recommendation never breaks non-clearance floor, and low-confidence strong actions become `INVESTIGAR`.

- [ ] **Step 2: Run CI and verify RED if any cross-layer behavior is still missing**

- [ ] **Step 3: Complete only the missing integration behavior revealed by the test**

- [ ] **Step 4: Document deployment**

Document `sqlcmd -S PC020 -E -C -i ".\sql\010_market_intelligence_v1.sql"`, server restart, example tool calls, meaning of opportunity/confidence/risk and the V1 no-write-to-marketplaces safety boundary.

- [ ] **Step 5: Run the full test suite**

Run GitHub Actions `pytest` workflow against the branch and require zero failures.

- [ ] **Step 6: Inspect diff against `feat/product-enrichment-engine-v2-current`**

Confirm only Market Intelligence files plus intentional additive wiring/docs changed.

- [ ] **Step 7: Commit**

```bash
git add README.md docs/MARKET_INTELLIGENCE_V1.md tests/test_market_intelligence_acceptance.py
git commit -m "docs: document market intelligence v1"
```
