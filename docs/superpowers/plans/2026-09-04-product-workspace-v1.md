# Product Workspace V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the first visible, database-backed Product Workspace for `82YU00XYLM`, where STECH MCP prepares and persists one canonical product snapshot + Coolbox draft, and SCR displays readiness, provenance, package data, missing fields, images metadata and the 81-field Coolbox preview without publishing anything.

**Architecture:** `DB_DISTRIBUIDORES` remains the operational source. `STECH_MCP` stores Product Master state, channel draft state, image metadata and audit events. All deterministic product preparation is executed by STECH MCP through a focused `product_prepare` tool; SCR reads the persisted workspace directly from SQL Server for fast UI rendering and calls the same MCP tool through a small local MCP client when the user presses **Preparar / Actualizar**, avoiding duplicate preparation logic. No marketplace write is performed in this milestone.

**Tech Stack:** Python 3.12+, SQL Server 2019, pyodbc 5.x, MCP Python SDK 2.x, FastAPI, vanilla JS/CSS, pytest.

**Spec:** `docs/superpowers/specs/2026-09-04-product-master-publishing-platform-design.md`

## Global Constraints

- SQL Server is the primary persistence layer for Product Master, drafts, image metadata and audit.
- `DB_DISTRIBUIDORES.dbo.V_PRD_PRODUCTO_ACTUAL` remains the current operational product source.
- Existing MCP tools remain backward compatible.
- Existing SCR channel and monitoring behavior remains backward compatible.
- No generic `execute_sql` MCP tool is added.
- No live Falabella, VTEX or Coolbox publication is performed in this milestone.
- No researched/manual approved value is overwritten automatically.
- Laptop screens `>= 15.0` and `< 16.0` use `33 x 54 x 7 cm`, `2500 g`, `ESTIMATED`, source `REGLA_STECH_EMPAQUE`, rule `LAPTOP_15_X_DEFAULT` only when no approved official package exists.
- The Coolbox laptop draft remains exactly 81 fields.
- SCR and ChatGPT do not implement separate product-preparation transformations; SCR invokes STECH MCP for preparation and reads the persisted result.
- Image binaries are not moved in V1. SQL stores metadata rows; the UI renders any `product_image` rows already present and otherwise reports `FALTAN_IMAGENES`.

---

## File Structure

### Repository: `artosperu-bot/mcp-stech` branch `feat/stech-mcp-v1`

**Create**
- `sql/003_product_workspace_v1.sql` — additive/idempotent Product Master, draft, image and audit schema.
- `src/stech_mcp/db/product_master_repository.py` — persistence for Product Master, drafts, images and audit.
- `src/stech_mcp/domain/product_readiness.py` — deterministic readiness calculator.
- `src/stech_mcp/services/product_prepare.py` — one preparation service used by MCP tools.
- `tests/test_product_master_repository.py`
- `tests/test_product_readiness.py`
- `tests/test_product_prepare.py`

**Modify**
- `src/stech_mcp/server.py` — expose `product_prepare`, `product_master_get`, `product_readiness_get`, `channel_draft_get`.
- `tests/test_server_smoke.py` — assert new tool surface.
- `README.md` — migration + Product Workspace acceptance commands.

### Repository: `artosperu-bot/scr` branch `v8-identity`

**Create**
- `src/distributor_monitor/product_workspace.py` — SQL read repository over `STECH_MCP` + workspace response assembly.
- `src/distributor_monitor/product_workspace_mcp.py` — local Streamable HTTP MCP client that calls `product_prepare`.
- `src/distributor_monitor/product_workspace_api.py` — GET/POST Product Workspace endpoints.
- `web/product-workspace-ui.js` — workspace UI rendering and actions.
- `web/product-workspace.css` — isolated workspace styles.
- `tests/test_product_workspace_repository.py`
- `tests/test_product_workspace_api.py`
- `tests/test_product_workspace_ui.py`

**Modify**
- `src/distributor_monitor/config.py` — add `stech_mcp_url`, default `http://127.0.0.1:8765/mcp`.
- `run.py` — wire Product Workspace repository/client/routes.
- `web/index.html` — add nav/view and load Product Workspace CSS/JS.
- `requirements.txt` — add `mcp>=2,<3` if not already present.

