# Multichannel Product Enrichment Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert STECH MCP Phase 1 into a master enrichment engine with persistent evidence, the approved 15.x laptop packaging fallback, generic marketplace schemas, and backward-compatible Coolbox preview.

**Architecture:** Keep `DB_DISTRIBUIDORES` as read-only operational source and `STECH_MCP` as the persistence layer for enrichment/evidence/rules/templates. Add focused repositories and resolvers so marketplace outputs consume one master product state. Official/approved enrichment always outranks fallback estimates; the 15.x packaging rule is used only when no higher-priority package evidence exists.

**Tech Stack:** Python 3.12+, MCP Python SDK 2.x, pyodbc 5.x, SQL Server 2019, Pydantic 2.x, pytest 8.x/9.x, openpyxl 3.x.

**Spec:** `docs/superpowers/specs/2026-09-04-multichannel-product-enrichment-design.md`

## Global Constraints

- Preserve existing `product_get`, `product_search`, `product_history`, `coolbox_preview`, packaging tools, and public MCP HTTP compatibility.
- Use only parameterized SQL for values; no arbitrary SQL tool is added.
- Official exact-PN evidence has priority over distributor data and estimates.
- Sensitive variant fields such as RAM, SSD, CPU, GPU, OS and color are never guessed.
- Approved manual values are never overwritten automatically.
- Laptop screens `>= 15.0` and `< 16.0` use fallback package `33 x 54 x 7 cm`, `2500 g` only when no trusted package value exists.
- Fallback package fields are always `ESTIMATED`, source `REGLA_STECH_EMPAQUE`, rule code `LAPTOP_15_X_DEFAULT`.
- Coolbox continues to expose exactly 81 fields for the current `Laptops-All in one` template.

---

## File Structure

### New files

- `sql/002_multichannel_enrichment_phase1.sql` — additive SQL migration for packaging rules and generic marketplace template metadata; seeds the approved 15.x rule.
- `src/stech_mcp/db/enrichment_repository.py` — persistence/read APIs for enrichment and evidence in `STECH_MCP`.
- `src/stech_mcp/db/packaging_rule_repository.py` — read-only matching of enabled package rules.
- `src/stech_mcp/domain/packaging_resolver.py` — precedence logic: approved enrichment first, rule fallback second.
- `src/stech_mcp/domain/marketplace_models.py` — small typed contracts for marketplace field state and resolved package metadata.
- `src/stech_mcp/services/marketplace_preview.py` — generic preview entry point; initially routes COOLBOX to current implementation while preserving generic interface.
- `tests/test_enrichment_repository.py`
- `tests/test_packaging_rule_repository.py`
- `tests/test_packaging_resolver.py`
- `tests/test_marketplace_preview.py`

### Modified files

- `src/stech_mcp/services/coolbox_preview.py` — remove hardcoded old package values for 15.x and consume a resolved package result.
- `src/stech_mcp/server.py` — create MCP persistence repositories and expose `packaging_rule_get`, `packaging_resolve`, `marketplace_preview` while keeping `coolbox_preview`.
- `tests/test_coolbox_preview.py` — update expected 15.x package fallback to approved values and test official override.
- `tests/test_server_smoke.py` — assert new tools are exposed.
- `README.md` — document Phase 1 tools, source precedence, and migration command.

---

### Task 1: Additive SQL schema for generic marketplace metadata and approved packaging rule

**Files:**
- Create: `sql/002_multichannel_enrichment_phase1.sql`
- Test: inspect migration manually plus repository tests in Tasks 2/3 against fake DB contracts; local integration executes migration on `STECH_MCP` before real MCP validation.

**Interfaces:**
- Produces table `dbo.packaging_rule`.
- Produces tables `dbo.marketplace_template`, `dbo.marketplace_template_field`, `dbo.marketplace_field_mapping`, `dbo.marketplace_product_override`, `dbo.marketplace_export_run`.
- Seeds `LAPTOP_15_X_DEFAULT` idempotently.

- [ ] **Step 1: Write the migration with additive/idempotent DDL**

Use the existing `sql/001_create_stech_mcp.sql` style: `IF OBJECT_ID(...) IS NULL` around each table. The packaging rule table must be:

