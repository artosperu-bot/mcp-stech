# STECH Excel Enrichment + Product Workspace Intelligence V1

**Date:** 2026-09-05  
**Status:** Approved conversational design; written specification pending user review  
**Canonical document repository:** `artosperu-bot/mcp-stech`  
**Implementation branches:** `mcp-stech/feat/excel-enrichment-analytics-v1` and `scr/feat/excel-enrichment-analytics-v1`  
**MCP base:** `feat/product-workspace-v1` at `7a67b311f6eb6755eb74865d22d90a12ce3ebb79`  
**SCR base:** `v8-identity` at `ce00c762cc74720af9ddf424c92305d9faa79cfc`  
**First category:** laptops  
**First acceptance Part Number:** `82YU00XYLM`

## 1. Goal

Allow STECH to provide a Part Number or an Excel workbook through either ChatGPT or the SCR Product Workspace and receive a high-quality completed workbook plus a persistent reviewable Product Workspace record.

The system must:

1. use exact Deltron/SQL product identity and specifications first;
2. fill only missing or disputed fields from reliable external sources;
3. preserve field-level provenance and conflicts;
4. discover and register usable product image URLs;
5. map one reusable Product Master into Coolbox, Falabella and VTEX drafts;
6. provide product autocomplete and broad commercial/history queries through STECH MCP;
7. avoid live publication and automatic commercial price/stock logic in this milestone.

The first vertical slice supports laptops, while category schemas and field mappings remain data-driven so other categories can be added without rewriting the core workflow.

## 2. Non-negotiable identity rule

No value may cross from one Part Number to another unless the field is explicitly classified as chassis-invariant and evidence proves both Part Numbers share that exact chassis.

The observed example is a required regression case:

- `82YU00X6LM`: Deltron identity shows 8 GB RAM and 256 GB SSD.
- `82YU00XYLM`: the target workbook row shows 16 GB RAM and 512 GB SSD.

Both may belong to Lenovo V15 G4 AMN, but RAM, storage, operating system, CPU, GPU, color and GTIN are variant-sensitive. A family/model match is insufficient for these fields.

Before a field is accepted, the pipeline records and validates:

```text
requested_partnumber
source_partnumber
producto_distribuidor_id
producto_maestro_id when available
identity_status
identity_confidence
field_variant_scope
```

An exact mismatch produces `IDENTITY_CONFLICT`; it never silently fills a cell.

## 3. Source hierarchy

The resolver uses the following priority and never labels an estimate as verified:

1. approved manual correction;
2. current exact-PN operational value from Deltron/ERP when the field is operational;
3. exact-PN Deltron specification from `PRD_DELTRON_ESPECIFICACION`;
4. A1 manufacturer page with exact Part Number;
5. A2 official support, PSREF, datasheet or manual with exact Part Number;
6. B authorized distributor with exact Part Number/SKU;
7. C trusted retailer with exact Part Number, only when higher-grade sources do not expose the field;
8. deterministic derived value;
9. explicitly labeled STECH estimate;
10. unresolved `RESEARCH_REQUIRED`.

For technical contradictions, the system does not automatically replace either candidate. It records a conflict with both values and their evidence for review. An approved manual value remains protected from automatic overwrite.

Required evidence metadata:

```text
partnumber
field_code
value_text / value_number
unit
method
source_grade
source_type
source_domain
source_url
source_partnumber
partnumber_match
retrieved_at
confidence
approval_status
```

## 4. Existing data contracts to reuse

### DB_DISTRIBUIDORES

- `dbo.V_PRD_PRODUCTO_ACTUAL`: exact product identity, current stock/price snapshot and product identifiers.
- `dbo.V_HST_PRODUCTO_OBSERVACION_V8`: historical stock, price and locations.
- `dbo.PRD_DELTRON_ESPECIFICACION`: original and normalized Deltron specifications, unit and normalization status.
- Existing intelligence/history tables and views used by `AnalyticsRepository` and `DemandRepository`.
- Existing Deltron image inventory, currently exposed through `dbo.PRD_DELTRON_IMAGEN`.

Before production SQL is written against `PRD_DELTRON_ESPECIFICACION`, its real columns, keys and indexes must be captured through the existing schema-discovery workflow. The implementation then adds a stable, read-only MCP view instead of coupling every consumer to its physical layout:

