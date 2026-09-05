# Exact-PN Specifications and Product Workspace Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose exact-Part-Number Deltron specifications through STECH MCP and add safe product autocomplete plus specification provenance to SCR Product Workspace.

**Architecture:** `DB_DISTRIBUIDORES` exposes one stable read-only specification view. STECH MCP validates requested/source Part Numbers before returning rows, while SCR reads the same view for fast Product Workspace rendering. Autocomplete uses the existing current-product view and ranks exact, prefix and text matches without introducing free SQL.

**Tech Stack:** Python 3, FastMCP, FastAPI, SQL Server 2019, pyodbc-style repositories, vanilla JavaScript/CSS, pytest.

**Spec:** `docs/superpowers/specs/2026-09-05-excel-enrichment-analytics-design.md`

## Global Constraints

- SCR implementation starts from `v8-identity` commit `ce00c762cc74720af9ddf424c92305d9faa79cfc`.
- MCP implementation starts from `feat/product-workspace-v1` commit `7a67b311f6eb6755eb74865d22d90a12ce3ebb79` plus the approved design commits.
- `82YU00X6LM` must never supply RAM, SSD or any other variant-sensitive value to `82YU00XYLM`.
- `PRD_DELTRON_ESPECIFICACION` is read-only.
- Consumers query `dbo.V_MCP_PRODUCT_SPECIFICATION`, never the physical specification table directly.
- Existing MCP tools and SCR views remain backward compatible.
- No arbitrary SQL tool, marketplace publication, automatic price or automatic stock write is added.
- All SQL values are parameterized; dynamic object identifiers come only from validated server configuration.
- Production code changes follow red-green-refactor and each task ends with focused tests and a commit.

---

## File Structure

### `artosperu-bot/mcp-stech`

- Modify: `sql/900_discover_erp_schema.sql` — include the Deltron specification table in the read-only discovery report.
- Create: `sql/005_product_specification_contract.sql` — documented target contract, applied only after discovery confirms source columns.
- Create: `src/stech_mcp/domain/product_specifications.py` — exact-PN validation and row normalization.
- Create: `src/stech_mcp/db/product_specification_repository.py` — parameterized reader for the stable view.
- Modify: `src/stech_mcp/config.py` — configure the stable specification view.
- Modify: `src/stech_mcp/server.py` — expose `product_specifications_get`.
- Create: `tests/test_product_specification_discovery_sql.py` — prove discovery is read-only and covers the source table.
- Create: `tests/test_product_specifications.py` — prove normalization and mismatch blocking.
- Create: `tests/test_product_specification_repository.py` — prove parameterization and stable-view usage.
- Modify: `tests/test_server_smoke.py` — include the new MCP tool.

### `artosperu-bot/scr`

- Modify: `src/distributor_monitor/product_workspace.py` — add ranked search and exact specification reads.
- Modify: `src/distributor_monitor/product_workspace_api.py` — expose autocomplete and specification endpoints.
- Modify: `web/product-workspace-ui.js` — accessible debounced combobox and specification table.
- Modify: `web/product-workspace.css` — autocomplete and provenance-table presentation.
- Modify: `web/index.html` — suggestion list/status containers.
- Modify: `tests/test_product_workspace_repository.py` — repository query/ranking/specification coverage.
- Modify: `tests/test_product_workspace_api.py` — API validation and limits.
- Modify: `tests/test_product_workspace_ui.py` — UI regression coverage.

## Task 1: Discover and Freeze the Deltron Specification Contract

**Files:**
- Modify: `sql/900_discover_erp_schema.sql`
- Create: `tests/test_product_specification_discovery_sql.py`

**Interfaces:**
- Consumes: SQL Server metadata for `dbo.PRD_DELTRON_ESPECIFICACION`.
- Produces: a read-only report containing column names, types, indexes, foreign keys and ten exact-PN sample rows.

- [ ] **Step 1: Write the failing discovery-contract test**