---

### Task 1: Add database-first Product Workspace schema in `STECH_MCP`

**Files:**
- Create: `mcp-stech/sql/003_product_workspace_v1.sql`

**Interfaces:**
- Produces `dbo.product_master` keyed by `partnumber`.
- Produces `dbo.channel_draft`, unique by `(partnumber, marketplace, draft_version)`.
- Produces `dbo.channel_draft_field`, unique by `(channel_draft_id, field_name)`.
- Produces `dbo.product_image` for metadata-only image inventory.
- Produces `dbo.product_audit_event`.
- Produces `dbo.V_PRODUCT_WORKSPACE_V1` for lightweight workspace summary reads.

- [ ] **Step 1: Write additive/idempotent migration**

Create `sql/003_product_workspace_v1.sql` with `USE STECH_MCP;` and `IF OBJECT_ID(...) IS NULL` guards. The core table contracts are:

```sql
IF OBJECT_ID(N'dbo.product_master', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.product_master (
        product_master_id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_product_master PRIMARY KEY,
        partnumber NVARCHAR(120) NOT NULL CONSTRAINT UQ_product_master_partnumber UNIQUE,
        source_product_id BIGINT NULL,
        distributor NVARCHAR(80) NULL,
        brand NVARCHAR(120) NULL,
        model NVARCHAR(240) NULL,
        product_name NVARCHAR(1000) NULL,
        ean NVARCHAR(32) NULL,
        upc NVARCHAR(32) NULL,
        mini_codigo NVARCHAR(80) NULL,
        category_code NVARCHAR(120) NULL,
        subcategory_code NVARCHAR(120) NULL,
        source_stock_value DECIMAL(18,4) NULL,
        source_stock_operator NVARCHAR(10) NULL,
        source_price_usd_sin_igv DECIMAL(18,4) NULL,
        source_observed_at DATETIME2(0) NULL,
        screen_inches DECIMAL(6,2) NULL,
        package_width_cm DECIMAL(8,2) NULL,
        package_length_cm DECIMAL(8,2) NULL,
        package_height_cm DECIMAL(8,2) NULL,
        package_weight_g INT NULL,
        package_status NVARCHAR(40) NULL,
        package_method NVARCHAR(40) NULL,
        package_source NVARCHAR(200) NULL,
        package_rule_code NVARCHAR(100) NULL,
        package_confidence_grade NVARCHAR(20) NULL,
        readiness_state NVARCHAR(40) NOT NULL CONSTRAINT DF_product_master_readiness DEFAULT (N'ENRIQUECIENDO'),
        identity_score INT NOT NULL CONSTRAINT DF_product_master_identity_score DEFAULT (0),
        technical_score INT NOT NULL CONSTRAINT DF_product_master_technical_score DEFAULT (0),
        image_score INT NOT NULL CONSTRAINT DF_product_master_image_score DEFAULT (0),
        package_score INT NOT NULL CONSTRAINT DF_product_master_package_score DEFAULT (0),
        coolbox_score INT NOT NULL CONSTRAINT DF_product_master_coolbox_score DEFAULT (0),
        created_at DATETIME2(0) NOT NULL CONSTRAINT DF_product_master_created DEFAULT (SYSUTCDATETIME()),
        updated_at DATETIME2(0) NOT NULL CONSTRAINT DF_product_master_updated DEFAULT (SYSUTCDATETIME())
    );
END;
GO
```

Create `channel_draft` with columns `channel_draft_id`, `partnumber`, `marketplace`, `template_name`, `draft_version`, `status`, `field_count`, `required_missing_count`, `estimated_count`, `payload_json`, `created_at`, `updated_at`; enforce uniqueness `(partnumber, marketplace, draft_version)`.

Create `channel_draft_field` with `channel_draft_field_id`, `channel_draft_id`, `field_position`, `field_name`, `value_text`, `status`, `source`, `method`, `note`, and unique `(channel_draft_id, field_name)`.

Create `product_image` with the exact V1 metadata columns:

```text
product_image_id, partnumber, source_type, source_url, source_domain,
is_official, partnumber_match, storage_path, variant_type, parent_image_id,
sha256_hash, width_px, height_px, format, background_status,
is_approved, position, created_at, updated_at
```