```text
dbo.V_MCP_PRODUCT_SPECIFICATION
```

The view must expose exact product identity, section, attribute, original value, normalized value, unit, normalization status, source timestamp and deterministic ordering.

### STECH_MCP

Continue using the existing Product Master, enrichment/evidence, packaging rule, channel draft, image metadata, approval and audit entities. Add only additive structures needed for import jobs, template versions, field candidates/conflicts and source refresh state.

No generic `execute_sql` MCP tool is permitted.

## 5. Two workbook entry paths

### Path A — Excel sent in ChatGPT

1. ChatGPT reads the workbook without altering it.
2. The workbook adapter identifies the template by normalized headers and a template fingerprint.
3. Part Numbers and existing cell values become normalized row JSON.
4. ChatGPT calls focused STECH MCP tools to prepare products and retrieve resolved export payloads.
5. Missing fields are researched and persisted with evidence through focused MCP tools.
6. ChatGPT writes resolved values back into a copy of the original workbook and returns it.
7. The same resolved state is visible in Product Workspace.

### Path B — Excel uploaded in Product Workspace

1. SCR accepts the workbook through a multipart upload endpoint with size and file-type limits.
2. SCR's workbook adapter extracts the same normalized row JSON.
3. SCR invokes the same MCP preparation and resolution contracts used by ChatGPT.
4. The import runs as a persistent job and can resume after interruption.
5. SCR writes a result copy preserving the original workbook structure and exposes it for download.

The binary workbook reader/writer is an edge adapter. Product resolution, provenance, conflict and channel mapping logic remain centralized in STECH MCP.

## 6. Workbook preservation and laptop template

For the current 81-column laptop workbook, the adapter must preserve:

- sheet names and ordering;
- original column ordering and header spelling;
- styles, widths, merged cells and frozen panes;
- formulas and character counters;
- data validation and dropdown lists;
- hidden sheets and named ranges;
- dates and number formats;
- unrelated rows and cells.

The output is a new workbook; the uploaded original is never overwritten.

The Part Number is read from `Sku code reference (Max. hasta 15 caracteres)`. The character-count column is preserved as a formula when the template supplies one. Empty commercial fields remain empty unless the user supplies them. Price and stock are not inferred from Deltron in this milestone.

Template metadata is versioned by:

```text
marketplace_code
template_code
category_code
header_fingerprint
template_version
source_filename
imported_at
```

An unknown or changed header set produces `TEMPLATE_REVIEW_REQUIRED`; the system does not guess column positions.

## 7. Canonical field mapping

`PRD_DELTRON_ESPECIFICACION` is mapped by normalized `(section, attribute)` pairs into canonical field codes. Examples include:

| Deltron section/attribute | Canonical field |
|---|---|
| `DESCRIPCION / MARCA` | `brand` |
| `DESCRIPCION / MODELO` | `model` |
| `DESCRIPCION / PART NUMBER` | `partnumber` |
| `PANTALLA / ESPECIFICACION` | screen candidates requiring parsing |
| `CPU / ESPECIFICACION` | processor detail candidate |
| `MEMORIA / CAPACIDAD` | `ram_capacity_gb` |
| `MEMORIA / TIPO` | `ram_type` |
| `MEMORIA / BUS` | `ram_speed_mhz` |
| `ALMACENAMIENTO / CAPACIDAD` | storage-capacity candidate |
| `ALMACENAMIENTO / TIPO` | storage-type candidate |
| `VIDEO / CHIPSET` | `graphics_model` candidate |
| `BATERIA / CAPACIDAD` | `battery_capacity_wh` |

Compound Deltron strings are stored unchanged as source evidence, then parsed into separate candidates. Parsing must never discard the original value.

Each Excel column maps to one canonical field or a deterministic presentation transform. Titles, descriptions and additional information are rendered from resolved fields rather than becoming the source of truth.

## 8. Field-resolution states

Every requested field ends in one of these states:

- `VERIFIED`: reliable evidence accepted.
- `DELTRON`: exact-PN Deltron value with no accepted contradiction.
- `DERIVED`: deterministic transform from resolved fields.
- `ESTIMATED`: approved STECH fallback, clearly labeled.
- `CONFLICT`: two plausible incompatible candidates need review.
- `RESEARCH_REQUIRED`: missing or insufficient evidence.
- `NOT_APPLICABLE`: category/schema proves the field does not apply.
- `MANUAL`: user-approved value.

