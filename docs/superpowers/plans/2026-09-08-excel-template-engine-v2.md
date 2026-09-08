# Excel Template Engine V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recognize Falabella, Coolbox and future marketplace Excel files from workbook structure, map their columns to canonical STECH fields, detect Part Numbers, calculate missing fields, and feed the same persistent enrichment queue.

**Architecture:** V8 performs physical workbook upload/read and sends a compact neutral manifest; STECH MCP owns template recognition, mapping and validation rules. Excel remains a channel input/output format, never Product Workspace master data. Commercial columns are preserved but excluded from `ENRICH_TECHNICAL`.

**Tech Stack:** Python 3.12, openpyxl, SQL Server 2019, FastMCP, pytest.

**Spec:** `docs/superpowers/specs/2026-09-08-product-enrichment-engine-v2-design.md`

## Global Constraints

- Recognition MUST NOT rely only on filename.
- High-confidence recognition may proceed automatically; medium-confidence requires UI confirmation; low/ambiguous recognition must not create a job.
- Exact thresholds are: `HIGH >= 90`, `MEDIUM 70..89`, `LOW < 70`; a top-two score gap `< 8` is `AMBIGUOUS` regardless of top score.
- `PRICE`, `STOCK`, promotion dates and other commercial columns use scope `COMMERCIAL` and never become technical missing fields.
- Coolbox and Falabella are peer templates mapped to the same canonical facts.
- Physical Excel export remains in V8; MCP returns template identity, mappings, readiness and row values.

---

### Task 1: Marketplace template registry

**Files:**
- Create: `sql/009_marketplace_templates_v2.sql`
- Create: `src/stech_mcp/db/marketplace_template_repository.py`
- Test: `tests/test_marketplace_template_schema.py`
- Test: `tests/test_marketplace_template_repository.py`

**Interfaces:**
- Consumes: STECH_MCP DB connection factory.
- Produces:
  - `marketplace_template`
  - `marketplace_template_field`
  - `marketplace_field_alias`
  - `MarketplaceTemplateRepository.list_active() -> list[dict]`
  - `MarketplaceTemplateRepository.get(template_code: str) -> dict | None`.

- [ ] **Step 1: Write the failing SQL contract test**

```python
from pathlib import Path


def test_marketplace_template_schema_contract():
    text = Path("sql/009_marketplace_templates_v2.sql").read_text(encoding="utf-8").upper()
    for token in ("MARKETPLACE_TEMPLATE", "MARKETPLACE_TEMPLATE_FIELD", "MARKETPLACE_FIELD_ALIAS", "DATA_SCOPE"):
        assert token in text
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_marketplace_template_schema.py -v`

Expected: FAIL because SQL file does not exist.

- [ ] **Step 3: Implement exact SQL contract**

`marketplace_template` fields: `template_code`, `channel_code`, `category_code`, `version_code`, `sheet_pattern`, `header_row_min`, `header_row_max`, `is_active`, timestamps.

`marketplace_template_field` fields: `template_code`, `ordinal`, `header_name`, `field_code`, `required_flag`, `data_scope`, `recognition_weight`, `is_distinctive`.

`marketplace_field_alias` fields: `template_code` nullable, `field_code`, `alias_text`, `normalized_alias`.

Allowed scopes exactly: `TECHNICAL`, `IDENTITY`, `CONTENT`, `COMMERCIAL`, `CONTROL`.

- [ ] **Step 4: Write repository test then implement repository**

```python
def test_repository_excludes_inactive_templates(repo):
    rows = repo.list_active()
    assert rows
    assert all(row["is_active"] for row in rows)
```

Normalize aliases using Unicode NFKD, remove diacritics, collapse whitespace and lowercase.

- [ ] **Step 5: Run tests and commit**

```bash
pytest tests/test_marketplace_template_schema.py tests/test_marketplace_template_repository.py -v
git add sql/009_marketplace_templates_v2.sql src/stech_mcp/db/marketplace_template_repository.py tests/test_marketplace_template_schema.py tests/test_marketplace_template_repository.py
git commit -m "feat: add marketplace Excel template registry"
```

---

### Task 2: Neutral workbook manifest

**Files:**
- Create: `src/stech_mcp/domain/excel_manifest.py`
- Create: `src/stech_mcp/services/excel_manifest_builder.py`
- Test: `tests/test_excel_manifest_builder.py`