Create `product_audit_event` with `event_id`, `partnumber`, `event_type`, `actor_source`, `channel`, `detail_json`, `created_at`.

Create view `dbo.V_PRODUCT_WORKSPACE_V1` joining `product_master` with the latest COOLBOX draft via `OUTER APPLY`, returning master columns plus `coolbox_draft_id`, `coolbox_status`, `coolbox_field_count`, `coolbox_required_missing_count`, `coolbox_estimated_count`, and a correlated image count.

- [ ] **Step 2: Apply migration on local SQL Server**

Run:

```powershell
sqlcmd -S PC020 -E -C -i ".\sql\003_product_workspace_v1.sql"
```

Expected: database context changes to `STECH_MCP`; no destructive operations.

- [ ] **Step 3: Verify schema explicitly**

Run:

```powershell
sqlcmd -S PC020 -E -C -Q "SELECT OBJECT_ID('STECH_MCP.dbo.product_master') AS product_master_id, OBJECT_ID('STECH_MCP.dbo.channel_draft') AS channel_draft_id, OBJECT_ID('STECH_MCP.dbo.product_image') AS product_image_id, OBJECT_ID('STECH_MCP.dbo.V_PRODUCT_WORKSPACE_V1') AS workspace_view_id;"
```

Expected: all four values are non-NULL.

- [ ] **Step 4: Commit**

```bash
git add sql/003_product_workspace_v1.sql
git commit -m "feat: add product workspace v1 schema"
```

---

### Task 2: Persist Product Master snapshots and channel drafts in `mcp-stech`

**Files:**
- Create: `src/stech_mcp/db/product_master_repository.py`
- Create: `tests/test_product_master_repository.py`

**Interfaces:**
- Consumes `Callable[[], Any]` MCP connection factory.
- Produces `ProductMasterRepository.upsert_master(snapshot: dict[str, Any]) -> dict[str, Any]`.
- Produces `ProductMasterRepository.get(partnumber: str) -> dict[str, Any] | None`.
- Produces `ProductMasterRepository.replace_draft(*, partnumber: str, marketplace: str, template_name: str, payload: dict[str, Any]) -> dict[str, Any]`.
- Produces `ProductMasterRepository.get_latest_draft(partnumber: str, marketplace: str) -> dict[str, Any] | None`.
- Produces `ProductMasterRepository.list_images(partnumber: str) -> list[dict[str, Any]]`.
- Produces `ProductMasterRepository.add_audit_event(...) -> None`.

- [ ] **Step 1: Write failing parameterization/idempotency tests**

Use a DB-API fake cursor/connection matching existing repository tests. Include:

```python
def test_upsert_master_is_parameterized_and_updates_same_partnumber():
    repo = ProductMasterRepository(factory)
    repo.upsert_master({"partnumber": "82YU00XYLM", "brand": "LENOVO"})
    assert "82YU00XYLM" not in cursor.last_sql
    assert cursor.last_params[0] == "82YU00XYLM"


def test_replace_draft_persists_exactly_81_coolbox_fields():
    result = repo.replace_draft(
        partnumber="82YU00XYLM",
        marketplace="COOLBOX",
        template_name="Laptops-All in one",
        payload={"fields": [{"field": f"F{i}", "value": i, "status": "DISTRIBUTOR"} for i in range(81)]},
    )
    assert result["field_count"] == 81
```

Also assert connections close and draft field values are passed as parameters, not interpolated.

- [ ] **Step 2: Run RED**

```bash
pytest tests/test_product_master_repository.py -v
```

Expected: `ModuleNotFoundError` for `stech_mcp.db.product_master_repository`.

- [ ] **Step 3: Implement minimal repository**

Use update-then-insert for `product_master` to avoid `MERGE` concurrency surprises. Normalize PN with `.strip().upper()`.

`replace_draft` must:
1. determine `draft_version = previous + 1` for the PN/marketplace,
2. insert one new `channel_draft`,
3. insert every payload field preserving list order in `field_position`,
4. set `required_missing_count` from `RESEARCH_REQUIRED`,
5. set `estimated_count` from `ESTIMATED`,
6. persist compact `payload_json`,
7. return draft id/version/counts.