```sql
IF OBJECT_ID(N'dbo.packaging_rule', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.packaging_rule (
        rule_code NVARCHAR(100) NOT NULL CONSTRAINT PK_packaging_rule PRIMARY KEY,
        category_code NVARCHAR(80) NOT NULL,
        screen_min_inches DECIMAL(5,2) NULL,
        screen_max_inches DECIMAL(5,2) NULL,
        width_cm DECIMAL(8,2) NOT NULL,
        length_cm DECIMAL(8,2) NOT NULL,
        height_cm DECIMAL(8,2) NOT NULL,
        weight_g INT NOT NULL,
        priority INT NOT NULL,
        enabled BIT NOT NULL CONSTRAINT DF_packaging_rule_enabled DEFAULT (1),
        source_code NVARCHAR(100) NOT NULL,
        created_at DATETIME2(0) NOT NULL CONSTRAINT DF_packaging_rule_created DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT CK_packaging_rule_dimensions CHECK (
            width_cm > 0 AND length_cm > 0 AND height_cm > 0 AND weight_g > 0
        )
    );
END;
GO
```

Seed the approved rule idempotently:

```sql
IF NOT EXISTS (SELECT 1 FROM dbo.packaging_rule WHERE rule_code = N'LAPTOP_15_X_DEFAULT')
BEGIN
    INSERT dbo.packaging_rule (
        rule_code, category_code, screen_min_inches, screen_max_inches,
        width_cm, length_cm, height_cm, weight_g, priority, enabled, source_code
    )
    VALUES (
        N'LAPTOP_15_X_DEFAULT', N'LAPTOP', 15.00, 16.00,
        33.00, 54.00, 7.00, 2500, 100, 1, N'REGLA_STECH_EMPAQUE'
    );
END;
GO
```

Create generic marketplace tables using composite keys so different template versions can coexist. Do not delete `coolbox_template_field` yet; migration must be backward-compatible.

- [ ] **Step 2: Validate migration syntax locally**

Run in SSMS against `STECH_MCP`:

```sql
:r .\sql\002_multichannel_enrichment_phase1.sql
```

Then verify:

```sql
SELECT *
FROM STECH_MCP.dbo.packaging_rule
WHERE rule_code = N'LAPTOP_15_X_DEFAULT';
```

Expected row: width `33`, length `54`, height `7`, weight `2500`, enabled `1`, source `REGLA_STECH_EMPAQUE`.

- [ ] **Step 3: Commit**

```bash
git add sql/002_multichannel_enrichment_phase1.sql
git commit -m "feat: add multichannel enrichment schema and packaging rule"
```

---

### Task 2: Add persistent enrichment/evidence repository

**Files:**
- Create: `src/stech_mcp/db/enrichment_repository.py`
- Create: `tests/test_enrichment_repository.py`

**Interfaces:**
- Consumes connection factory `Callable[[], Any]` from `make_mcp_connection_factory(settings)`.
- Produces `EnrichmentRepository.get_approved(partnumber: str, field_codes: list[str] | None = None) -> list[dict[str, Any]]`.
- Produces `EnrichmentRepository.upsert(...) -> dict[str, Any]`.
- Produces `EnrichmentRepository.add_evidence(...) -> dict[str, Any]`.

- [ ] **Step 1: Write failing repository tests with a fake DB-API connection**

Cover these behaviors:

```python
def test_get_approved_filters_by_partnumber_and_approved_only():
    repo = EnrichmentRepository(fake_factory)
    rows = repo.get_approved("82YU00XYLM")
    assert all(row["partnumber"] == "82YU00XYLM" for row in rows)
    assert all(row["is_approved"] for row in rows)


def test_upsert_uses_parameters_not_interpolated_sql():
    repo = EnrichmentRepository(fake_factory)
    repo.upsert(
        partnumber="82YU00XYLM",
        field_code="package_weight_g",
        value_number=2180,
        unit="g",
        method="VERIFIED",
        confidence_grade="A1",
        is_approved=True,
    )
    assert "82YU00XYLM" not in fake_cursor.last_sql
    assert fake_cursor.last_params[0] == "82YU00XYLM"
```

- [ ] **Step 2: Run tests and verify RED**

```bash
pytest tests/test_enrichment_repository.py -v
```

Expected: import/module failure because repository does not exist yet.

- [ ] **Step 3: Implement minimal repository**

`get_approved` query shape:

