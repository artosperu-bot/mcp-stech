# Product Workbench V1 MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the reusable Product Workbench backend to `mcp-stech`: persistent jobs, idempotent orchestration, safe VTEX Product/SKU ensure, image editing metadata and MCP tools used by SCR/V8.

**Architecture:** `mcp-stech` owns domain orchestration and persistence in `STECH_MCP`; SCR sends normalized import rows and renders progress. Existing Product Master and VTEX image services are reused. Product/SKU creation is a separate explicit service with exact Part Number identity and read-back verification.

**Tech Stack:** Python 3.12, MCP 2.x, pyodbc/SQL Server, openpyxl/Pillow already present, pytest, VTEX HTTP APIs through existing `VtexImageClient` transport.

**Spec:** `docs/superpowers/specs/2026-09-07-product-workbench-v1-design.md`

## Global Constraints

- Exact Part Number is the primary identity; never heuristically strip `-S` or accept another variant.
- `Product RefId = <PARTNUMBER>` and initial `SKU RefId = <PARTNUMBER>-S`.
- Do not automatically activate Product/SKU.
- Do not publish price or stock from Product Workbench V1.
- Do not replace the validated VTEX image pipeline.
- `_01` remains the local/publication main-image priority.
- Never destroy or overwrite ORIGINAL image metadata; edited images are child variants.
- No automatic Web Research in V1; insufficient images become `RESEARCH_REQUIRED`.
- Every remote creation/write must be followed by read-back before the item can advance.
- One failed item must not stop the rest of a job.
- Job re-runs must reuse already-confirmed ProductId, SkuId and image state instead of duplicating remote objects.

---

## File Structure

Create:
- `sql/005_product_workbench_jobs.sql` — additive job/item/event persistence.
- `src/stech_mcp/domain/product_loader_models.py` — canonical job/item states and row normalization helpers.
- `src/stech_mcp/db/product_loader_repository.py` — job persistence and idempotent state transitions.
- `src/stech_mcp/services/product_loader_preview.py` — pure preview/validation of normalized rows.
- `src/stech_mcp/services/vtex_product_ensure.py` — exact Product/SKU lookup/create/read-back service.
- `src/stech_mcp/services/product_loader_orchestrator.py` — background per-item workflow and resume/retry behavior.
- `src/stech_mcp/services/product_image_editor.py` — approve/reorder/register child variant metadata without destroying originals.
- `tests/test_product_workbench_schema.py`
- `tests/test_product_loader_repository.py`
- `tests/test_product_loader_preview.py`
- `tests/test_vtex_product_ensure.py`
- `tests/test_product_loader_orchestrator.py`
- `tests/test_product_image_editor.py`
- `tests/test_server_product_workbench_tools.py`

Modify:
- `src/stech_mcp/services/vtex_image_client.py` — add minimal Product/SKU catalog helpers using the same authenticated transport.
- `src/stech_mcp/db/product_image_repository.py` — explicit approval/order/child-variant writes.
- `src/stech_mcp/server.py` — instantiate services and expose MCP tools.
- `docs/VTEX_IMAGES_MCP.md` — document that Workbench reuses image sync and does not widen image-write scope.

---

### Task 1: Persistent Product Loader schema and repository

**Files:**
- Create: `sql/005_product_workbench_jobs.sql`
- Create: `src/stech_mcp/domain/product_loader_models.py`
- Create: `src/stech_mcp/db/product_loader_repository.py`
- Test: `tests/test_product_workbench_schema.py`
- Test: `tests/test_product_loader_repository.py`

**Interfaces:**
- Produces `normalize_partnumber(value: str) -> str`.
- Produces `JOB_STATES`, `ITEM_STATES`, `TERMINAL_ITEM_STATES`.
- Produces `ProductLoaderRepository.create_job(source_name, rows, actor_source, channel) -> dict`.
- Produces `ProductLoaderRepository.get_job(job_id) -> dict | None` including ordered items/events and summary counts.
- Produces `claim_item(item_id, expected_states) -> bool`, `update_item(...)`, `append_event(...)`, `reset_item_for_retry(item_id)` and `list_resumable_items()`.

- [ ] **Step 1: Write failing schema tests**

```python
from pathlib import Path


def test_workbench_sql_creates_job_item_and_event_tables():
    sql = Path("sql/005_product_workbench_jobs.sql").read_text(encoding="utf-8")
    for name in ("product_loader_job", "product_loader_job_item", "product_loader_job_event"):
        assert name in sql
    assert "UNIQUE" in sql.upper()
    assert "input_json" in sql
    assert "product_id_vtex" in sql
    assert "sku_id_vtex" in sql
```