**Interfaces:**
- Consumes: workbook bytes/stream for local MCP tests or JSON manifest produced by V8.
- Produces `WorkbookManifest.to_dict() -> dict` with `filename`, `sheets`, `header_candidates`, `sample_rows`.

- [ ] **Step 1: Write failing manifest test**

```python
from io import BytesIO
from openpyxl import Workbook


def test_manifest_finds_header_candidates_without_filename_dependency(builder):
    wb = Workbook()
    ws = wb.active
    ws.title = "Laptops-All in one"
    ws.append(["nota", None, None])
    ws.append(["Sku code ref", "Título", "Marca", "Modelo", "RAM"])
    ws.append(["PN1", "Laptop", "Lenovo", "V15", "16 GB"])
    stream = BytesIO(); wb.save(stream)
    manifest = builder.from_bytes(stream.getvalue(), filename="archivo-random.xlsx")
    assert manifest.header_candidates[0].row_number == 2
    assert "Sku code ref" in manifest.header_candidates[0].headers
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_excel_manifest_builder.py -v`

Expected: FAIL.

- [ ] **Step 3: Implement bounded manifest builder**

Inspect max 20 rows per sheet for header candidates, retain max 10 sample product rows, max 200 columns, and return workbook error `WORKBOOK_TOO_LARGE` if sheet count exceeds 50. Load with `data_only=False`, `read_only=True`; never evaluate formulas or macros.

Serializable shape:

```python
{
  "filename": "archivo-random.xlsx",
  "sheets": [{"name": "Laptops-All in one", "max_row": 3, "max_column": 5}],
  "header_candidates": [{"sheet": "Laptops-All in one", "row_number": 2, "headers": ["Sku code ref", "Título", "Marca", "Modelo", "RAM"]}],
  "sample_rows": [{"sheet": "Laptops-All in one", "row_number": 3, "values": ["PN1", "Laptop", "Lenovo", "V15", "16 GB"]}],
}
```

- [ ] **Step 4: Run and commit**

```bash
pytest tests/test_excel_manifest_builder.py -v
git add src/stech_mcp/domain/excel_manifest.py src/stech_mcp/services/excel_manifest_builder.py tests/test_excel_manifest_builder.py
git commit -m "feat: build neutral workbook manifests"
```

---

### Task 3: Structure-based recognizer and mapper

**Files:**
- Create: `src/stech_mcp/services/excel_template_recognizer.py`
- Create: `src/stech_mcp/services/excel_template_mapper.py`
- Test: `tests/test_excel_template_recognizer.py`
- Test: `tests/test_excel_template_mapper.py`

**Interfaces:**
- Consumes: `WorkbookManifest` and active template definitions.
- Produces:
  - `ExcelTemplateRecognizer.recognize(manifest: dict) -> dict`
  - `ExcelTemplateMapper.map_headers(template_code: str, headers: list[str]) -> list[dict]`.

- [ ] **Step 1: Write failing recognizer tests**

```python
def test_recognizer_uses_structure_not_filename(recognizer, coolbox_manifest):
    coolbox_manifest["filename"] = "falabella.xlsx"
    result = recognizer.recognize(coolbox_manifest)
    assert result["template_code"] == "COOLBOX_LAPTOP_V1"
    assert result["confidence_band"] == "HIGH"


def test_close_scores_are_ambiguous(recognizer, ambiguous_manifest):
    result = recognizer.recognize(ambiguous_manifest)
    assert result["state"] == "AMBIGUOUS"
```

- [ ] **Step 2: Implement deterministic scoring**

Score 0–100 with exact weights:
- matched weighted headers: up to 60;
- distinctive headers: up to 20;
- sheet-name match: up to 10;
- relative column order: up to 5;
- PN/SKU identifier header: up to 5.

Filename contributes 0 points. Return top 3 alternatives and reasons.

- [ ] **Step 3: Write failing mapper test**

```python
def test_mapper_separates_technical_and_commercial(mapper):
    rows = mapper.map_headers("COOLBOX_LAPTOP_V1", ["Memoria RAM", "Stock", "Precio Base"])
    by_header = {x["header"]: x for x in rows}
    assert by_header["Memoria RAM"]["field_code"] == "ram_gb"
    assert by_header["Stock"]["data_scope"] == "COMMERCIAL"
    assert by_header["Precio Base"]["data_scope"] == "COMMERCIAL"
```