```sql
SELECT enrichment_id, partnumber, field_code, value_text, value_number,
       unit, method, confidence_grade, is_approved, created_at, updated_at
FROM dbo.product_enrichment
WHERE partnumber = ? AND is_approved = 1
ORDER BY field_code;
```

When `field_codes` is provided, build only the placeholder count dynamically and pass values separately:

```python
placeholders = ",".join("?" for _ in field_codes)
sql += f" AND field_code IN ({placeholders})"
params.extend(field_codes)
```

`upsert` must use SQL Server `MERGE` or update-then-insert with parameters and must preserve an approved `MANUAL` value unless caller explicitly passes `allow_manual_override=True`.

- [ ] **Step 4: Run repository tests GREEN**

```bash
pytest tests/test_enrichment_repository.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/stech_mcp/db/enrichment_repository.py tests/test_enrichment_repository.py
git commit -m "feat: add enrichment and evidence repository"
```

---

### Task 3: Add packaging rule repository and precedence resolver

**Files:**
- Create: `src/stech_mcp/db/packaging_rule_repository.py`
- Create: `src/stech_mcp/domain/packaging_resolver.py`
- Create: `src/stech_mcp/domain/marketplace_models.py`
- Create: `tests/test_packaging_rule_repository.py`
- Create: `tests/test_packaging_resolver.py`

**Interfaces:**
- `PackagingRuleRepository.match(category_code: str, screen_inches: Decimal) -> dict[str, Any] | None`
- `resolve_package(*, partnumber: str, category_code: str, screen_inches: Decimal, enrichment_repository: EnrichmentRepository, packaging_rule_repository: PackagingRuleRepository) -> dict[str, Any]`
- Return keys: `width_cm`, `length_cm`, `height_cm`, `weight_g`, `status`, `method`, `source`, `rule_code`, `confidence_grade`.

- [ ] **Step 1: Write failing rule boundary tests**

```python
def test_15_6_matches_approved_laptop_rule():
    rule = repo.match("LAPTOP", Decimal("15.6"))
    assert rule["rule_code"] == "LAPTOP_15_X_DEFAULT"
    assert rule["width_cm"] == Decimal("33.00")
    assert rule["length_cm"] == Decimal("54.00")
    assert rule["height_cm"] == Decimal("7.00")
    assert rule["weight_g"] == 2500


def test_16_0_does_not_match_15_x_rule():
    assert repo.match("LAPTOP", Decimal("16.0")) is None
```

The SQL predicate must make max exclusive:

```sql
WHERE enabled = 1
  AND category_code = ?
  AND (screen_min_inches IS NULL OR ? >= screen_min_inches)
  AND (screen_max_inches IS NULL OR ? < screen_max_inches)
ORDER BY priority ASC, rule_code ASC;
```

- [ ] **Step 2: Run rule tests RED**

```bash
pytest tests/test_packaging_rule_repository.py -v
```

- [ ] **Step 3: Implement `PackagingRuleRepository.match`**

Return the first matching enabled row as a dict and always close the connection.

- [ ] **Step 4: Write failing resolver precedence tests**

```python
def test_resolver_uses_estimated_rule_when_no_official_package_exists():
    result = resolve_package(
        partnumber="82YU00XYLM",
        category_code="LAPTOP",
        screen_inches=Decimal("15.6"),
        enrichment_repository=empty_enrichment_repo,
        packaging_rule_repository=rule_repo,
    )
    assert result == {
        "width_cm": Decimal("33.00"),
        "length_cm": Decimal("54.00"),
        "height_cm": Decimal("7.00"),
        "weight_g": 2500,
        "status": "ESTIMATED",
        "method": "ESTIMATED",
        "source": "REGLA_STECH_EMPAQUE",
        "rule_code": "LAPTOP_15_X_DEFAULT",
        "confidence_grade": "E",
    }


def test_resolver_prefers_approved_official_package_over_rule():
    result = resolve_package(
        partnumber="82YU00XYLM",
        category_code="LAPTOP",
        screen_inches=Decimal("15.6"),
        enrichment_repository=official_package_repo,
        packaging_rule_repository=rule_repo,
    )
    assert result["weight_g"] == 2180
    assert result["width_cm"] == Decimal("31.0")
    assert result["method"] == "VERIFIED"
    assert result["confidence_grade"] == "A1"
    assert result["rule_code"] is None
```