- [ ] **Step 2: Run RED**

Run: `pytest tests/test_product_workbench_schema.py -q`
Expected: FAIL because migration does not exist.

- [ ] **Step 3: Add migration**

Implement additive `IF OBJECT_ID(...) IS NULL CREATE TABLE...` DDL. `product_loader_job_item` must store `row_number`, exact `partnumber`, `input_json`, current state, retry count, `product_id_vtex`, `sku_id_vtex`, `product_ref_id_vtex`, `sku_ref_id_vtex`, last error code/detail and timestamps. Add a unique key per job + row number and an index by job/state.

- [ ] **Step 4: Write repository RED tests**

Use the repository test style already used in the project with fake connection/cursor objects. Assert that `create_job` normalizes PN to uppercase, serializes input safely, creates one item per row, and `get_job` returns summary counts without leaking credentials.

- [ ] **Step 5: Implement minimal repository and models**

`product_loader_models.py` defines:

```python
JOB_STATES = {"PENDING","RUNNING","WAITING_REVIEW","COMPLETED","PARTIAL","FAILED","CANCELLED"}
ITEM_STATES = {
    "PENDING","VALIDATING","PREPARING","IMAGES_LOCAL","RESEARCH_REQUIRED",
    "VTEX_CHECK","VTEX_CREATE_PRODUCT","VTEX_CREATE_SKU","VTEX_IMAGES",
    "VERIFYING","COMPLETED","REVIEW_REQUIRED","BLOCKED","FAILED",
}
TERMINAL_ITEM_STATES = {"COMPLETED","RESEARCH_REQUIRED","REVIEW_REQUIRED","BLOCKED","FAILED"}
```

Repository transitions must be parameterized SQL and transactional.

- [ ] **Step 6: Run GREEN**

Run: `pytest tests/test_product_workbench_schema.py tests/test_product_loader_repository.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add sql/005_product_workbench_jobs.sql src/stech_mcp/domain/product_loader_models.py src/stech_mcp/db/product_loader_repository.py tests/test_product_workbench_schema.py tests/test_product_loader_repository.py
git commit -m "feat: persist Product Loader jobs"
```

---

### Task 2: Import preview and row contract

**Files:**
- Create: `src/stech_mcp/services/product_loader_preview.py`
- Test: `tests/test_product_loader_preview.py`

**Interfaces:**
- Consumes normalized rows from SCR, each carrying `row_number`, `partnumber`, and optional `brand`, `product_name`, `category`, `vtex_category_id`, `vtex_brand_id`.
- Produces `preview_product_rows(rows: list[dict], source_name: str) -> dict` with `valid`, `errors`, `warnings`, normalized `rows`, duplicate flags and counts.

- [ ] **Step 1: Write RED tests**

```python
from stech_mcp.services.product_loader_preview import preview_product_rows


def test_preview_normalizes_exact_pn_and_flags_duplicates_without_writes():
    result = preview_product_rows([
        {"row_number": 2, "partnumber": " 82yu00xylm "},
        {"row_number": 3, "partnumber": "82YU00XYLM"},
    ], "carga.xlsx")
    assert result["rows"][0]["partnumber"] == "82YU00XYLM"
    assert result["rows"][1]["duplicate_in_file"] is True
    assert result["has_blocking_errors"] is True
```

Also cover missing PN, non-positive VTEX IDs, blank rows already removed by SCR, and preservation of Excel row number.

- [ ] **Step 2: Run RED**

Run: `pytest tests/test_product_loader_preview.py -q`
Expected: import failure.

- [ ] **Step 3: Implement pure preview service**

No DB and no VTEX calls. Return deterministic error codes such as `PARTNUMBER_REQUIRED`, `DUPLICATE_PARTNUMBER`, `VTEX_CATEGORY_ID_INVALID`, `VTEX_BRAND_ID_INVALID`.

- [ ] **Step 4: Run GREEN**

Run: `pytest tests/test_product_loader_preview.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stech_mcp/services/product_loader_preview.py tests/test_product_loader_preview.py
git commit -m "feat: validate Product Loader rows"
```

---

### Task 3: Safe VTEX Product/SKU ensure

**Files:**
- Create: `src/stech_mcp/services/vtex_product_ensure.py`
- Modify: `src/stech_mcp/services/vtex_image_client.py`
- Test: `tests/test_vtex_product_ensure.py`
- Modify test: `tests/test_vtex_image_client.py`

**Interfaces:**
- Adds to `VtexImageClient`:
  - `get_product(product_id: int) -> dict`
  - `create_product(payload: dict) -> dict`
  - `get_sku(sku_id: int) -> dict`
  - `create_sku(payload: dict) -> dict`