Do not update an older draft in place; drafts are versioned snapshots.

- [ ] **Step 4: Run GREEN**

```bash
pytest tests/test_product_master_repository.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/stech_mcp/db/product_master_repository.py tests/test_product_master_repository.py
git commit -m "feat: persist product master and channel drafts"
```

---

### Task 3: Add deterministic readiness model and one Product Prepare service

**Files:**
- Create: `src/stech_mcp/domain/product_readiness.py`
- Create: `src/stech_mcp/services/product_prepare.py`
- Create: `tests/test_product_readiness.py`
- Create: `tests/test_product_prepare.py`

**Interfaces:**
- Produces `calculate_readiness(*, product: dict[str, Any], coolbox_preview: dict[str, Any], package: dict[str, Any] | None, images: list[dict[str, Any]]) -> dict[str, Any]`.
- Produces `ProductPrepareService.prepare(partnumber: str, category: str = "LAPTOP") -> dict[str, Any]`.
- `ProductPrepareService` consumes existing `ProductRepository`, `EnrichmentRepository`, `PackagingRuleRepository`, `ProductMasterRepository`.

- [ ] **Step 1: Write readiness tests**

Define scores deterministically:

```python
identity_required = ["part_number", "marca", "nombre"]
identity optional bonus = one of ["ean", "upc"]
identity_score = round(present / 4 * 100)
technical_score = round(non_missing_coolbox_noncommercial / total_coolbox_noncommercial * 100)
image_score = 100 if approved_images >= 4 else 75 if approved_images == 3 else 50 if approved_images == 2 else 25 if approved_images == 1 else 0
package_score = 100 if package.method == "VERIFIED" else 70 if package.method == "ESTIMATED" else 0
coolbox_score = round((81 - research_required - marketplace_input) / (81 - marketplace_input) * 100)
```

Readiness state precedence:

```text
FALTAN_IMAGENES if image_score == 0
FALTAN_DATOS if RESEARCH_REQUIRED > 0
LISTO_PARA_REVISAR otherwise
```

For V1, `MARKETPLACE_INPUT` does not block technical readiness because price/stock/date inputs are commercial and separate.

Write tests proving a product with complete identity but no images and missing Coolbox fields becomes `FALTAN_IMAGENES`, and a product with images but research-required fields becomes `FALTAN_DATOS`.

- [ ] **Step 2: Run readiness tests RED**

```bash
pytest tests/test_product_readiness.py -v
```

- [ ] **Step 3: Implement readiness calculator**

Return:

```python
{
    "state": "FALTAN_DATOS",
    "identity_score": 100,
    "technical_score": 63,
    "image_score": 0,
    "package_score": 70,
    "coolbox_score": 62,
    "missing_fields": [...],
    "estimated_fields": [...],
    "image_count": 0,
}
```

- [ ] **Step 4: Write ProductPrepareService tests**

Use fakes for all repositories. Assert `prepare("82YU00XYLM")`:
- calls source `get_by_partnumber` once,
- resolves 15.6-inch package,
- passes the resolved package into `build_coolbox_preview`,
- creates/updates one Product Master snapshot,
- creates a new versioned COOLBOX draft with 81 fields,
- records audit event `PRODUCT_PREPARED`,
- returns master + package + readiness + draft summary,
- performs no marketplace write.

- [ ] **Step 5: Run service tests RED**

```bash
pytest tests/test_product_prepare.py -v
```

- [ ] **Step 6: Implement ProductPrepareService**

Derive `screen_inches` using a focused public helper from `coolbox_preview.py`; if necessary rename `_screen` to `extract_screen_inches` while preserving existing behavior/tests.

Snapshot mapping for source product:

```python
{
    "partnumber": source.get("part_number") or source.get("partnumber"),
    "source_product_id": source.get("producto_distribuidor_id"),
    "distributor": source.get("distribuidor"),
    "brand": source.get("marca"),
    "model": extracted_model,
    "product_name": source.get("nombre"),
    "ean": source.get("ean"),
    "upc": source.get("upc"),
    "mini_codigo": source.get("mini_codigo"),
    "category_code": source.get("categoria") or "LAPTOP",
    "subcategory_code": source.get("subcategoria"),
    "source_stock_value": source.get("stock_valor"),
    "source_stock_operator": source.get("stock_operador"),
    "source_price_usd_sin_igv": source.get("precio_usd_sin_igv"),
    "source_observed_at": source.get("observado_at"),
    "screen_inches": screen_inches,
    ...resolved package fields...,
    ...readiness scores/state...,
}
```