Official package fields are read from approved master codes:

- `package_width_cm`
- `package_length_cm`
- `package_height_cm`
- `package_weight_g`

Only use an official package if all four fields are present and approved. A partial package remains insufficient and falls back to a rule while the partial enrichment remains stored for later research.

- [ ] **Step 5: Implement resolver and run tests GREEN**

```bash
pytest tests/test_packaging_rule_repository.py tests/test_packaging_resolver.py -v
```

- [ ] **Step 6: Commit**

```bash
git add src/stech_mcp/db/packaging_rule_repository.py src/stech_mcp/domain/packaging_resolver.py src/stech_mcp/domain/marketplace_models.py tests/test_packaging_rule_repository.py tests/test_packaging_resolver.py
git commit -m "feat: resolve official packaging before fallback rules"
```

---

### Task 4: Migrate Coolbox package fields to the master resolver without changing its 81-field contract

**Files:**
- Modify: `src/stech_mcp/services/coolbox_preview.py`
- Modify: `tests/test_coolbox_preview.py`

**Interfaces:**
- Change `build_coolbox_preview` to accept optional resolved package input:

```python
def build_coolbox_preview(
    product: dict[str, Any],
    *,
    package: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ...
```

- When `package is None`, the service may retain a deterministic in-memory fallback for compatibility, but the 15.x fallback must use the approved values `33, 54, 7, 2500` and metadata `ESTIMATED/REGLA_STECH_EMPAQUE/LAPTOP_15_X_DEFAULT`.
- Server-side `coolbox_preview` in Task 6 will pass the DB-backed resolver result.

- [ ] **Step 1: Update existing failing expectation first**

Change the 15.6-inch package test to:

```python
def test_preview_uses_approved_15_x_packaging_fallback():
    preview = build_coolbox_preview(_product())
    fields = {row["field"]: row for row in preview["fields"]}

    assert fields["Alto (cm)"]["value"] == 7
    assert fields["Ancho (cm)"]["value"] == 33
    assert fields["Largo  (cm)"]["value"] == 54
    assert fields["Peso (g)"]["value"] == 2500
    assert fields["Peso (g)"]["status"] == "ESTIMATED"
    assert fields["Peso (g)"]["source"] == "REGLA_STECH_EMPAQUE"
```

Add official override test:

```python
def test_preview_accepts_verified_package_override():
    preview = build_coolbox_preview(
        _product(),
        package={
            "width_cm": 31.0,
            "length_cm": 50.5,
            "height_cm": 7.2,
            "weight_g": 2180,
            "status": "VERIFIED",
            "method": "VERIFIED",
            "source": "Lenovo PSREF",
            "rule_code": None,
            "confidence_grade": "A1",
        },
    )
    fields = {row["field"]: row for row in preview["fields"]}
    assert fields["Peso (g)"]["value"] == 2180
    assert fields["Peso (g)"]["status"] == "VERIFIED"
    assert fields["Peso (g)"]["source"] == "Lenovo PSREF"
```

- [ ] **Step 2: Run Coolbox tests RED**

```bash
pytest tests/test_coolbox_preview.py -v
```

Expected: current old package values `7.4, 33.3, 53.3, 2350` fail.

- [ ] **Step 3: Replace package-specific hardcoding**

Remove use of `estimate_package_weight` for `Peso (g)` inside Coolbox preview and centralize package assignment through a helper:

```python
def _apply_package(fields: dict[str, dict[str, Any]], package: dict[str, Any]) -> None:
    mapping = {
        "Alto (cm)": "height_cm",
        "Ancho (cm)": "width_cm",
        "Largo  (cm)": "length_cm",
        "Peso (g)": "weight_g",
    }
    for field_name, key in mapping.items():
        fields[field_name] = _field(
            package[key],
            package["status"],
            package["source"],
            package["method"],
            note=(f"rule_code={package['rule_code']}" if package.get("rule_code") else None),
        )
```

The compatibility fallback for 15.x must return exactly the approved package rule metadata.

- [ ] **Step 4: Run Coolbox tests GREEN**

```bash
pytest tests/test_coolbox_preview.py -v
```

Also confirm the sensitive-field test still passes: SSD capacity, refresh rate and GPU remain `RESEARCH_REQUIRED` when absent.

- [ ] **Step 5: Commit**