- Produces `VtexProductEnsureService.ensure(partnumber: str, master: dict, *, category_id: int, brand_id: int) -> dict`.
- Result keys: `status`, `product_created`, `sku_created`, `product_id`, `sku_id`, `product_ref_id`, `sku_ref_id`, `read_back_verified`.

- [ ] **Step 1: Write client RED tests**

Assert exact endpoints and payloads using the existing fake opener pattern. Product endpoint: `POST /api/catalog/pvt/product`; SKU endpoint: `POST /api/catalog/pvt/stockkeepingunit`. Ensure SKU payload forces `IsActive=False` and `ActivateIfPossible=False` in this Workbench path.

- [ ] **Step 2: Run RED**

Run: `pytest tests/test_vtex_image_client.py -q`
Expected: missing methods.

- [ ] **Step 3: Add the four catalog helpers**

Reuse `_request`; do not alter existing CatalogV2 image methods.

- [ ] **Step 4: Write ensure-service RED tests**

Cover:
1. Existing exact Product + exact SKU => no POST.
2. Missing Product => create Product, read-back exact `RefId`, create SKU, read-back exact `RefId`.
3. Product exists but SKU missing => create SKU only.
4. Product creation succeeds but SKU fails => exception/result preserves Product ID for caller persistence.
5. Missing/non-positive category/brand => `REVIEW_REQUIRED`, zero write.
6. Read-back RefId mismatch => `VERIFY_FAILED`.

Use fakes; no live VTEX tests in CI.

- [ ] **Step 5: Implement ensure service**

Existing lookup uses exact Seller Portal Product external ID plus exact `resolve_sku_id(<PN>-S)`. Treat only HTTP 404 as missing; permission/network errors are errors, not absence. Build minimum product payload from Product Master and explicit VTEX IDs; set visibility false for new product and keep SKU inactive.

- [ ] **Step 6: Run GREEN**

Run: `pytest tests/test_vtex_image_client.py tests/test_vtex_product_ensure.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/stech_mcp/services/vtex_image_client.py src/stech_mcp/services/vtex_product_ensure.py tests/test_vtex_image_client.py tests/test_vtex_product_ensure.py
git commit -m "feat: ensure VTEX Product and SKU safely"
```

---

### Task 4: Image metadata editor without destructive originals

**Files:**
- Modify: `src/stech_mcp/db/product_image_repository.py`
- Create: `src/stech_mcp/services/product_image_editor.py`
- Test: `tests/test_product_image_editor.py`

**Interfaces:**
- Repository adds `set_approval(product_image_id: int, approved: bool)`, `reorder(partnumber: str, ordered_ids: list[int])`, and `insert_variant(parent_image_id: int, storage_path: str, sha256_hash: str, width_px: int, height_px: int, format: str, variant_type: str = "EDITED_STECH")`.
- Service exposes `approve`, `reorder`, `register_variant` and returns read-back rows.

- [ ] **Step 1: Write RED tests**

Assert `register_variant` refuses a parent from another PN, refuses `variant_type="ORIGINAL"`, keeps parent row untouched, and stores `parent_image_id`. Assert reorder produces contiguous positions beginning at 1 so `_01`/first approved image remains deterministic.

- [ ] **Step 2: Run RED**

Run: `pytest tests/test_product_image_editor.py -q`
Expected: missing service/repository methods.

- [ ] **Step 3: Implement repository writes and service validation**

All writes are parameterized, transactional and followed by read-back. No delete method is added.

- [ ] **Step 4: Run GREEN**

Run: `pytest tests/test_product_image_editor.py tests/test_local_image_sync.py -q`
Expected: PASS, proving no regression in existing local discovery.

- [ ] **Step 5: Commit**

```bash
git add src/stech_mcp/db/product_image_repository.py src/stech_mcp/services/product_image_editor.py tests/test_product_image_editor.py
git commit -m "feat: edit Product Workspace image metadata safely"
```

---

### Task 5: Persistent ProductLoaderOrchestrator

**Files:**
- Create: `src/stech_mcp/services/product_loader_orchestrator.py`
- Test: `tests/test_product_loader_orchestrator.py`

**Interfaces:**
- Constructor dependencies: repository, prepare service, product master repository, local image sync service, VTEX ensure service, VTEX image sync service.
- Produces:
  - `start(rows, source_name, actor_source="SCR_UI", channel="VTEX") -> dict`
  - `get_job(job_id) -> dict | None`
  - `retry_item(job_id, item_id) -> dict`
  - `resume_pending() -> int`
  - internal `_process_item(item_id)`.