- [ ] **Step 7: Run targeted GREEN**

```bash
pytest tests/test_product_readiness.py tests/test_product_prepare.py tests/test_coolbox_preview.py tests/test_packaging_resolver.py -v
```

- [ ] **Step 8: Commit**

```bash
git add src/stech_mcp/domain/product_readiness.py src/stech_mcp/services/product_prepare.py src/stech_mcp/services/coolbox_preview.py tests/test_product_readiness.py tests/test_product_prepare.py tests/test_coolbox_preview.py
git commit -m "feat: prepare persistent product workspace state"
```

---

### Task 4: Expose Product Workspace MCP tools

**Files:**
- Modify: `src/stech_mcp/server.py`
- Modify: `tests/test_server_smoke.py`

**Interfaces:**
- Adds `product_prepare(partnumber: str, category: str = "LAPTOP")`.
- Adds `product_master_get(partnumber: str)`.
- Adds `product_readiness_get(partnumber: str)`.
- Adds `channel_draft_get(partnumber: str, marketplace: str = "COOLBOX")`.

- [ ] **Step 1: Extend smoke test first**

Add:

```python
assert callable(server.product_prepare)
assert callable(server.product_master_get)
assert callable(server.product_readiness_get)
assert callable(server.channel_draft_get)
```

- [ ] **Step 2: Run RED**

```bash
pytest tests/test_server_smoke.py -v
```

Expected: missing new callables.

- [ ] **Step 3: Wire repositories/service once at module startup**

Using existing MCP DB connection factory:

```python
product_master_repository = ProductMasterRepository(mcp_connection_factory)
product_prepare_service = ProductPrepareService(
    product_repository=product_repository,
    enrichment_repository=enrichment_repository,
    packaging_rule_repository=packaging_rule_repository,
    product_master_repository=product_master_repository,
)
```

- [ ] **Step 4: Implement tools**

`product_prepare` delegates to `product_prepare_service.prepare`.

`product_master_get` returns `{found, partnumber, master, images}`.

`product_readiness_get` returns persisted readiness plus latest COOLBOX draft counts.

`channel_draft_get` returns the latest versioned draft including ordered `fields`.

- [ ] **Step 5: Run full MCP test suite**

```bash
pytest -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/stech_mcp/server.py tests/test_server_smoke.py
git commit -m "feat: expose product workspace mcp tools"
```

---

### Task 5: Add SCR read repository and MCP preparation bridge

**Files:**
- Create: `scr/src/distributor_monitor/product_workspace.py`
- Create: `scr/src/distributor_monitor/product_workspace_mcp.py`
- Create: `scr/tests/test_product_workspace_repository.py`
- Modify: `scr/src/distributor_monitor/config.py`
- Modify: `scr/requirements.txt`

**Interfaces:**
- Produces `ProductWorkspaceRepository(db).get(partnumber: str) -> dict | None`.
- Produces async `McpProductWorkspaceClient.prepare(partnumber: str, category: str = "LAPTOP") -> dict`.
- New `Settings.stech_mcp_url`, env `STECH_MCP_URL`, default `http://127.0.0.1:8765/mcp`.

- [ ] **Step 1: Write repository tests**

Use SCR's `SqlServer(connection_factory=...)` fake pattern. Assert query is parameterized and uses three-part names only:

```sql
SELECT ... FROM STECH_MCP.dbo.V_PRODUCT_WORKSPACE_V1 WHERE partnumber = ?
```

Then load:

```sql
SELECT ... FROM STECH_MCP.dbo.channel_draft_field WHERE channel_draft_id = ? ORDER BY field_position
SELECT ... FROM STECH_MCP.dbo.product_image WHERE partnumber = ? ORDER BY position, product_image_id
```

The returned shape must be:

```python
{
    "master": {...},
    "readiness": {...},
    "package": {...},
    "coolbox": {"draft_id": ..., "field_count": 81, "fields": [...]},
    "images": [...],
}
```