```bash
git add src/stech_mcp/services/coolbox_preview.py tests/test_coolbox_preview.py
git commit -m "feat: use approved packaging fallback in Coolbox preview"
```

---

### Task 5: Add generic marketplace preview interface

**Files:**
- Create: `src/stech_mcp/services/marketplace_preview.py`
- Create: `tests/test_marketplace_preview.py`

**Interfaces:**
- Produces:

```python
def build_marketplace_preview(
    *,
    product: dict[str, Any],
    marketplace: str,
    category: str,
    package: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ...
```

- Phase 1 supports `marketplace="COOLBOX"`, `category="LAPTOP"` and delegates to `build_coolbox_preview`.
- Unsupported marketplace/category combinations raise `ValueError` with stable message.

- [ ] **Step 1: Write failing routing tests**

```python
def test_generic_preview_routes_coolbox_laptop():
    result = build_marketplace_preview(
        product=_product(),
        marketplace="coolbox",
        category="laptop",
        package=None,
    )
    assert result["template"] == "Laptops-All in one"
    assert result["field_count"] == 81


def test_generic_preview_rejects_unknown_marketplace():
    with pytest.raises(ValueError, match="unsupported marketplace/category"):
        build_marketplace_preview(
            product=_product(), marketplace="UNKNOWN", category="LAPTOP"
        )
```

- [ ] **Step 2: Run tests RED**

```bash
pytest tests/test_marketplace_preview.py -v
```

- [ ] **Step 3: Implement minimal generic router**

Normalize marketplace/category to uppercase and route only the approved Phase 1 contract. Do not implement Falabella or VTEX columns until their real templates/schemas are reviewed.

- [ ] **Step 4: Run tests GREEN**

```bash
pytest tests/test_marketplace_preview.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/stech_mcp/services/marketplace_preview.py tests/test_marketplace_preview.py
git commit -m "feat: add generic marketplace preview interface"
```

---

### Task 6: Wire master repositories/resolver into MCP tools

**Files:**
- Modify: `src/stech_mcp/server.py`
- Modify: `tests/test_server_smoke.py`

**Interfaces:**
- Existing tools remain unchanged.
- Add:
  - `packaging_rule_get(screen_inches: float, category: str = "LAPTOP")`
  - `packaging_resolve(partnumber: str, category: str = "LAPTOP")`
  - `marketplace_preview(partnumber: str, marketplace: str, category: str = "LAPTOP")`

- [ ] **Step 1: Write failing smoke tests**

Extend `tests/test_server_smoke.py`:

```python
assert callable(server.packaging_rule_get)
assert callable(server.packaging_resolve)
assert callable(server.marketplace_preview)
```

- [ ] **Step 2: Run smoke test RED**

```bash
pytest tests/test_server_smoke.py -v
```

- [ ] **Step 3: Instantiate MCP DB repositories**

In `server.py` use existing factory:

```python
from stech_mcp.db.connection import make_mcp_connection_factory
from stech_mcp.db.enrichment_repository import EnrichmentRepository
from stech_mcp.db.packaging_rule_repository import PackagingRuleRepository

mcp_connection_factory = make_mcp_connection_factory(settings)
enrichment_repository = EnrichmentRepository(mcp_connection_factory)
packaging_rule_repository = PackagingRuleRepository(mcp_connection_factory)
```

- [ ] **Step 4: Implement `packaging_rule_get`**

```python
@mcp.tool()
def packaging_rule_get(screen_inches: float, category: str = "LAPTOP") -> dict[str, Any]:
    rule = packaging_rule_repository.match(category.strip().upper(), Decimal(str(screen_inches)))
    return {"found": rule is not None, "rule": rule}
```

- [ ] **Step 5: Implement `packaging_resolve`**

Load product via `ProductRepository`; derive screen inches from the existing Coolbox parsing helper moved to a public focused helper if necessary. If product is absent return `found=False`. Otherwise call `resolve_package` and return `found=True`, `partnumber`, `package`.

- [ ] **Step 6: Make existing `coolbox_preview` use the DB-backed package resolver**

Server flow:

```python
product = product_repository.get_by_partnumber(partnumber)
package = resolve_package(...)
preview = build_coolbox_preview(product, package=package)
```

This is where official approved package enrichment begins to outrank the fallback rule in real MCP use.

- [ ] **Step 7: Implement generic `marketplace_preview` MCP tool**