- [ ] **Step 4: Implement mapper**

Aliases resolve only to canonical `field_code`; unknown headers return `state="UNMAPPED"` and are preserved. Never guess a canonical field from fuzzy semantic similarity alone.

- [ ] **Step 5: Run and commit**

```bash
pytest tests/test_excel_template_recognizer.py tests/test_excel_template_mapper.py -v
git add src/stech_mcp/services/excel_template_recognizer.py src/stech_mcp/services/excel_template_mapper.py tests/test_excel_template_recognizer.py tests/test_excel_template_mapper.py
git commit -m "feat: recognize and map marketplace Excel structures"
```

---

### Task 4: Initial Coolbox and Falabella template seeds

**Files:**
- Create: `sql/010_seed_marketplace_templates_v2.sql`
- Test: `tests/test_marketplace_template_seeds.py`

**Interfaces:**
- Consumes: registry from Task 1 and confirmed existing template contracts from current Coolbox/V8 Falabella code.
- Produces active seed templates `COOLBOX_LAPTOP_V1` and `FALABELLA_LAPTOP_V1`.

- [ ] **Step 1: Write failing seed test**

```python
from pathlib import Path


def test_seed_contains_peer_coolbox_and_falabella_templates():
    text = Path("sql/010_seed_marketplace_templates_v2.sql").read_text(encoding="utf-8")
    assert "COOLBOX_LAPTOP_V1" in text
    assert "FALABELLA_LAPTOP_V1" in text
    for commercial in ("Precio Lista", "Precio Base", "Fecha de Inicio", "Fecha Fin", "Stock"):
        assert commercial in text
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_marketplace_template_seeds.py -v`

Expected: FAIL.

- [ ] **Step 3: Implement idempotent seeds**

For Coolbox use the known `Laptops-All in one` header contract already represented in `coolbox_preview.py`; classify final commercial columns as `COMMERCIAL`. For Falabella, read only field names already present in SCR `channels/falabella.py`, `channels/falabella_categories.py` and related tests; do not invent a field that is not represented by current V8 contracts. Seed aliases such as `RAM`, `Memoria RAM`, `Capacidad RAM` → `ram_gb` where supported.

- [ ] **Step 4: Run and commit**

```bash
pytest tests/test_marketplace_template_seeds.py -v
git add sql/010_seed_marketplace_templates_v2.sql tests/test_marketplace_template_seeds.py
git commit -m "feat: seed Coolbox and Falabella Excel templates"
```

---

### Task 5: Product-row extraction and template readiness

**Files:**
- Create: `src/stech_mcp/services/excel_product_rows.py`
- Create: `src/stech_mcp/services/excel_template_validator.py`
- Create: `src/stech_mcp/services/excel_template_service.py`
- Test: `tests/test_excel_product_rows.py`
- Test: `tests/test_excel_template_validator.py`
- Test: `tests/test_excel_template_service.py`

**Interfaces:**
- Consumes: recognized template, mapped headers, Product Technical Status from Enrichment Core.
- Produces `ExcelTemplateService.analyze_manifest(manifest: dict) -> dict`.

- [ ] **Step 1: Write failing row extraction test**

```python
def test_rows_preserve_excel_row_and_dedupe_partnumber(extractor):
    result = extractor.extract(template="COOLBOX_LAPTOP_V1", rows=[
        {"row_number": 3, "Sku code ref": "pn1"},
        {"row_number": 4, "Sku code ref": "PN1"},
    ])
    assert [x["partnumber"] for x in result["products"]] == ["PN1"]
    assert result["duplicates"][0]["row_number"] == 4
```

Identifier column comes from template configuration. A marketplace SKU that is not configured as PN cannot be silently treated as PN.

- [ ] **Step 2: Write failing validator test**

```python
def test_validator_reports_missing_by_scope(validator):
    result = validator.validate("PN1", "COOLBOX_LAPTOP_V1")
    assert "ram_gb" in result["missing_technical"]
    assert "Stock" not in result["missing_technical"]
    assert result["commercial_fields"]
```

- [ ] **Step 3: Implement extractor and validator**

`validate()` returns `required_total`, `available_total`, `missing_technical`, `missing_identity`, `missing_content`, `commercial_fields`, `completion_pct`, `readiness_state`.

- [ ] **Step 4: Write failing coordinator test**

