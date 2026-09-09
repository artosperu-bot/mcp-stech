# V8 Product Enrichment Workbench V2 Implementation Plan

> **Goal:** Add a simple, non-blocking technical enrichment control surface to SCR/V8 Product Workbench. The user selects Part Numbers, submits one `ENRICH_TECHNICAL` Product Work job, may close the view, and later returns to see persistent progress/results. SCR remains a controller/monitor only; STECH MCP remains the queue, worker, research, validation and canonical-fact authority.

## Scope and invariants

- Repository: `artosperu-bot/scr`.
- Base branch: `v8-identity` at the latest upstream SHA when implementation begins.
- Feature branch: `feat/product-enrichment-workbench-v2`.
- Do not replace or reinterpret Product Loader V1 jobs, VTEX publication, images, price, stock or activation flows.
- Do not add a second queue/database in SCR. All enrichment jobs use STECH MCP `product_work_*`.
- Technical enrichment never sends `price`, `stock`, `activate`, `is_active`, channel publication or VTEX write arguments.
- Category may be omitted by the UI; STECH MCP resolves supported categories conservatively.
- The Product Workspace remains the destination. V8 exposes control, progress, missing fields and channel readiness.
- Preserve existing `Cargar Excel`, `Buscar / Editar`, `Jobs`, VTEX and image behavior unchanged.

## Task 1 — Extend the V8 MCP client with Product Work V2 contracts

**Modify:**
- `src/distributor_monitor/product_workspace_mcp.py`
- `tests/test_product_workbench_mcp_client.py`

**New client methods:**

```python
async def start_enrichment_job(
    self,
    partnumbers: list[str],
    priority: int = 50,
    source_name: str = "V8_PRODUCT_WORKBENCH",
    actor_source: str = "SCR_UI",
) -> dict[str, Any]

async def list_enrichment_jobs(self, limit: int = 50) -> dict[str, Any]
async def get_enrichment_job(self, job_id: int) -> dict[str, Any]
async def retry_enrichment_item(self, item_id: int) -> dict[str, Any]
async def cancel_enrichment_item(self, item_id: int) -> dict[str, Any]
async def technical_missing_list(self, partnumbers: list[str]) -> dict[str, Any]
async def channel_readiness(self, partnumber: str) -> dict[str, Any]
```

**Exact tool mapping:**
- `product_work_job_create`
- `product_work_job_list`
- `product_work_job_get`
- `product_work_item_retry`
- `product_work_item_cancel`
- `product_technical_missing_list`
- `product_channel_readiness`

`start_enrichment_job()` sends:

```python
{
  "items": [{"partnumber": "PN1"}, {"partnumber": "PN2"}],
  "work_type": "ENRICH_TECHNICAL",
  "source_name": "V8_PRODUCT_WORKBENCH",
  "actor_source": "SCR_UI",
  "priority": 50,
}
```

Normalize, de-duplicate and discard blank Part Numbers before the call. Bound UI submissions to 2,000 products per job.

### TDD steps

1. Add RED tests to `tests/test_product_workbench_mcp_client.py` asserting exact MCP tool names/arguments and that forbidden commercial keys are absent.
2. Run `pytest tests/test_product_workbench_mcp_client.py -q` and confirm only new contract tests fail.
3. Implement the client methods.
4. Re-run focused test; expect GREEN.

## Task 2 — Add V8 enrichment API proxy without a local queue

**Modify:**
- `src/distributor_monitor/product_workbench_repository.py`
- `src/distributor_monitor/product_workbench_api.py`
- `tests/test_product_workbench_repository.py`
- `tests/test_product_workbench_api.py`

**Repository method:**

```python
def search_products(self, query: str = "", limit: int = 100) -> list[dict[str, Any]]
```

Read only `dbo.V_PRD_PRODUCTO_ACTUAL`; return Part Number, brand, name, category/subcategory where available, distributor and identity/status context. Never return duplicate Part Numbers; prefer the most recently observed row when the same PN exists through multiple observations/distributors. Bound `limit` to 1..500.

**Pydantic body:**