Blank is not treated as zero, `No` or `Sin`. Those are explicit values only when evidence or channel rules support them.

## 9. Images

Image preparation follows this order:

1. reuse exact-product images already captured from Deltron;
2. manufacturer official product/support/media/CDN pages using exact Part Number;
3. authorized distributor exact-SKU assets;
4. trusted retailer exact-SKU assets only if higher grades are insufficient.

The pipeline stores source URL, source domain, exact-PN match, official status, dimensions, format, hash, position and approval state. It preserves originals and deduplicates by hash and normalized URL.

For Falabella, validation reflects the official contract: images are URL-based, the first image is primary, at most eight images are submitted, supported formats are PNG/JPG and resolution must be between 500×500 and 2000×2000. Image submission remains disabled in this milestone.

Product Workspace displays source images and workspace variants separately, including why an image is or is not usable.

## 10. Product Workspace UX

Add a product search/autocomplete control and an Excel import panel.

Autocomplete searches exact and partial matches across:

- Part Number;
- EAN and UPC;
- mini code and external code;
- product name;
- brand and model;
- family, category and subcategory.

The API is debounced, parameterized and limited. Exact Part Number matches appear first, then prefix matches, then text matches. Keyboard navigation, empty state and error state are required.

The product page shows:

- identity and exact-PN guard result;
- Deltron original/normalized specifications;
- resolved Excel fields;
- missing fields;
- conflicts and candidate evidence;
- source URLs and retrieval dates;
- image gallery and readiness;
- per-channel draft readiness;
- import/export job status;
- audit timeline.

No UI control publishes live products in this milestone.

## 11. MCP capabilities

Existing tools remain backward compatible. Add focused tools along these boundaries:

### Product and Excel resolution

- `product_specifications_get(partnumber)`
- `product_missing_fields(partnumber, marketplace, category)`
- `product_prepare_batch(partnumbers, marketplace, category)`
- `product_export_payload_get(partnumber, marketplace, template_code)`
- `product_conflicts_get(partnumber)`
- `product_field_candidates_get(partnumber, field_code=None)`
- `template_schema_get(marketplace, category, template_code=None)`

### Evidence and images

- retain `product_field_verify`
- `product_field_candidate_save(...)`
- `product_conflict_resolve(...)`
- retain `product_images_get`
- `product_image_source_save(...)`
- `product_image_approve(...)`

External research is performed by an agent with internet access. MCP stores, validates and resolves the evidence; it does not invent values when research is unavailable.

### Commercial and historical intelligence

- `movement_rank(...)`
- `category_movement(...)`
- `brand_movement(...)`
- `opportunity_rank(...)`
- `stockout_risk(...)`
- `price_changes(...)`
- `replenishment_rank(...)`
- `stagnant_products(...)`
- `new_products(...)`
- `discontinued_candidates(...)`
- `product_compare(partnumbers, period_days, scope)`
- `marketplace_candidates(marketplace, filters, period_days)`

All analytical responses state that observed supplier stock reductions are movement signals, not proven end-customer sales. Filters cover period, distributor, brand, family, category, subcategory, warehouse scope, stock state and result limit where applicable.

## 12. SCR APIs

Add or extend controlled endpoints:

```text
GET  /api/product-workspace/search?q=&limit=
GET  /api/product-workspace/{partnumber}/specifications
GET  /api/product-workspace/{partnumber}/fields
GET  /api/product-workspace/{partnumber}/conflicts
POST /api/product-workspace/imports/inspect
POST /api/product-workspace/imports
GET  /api/product-workspace/imports/{job_id}
GET  /api/product-workspace/imports/{job_id}/result.xlsx
```

Multipart upload endpoints enforce XLSX/XLSM policy, maximum size, normalized safe filenames and temporary-file cleanup. A later decision is required before macro-enabled workbooks are accepted; V1 accepts XLSX only.

## 13. Falabella schema adapter

Falabella category data is never hardcoded from memory. The adapter reads and versions:

- `GetCategorySuggestion` as optional assistance;
- `GetCategoryTree` to confirm the category exists and is a leaf;
- `GetCategoryAttributes` for mandatory fields, field types, options and variation behavior;
- `GetContentScore` for current category scoring rules;
- `GetBrands` and mapped brand contracts when required.