```python
def test_analysis_never_creates_job(service, work_service, manifest):
    result = service.analyze_manifest(manifest)
    assert result["recognition"]
    assert result["products"]
    work_service.create_job.assert_not_called()
```

`analyze_manifest()` returns recognition + products + duplicates + unmapped columns + per-product readiness + recommendation `UP_TO_DATE`, `ENRICH_LIGHT`, `ENRICH_DEEP` or `REVIEW_TEMPLATE`.

- [ ] **Step 5: Run and commit**

```bash
pytest tests/test_excel_product_rows.py tests/test_excel_template_validator.py tests/test_excel_template_service.py -v
git add src/stech_mcp/services/excel_product_rows.py src/stech_mcp/services/excel_template_validator.py src/stech_mcp/services/excel_template_service.py tests/test_excel_product_rows.py tests/test_excel_template_validator.py tests/test_excel_template_service.py
git commit -m "feat: analyze Excel products against Product Workspace"
```

---

### Task 6: MCP tools, queue handoff, and export mapping

**Files:**
- Create: `src/stech_mcp/tools/excel_template.py`
- Create: `src/stech_mcp/services/marketplace_export_mapping.py`
- Modify: `src/stech_mcp/server.py` tool-registration section.
- Test: `tests/test_server_excel_template_tools.py`
- Test: `tests/test_marketplace_export_mapping.py`
- Test: `tests/test_excel_template_engine_v2_integration.py`

**Interfaces:**
- Consumes: Task 5 analysis and ProductWorkService from Queue Plan.
- Produces MCP tools `excel_template_recognize`, `excel_template_analyze`, `excel_template_job_create`, plus `MarketplaceExportMappingService.values_for(partnumber, template_code) -> dict`.

- [ ] **Step 1: Write failing tool registration test**

```python
def test_excel_tools_registered(tool_names):
    assert {"excel_template_recognize", "excel_template_analyze", "excel_template_job_create"} <= set(tool_names)
```

- [ ] **Step 2: Implement tools with confidence gate**

`excel_template_job_create` accepts only a prior analysis/result with recognition state `RECOGNIZED` and confidence band `HIGH`, or `MEDIUM` with `user_confirmed_template=True`. `LOW` and `AMBIGUOUS` raise `TEMPLATE_CONFIRMATION_REQUIRED`. It calls `ProductWorkService.create_job(... work_type="ENRICH_TECHNICAL" ...)` and never creates Excel-specific queue tables.

- [ ] **Step 3: Write failing export mapping test**

```python
def test_export_mapping_preserves_commercial_columns(service):
    result = service.values_for("PN1", "COOLBOX_LAPTOP_V1")
    assert result["values"]["Memoria RAM"] == "16 GB"
    assert result["values"]["Stock"] is None
    assert result["write_policy"]["Stock"] == "PRESERVE_EXISTING"
```

Physical workbook writing stays outside MCP.

- [ ] **Step 4: Implement export mapping**

Map canonical facts to channel headers and channel units/enums. Unknown/unmanaged and `COMMERCIAL` columns return `PRESERVE_EXISTING`.

- [ ] **Step 5: Write final integration test**

Generate a workbook manifest with three PNs: complete, missing three technical fields, and conflict. Assert structure-based recognition, deduped queue handoff, only missing fields requested, and export mapping does not change price/stock.

- [ ] **Step 6: Run focused and full tests**

```bash
pytest tests/test_server_excel_template_tools.py tests/test_marketplace_export_mapping.py tests/test_excel_template_engine_v2_integration.py -v
pytest -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/stech_mcp/tools/excel_template.py src/stech_mcp/services/marketplace_export_mapping.py src/stech_mcp/server.py tests/test_server_excel_template_tools.py tests/test_marketplace_export_mapping.py tests/test_excel_template_engine_v2_integration.py
git commit -m "feat: complete Excel template enrichment workflow"
```

## Definition of Done

- Excel recognition uses structure, aliases and explainable scoring, never filename alone.
- Coolbox/Falabella initial templates are registered as peers.
- Medium/low/ambiguous recognition is safely gated.
- PN extraction is explicit and deduplicated.
- Technical missing fields are calculated from Product Workspace.
- Commercial columns are preserved and excluded from technical enrichment.
- Import uses the generic Product Work Queue.
- Export mapping can repopulate channel fields without making Excel the master.
- Full MCP test suite passes.