```python
class EnrichmentJobStartBody(BaseModel):
    partnumbers: list[str] = Field(min_length=1, max_length=2000)
    priority: int = Field(default=50, ge=1, le=100)
```

**New routes:**
- `GET /api/product-workbench/enrichment/products?q=&limit=100`
- `POST /api/product-workbench/enrichment/missing`
- `POST /api/product-workbench/enrichment/jobs`
- `GET /api/product-workbench/enrichment/jobs?limit=50`
- `GET /api/product-workbench/enrichment/jobs/{job_id}`
- `POST /api/product-workbench/enrichment/items/{item_id}/retry`
- `POST /api/product-workbench/enrichment/items/{item_id}/cancel`
- `GET /api/product-workbench/enrichment/{partnumber}/readiness`

The routes call only `McpProductWorkspaceClient` V2 methods. Existing `/api/product-workbench/jobs` remains the legacy Product Loader endpoint and is not renamed or redirected.

### TDD steps

1. Add RED repository tests for query, bounded limit, Part Number de-duplication and read-only SQL.
2. Add RED FastAPI tests for all V2 route contracts and 400 validation on empty selection.
3. Run:
   `pytest tests/test_product_workbench_repository.py tests/test_product_workbench_api.py -q`
4. Implement repository + routes.
5. Re-run; expect GREEN.

## Task 3 — Add an isolated Enrichment tab to Product Workbench

**Create:**
- `web/product-enrichment-workbench-ui.js`
- `tests/test_product_enrichment_workbench_ui.py`

**Modify minimally:**
- `web/product-workspace-ui.js`
- `web/index.html`
- `web/product-workspace.css`
- `tests/test_product_workbench_ui.py`

**Shell integration:**
- Add fourth tab button: `data-workbench-tab="enrichment"` text `Enriquecimiento`.
- Add pane host `#workbenchEnrichment`.
- Add the pane to the existing `tab()` map; existing default remains `edit`.
- Extend `window.ProductWorkbenchUI` with `openPartnumber(partnumber)` that switches to `edit`, fills `#workbenchPn`, and calls existing `searchProduct()`.
- Load `/product-enrichment-workbench-ui.js` immediately after `/product-workspace-ui.js` in `web/index.html`.

**New enrichment module behavior:**
- Search box calls `/api/product-workbench/enrichment/products`.
- Render a checkbox table with Part Number, brand, product name, distributor and technical status summary.
- Controls:
  - `Seleccionar visibles`
  - `Quitar selección`
  - priority selector `Normal (50)` / `Alta (100)`
  - main action `Enriquecer seleccionados`
  - `Actualizar jobs`
- Before submit, call `/enrichment/missing` for the selected products and show how many already have no missing technical fields.
- Submit selected PNs to `/enrichment/jobs`; the response returns immediately.
- Store only the current job id in `localStorage` for UX convenience. The queue state itself lives only in MCP SQL.

**Safety/UI invariants:**
- No inputs for price, stock, activation, VTEX publish or marketplace writes.
- The UI must not decide technical truth; it only displays MCP states.
- Checkbox selection is keyed by exact normalized Part Number, not row index.

### TDD steps

1. Create RED static UI tests asserting the new tab/host/script and forbidden commercial controls are absent from the enrichment module.
2. Add RED behavior-source tests asserting exact V2 endpoint strings, checkbox selection, priority values, localStorage job id and `ProductWorkbenchUI.openPartnumber` use.
3. Run:
   `pytest tests/test_product_workbench_ui.py tests/test_product_enrichment_workbench_ui.py -q`
4. Implement minimal shell changes + new module + CSS.
5. Re-run focused UI tests; expect GREEN.

## Task 4 — Persistent job monitor, retry/cancel and progressive Product Workspace access

**Modify:**
- `web/product-enrichment-workbench-ui.js`
- `tests/test_product_enrichment_workbench_ui.py`

**Terminal item states:**
- `COMPLETED`
- `PARTIAL`
- `REVIEW_REQUIRED`
- `NO_DATA_FOUND`
- `FAILED`
- `CANCELLED`

