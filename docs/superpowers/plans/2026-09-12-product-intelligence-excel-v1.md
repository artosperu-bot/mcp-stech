# STECH Product Intelligence + Excel Enrichment V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert Product Workspace into the canonical product-data engine for technology products, dynamically inspect marketplace Excel templates, research only missing facts through Product Work + the scheduled ChatGPT bridge, derive explainable classifications, generate factual descriptions, and write completed Excel files without corrupting their structure.

**Architecture:** A `TemplateInspector` turns workbook structure into a channel-neutral schema. A `ProductIntelligenceResolver` combines exact-PN distributor facts, approved enrichments, derived rules and Product Work gaps, while channel adapters map the resulting canonical data back to exact template fields/options. Product and channel readiness remain separate, with research flowing through the existing persistent queue and scheduled ChatGPT bridge rather than a new web-search API.

**Tech Stack:** Python 3.12, openpyxl, Pydantic 2, SQL Server 2019/pyodbc, Product Work V2, Product Workspace V2, GitHub mailbox Research Bridge, pytest/GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-12-product-intelligence-excel-v1-design.md`

## Global Constraints

- No OpenAI API key is required.
- `STECH_BRAVE_SEARCH_API_KEY` remains optional and may be empty.
- Deltron is the first operational source when an exact-PN field is available and policy permits it.
- Do not research or invent price, stock, cost, promotions or promotional dates with ChatGPT.
- Do not treat estimated package dimensions/weight as verified product facts.
- `PRODUCT_DATA_STATUS=LISTO` is independent from channel/logistics readiness.
- Derived values must persist `rule_code`, `rule_version`, inputs, timestamp, confidence and explanation.
- Closed-list channel values must exactly match a permitted template value or remain `REVIEW_REQUIRED`.
- Existing confirmed/manual values are never silently overwritten.
- Preserve workbook sheet names, headers, formulas, validations, styles and auxiliary sheets unless an explicit audit mode says otherwise.
- Research requests are only for currently missing/invalid/stale facts and remain idempotent.
- No merge before CI is green, a real Excel is accepted in PC020, and the user explicitly approves merge.

---

### Task 1: Generic Excel Template Inspector

**Files:**
- Create: `src/stech_mcp/excel/template_models.py`
- Create: `src/stech_mcp/excel/template_inspector.py`
- Test: `tests/test_template_inspector.py`

**Interfaces:**
- Produces `TemplateSchema`, `TemplateSheet`, `TemplateField`, `AllowedValueSet`.
- `TemplateInspector.inspect(path: str | Path) -> TemplateSchema`.
- Stable field identity prioritizes header IDs such as `#56`, `#1540`, `#396393` before column position.

- [ ] **Step 1: Write failing tests** using generated in-memory/openpyxl fixtures for Falabella-like and generic technology templates. Assert sheet detection, stable attribute ID extraction, headers, required markers, data validations/options, brand/category sheets and unchanged workbook structure.
- [ ] **Step 2: Run** `pytest tests/test_template_inspector.py -q` and confirm RED because the inspector does not exist.
- [ ] **Step 3: Implement models and inspector** with read-only discovery and no workbook mutation.
- [ ] **Step 4: Run** `pytest tests/test_template_inspector.py -q` and confirm GREEN.
- [ ] **Step 5: Commit** `feat: add generic excel template inspector`.

### Task 2: Canonical Field and Channel Mapping Layer

**Files:**
- Create: `src/stech_mcp/excel/channel_schema.py`
- Create: `src/stech_mcp/services/channel_value_mapper.py`
- Modify: `src/stech_mcp/db/channel_requirement_repository.py`
- Create: `tests/test_channel_schema.py`
- Create: `tests/test_channel_value_mapper.py`

**Interfaces:**
- `build_channel_schema(template: TemplateSchema) -> ChannelSchema`.
- `ChannelValueMapper.map(field, canonical_value, allowed_values) -> MappingResult`.
- Mapping rules are explicit/versioned; no fuzzy free-form choice may silently become accepted.

- [ ] **Step 1: Write failing tests** proving IDs survive moved columns and closed-list output uses exact allowed spelling.
- [ ] **Step 2: Run focused tests** and verify RED.
- [ ] **Step 3: Implement channel schema conversion and deterministic mappings**, including `Laptop`, `Laptop Gamer`, boolean and common normalized units only where an explicit rule exists.
- [ ] **Step 4: Run focused tests** and verify GREEN.
- [ ] **Step 5: Commit** `feat: add dynamic channel schema mapping`.

### Task 3: Product Fact Resolver and Gap Planner

**Files:**
- Create: `src/stech_mcp/services/product_fact_resolver.py`
- Create: `src/stech_mcp/services/product_gap_planner.py`
- Modify: `src/stech_mcp/services/deltron_fact_adapter.py`
- Modify: `src/stech_mcp/services/product_technical_status.py`
- Modify: `src/stech_mcp/services/product_work_service.py`
- Test: `tests/test_product_fact_resolver.py`
- Test: `tests/test_product_gap_planner.py`
- Modify test: `tests/test_deltron_fact_adapter.py`