- [ ] **Step 2: Run repository test RED**

```bash
pytest tests/test_product_workspace_repository.py -v
```

- [ ] **Step 3: Implement repository**

No writes. Normalize PN to uppercase. If `V_PRODUCT_WORKSPACE_V1` returns no row, return `None`.

- [ ] **Step 4: Add MCP client config test**

Extend config tests to assert default URL and env override:

```python
assert Settings.from_env(...).stech_mcp_url == "http://127.0.0.1:8765/mcp"
```

- [ ] **Step 5: Implement MCP client**

Use:

```python
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
```

Inside `prepare`, open a session, `initialize()`, call `product_prepare`, and read `result.structured_content` (snake_case, not `structuredContent`). If `is_error`, raise `RuntimeError` with the returned text.

- [ ] **Step 6: Add dependency**

Append exactly:

```text
mcp>=2,<3
```

to `requirements.txt` only if not already present.

- [ ] **Step 7: Run targeted tests GREEN**

```bash
pytest tests/test_product_workspace_repository.py tests/test_v8_detail_budget_config.py -v
```

- [ ] **Step 8: Commit in SCR**

```bash
git add src/distributor_monitor/product_workspace.py src/distributor_monitor/product_workspace_mcp.py src/distributor_monitor/config.py requirements.txt tests/test_product_workspace_repository.py
git commit -m "feat: add product workspace read model and mcp bridge"
```

---

### Task 6: Add SCR Product Workspace API

**Files:**
- Create: `scr/src/distributor_monitor/product_workspace_api.py`
- Create: `scr/tests/test_product_workspace_api.py`
- Modify: `scr/run.py`

**Interfaces:**
- `GET /api/product-workspace/{partnumber}` — reads persisted workspace.
- `POST /api/product-workspace/{partnumber}/prepare?category=LAPTOP` — calls STECH MCP `product_prepare`, then re-reads persisted workspace.

- [ ] **Step 1: Write API tests first**

Use FastAPI `TestClient` with fake repository/client.

Required tests:

```python
def test_get_workspace_returns_404_when_not_prepared(): ...
def test_get_workspace_returns_persisted_master_and_81_coolbox_fields(): ...
def test_prepare_calls_mcp_then_returns_persisted_workspace(): ...
```

Assert the POST fake MCP client is called exactly once with `82YU00XYLM` and `LAPTOP`.

- [ ] **Step 2: Run RED**

```bash
pytest tests/test_product_workspace_api.py -v
```

- [ ] **Step 3: Implement route registrar**

Signature:

```python
def register_product_workspace_routes(app, repository, mcp_client):
    ...
```

Use async POST handler:

```python
@app.post("/api/product-workspace/{partnumber}/prepare")
async def prepare_workspace(partnumber: str, category: str = "LAPTOP"):
    await mcp_client.prepare(partnumber.strip().upper(), category.strip().upper())
    row = repository.get(partnumber)
    if row is None:
        raise HTTPException(502, "STECH MCP preparó el producto pero no quedó persistido en STECH_MCP")
    return row
```

- [ ] **Step 4: Wire in `run.py`**

After `db=SqlServer(...)`, instantiate:

```python
workspace_repository = ProductWorkspaceRepository(db)
workspace_mcp_client = McpProductWorkspaceClient(settings.stech_mcp_url)
```

Register routes before mounting static files:

```python
register_product_workspace_routes(app, ctx.product_workspace_repository, ctx.product_workspace_mcp_client)
```

- [ ] **Step 5: Run API regression set**

```bash
pytest tests/test_product_workspace_api.py tests/test_channels_api.py tests/test_v8_api.py -v
```

- [ ] **Step 6: Commit in SCR**

```bash
git add src/distributor_monitor/product_workspace_api.py run.py tests/test_product_workspace_api.py
git commit -m "feat: expose product workspace api"
```

---

### Task 7: Add visible Product Workspace V1 to SCR

**Files:**
- Create: `scr/web/product-workspace-ui.js`
- Create: `scr/web/product-workspace.css`
- Create: `scr/tests/test_product_workspace_ui.py`
- Modify: `scr/web/index.html`