For future publication, the draft models `ProductCreate`, `Image` and asynchronous feed tracking, but V1 only produces preview/validation/export artifacts. No request is sent to Falabella.

Category 432 and operator `fape` are configuration inputs to validate against the live account contract, not universal constants.

## 14. VTEX schema adapter

The adapter reuses the current SCR VTEX discovery and import work. It reads the live account's category, brand, product specification and SKU specification contracts. Product and SKU fields remain separate.

For enum specification types, a valid `FieldValueId` is required; text types use text values. Product creation, SKU creation, EAN, image, price, inventory and trade-policy steps remain separate draft stages. V1 does not perform new live writes.

## 15. Jobs, idempotency and audit

Workbook imports and batches are persistent jobs with item-level state:

```text
PENDING
READING_SQL
RESOLVING
WAITING_RESEARCH
WAITING_REVIEW
READY_TO_EXPORT
COMPLETED
FAILED
CANCELLED
```

Reprocessing the same `(template fingerprint, workbook hash, Part Number)` updates/reuses existing state rather than duplicating Product Masters or evidence. A changed source value creates a new candidate/audit event.

Every write records actor, source, timestamp, Part Number, job and before/after value where relevant.

## 16. Failure handling

- SQL/MCP unavailable: keep the job retryable and report the failed boundary.
- Product not found: mark only that row `PRODUCT_NOT_FOUND`.
- exact-PN mismatch: block affected fields with `IDENTITY_CONFLICT`.
- unknown template: do not write cells; request template mapping review.
- missing official evidence: leave `RESEARCH_REQUIRED`.
- malformed image URL or invalid dimensions: retain source candidate but mark unusable.
- export failure: preserve resolved Product Workspace state and allow export retry.

The currently deployed STECH MCP returns an internal error for both `stech_health` and `product_get`. Root cause is not established from the available response. Deployment recovery is an explicit acceptance prerequisite, not a reason to bypass the MCP contract.

## 17. Testing strategy

All production changes use test-driven development.

Required tests include:

- `82YU00X6LM` values cannot populate `82YU00XYLM`;
- exact-PN Deltron specs precede external research;
- approved manual fields are protected;
- original and normalized specification values are retained;
- source priority and conflict creation;
- all 81 laptop fields preserve deterministic ordering;
- workbook structure, formulas, validations, dates and styles survive round-trip;
- unknown headers fail safely;
- autocomplete ranking and parameterization;
- image source validation and deduplication;
- analytics filters, limits and supplier-movement disclaimer;
- Falabella schema cache/version parsing against fixtures from official contracts;
- VTEX product-vs-SKU and enum `FieldValueId` mapping;
- resumable/idempotent batch jobs;
- existing MCP and SCR suites remain green.

## 18. Delivery milestones

### Milestone 1 — SQL specification contract and MCP read tools

Discover the real `PRD_DELTRON_ESPECIFICACION` schema, create the stable read view, add exact-PN repository/tests and expose specifications/missing fields.

### Milestone 2 — Product Workspace autocomplete and evidence view

Add search, specification comparison, resolved fields, conflicts and source/image traceability.

### Milestone 3 — Laptop workbook round-trip

Implement the 81-column template fingerprint, upload/inspect/job/export endpoints and preservation tests.

### Milestone 4 — Research and image completion contracts

Add candidate/evidence/image save and approval tools so ChatGPT can complete missing fields and persist them safely.

### Milestone 5 — Analytical MCP tools

Expose current movement/opportunity/demand intelligence plus category, brand, stockout, price, replenishment, stagnation, comparison and marketplace candidate queries.

### Milestone 6 — Falabella and VTEX read-only schema adapters

Version official category/attribute contracts and generate channel-specific laptop drafts without publication.

### Milestone 7 — Real end-to-end acceptance

Using `82YU00XYLM`, produce a Product Workspace record and completed workbook, with every populated field classified by source/method and no contamination from `82YU00X6LM`. Verify images and unresolved fields explicitly. Do not publish.

## 19. Success definition

The milestone is successful when STECH can send the laptop workbook through ChatGPT or Product Workspace, obtain an equivalent completed XLSX, inspect all resolved values and evidence in Product Workspace, query commercial/history intelligence through MCP, and see exactly what remains unresolved—without guessed variant data, automatic commercial decisions or live marketplace writes.