**Interfaces:**
- `ProductFactResolver.resolve(partnumber, field_codes, category_code) -> FactResolution`.
- Source precedence: approved manual > policy-authoritative Deltron exact PN > approved verified exact-PN manufacturer/support > other strong evidence.
- `ProductGapPlanner.plan(...) -> list[GapRequest]` only returns genuine missing/invalid/stale fields.

- [ ] **Step 1: Write failing tests** for precedence, conflicts, Deltron-first reuse, exclusion of commercial fields, and no research when a valid fact already exists.
- [ ] **Step 2: Run focused tests** and confirm RED.
- [ ] **Step 3: Implement resolver and gap planner** by reusing `EnrichmentRepository`, `FactCandidateRepository`, `ProductFieldVerificationService`, technical schema and existing Product Work dedupe.
- [ ] **Step 4: Extend Deltron aliases** for prioritized technology categories without adding marketplace column names to canonical facts.
- [ ] **Step 5: Run focused tests and existing enrichment tests** and confirm GREEN.
- [ ] **Step 6: Commit** `feat: resolve canonical product facts and gaps`.

### Task 4: Derived Rules Engine and GAMA V1

**Files:**
- Create: `src/stech_mcp/domain/derived_fact.py`
- Create: `src/stech_mcp/services/derived_rules.py`
- Create: `src/stech_mcp/services/rules/laptop_gama_v1.py`
- Create: `tests/test_derived_rules.py`
- Create: `tests/test_laptop_gama_v1.py`

**Interfaces:**
- `DerivedFact(value, rule_code, rule_version, inputs, confidence, explanation, derived_at)`.
- `DerivedRuleEngine.derive(field_code, category_code, facts, context) -> DerivedFact | None`.
- Coolbox/Falabella adapters later map internal result to exact `Baja|Media|Alta` when the template requires it.

- [ ] **Step 1: Write failing tests** for low/mid/high laptop profiles, insufficient inputs and the rule that high price alone cannot force `Alta`.
- [ ] **Step 2: Run focused tests** and verify RED.
- [ ] **Step 3: Implement `LAPTOP_GAMA_V1`** using CPU family/performance signals, discrete/integrated GPU, RAM, storage, screen and optional Deltron relative-price signal.
- [ ] **Step 4: Run focused tests** and verify GREEN.
- [ ] **Step 5: Commit** `feat: add versioned derived rules and laptop gama`.

### Task 5: Factual Description Builder

**Files:**
- Create: `src/stech_mcp/services/description_builder.py`
- Create: `src/stech_mcp/services/descriptions/technology.py`
- Test: `tests/test_description_builder.py`

**Interfaces:**
- `DescriptionBuilder.build(partnumber, category_code, facts, derived_facts, max_chars, identity_footer=True) -> str`.
- Never consumes unapproved candidates or commercial price/stock.

- [ ] **Step 1: Write failing tests** for laptop and smartphone descriptions, PN correctness, verified-spec inclusion, missing-field omission, `sin sistema operativo`, max length and deterministic repeat output.
- [ ] **Step 2: Run** `pytest tests/test_description_builder.py -q` and confirm RED.
- [ ] **Step 3: Implement deterministic category-aware prose builder** with factual benefits only when supported by approved facts.
- [ ] **Step 4: Run focused tests** and verify GREEN.
- [ ] **Step 5: Commit** `feat: build factual marketplace descriptions`.

### Task 6: Product and Channel Readiness Separation

**Files:**
- Create: `src/stech_mcp/services/product_data_readiness.py`
- Modify: `src/stech_mcp/services/channel_gap_analyzer.py`
- Modify: `src/stech_mcp/services/product_workspace_v2.py`
- Modify: `src/stech_mcp/domain/product_readiness.py`
- Test: `tests/test_product_data_readiness.py`
- Modify test: `tests/test_channel_gap_analyzer.py`
- Modify test: `tests/test_product_workspace_v2.py`

**Interfaces:**
- Product states: `LISTO`, `INCOMPLETO`, `REVIEW_REQUIRED`.
- Channel states: `READY`, `BLOCKED_REQUIRED_FIELD`, `BLOCKED_LOGISTICS`, `BLOCKED_IDENTITY`, `BLOCKED_IMAGES`, `REVIEW_REQUIRED`.

- [ ] **Step 1: Write failing tests** proving product can be `LISTO` while Falabella is `BLOCKED_LOGISTICS`, and price/stock never affect product-data readiness.
- [ ] **Step 2: Run focused tests** and verify RED.
- [ ] **Step 3: Implement separate readiness evaluator** based on required factual/derived fields and unresolved conflicts.
- [ ] **Step 4: Adapt channel gap output** to precise block reason without changing channel publication behavior.
- [ ] **Step 5: Run focused + existing readiness tests** and verify GREEN.
- [ ] **Step 6: Commit** `feat: separate product and channel readiness`.