**Interfaces:**
- Adds left navigation `Product Workspace` with `data-view="productWorkspace"`.
- Adds `<section id="productWorkspace" class="view">`.
- UI calls `GET /api/product-workspace/{pn}` and `POST /api/product-workspace/{pn}/prepare`.

- [ ] **Step 1: Write static UI contract test**

Test reads `web/index.html`, `web/product-workspace-ui.js`, `web/product-workspace.css` and asserts:

```text
data-view="productWorkspace"
id="productWorkspace"
id="workspacePartnumber"
id="workspacePrepare"
id="workspaceRefresh"
id="workspaceIdentity"
id="workspaceReadiness"
id="workspaceImages"
id="workspacePackage"
id="workspaceCoolbox"
/product-workspace/
```

Also assert no live publish endpoint string (`/publications/`, `/price`, `/stock`) appears in `product-workspace-ui.js`.

- [ ] **Step 2: Run RED**

```bash
pytest tests/test_product_workspace_ui.py -v
```

- [ ] **Step 3: Add workspace view markup**

Add nav near `Producto maestro`.

The view contains:

```html
<section id="productWorkspace" class="view">
  <div class="panel workspace-toolbar">
    <div><h2>Product Workspace</h2><p>Preparación y revisión antes de publicar.</p></div>
    <div class="form-row">
      <input id="workspacePartnumber" placeholder="Part Number, ej. 82YU00XYLM">
      <button id="workspacePrepare">Preparar / Actualizar</button>
      <button id="workspaceRefresh" class="secondary">Refrescar</button>
    </div>
    <span id="workspaceMessage" class="muted"></span>
  </div>
  <div id="workspaceHeader"></div>
  <div id="workspaceReadiness"></div>
  <div id="workspaceIdentity"></div>
  <div id="workspaceImages"></div>
  <div id="workspacePackage"></div>
  <div id="workspaceCoolbox"></div>
</section>
```

Load `/product-workspace.css` in `<head>` and `/product-workspace-ui.js` after the common app helpers are loaded.

- [ ] **Step 4: Implement JS rendering**

Render:

**Header** — brand/model/name/PN/readiness badge.

**Readiness cards** — identity, technical, images, package, Coolbox scores.

**Identity** — PN, UPC/EAN, mini code, distributor, source stock with operator semantics, price USD sin IGV, last observation.

**Images** — main image is first approved/positioned row; thumbnails for all rows. If none, render `Sin imágenes registradas — FALTAN_IMAGENES`.

**Package** — `33 × 54 × 7 cm`, `2500 g`, plus status/method/source/rule/confidence.

**Coolbox** — summary line `81 campos`, missing/estimated counts, and collapsible table with columns `Campo`, `Valor`, `Estado`, `Fuente`.

`Preparar / Actualizar` calls POST, disables button while running, then renders returned workspace. `Refrescar` calls GET only.

No **APROBAR** or **SUBIR** button is enabled in V1; render them disabled with tooltip `Se habilita en el milestone de aprobación/publicación` only if desired visually.

- [ ] **Step 5: Implement isolated CSS**

Use `.workspace-*` class prefix. Do not alter global table/nav styles. Use responsive CSS grid for readiness cards and identity/package panels.

- [ ] **Step 6: Run UI tests GREEN**

```bash
pytest tests/test_product_workspace_ui.py tests/test_channels_frontend.py tests/test_channel_provider_ui_separation.py -v
```

- [ ] **Step 7: Commit in SCR**

```bash
git add web/index.html web/product-workspace-ui.js web/product-workspace.css tests/test_product_workspace_ui.py
git commit -m "feat: add product workspace v1 ui"
```

---

### Task 8: Real acceptance for `82YU00XYLM`

**Files:**
- Modify: `mcp-stech/README.md`
- No live marketplace writes.

**Interfaces:**
- Confirms MCP public tool list expands from 10 to 14 tools.
- Confirms Product Workspace persisted/readable from SCR.

- [ ] **Step 1: Pull both updated branches on PC020**

```powershell
cd C:\DESAROLLO\mcp-stech
git checkout feat/stech-mcp-v1
git pull
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

cd C:\DESAROLLO\scr
git checkout v8-identity
git pull
pip install -r requirements.txt
```