**Active/retry state support:**
- `QUEUED`
- `LOADING_SOURCE_DATA`
- `ANALYZING_MISSING_FIELDS`
- `RESEARCHING`
- `READING_DOCUMENTS`
- `VALIDATING`
- `PROMOTING_FACTS`
- `REBUILDING_PRODUCT_MASTER`
- `FAILED_RETRYABLE`

**Monitor behavior:**
- List recent V2 jobs on opening the Enrichment tab.
- Poll the selected active job every 2 seconds while the Enrichment tab is visible.
- Stop polling on terminal job state or when user changes tab.
- Each row shows Part Number, status badge, progress %, current step, attempt count, error code/detail.
- Eligible rows expose `Reintentar` and non-terminal rows expose `Cancelar`.
- Every row exposes `Abrir Product Workspace`, calling `window.ProductWorkbenchUI.openPartnumber(pn)`.
- Completed products may be opened immediately even while sibling items in the same job are still running.
- Readiness button/query displays independent `FALABELLA`, `COOLBOX`, `VTEX` completion returned by MCP.

### TDD steps

1. Add RED source tests for every required status, polling endpoint, retry/cancel endpoints, and `openPartnumber` action.
2. Add test that job monitor uses the V2 `/enrichment/jobs/...` endpoints and never the legacy `/api/product-workbench/jobs` endpoint.
3. Implement monitor/actions.
4. Run focused UI suite; expect GREEN.

## Task 5 — App regression and branch integration safeguards

**Modify only if required by failing tests:**
- `run.py`
- existing Product Workbench files already listed.

No new route registrar is required because Task 2 extends the existing `register_product_workbench_routes()` that `run.py` already installs. Do not alter channel, commercial stock, VTEX hourly sync or capture startup wiring.

### Verification steps

1. Run focused V2 suite:

```bash
pytest tests/test_product_workbench_mcp_client.py \
       tests/test_product_workbench_repository.py \
       tests/test_product_workbench_api.py \
       tests/test_product_workbench_ui.py \
       tests/test_product_enrichment_workbench_ui.py -q
```

2. Run full SCR suite:

```bash
pytest -q
```

3. Compare feature branch with latest `v8-identity` and require `behind_by == 0`. If base advanced, merge/rebase latest base before final verification.
4. Review diff and confirm no changes to channel write services, commercial stock code, VTEX publication code, connector capture logic or migrations.
5. Do not merge without explicit integration decision.

## Task 6 — Deployment handoff for PC020

**No secret values committed.**

Backend prerequisites on PC020:
- STECH MCP feature code containing SQL `006`–`009` migrations applied to `STECH_MCP`.
- `STECH_BRAVE_SEARCH_API_KEY` configured outside Git.
- `STECH_SEARCH_COUNTRY=PE`.
- `stech-enrichment-worker` installed/running as the separate Windows service.
- V8 `.env` continues to point `STECH_MCP_URL` to the MCP endpoint.

Deployment verification checklist:
1. MCP health/startup succeeds.
2. Worker service starts and releases expired leases on startup.
3. V8 opens Product Workbench → Enrichment.
4. Select one laptop, one portable speaker and one headphones PN.
5. Submit one normal-priority job and close/reopen the view.
6. Confirm persisted progress returns.
7. Confirm at least one completed item opens Product Workspace before whole batch ends.
8. Simulate worker restart during an active item; confirm lease recovery/retry.
9. Compare before/after V8 `precio_usd_sin_igv`, `stock_valor` for all test PNs; require equality.
10. Confirm readiness shows independent Falabella/Coolbox/VTEX values.

## Definition of Done

- User can select one or many Part Numbers with checkboxes and submit technical enrichment in one action.
- Submission returns immediately; work continues in the independent MCP worker.
- Closing/reopening V8 does not lose job state.
- Progress/retry/cancel/review states are visible per PN.
- Completed items are visible progressively in Product Workspace.
- V8 never creates its own enrichment queue and never decides technical truth.
- Existing Product Loader/VTEX/images remain operational and separate.
- No technical enrichment API/UI sends or writes price, stock, activation or publication fields.
- Focused V2 tests and full SCR tests pass.
- Feature branch is based on latest `v8-identity` and is not merged until explicitly approved.
