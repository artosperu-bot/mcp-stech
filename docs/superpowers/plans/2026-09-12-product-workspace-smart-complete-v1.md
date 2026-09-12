# Product Workspace Smart Complete v1 — Implementation Plan

**Date:** 2026-09-12

## Goal

Turn Product Workspace into a compact Excel-driven orchestrator that accepts Part Numbers from three equivalent entry paths (Monitor selection, existing Workspace product, or manual PN entry), resolves only the fields demanded by the chosen Excel template, reuses verified data, creates only the missing research work, includes image completion, and produces a validated Excel copy. Also paginate the Stock Automático product table at 20 rows by default without changing stock calculation/policy/sync behavior.

## Guardrails

- No merge before PC020 local end-to-end acceptance and explicit user approval.
- Excel/template defines demand. Do not research a giant product master.
- Deltron/verified Product Workspace facts first; scheduled ChatGPT only for missing, ambiguous, semantic, derived, identity, or image evidence that cannot be solved deterministically.
- Never let ChatGPT invent price, stock, cost, promotion, publication state, or logistics/package measurements.
- Product/net weight is distinct from package weight.
- Original Excel stays untouched; write a copy only.
- Images are researched/downloaded only when the selected template requires more usable images than are already local.
- Local image root: `C:\STECH_IMAGENES\MARCA\CATEGORIA_SUBCATEGORIA\PARTNUMBER`; naming `PN_01`, `PN_02`, ...
- Prefer exact-PN official/manufacturer images, avoid duplicates/watermarks, minimum useful dimension around 800 px, prefer 1000 px+; PC020 performs final validation/download.
- Preserve existing commercial-stock calculation, policy, and VTEX sync behavior; only change table presentation/pagination in this scope.

## Task 1 — Stock Automático visual pagination (SCR)

**Files:**
- `tests/test_commercial_stock_pagination_ui.py` (new)
- `web/commercial-stock-ui.js`

**TDD:**
1. Add RED tests asserting default page size 20, selector `20/50/100`, previous/next controls, visible range/page status, and page reset after search/filter/page-size changes.
2. Verify RED in CI.
3. Add local pagination state and render only the current slice; retain existing API/data/policy/sync logic.
4. Verify focused tests and full CI GREEN.

## Task 2 — Compact Product Workspace shell + unified PN intake (SCR)

**Files:**
- `tests/test_product_workspace_smart_complete_ui.py` (new)
- `web/product_workspace_v2.js`
- existing selection/handoff JS only if needed after inspection

**Behavior:**
- Manual PN input remains first-class and does not require an existing Workspace record.
- Monitor-selected PNs and manual PNs feed one selection model.
- Main UI exposes template selector/file chooser, concise batch/status view, and one primary `Completar seleccionados` action.
- Existing granular actions remain available under `Más acciones` / `Revisión`, not in the main surface.
- Main product summary shows requested-field progress and compact image progress; detailed technical fields/candidates/jobs render on demand.

**TDD:** RED UI-contract tests first, then minimal implementation, then CI GREEN.

## Task 3 — Smart completion contract/orchestrator (MCP + SCR API adapter)

**Files to inspect/reuse before edits:**
- existing Product Workspace v2 handlers/services
- `src/stech_mcp/excel/template_inspector.py`
- existing fact resolver, gap planner, readiness, channel schema/value mapper, writer
- existing Product Work job creation/batch contracts
- corresponding tests

**Behavior:**
- Input: exact PN list + template descriptor/schema.
- PN may already exist or may be new/manual; both are accepted into the same workflow.
- Inspect template and derive requested fields/options/image slots.
- Resolve from verified Workspace facts and Deltron first.
- Generate only required work items for unresolved targets and minimal support facts needed to derive them.
- Return per-PN state: ready / processing / waiting external research / review / blocked, plus requested/resolved counts and image progress.
- Avoid duplicate active jobs.

**TDD:** contract tests first; verify RED; implement smallest orchestrator using existing services; verify GREEN.

## Task 4 — Semantic/template-field research through existing ChatGPT bridge

**Behavior:**
- Extend bridge contract only as needed for requested template fields/content; do not create a second bridge or a second scheduled automation.
- Deterministic fields never wait for ChatGPT.
- ChatGPT handles ambiguous enum mapping, derived classifications such as Gama, rich grounded descriptions, exact missing technical/identity evidence, and image-source research.
- PC020 validates returned values against template options before promotion/writing.
- Update existing `STECH Research Bridge` automation only if the contract requires it; keep hourly schedule. Local bridge polling can remain every 20 minutes.

**TDD:** request/result schema tests, importer validation tests, idempotency tests.

## Task 5 — Local image resolver/downloader (MCP/PC020)

**Behavior:**
1. Resolve local path by normalized brand/category-subcategory/PN.
2. Scan existing files first; validate image format/dimensions and dedupe.
3. Compare usable local count to template-required image count.
4. If enough: create no image-research work.
5. If short: research only the deficit.
6. For exact strong official candidates, PC020 validates and localizes into the resolved folder using next free `PN_NN` name; never overwrite a good existing file.
7. Register provenance/readiness; local download does not mean marketplace publication.

**TDD:** path resolution, missing folder creation, existing-image short-circuit, deficit-only research, naming, minimum quality, duplicate rejection, idempotency.

## Task 6 — Validated Excel-copy generation (MCP)

**Behavior:**
- For each requested cell, choose verified/derived/ChatGPT-resolved value only if it satisfies template constraints.
- Preserve workbook sheets/styles/formulas/validations.
- Do not map net weight into package weight.
- Write output copy such as `<original>_COMPLETADA_<timestamp>.xlsx`; never overwrite original.
- Status is template-specific (`LISTO`, `PROCESANDO`, `REVISAR`, `BLOQUEADO`) and separate from generic product readiness.

**TDD:** exact enum enforcement, untouched original, stable auxiliary sheets, no commercial-field invention, output status.

## Task 7 — PC020 unattended acceptance

Test all of these without manual code edits or manual result-file creation:

1. Existing PN selected from Monitor -> smart completion.
2. Manual PN not yet present in Product Workspace -> accepted and queued.
3. Product with sufficient local images -> no image web research.
4. Product with missing images -> scheduled ChatGPT result -> PC020 download to correct `C:\STECH_IMAGENES\...\PN` folder.
5. Real Falabella/Coolbox Excel -> only requested fields resolved; output copy created; original unchanged.
6. Re-run same PN/template -> no duplicate facts/images/jobs.
7. Stock Automático shows 20 rows by default and preserves search/filter/policy/VTEX behavior.
8. Bridge process survives/restarts as configured and does not require an interactive PowerShell window.

Only after this acceptance and explicit user approval may any merge be proposed.