```python
from pathlib import Path


def test_discovery_covers_deltron_specifications_without_writes():
    sql = Path("sql/900_discover_erp_schema.sql").read_text(encoding="utf-8").upper()
    assert "PRD_DELTRON_ESPECIFICACION" in sql
    assert "SYS.INDEXES" in sql
    assert "SYS.FOREIGN_KEY_COLUMNS" in sql
    assert "SELECT TOP (10)" in sql
    for forbidden in ("INSERT ", "UPDATE ", "DELETE ", "DROP ", "TRUNCATE ", "MERGE "):
        assert forbidden not in sql
```

- [ ] **Step 2: Run the test and confirm the expected failure**

Run: `pytest tests/test_product_specification_discovery_sql.py -v`  
Expected: FAIL because the current discovery script does not mention the specification table or its indexes/foreign keys.

- [ ] **Step 3: Extend the discovery script**

Add metadata queries scoped to `OBJECT_ID(N'dbo.PRD_DELTRON_ESPECIFICACION')`:

```sql
SELECT c.column_id, c.name AS column_name, ty.name AS data_type,
       c.max_length, c.precision, c.scale, c.is_nullable
FROM sys.columns AS c
JOIN sys.types AS ty ON ty.user_type_id = c.user_type_id
WHERE c.object_id = OBJECT_ID(N'dbo.PRD_DELTRON_ESPECIFICACION')
ORDER BY c.column_id;

SELECT i.name AS index_name, i.is_unique, i.is_primary_key,
       ic.key_ordinal, c.name AS column_name
FROM sys.indexes AS i
JOIN sys.index_columns AS ic
  ON ic.object_id = i.object_id AND ic.index_id = i.index_id
JOIN sys.columns AS c
  ON c.object_id = ic.object_id AND c.column_id = ic.column_id
WHERE i.object_id = OBJECT_ID(N'dbo.PRD_DELTRON_ESPECIFICACION')
ORDER BY i.index_id, ic.key_ordinal;

SELECT OBJECT_SCHEMA_NAME(fkc.parent_object_id) AS child_schema,
       OBJECT_NAME(fkc.parent_object_id) AS child_table,
       COL_NAME(fkc.parent_object_id, fkc.parent_column_id) AS child_column,
       OBJECT_SCHEMA_NAME(fkc.referenced_object_id) AS parent_schema,
       OBJECT_NAME(fkc.referenced_object_id) AS parent_table,
       COL_NAME(fkc.referenced_object_id, fkc.referenced_column_id) AS parent_column
FROM sys.foreign_key_columns AS fkc
WHERE fkc.parent_object_id = OBJECT_ID(N'dbo.PRD_DELTRON_ESPECIFICACION');

SELECT TOP (10) *
FROM dbo.PRD_DELTRON_ESPECIFICACION;
```

Also add `N'PRD_DELTRON_ESPECIFICACION'` to the existing table-name filter.

- [ ] **Step 4: Run the focused test**

Run: `pytest tests/test_product_specification_discovery_sql.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit the read-only discovery change**

```bash
git add sql/900_discover_erp_schema.sql tests/test_product_specification_discovery_sql.py
git commit -m "test: discover Deltron specification contract"
```

- [ ] **Step 6: Production checkpoint**

Run on `DB_DISTRIBUIDORES`:

```powershell
sqlcmd -S PC020 -d DB_DISTRIBUIDORES -E -C -i ".\sql\900_discover_erp_schema.sql" -o ".\deltron_spec_schema.txt"
```

Expected: the report contains the physical key joining a specification row to `producto_distribuidor_id` or the exact product identity, plus the visible fields corresponding to section, attribute, original value, normalized value, unit and normalization status. The output contains no secrets and becomes the evidence used to finish `005_product_specification_contract.sql`.

## Task 2: Add Exact-Part-Number Domain Validation

**Files:**
- Create: `src/stech_mcp/domain/product_specifications.py`
- Create: `tests/test_product_specifications.py`

**Interfaces:**
- Consumes: `requested_partnumber: str` and rows containing `source_partnumber`.
- Produces: `normalize_specification_rows(requested_partnumber: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]`.
- Raises: `ProductIdentityConflict` on any non-empty mismatched source Part Number.

- [ ] **Step 1: Write failing exact-match tests**

```python
import pytest
from stech_mcp.domain.product_specifications import (
    ProductIdentityConflict,
    normalize_specification_rows,
)