### Task 7: Safe Excel Writer and End-to-End Enrichment Service

**Files:**
- Create: `src/stech_mcp/excel/excel_writer.py`
- Create: `src/stech_mcp/services/excel_enrichment_service.py`
- Test: `tests/test_excel_writer.py`
- Test: `tests/test_excel_enrichment_service.py`

**Interfaces:**
- `ExcelWriter.write(source_path, output_path, schema, row_updates) -> WriteReport`.
- `ExcelEnrichmentService.process(source_path, output_path, channel_code=None) -> EnrichmentRunReport`.
- Only data cells are modified; auxiliary sheets/header/formulas/validation/style remain intact.

- [ ] **Step 1: Write failing writer tests** comparing before/after workbook metadata and formulas while asserting intended cells changed.
- [ ] **Step 2: Run focused tests** and verify RED.
- [ ] **Step 3: Implement safe writer** preserving workbook structure and exact closed-list values.
- [ ] **Step 4: Write failing service tests** proving existing valid values are reused, missing facts create Product Work, commercial fields are not researched and rerun is idempotent.
- [ ] **Step 5: Implement orchestration service** using inspector, resolver, gap planner, derived rules, description builder and readiness.
- [ ] **Step 6: Run focused tests** and verify GREEN.
- [ ] **Step 7: Commit** `feat: enrich marketplace excel safely`.

### Task 8: Product Work + Scheduled ChatGPT Bridge Integration

**Files:**
- Modify: `src/stech_mcp/chatgpt_bridge/exporter.py`
- Modify: `src/stech_mcp/chatgpt_bridge/importer.py`
- Modify: `src/stech_mcp/services/handlers/enrich_technical.py`
- Modify: `tests/test_chatgpt_bridge_exporter.py`
- Modify: `tests/test_chatgpt_bridge_importer.py`
- Modify: `tests/test_external_research_handoff.py`

**Interfaces:**
- Technical bridge request carries only requested missing canonical fields.
- Result importer remains schema-restricted and never imports price/stock/cost/promotions.
- Successful external evidence must be re-evaluated through canonical promotion/readiness before product can become `LISTO`.

- [ ] **Step 1: Write failing tests** for exact requested-field export, already-resolved field suppression, idempotent import and no commercial-data path.
- [ ] **Step 2: Run focused tests** and verify RED.
- [ ] **Step 3: Implement bridge enrichment integration** without introducing Brave/OpenAI API requirements.
- [ ] **Step 4: Run all bridge + Product Work tests** and verify GREEN.
- [ ] **Step 5: Commit** `feat: connect excel gaps to scheduled research bridge`.

### Task 9: PC020 Background Operation and Observability

**Files:**
- Modify: `src/stech_mcp/background_config.py`
- Modify: `src/stech_mcp/background.py`
- Modify: `src/stech_mcp/server_authoritative.py`
- Modify: `.env.example`
- Modify: `README.md`
- Test: `tests/test_background_config.py`
- Test: `tests/test_background_runtime.py`

**Interfaces:**
- Product scanner cadence remains independently configurable.
- Local Research Bridge operational cadence defaults to 1200 seconds for the unattended PC020 setup.
- Health exposes bridge heartbeat/last success/old pending counts without exposing secrets.

- [ ] **Step 1: Write failing tests** for 20-minute bridge cadence config and health/heartbeat reporting.
- [ ] **Step 2: Run focused tests** and verify RED.
- [ ] **Step 3: Implement bounded background integration** without running Git operations from multiple concurrent threads.
- [ ] **Step 4: Document PC020 worktree layout** so the bridge stays checked out on its configured mailbox branch while the main MCP code can use the Product Intelligence branch.
- [ ] **Step 5: Run focused tests** and verify GREEN.
- [ ] **Step 6: Commit** `feat: run product intelligence bridge unattended on pc020`.

### Task 10: Full Regression and Real Excel Acceptance

**Files:**
- Add/update only tests/docs required by failures found during verification.

- [ ] **Step 1: Run full suite** `pytest -q` and require zero failures.
- [ ] **Step 2: Verify GitHub Actions** on the branch is green.
- [ ] **Step 3: On PC020 apply only required additive SQL migrations** and restart MCP/worker/bridge processes with `STECH_CHATGPT_BRIDGE_ENABLED=true` and no Brave key.
- [ ] **Step 4: Process at least one real user-provided technology Excel** and verify automatic schema/category discovery, exact PN lookup, Deltron/Product Workspace reuse, targeted research, derived GAMA, factual description and output workbook preservation.
- [ ] **Step 5: Verify negative guarantees**: no invented price/stock/cost/promotion; estimated package does not become a verified fact; no channel publication side effect.
- [ ] **Step 6: Reprocess the same workbook** and prove idempotency (no duplicate research/candidates and stable output).
- [ ] **Step 7: Present PC020 results to the user and wait for explicit merge approval.**