```python
@mcp.tool()
def marketplace_preview(partnumber: str, marketplace: str, category: str = "LAPTOP") -> dict[str, Any]:
    product = product_repository.get_by_partnumber(partnumber)
    if product is None:
        return {"found": False, "partnumber": partnumber.strip(), "fields": []}
    package = resolve_package(...)
    preview = build_marketplace_preview(
        product=product,
        marketplace=marketplace,
        category=category,
        package=package,
    )
    return {"found": True, **preview}
```

- [ ] **Step 8: Run targeted server tests GREEN**

```bash
pytest tests/test_server_smoke.py tests/test_packaging_resolver.py tests/test_marketplace_preview.py tests/test_coolbox_preview.py -v
```

- [ ] **Step 9: Commit**

```bash
git add src/stech_mcp/server.py tests/test_server_smoke.py
git commit -m "feat: expose master packaging and marketplace tools"
```

---

### Task 7: Full verification and real-data acceptance for `82YU00XYLM`

**Files:**
- Modify: `README.md`
- No production data writes beyond executing the approved additive SQL migration.

**Interfaces:**
- Confirms public MCP continues to list tools.
- Confirms SQL source product data remains unchanged.
- Confirms package fallback is now the approved S-TECH rule.

- [ ] **Step 1: Run the complete local suite**

```bash
pytest
```

Expected: all tests pass, zero failures.

- [ ] **Step 2: Update README with exact migration/run commands**

Document:

```powershell
cd C:\DESAROLLO\mcp-stech
git pull
pip install -e ".[dev]"
pytest
```

SQL migration:

```text
sql/002_multichannel_enrichment_phase1.sql
```

MCP restart after migration/code update:

```powershell
stech-mcp
```

- [ ] **Step 3: Verify approved packaging rule through public MCP**

Call:

```python
await session.call_tool(
    "packaging_resolve",
    {"partnumber": "82YU00XYLM", "category": "LAPTOP"},
)
```

Expected package when no approved official package is stored:

```json
{
  "width_cm": 33.0,
  "length_cm": 54.0,
  "height_cm": 7.0,
  "weight_g": 2500,
  "status": "ESTIMATED",
  "method": "ESTIMATED",
  "source": "REGLA_STECH_EMPAQUE",
  "rule_code": "LAPTOP_15_X_DEFAULT",
  "confidence_grade": "E"
}
```

- [ ] **Step 4: Verify Coolbox preview through public MCP**

Call `coolbox_preview(partnumber="82YU00XYLM")` and assert:

- `field_count == 81`
- `Alto (cm) == 7`
- `Ancho (cm) == 33`
- `Largo (cm) == 54`
- `Peso (g) == 2500`
- package statuses are `ESTIMATED`
- SSD capacity, refresh rate and GPU remain `RESEARCH_REQUIRED` unless approved evidence has been stored.

- [ ] **Step 5: Verify tools/list through `https://mcp.artos.pe/mcp`**

Expected old tools plus:

```text
packaging_rule_get
packaging_resolve
marketplace_preview
```

- [ ] **Step 6: Commit docs**

```bash
git add README.md
git commit -m "docs: document multichannel enrichment phase 1"
```

---

## Self-Review

### Spec coverage

- Approved 15.x packaging fallback: Task 1, 3, 4, 7.
- Official package precedence: Task 2, 3, 6, 7.
- Persistent evidence/enrichment: Task 2.
- Generic marketplace schema: Task 1.
- Generic marketplace preview contract: Task 5, 6.
- Coolbox compatibility: Task 4, 6, 7.
- No sensitive field guessing: preserved and explicitly regression-tested in Task 4/7.
- Parameterized SQL/no arbitrary SQL: Task 2/3 and Global Constraints.
- Falabella/VTEX are intentionally not fabricated in Phase 1; their real templates/schemas are prerequisites for later plans.

### Placeholder scan

No TBD/TODO placeholders. Falabella and VTEX implementation is explicitly outside Phase 1 until their real source templates are reviewed.

### Type consistency

`Decimal` is used for rule matching and package dimensions internally; MCP JSON surfaces numeric values. `package` dictionaries consistently carry `width_cm`, `length_cm`, `height_cm`, `weight_g`, `status`, `method`, `source`, `rule_code`, `confidence_grade`.