def test_normalizes_exact_partnumber_rows_without_losing_original_value():
    rows = [{
        "source_partnumber": " 82yu00xylm ",
        "section_name": "MEMORIA",
        "attribute_name": "CAPACIDAD",
        "original_value": "16 GB",
        "normalized_value": 16,
        "unit": "GB",
        "normalization_status": "NORMALIZADO",
        "section_order": 6,
        "attribute_order": 9,
    }]
    assert normalize_specification_rows("82YU00XYLM", rows)[0] == {
        "source_partnumber": "82YU00XYLM",
        "section_name": "MEMORIA",
        "attribute_name": "CAPACIDAD",
        "original_value": "16 GB",
        "normalized_value": 16,
        "unit": "GB",
        "normalization_status": "NORMALIZADO",
        "section_order": 6,
        "attribute_order": 9,
        "partnumber_match": "EXACT",
    }


def test_blocks_x6lm_rows_from_xylm_request():
    with pytest.raises(ProductIdentityConflict) as error:
        normalize_specification_rows(
            "82YU00XYLM",
            [{"source_partnumber": "82YU00X6LM", "original_value": "8 GB"}],
        )
    assert error.value.requested_partnumber == "82YU00XYLM"
    assert error.value.source_partnumber == "82YU00X6LM"
```

- [ ] **Step 2: Run tests to verify RED**

Run: `pytest tests/test_product_specifications.py -v`  
Expected: collection fails because the module does not exist.

- [ ] **Step 3: Implement the minimal validator**

```python
from __future__ import annotations

from typing import Any


def normalize_partnumber(value: str) -> str:
    return str(value or "").strip().upper()


class ProductIdentityConflict(ValueError):
    def __init__(self, requested_partnumber: str, source_partnumber: str):
        self.requested_partnumber = normalize_partnumber(requested_partnumber)
        self.source_partnumber = normalize_partnumber(source_partnumber)
        super().__init__(
            f"Specification identity mismatch: requested={self.requested_partnumber} "
            f"source={self.source_partnumber}"
        )