- [ ] **Step 2: Apply Product Workspace migration**

```powershell
cd C:\DESAROLLO\mcp-stech
sqlcmd -S PC020 -E -C -i ".\sql\003_product_workspace_v1.sql"
```

- [ ] **Step 3: Restart STECH MCP and SCR**

Start MCP with existing `.env` (`MCP_TRANSPORT=streamable-http`) and start SCR using its normal launcher.

- [ ] **Step 4: Verify public MCP tools**

Call `tools/list` against `https://mcp.artos.pe/mcp` and assert the original 10 plus:

```text
product_prepare
product_master_get
product_readiness_get
channel_draft_get
```

- [ ] **Step 5: Prepare real product**

Call:

```python
await session.call_tool("product_prepare", {"partnumber": "82YU00XYLM", "category": "LAPTOP"})
```

Expected minimum:

```text
found = true
partnumber = 82YU00XYLM
package.width_cm = 33
package.length_cm = 54
package.height_cm = 7
package.weight_g = 2500
package.status = ESTIMATED
package.source = REGLA_STECH_EMPAQUE
coolbox.field_count = 81
```

- [ ] **Step 6: Verify persisted SQL state**

```powershell
sqlcmd -S PC020 -E -C -Q "SELECT partnumber, brand, model, readiness_state, package_width_cm, package_length_cm, package_height_cm, package_weight_g, package_status, coolbox_field_count FROM STECH_MCP.dbo.V_PRODUCT_WORKSPACE_V1 WHERE partnumber=N'82YU00XYLM';"
```

Expected one row, package `33/54/7/2500`, `coolbox_field_count=81`.

- [ ] **Step 7: Verify SCR API**

Open:

```text
http://127.0.0.1:8787/api/product-workspace/82YU00XYLM
```

Use the actual configured SCR port if different. Response must contain `master`, `readiness`, `package`, `coolbox`, `images`.

- [ ] **Step 8: Verify visual workspace**

Open SCR and select **Product Workspace**. Enter `82YU00XYLM`. Confirm:
- Lenovo identity visible,
- package displays `33 × 54 × 7 cm / 2500 g` as `ESTIMATED`,
- Coolbox reports exactly `81 campos`,
- missing research fields are visible,
- image panel renders images if registered or clear `FALTAN_IMAGENES` state,
- no live publication occurs.

- [ ] **Step 9: Run both full test suites**

`mcp-stech`:

```bash
pytest -q
```

`scr`:

```bash
pytest -q
```

Both must pass before claiming V1 complete.

- [ ] **Step 10: Update README and commit**

Document the migration, new MCP tools, SCR URL and acceptance SKU. Commit in `mcp-stech`:

```bash
git add README.md
git commit -m "docs: add product workspace v1 acceptance flow"
```

---

## Self-Review

### Spec coverage for Product Workspace V1

Covered in this plan:
- database-first Product Master persistence,
- real Deltron/SQL source snapshot,
- package provenance and approved 15.x fallback,
- field-level status/source through persisted Coolbox draft,
- image metadata inventory/readiness,
- one MCP preparation path reused by SCR,
- versioned channel draft,
- visible SCR workspace,
- audit event on preparation,
- no publication before approval,
- real acceptance SKU `82YU00XYLM`,
- backward compatibility and full-suite verification.

Intentionally deferred to later milestone plans from the approved spec:
- automated official-web research jobs,
- image discovery/editing recipe and binary processing,
- manual field editing/approval records,
- Falabella draft generation from its real schema,
- VTEX draft generation/write parity,
- unified Publish Service and live writes,
- batch job orchestration.

### Type/name consistency

- MCP preparation entry point: `product_prepare` → `ProductPrepareService.prepare`.
- Persisted master key: `partnumber` normalized uppercase.
- SCR MCP response property: `structured_content` (snake_case).
- Coolbox draft marketplace code: `COOLBOX`.
- Workspace SQL view: `STECH_MCP.dbo.V_PRODUCT_WORKSPACE_V1`.
- SCR API base: `/api/product-workspace/{partnumber}`.

### Placeholder scan

No `TBD`, `TODO`, guessed marketplace schema, or unspecified production write remains in this V1 plan.