- [ ] **Step 1: Write RED orchestration tests**

Use fakes to prove ordered state transitions:

```text
VALIDATING -> PREPARING -> IMAGES_LOCAL -> VTEX_CHECK -> (CREATE PRODUCT/SKU when needed) -> VTEX_IMAGES -> VERIFYING -> COMPLETED
```

Also test:
- missing/insufficient images => `RESEARCH_REQUIRED`, no VTEX create/image sync;
- missing category/brand for a new VTEX product => `REVIEW_REQUIRED`, no remote write;
- existing product does not require creation IDs in input;
- one failing item does not stop the next item;
- retry of Product-created/SKU-failed item calls ensure service and does not recreate Product;
- already `COMPLETED` item is skipped.

- [ ] **Step 2: Run RED**

Run: `pytest tests/test_product_loader_orchestrator.py -q`
Expected: import failure.

- [ ] **Step 3: Implement orchestrator**

`start` persists all rows then runs items in a daemon worker thread. Guard each item with repository claim semantics. After any exception persist `FAILED` plus sanitized error. Recompute job state after each item: all completed => `COMPLETED`; terminal mix => `PARTIAL`; review/research present with unfinished work => `WAITING_REVIEW`; active worker => `RUNNING`.

- [ ] **Step 4: Add restart behavior**

`resume_pending()` converts stale in-progress states back to a resumable step and launches work from persisted identity. It must never clear ProductId/SkuId confirmed previously.

- [ ] **Step 5: Run GREEN**

Run: `pytest tests/test_product_loader_orchestrator.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/stech_mcp/services/product_loader_orchestrator.py tests/test_product_loader_orchestrator.py
git commit -m "feat: orchestrate persistent Product Loader jobs"
```

---

### Task 6: MCP tools and server wiring

**Files:**
- Modify: `src/stech_mcp/server.py`
- Create: `tests/test_server_product_workbench_tools.py`

**Interfaces:**
Expose tools:
- `product_loader_preview(rows: list[dict], source_name: str = "SCR")`
- `product_loader_start(rows: list[dict], source_name: str, actor_source: str = "SCR_UI")`
- `product_loader_job_get(job_id: int)`
- `product_loader_retry_item(job_id: int, item_id: int)`
- `vtex_product_ensure(partnumber: str, category_id: int, brand_id: int)`
- `product_image_approve(product_image_id: int, approved: bool = True)`
- `product_image_reorder(partnumber: str, ordered_ids: list[int])`
- `product_image_variant_register(...)`

Existing tools `product_images_sync_local`, `product_images_validate`, `vtex_images_status`, `vtex_images_sync` remain unchanged.

- [ ] **Step 1: Write RED tool-registration test**

Follow `tests/test_server_vtex_image_tools.py`; assert source contains all required tool names and server smoke imports.

- [ ] **Step 2: Run RED**

Run: `pytest tests/test_server_product_workbench_tools.py -q`
Expected: FAIL.

- [ ] **Step 3: Wire repositories/services and tools**

Instantiate the new services using existing factories/clients. Call `resume_pending()` during server startup after dependencies exist, but isolate startup-resume exceptions so health tool remains available and failed resume is logged/audited rather than crashing import.

- [ ] **Step 4: Run GREEN plus regression**

Run: `pytest tests/test_server_product_workbench_tools.py tests/test_server_smoke.py tests/test_server_vtex_image_tools.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stech_mcp/server.py tests/test_server_product_workbench_tools.py
git commit -m "feat: expose Product Workbench MCP tools"
```

---

### Task 7: Documentation and full verification

**Files:**
- Modify: `docs/VTEX_IMAGES_MCP.md`
- Modify: `README.md` only if tool inventory is documented there.

- [ ] **Step 1: Document operational boundaries**

State explicitly that Product Workbench creation is separate from image sync; image sync still never changes price, stock, category, attributes, EAN/UPC or activation. Document SQL script `sql/005_product_workbench_jobs.sql` as required deployment migration.

- [ ] **Step 2: Run full tests**

Run: `pytest -q`
Expected: all tests pass.

- [ ] **Step 3: Run syntax check**

Run: `python -m compileall -q src`
Expected: exit 0.

- [ ] **Step 4: Commit docs**

```bash
git add docs/VTEX_IMAGES_MCP.md README.md
git commit -m "docs: document Product Workbench MCP operations"
```

- [ ] **Step 5: Verify branch HEAD in CI**

Push `feat/product-workbench-v1`, require GitHub Actions `ci.yml` success on the exact head SHA before marking PR #5 ready.