def normalize_specification_rows(
    requested_partnumber: str,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    requested = normalize_partnumber(requested_partnumber)
    normalized: list[dict[str, Any]] = []
    for row in rows:
        source = normalize_partnumber(row.get("source_partnumber"))
        if source and source != requested:
            raise ProductIdentityConflict(requested, source)
        normalized.append({**row, "source_partnumber": source or requested, "partnumber_match": "EXACT"})
    return normalized
```

- [ ] **Step 4: Run focused tests to verify GREEN**

Run: `pytest tests/test_product_specifications.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit the domain guard**

```bash
git add src/stech_mcp/domain/product_specifications.py tests/test_product_specifications.py
git commit -m "feat: block cross-variant specification values"
```

## Task 3: Create the Stable Specification View and MCP Repository

**Files:**
- Create: `sql/005_product_specification_contract.sql`
- Create: `src/stech_mcp/db/product_specification_repository.py`
- Modify: `src/stech_mcp/config.py`
- Create: `tests/test_product_specification_repository.py`

**Interfaces:**
- Consumes: the verified physical-column mapping produced by Task 1.
- Produces SQL view columns: `producto_distribuidor_id`, `source_partnumber`, `section_order`, `section_name`, `attribute_order`, `attribute_name`, `original_value`, `normalized_value`, `unit`, `normalization_status`, `source_observed_at`.
- Produces Python interface: `ProductSpecificationRepository.list_for_partnumber(partnumber: str) -> list[dict[str, Any]]`.

- [ ] **Step 1: Write the failing repository tests**

```python
from stech_mcp.db.product_specification_repository import ProductSpecificationRepository


class FakeDb:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def query(self, sql, params):
        self.calls.append((sql, params))
        return self.rows


def test_repository_uses_stable_view_and_parameterizes_partnumber():
    db = FakeDb([{"source_partnumber": "82YU00XYLM", "original_value": "16 GB"}])
    repo = ProductSpecificationRepository(db, "dbo.V_MCP_PRODUCT_SPECIFICATION")
    rows = repo.list_for_partnumber(" 82yu00xylm ")
    sql, params = db.calls[0]
    assert "V_MCP_PRODUCT_SPECIFICATION" in sql
    assert "PRD_DELTRON_ESPECIFICACION" not in sql
    assert "WHERE source_partnumber = ?" in sql
    assert params == ("82YU00XYLM",)
    assert rows[0]["partnumber_match"] == "EXACT"
```

- [ ] **Step 2: Run the focused test to verify RED**

Run: `pytest tests/test_product_specification_repository.py -v`  
Expected: FAIL because the repository is not implemented.

- [ ] **Step 3: Add validated view configuration**

Extend `Settings` with:

```python
product_specification_view: str = "dbo.V_MCP_PRODUCT_SPECIFICATION"
```

Load it from `ERP_PRODUCT_SPECIFICATION_VIEW`. Reuse the existing validated `schema.object` identifier policy used for `ERP_PRODUCT_VIEW`; reject whitespace, semicolons and names outside `[A-Za-z0-9_.\[\]]`.

- [ ] **Step 4: Create the repository**

```python
from __future__ import annotations

from typing import Any

from stech_mcp.domain.product_specifications import normalize_partnumber, normalize_specification_rows


class ProductSpecificationRepository:
    def __init__(self, db: Any, view_name: str):
        self.db = db
        self.view_name = view_name

    def list_for_partnumber(self, partnumber: str) -> list[dict[str, Any]]:
        normalized = normalize_partnumber(partnumber)
        rows = self.db.query(
            f"""SELECT producto_distribuidor_id, source_partnumber,
                       section_order, section_name, attribute_order, attribute_name,
                       original_value, normalized_value, unit,
                       normalization_status, source_observed_at
                FROM {self.view_name}
                WHERE source_partnumber = ?
                ORDER BY section_order, attribute_order""",
            (normalized,),
        )
        return normalize_specification_rows(normalized, rows)
```

- [ ] **Step 5: Create the stable view migration with fail-closed source assertions**

The screen contract identifies the source concepts as product key, section order/name, attribute order/name, original value, normalized value, unit and normalization state. Assert the corresponding SQL columns before creating the view; if production uses a different physical name, the migration stops before changing any object and Task 1 evidence is used to change only the relevant assertion/alias:

```sql
SET NOCOUNT ON;
SET XACT_ABORT ON;

IF OBJECT_ID(N'dbo.PRD_DELTRON_ESPECIFICACION', N'U') IS NULL
    THROW 51000, 'Missing dbo.PRD_DELTRON_ESPECIFICACION', 1;

IF COL_LENGTH(N'dbo.PRD_DELTRON_ESPECIFICACION', N'producto_distribuidor_id') IS NULL
    THROW 51001, 'Missing specification product key: producto_distribuidor_id', 1;
IF COL_LENGTH(N'dbo.PRD_DELTRON_ESPECIFICACION', N'orden_seccion') IS NULL
    THROW 51002, 'Missing specification section order: orden_seccion', 1;
IF COL_LENGTH(N'dbo.PRD_DELTRON_ESPECIFICACION', N'seccion') IS NULL
    THROW 51003, 'Missing specification section name: seccion', 1;
IF COL_LENGTH(N'dbo.PRD_DELTRON_ESPECIFICACION', N'orden') IS NULL
    THROW 51004, 'Missing specification attribute order: orden', 1;
IF COL_LENGTH(N'dbo.PRD_DELTRON_ESPECIFICACION', N'atributo') IS NULL
    THROW 51005, 'Missing specification attribute name: atributo', 1;
IF COL_LENGTH(N'dbo.PRD_DELTRON_ESPECIFICACION', N'valor_original') IS NULL
    THROW 51006, 'Missing specification original value: valor_original', 1;
IF COL_LENGTH(N'dbo.PRD_DELTRON_ESPECIFICACION', N'valor_normalizado') IS NULL
    THROW 51007, 'Missing normalized value: valor_normalizado', 1;
IF COL_LENGTH(N'dbo.PRD_DELTRON_ESPECIFICACION', N'unidad') IS NULL
    THROW 51008, 'Missing specification unit: unidad', 1;
IF COL_LENGTH(N'dbo.PRD_DELTRON_ESPECIFICACION', N'estado_normalizacion') IS NULL
    THROW 51009, 'Missing normalization status: estado_normalizacion', 1;

EXEC sys.sp_executesql N'
CREATE OR ALTER VIEW dbo.V_MCP_PRODUCT_SPECIFICATION
AS
SELECT
    s.producto_distribuidor_id,
    UPPER(LTRIM(RTRIM(p.part_number))) AS source_partnumber,
    s.orden_seccion AS section_order,
    s.seccion AS section_name,
    s.orden AS attribute_order,
    s.atributo AS attribute_name,
    CONVERT(nvarchar(max), s.valor_original) AS original_value,
    CONVERT(nvarchar(max), s.valor_normalizado) AS normalized_value,
    s.unidad AS unit,
    s.estado_normalizacion AS normalization_status,
    p.observado_at AS source_observed_at
FROM dbo.PRD_DELTRON_ESPECIFICACION AS s
INNER JOIN dbo.V_PRD_PRODUCTO_ACTUAL AS p
    ON p.producto_distribuidor_id = s.producto_distribuidor_id
WHERE p.part_number IS NOT NULL;
';
```

Add a smoke query for `82YU00XYLM` after the view creation. The migration performs no source-data mutation.

- [ ] **Step 6: Run repository, config and full MCP tests**

Run: `pytest tests/test_product_specification_repository.py tests/test_config.py -v`  
Expected: PASS.  
Run: `pytest`  
Expected: all MCP tests PASS.

- [ ] **Step 7: Commit the stable read contract**

```bash
git add sql/005_product_specification_contract.sql src/stech_mcp/config.py src/stech_mcp/db/product_specification_repository.py tests/test_product_specification_repository.py tests/test_config.py
git commit -m "feat: read exact Deltron specifications through stable view"
```

## Task 4: Expose `product_specifications_get` Through MCP

**Files:**
- Modify: `src/stech_mcp/server.py`
- Modify: `tests/test_server_smoke.py`
- Create: `tests/test_server_product_specifications.py`

**Interfaces:**
- Consumes: `ProductSpecificationRepository.list_for_partnumber(partnumber)`.
- Produces: `product_specifications_get(partnumber: str) -> {found, partnumber, count, specifications, source_view, exact_identity}`.

- [ ] **Step 1: Write failing server tests**

```python
def test_product_specifications_tool_returns_exact_rows(monkeypatch):
    monkeypatch.setattr(
        server.product_specification_repository,
        "list_for_partnumber",
        lambda partnumber: [{"source_partnumber": "82YU00XYLM", "partnumber_match": "EXACT"}],
    )
    result = server.product_specifications_get("82yu00xylm")
    assert result["found"] is True
    assert result["partnumber"] == "82YU00XYLM"
    assert result["count"] == 1
    assert result["exact_identity"] is True
```

Also update the tool-count/name smoke assertion to contain `product_specifications_get` without removing existing tools.

- [ ] **Step 2: Run server tests to verify RED**

Run: `pytest tests/test_server_product_specifications.py tests/test_server_smoke.py -v`  
Expected: FAIL because the repository dependency and tool are absent.

- [ ] **Step 3: Wire the repository and tool**

```python
@mcp.tool()
def product_specifications_get(partnumber: str) -> dict[str, Any]:
    """Obtiene especificaciones Deltron exactas, originales y normalizadas, sin mezclar variantes."""
    normalized = partnumber.strip().upper()
    if product_repository.get_by_partnumber(normalized) is None:
        return {"found": False, "partnumber": normalized, "count": 0, "specifications": []}
    rows = product_specification_repository.list_for_partnumber(normalized)
    return {
        "found": True,
        "partnumber": normalized,
        "count": len(rows),
        "specifications": rows,
        "source_view": settings.product_specification_view,
        "exact_identity": all(row["partnumber_match"] == "EXACT" for row in rows),
    }
```

Convert `ProductIdentityConflict` into a structured response with `found=True`, `exact_identity=False`, `status="IDENTITY_CONFLICT"`, requested/source Part Numbers and no specification values.

- [ ] **Step 4: Run focused and full MCP tests**

Run: `pytest tests/test_server_product_specifications.py tests/test_server_smoke.py -v`  
Expected: PASS.  
Run: `pytest`  
Expected: all MCP tests PASS.

- [ ] **Step 5: Commit the MCP capability**

```bash
git add src/stech_mcp/server.py tests/test_server_product_specifications.py tests/test_server_smoke.py
git commit -m "feat: expose exact product specifications through MCP"
```

## Task 5: Add Product Workspace Autocomplete API

**Files:**
- Modify: `src/distributor_monitor/product_workspace.py`
- Modify: `src/distributor_monitor/product_workspace_api.py`
- Modify: `tests/test_product_workspace_repository.py`
- Modify: `tests/test_product_workspace_api.py`

**Interfaces:**
- Produces repository method: `search(query: str, limit: int = 10) -> list[dict[str, Any]]`.
- Produces endpoint: `GET /api/product-workspace/search?q=<text>&limit=10`.
- Response fields: `partnumber`, `ean`, `upc`, `mini_codigo`, `codigo_externo`, `brand`, `model`, `product_name`, `family`, `category`, `subcategory`, `match_rank`.

- [ ] **Step 1: Write failing ranking and parameterization tests**

```python
def test_workspace_search_parameterizes_query_and_caps_limit(fake_db):
    repo = ProductWorkspaceRepository(fake_db)
    repo.search("82YU", limit=999)
    sql, params = fake_db.calls[-1]
    assert "TOP (20)" in sql
    assert "82YU" not in sql
    assert params[0] == "82YU"
    assert params[1] == "82YU%"
    assert params[-1] == "%82YU%"


def test_workspace_search_rejects_blank_query(client):
    response = client.get("/api/product-workspace/search?q=   ")
    assert response.status_code == 422
```

- [ ] **Step 2: Run tests to verify RED**

Run: `pytest tests/test_product_workspace_repository.py tests/test_product_workspace_api.py -v`  
Expected: FAIL because search is not implemented.

- [ ] **Step 3: Implement ranked repository search**

Use `dbo.V_PRD_PRODUCTO_ACTUAL` and a `CASE` expression:

```sql
CASE
  WHEN UPPER(part_number) = UPPER(?) THEN 0
  WHEN UPPER(part_number) LIKE UPPER(?) THEN 1
  WHEN UPPER(COALESCE(ean,'')) = UPPER(?) OR UPPER(COALESCE(upc,'')) = UPPER(?) THEN 2
  WHEN UPPER(COALESCE(mini_codigo,'')) = UPPER(?) OR UPPER(COALESCE(codigo_externo,'')) = UPPER(?) THEN 3
  ELSE 4
END AS match_rank
```

The `WHERE` clause searches Part Number, EAN, UPC, mini code, external code, product name, brand, model, family, category and subcategory with parameterized exact/prefix/contains values. Clamp `limit` to `1..20`; normalize output keys without modifying source data.

- [ ] **Step 4: Register the API before the dynamic Part Number route**

```python
@app.get("/api/product-workspace/search")
def search_workspace(q: str, limit: int = 10):
    query = q.strip()
    if not query:
        raise HTTPException(422, "Escribe un Part Number, EAN, código o nombre")
    return {"query": query, "products": repository.search(query, limit)}
```

Register this literal route before `/api/product-workspace/{partnumber}` so `search` is never captured as a Part Number.

- [ ] **Step 5: Run focused tests and commit**

Run: `pytest tests/test_product_workspace_repository.py tests/test_product_workspace_api.py -v`  
Expected: PASS.

```bash
git add src/distributor_monitor/product_workspace.py src/distributor_monitor/product_workspace_api.py tests/test_product_workspace_repository.py tests/test_product_workspace_api.py
git commit -m "feat: add ranked Product Workspace autocomplete API"
```

## Task 6: Display Exact Deltron Specifications in Product Workspace

**Files:**
- Modify: `src/distributor_monitor/product_workspace.py`
- Modify: `src/distributor_monitor/product_workspace_api.py`
- Modify: `tests/test_product_workspace_repository.py`
- Modify: `tests/test_product_workspace_api.py`

**Interfaces:**
- Produces repository method: `get_specifications(partnumber: str) -> list[dict[str, Any]]`.
- Extends the existing workspace response with `specifications: {count, exact_identity, source_view, rows}`.
- Produces endpoint: `GET /api/product-workspace/{partnumber}/specifications`.

- [ ] **Step 1: Write failing exact-view tests**

```python
def test_workspace_specs_use_stable_view_and_exact_partnumber(fake_db):
    repo = ProductWorkspaceRepository(fake_db)
    repo.get_specifications("82yu00xylm")
    sql, params = fake_db.calls[-1]
    assert "V_MCP_PRODUCT_SPECIFICATION" in sql
    assert "PRD_DELTRON_ESPECIFICACION" not in sql
    assert params == ("82YU00XYLM",)
```

Add an API test asserting `source_partnumber="82YU00X6LM"` under a request for `82YU00XYLM` returns HTTP 409 with `status="IDENTITY_CONFLICT"` and does not return the row values.

- [ ] **Step 2: Run focused tests to verify RED**

Run: `pytest tests/test_product_workspace_repository.py tests/test_product_workspace_api.py -v`  
Expected: FAIL because specification reads are absent.

- [ ] **Step 3: Implement repository and API response**

Query the stable view with a parameterized Part Number and deterministic `ORDER BY section_order, attribute_order`. Normalize requested and returned Part Numbers. If any non-empty source identity differs, raise a local `ProductWorkspaceIdentityConflict` and translate it to HTTP 409.

- [ ] **Step 4: Run focused tests and commit**

Run: `pytest tests/test_product_workspace_repository.py tests/test_product_workspace_api.py -v`  
Expected: PASS.

```bash
git add src/distributor_monitor/product_workspace.py src/distributor_monitor/product_workspace_api.py tests/test_product_workspace_repository.py tests/test_product_workspace_api.py
git commit -m "feat: show exact Deltron specifications in Product Workspace"
```

## Task 7: Add Accessible Autocomplete and Specification Provenance UI

**Files:**
- Modify: `web/index.html`
- Modify: `web/product-workspace-ui.js`
- Modify: `web/product-workspace.css`
- Modify: `tests/test_product_workspace_ui.py`

**Interfaces:**
- Consumes: `/api/product-workspace/search` and workspace `specifications` response.
- Produces: WAI-ARIA combobox/listbox behavior and a table with original value, normalized value, unit and normalization state.

- [ ] **Step 1: Write failing UI contract tests**

```python
def test_workspace_has_autocomplete_and_specification_provenance():
    html = Path("web/index.html").read_text(encoding="utf-8")
    js = Path("web/product-workspace-ui.js").read_text(encoding="utf-8")
    assert 'role="combobox"' in html
    assert 'id="workspaceSuggestions"' in html
    assert "/api/product-workspace/search" in js
    assert "Valor original" in js
    assert "Valor normalizado" in js
    assert "normalization_status" in js
```

- [ ] **Step 2: Run the UI test to verify RED**

Run: `pytest tests/test_product_workspace_ui.py -v`  
Expected: FAIL because the current input has no suggestion list or specification table.

- [ ] **Step 3: Add the combobox markup**

Set `role="combobox"`, `aria-autocomplete="list"`, `aria-controls="workspaceSuggestions"` and `aria-expanded="false"` on the existing Part Number input. Add:

```html
<div id="workspaceSuggestions" class="workspace-suggestions" role="listbox" hidden></div>
<div id="workspaceSpecifications"></div>
```

- [ ] **Step 4: Implement debounced lookup and keyboard selection**

Use a 250 ms debounce, `AbortController` for stale requests, a minimum query length of two characters, and at most ten results. Support ArrowUp, ArrowDown, Enter and Escape. Render each option with Part Number, product name, brand/model and one matched identifier. Selecting an option updates the input and calls the existing workspace refresh.

- [ ] **Step 5: Render source specifications**

Render an empty-state panel when there are no rows. Otherwise render a semantic table with columns `Sección`, `Atributo`, `Valor original`, `Valor normalizado`, `Unidad`, `Normalización`. Escape all server values through the existing `esc()` function and show an `IDENTIDAD EXACTA` badge only when `exact_identity` is true.

- [ ] **Step 6: Run UI and related backend tests**

Run: `pytest tests/test_product_workspace_ui.py tests/test_product_workspace_api.py -v`  
Expected: PASS.

- [ ] **Step 7: Commit the UI slice**

```bash
git add web/index.html web/product-workspace-ui.js web/product-workspace.css tests/test_product_workspace_ui.py
git commit -m "feat: add Product Workspace autocomplete and source specs"
```

## Task 8: Verify Both Repositories and Real Acceptance Boundary

**Files:**
- Modify: `README.md` in `mcp-stech`
- Modify: `docs/OPERATIONS_V8_PRODUCT_CENTRIC.md` in `scr`

**Interfaces:**
- Consumes: all tasks above.
- Produces: deployment/runbook instructions and verified test evidence.

- [ ] **Step 1: Run the complete MCP suite**

Run: `pytest` from `mcp-stech`.  
Expected: all tests PASS.

- [ ] **Step 2: Run the complete SCR suite and CI-equivalent syntax checks**

Run: `pytest` from `scr`.  
Expected: all tests PASS.

Run the exact Python, JavaScript and PowerShell syntax commands defined in `.github/workflows/v8-ci.yml`.  
Expected: all checks exit 0.

- [ ] **Step 3: Confirm branch ancestry**

Run:

```bash
git fetch origin
git merge-base --is-ancestor origin/v8-identity HEAD
```

Expected in SCR: exit 0. Compare the candidate against `v8-identity` and confirm no unrelated files are present.

- [ ] **Step 4: Document deployment and health checks**

Document the required order:

1. run the read-only discovery script;
2. verify and apply `005_product_specification_contract.sql`;
3. update/restart STECH MCP;
4. verify `stech_health`;
5. call `product_get("82YU00XYLM")`;
6. call `product_specifications_get("82YU00XYLM")`;
7. open Product Workspace and test autocomplete with `82YU`;
8. verify a forced X6LM/XYLM mismatch is blocked.

- [ ] **Step 5: Execute real read-only acceptance**

Expected for `82YU00XYLM`: exact identity, only XYLM source rows, original and normalized values present, and no live channel write.  
Expected for a mismatch fixture: `IDENTITY_CONFLICT` and no returned field values.

- [ ] **Step 6: Commit documentation**

```bash
git add README.md docs/OPERATIONS_V8_PRODUCT_CENTRIC.md
git commit -m "docs: operate exact product specification workspace"
```

## Self-Review

### Spec coverage

- Exact-PN isolation: Tasks 2, 4 and 6.
- Deltron specification source and stable contract: Tasks 1 and 3.
- Product Workspace autocomplete: Tasks 5 and 7.
- Original/normalized/unit/provenance display: Tasks 3, 6 and 7.
- No live publication or commercial writes: Global Constraints and Task 8.
- Full repository verification: Task 8.

The workbook round-trip, research/image write contracts, analytical MCP tools and Falabella/VTEX schema adapters are intentionally split into subsequent implementation plans because each is an independently reviewable subsystem. This plan creates the exact-identity data foundation they all require.

### Placeholder scan

Every code-producing task names concrete files, interfaces, tests, commands and expected outcomes. The only environment checkpoint is the real schema discovery required to avoid guessing physical SQL column names.

### Type consistency

- `ProductSpecificationRepository.list_for_partnumber(str) -> list[dict[str, Any]]` is used consistently by the MCP tool.
- SCR `search(str, int)` and `get_specifications(str)` are separate repository methods.
- All external response keys use `partnumber`; source rows use `source_partnumber`.
