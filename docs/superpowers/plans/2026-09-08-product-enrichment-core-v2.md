# Product Enrichment Core V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the channel-neutral technical enrichment engine that reuses Deltron/current facts, researches only missing or conflicting fields, stores source evidence, validates exact Part Number rules, and promotes safe canonical facts into Product Workspace.

**Architecture:** Category schemas define canonical facts; Deltron/web/PDF adapters only produce candidates. `FactPromotionService` is the only path from research candidates to approved `product_enrichment`, and it reuses the existing source policy/field verification rules. The worker from Plan A calls one `ENRICH_TECHNICAL` handler per product.

**Tech Stack:** Python 3.12, SQL Server 2019, pyodbc, httpx, pypdf, Brave Search API, pytest.

**Spec:** `docs/superpowers/specs/2026-09-08-product-enrichment-engine-v2-design.md`

## Global Constraints

- `ENRICH_TECHNICAL` MUST NOT update price or stock.
- Canonical facts live in `product_enrichment`/evidence, not hardcoded marketplace columns.
- Initial supported category schemas are exactly `LAPTOP`, `PORTABLE_SPEAKER`, `HEADPHONES`.
- Variant-sensitive facts require exact Part Number for automatic promotion.
- Source priority stays A1 manufacturer exact PN, A2 official document/support exact PN, B authorized distributor exact PN, C trusted retailer exact SKU/PN, D same model/chassis only for explicitly reusable facts, E deterministic approved rule.
- HTML/PDF/search results never write directly to approved enrichment.
- Automatic general web discovery uses Brave Search API endpoint `https://api.search.brave.com/res/v1/web/search` with `X-Subscription-Token` from `STECH_BRAVE_SEARCH_API_KEY`; no key is committed.
- When the search key is absent, known URLs/documents may still be ingested, but unresolved missing fields finish `PARTIAL` with code `SEARCH_PROVIDER_NOT_CONFIGURED` rather than fabricated data.

---

### Task 1: Canonical category schema registry

**Files:**
- Create: `sql/007_product_attribute_schema_v2.sql`
- Create: `src/stech_mcp/domain/product_schema.py`
- Create: `src/stech_mcp/db/product_schema_repository.py`
- Test: `tests/test_product_schema_v2.py`
- Test: `tests/test_product_schema_repository.py`

**Interfaces:**
- Consumes: STECH_MCP database connection factory.
- Produces:
  - `ProductAttributeDefinition(field_code, value_type, unit, variant_sensitive, reuse_policy)`
  - `CategoryAttribute(category_code, field_code, requirement, ordinal)`
  - `ProductSchemaRepository.get_category_schema(category_code: str) -> list[CategoryAttribute]`

- [ ] **Step 1: Write the failing schema test**

```python
from pathlib import Path


def test_attribute_schema_sql_contains_initial_categories():
    text = Path("sql/007_product_attribute_schema_v2.sql").read_text(encoding="utf-8")
    for value in ("product_attribute_definition", "category_attribute", "LAPTOP", "PORTABLE_SPEAKER", "HEADPHONES"):
        assert value in text
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_product_schema_v2.py -v`

Expected: FAIL because SQL/module do not exist.

- [ ] **Step 3: Implement schema and Python models**

Use requirement enum exactly `REQUIRED`/`RECOMMENDED`. Seed at least these canonical field codes:

```python
LAPTOP = {"cpu_model", "ram_gb", "storage_gb", "storage_type", "screen_inches", "resolution", "wifi", "bluetooth_version", "battery_wh", "weight_kg", "dimensions_mm", "os_name"}
PORTABLE_SPEAKER = {"speaker_power_w", "bluetooth_version", "battery_runtime_hours", "battery_capacity_wh", "ip_rating", "frequency_response_hz", "weight_kg", "dimensions_mm", "box_contents"}
HEADPHONES = {"driver_size_mm", "anc", "transparency_mode", "bluetooth_version", "codec", "microphone", "battery_runtime_hours", "charging_time_hours", "impedance_ohm", "sensitivity_db", "frequency_response_hz", "weight_g"}
```

Mark CPU/RAM/storage/OS/color/battery-variant facts as variant-sensitive; generic dimensions/weight reuse is allowed only when schema policy explicitly says `SAME_CHASSIS_ALLOWED`.

- [ ] **Step 4: Write repository test and implement repository**

```python
def test_repository_returns_required_fields_in_ordinal_order(repo):
    schema = repo.get_category_schema("PORTABLE_SPEAKER")
    required = [x.field_code for x in schema if x.requirement == "REQUIRED"]
    assert required
    assert schema == sorted(schema, key=lambda x: x.ordinal)
```

Follow existing repository connection/close patterns.

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_product_schema_v2.py tests/test_product_schema_repository.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add sql/007_product_attribute_schema_v2.sql src/stech_mcp/domain/product_schema.py src/stech_mcp/db/product_schema_repository.py tests/test_product_schema_v2.py tests/test_product_schema_repository.py
git commit -m "feat: add canonical technical category schemas"
```

---

### Task 2: Technical status and missing-field analyzer

**Files:**
- Create: `src/stech_mcp/services/product_technical_status.py`
- Create: `src/stech_mcp/tools/product_schema.py`
- Modify: `src/stech_mcp/server.py` in existing tool-registration section.
- Test: `tests/test_product_technical_status.py`
- Test: `tests/test_server_product_schema_tools.py`

**Interfaces:**
- Consumes: `ProductRepository.get_by_partnumber`, `EnrichmentRepository.get_approved`, Task 1 schema repository.
- Produces:
  - `ProductTechnicalStatusService.get(partnumber: str) -> dict`
  - MCP `product_schema_get(category)` and `product_technical_status(partnumber)`.

- [ ] **Step 1: Write failing status test**

```python
def test_status_returns_only_missing_technical_fields(service):
    result = service.get("PN1")
    assert result["category_code"] == "PORTABLE_SPEAKER"
    assert result["known_fields"]["bluetooth_version"] == "5.4"
    assert "speaker_power_w" in result["missing_required"]
    assert "price" not in result["missing_required"]
    assert "stock" not in result["missing_required"]
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_product_technical_status.py -v`

Expected: FAIL.

- [ ] **Step 3: Implement status calculation**

Return exact keys:

```python
{
    "partnumber": str,
    "category_code": str,
    "known_fields": dict[str, object],
    "missing_required": list[str],
    "missing_recommended": list[str],
    "conflicts": list[dict],
    "completion_pct": int,
}
```

Existing approved facts override raw Deltron values only after source policy; raw source data remains available for candidate generation in Task 3.

- [ ] **Step 4: Register MCP tools and test registration**

```python
def test_schema_tools_registered(tool_names):
    assert {"product_schema_get", "product_technical_status"} <= set(tool_names)
```

- [ ] **Step 5: Run tests and commit**

```bash
pytest tests/test_product_technical_status.py tests/test_server_product_schema_tools.py tests/test_server_smoke.py -v
git add src/stech_mcp/services/product_technical_status.py src/stech_mcp/tools/product_schema.py src/stech_mcp/server.py tests/test_product_technical_status.py tests/test_server_product_schema_tools.py
git commit -m "feat: detect missing canonical technical fields"
```

---

### Task 3: Deltron canonical fact adapter

**Files:**
- Create: `src/stech_mcp/services/deltron_fact_adapter.py`
- Create: `src/stech_mcp/services/fact_normalizers.py`
- Test: `tests/test_deltron_fact_adapter.py`
- Test: `tests/test_fact_normalizers.py`

**Interfaces:**
- Consumes: product V8 `atributos_json` / `especificaciones` already exposed by `ProductRepository`.
- Produces `list[Evidence]`/candidate dicts with `field_code`, `raw_value`, `normalized_value`, `source_type="AUTHORIZED_DISTRIBUTOR"`, `source_name="DELTRON"`, `source_partnumber`.

- [ ] **Step 1: Write failing normalizer tests**

```python
def test_normalizes_common_units():
    assert normalize_weight("1.65 kg") == {"value": 1.65, "unit": "kg"}
    assert normalize_bluetooth("Bluetooth 5.4") == "5.4"
    assert normalize_ip_rating("IP67 waterproof") == "IP67"
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_fact_normalizers.py -v`

Expected: FAIL.

- [ ] **Step 3: Implement deterministic normalizers**

Implement exact helpers for weight, dimensions, power, capacity, duration, Bluetooth, IP rating, frequency, RAM/storage and resolution. Return `None` when ambiguous instead of guessing.

- [ ] **Step 4: Write failing adapter test**

```python
def test_adapter_excludes_commercial_fields(adapter):
    candidates = adapter.adapt({
        "partnumber": "PN1",
        "precio": "99.00",
        "stock": 12,
        "atributos_json": {"especificaciones": {"Bluetooth": "5.4", "Potencia": "30 W"}},
    }, category_code="PORTABLE_SPEAKER")
    fields = {c["field_code"] for c in candidates}
    assert fields == {"bluetooth_version", "speaker_power_w"}
```

- [ ] **Step 5: Implement declarative alias mapping**

Store aliases by field code, not marketplace, e.g. `{"bluetooth_version": ("bluetooth", "versión bluetooth", "version bluetooth")}`. Do not import `coolbox_preview.py`.

- [ ] **Step 6: Run tests and commit**

```bash
pytest tests/test_fact_normalizers.py tests/test_deltron_fact_adapter.py -v
git add src/stech_mcp/services/fact_normalizers.py src/stech_mcp/services/deltron_fact_adapter.py tests/test_fact_normalizers.py tests/test_deltron_fact_adapter.py
git commit -m "feat: normalize Deltron specs into canonical candidates"
```

---

### Task 4: Persistent documents and candidate evidence

**Files:**
- Create: `sql/008_product_research_evidence_v2.sql`
- Create: `src/stech_mcp/db/source_document_repository.py`
- Create: `src/stech_mcp/db/fact_candidate_repository.py`
- Test: `tests/test_source_document_repository.py`
- Test: `tests/test_fact_candidate_repository.py`

**Interfaces:**
- Consumes: DB connection factory.
- Produces:
  - `SourceDocumentRepository.upsert_by_hash(...) -> dict`
  - `SourceDocumentRepository.add_match(document_id, partnumber, match_type, pages, confidence) -> None`
  - `FactCandidateRepository.add(...) -> dict`
  - `FactCandidateRepository.list_for_product(partnumber) -> list[dict]`.

- [ ] **Step 1: Write failing SQL/repository tests**

```python
def test_same_sha_reuses_document(repo):
    first = repo.upsert_by_hash(sha256="abc", url="https://example/a.pdf", document_type="PDF")
    second = repo.upsert_by_hash(sha256="abc", url="https://example/copy.pdf", document_type="PDF")
    assert first["source_document_id"] == second["source_document_id"]


def test_candidates_keep_conflicting_evidence(candidate_repo):
    candidate_repo.add(partnumber="PN1", field_code="bluetooth_version", normalized_value="5.4", confidence_rank="A1")
    candidate_repo.add(partnumber="PN1", field_code="bluetooth_version", normalized_value="5.3", confidence_rank="B")
    assert len(candidate_repo.list_for_product("PN1")) == 2
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_source_document_repository.py tests/test_fact_candidate_repository.py -v`

Expected: FAIL.

- [ ] **Step 3: Implement SQL tables**

Create `source_document`, `source_document_match`, `product_fact_candidate`. Candidate states exactly `PENDING`, `VERIFIED`, `REJECTED`, `CONFLICT`, `PROMOTED`. Store source URL, source PN, evidence text, page number, raw/normalized value, unit, source type, confidence rank and timestamps.

- [ ] **Step 4: Implement repositories and run tests**

Run: `pytest tests/test_source_document_repository.py tests/test_fact_candidate_repository.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sql/008_product_research_evidence_v2.sql src/stech_mcp/db/source_document_repository.py src/stech_mcp/db/fact_candidate_repository.py tests/test_source_document_repository.py tests/test_fact_candidate_repository.py
git commit -m "feat: persist reusable research evidence"
```

---

### Task 5: HTML/PDF ingestion and Brave web discovery

**Files:**
- Modify: `pyproject.toml` dependency list.
- Modify: `.env.example` search configuration section.
- Create: `src/stech_mcp/http/source_client.py`
- Create: `src/stech_mcp/services/source_document_service.py`
- Create: `src/stech_mcp/services/research/search_provider.py`
- Create: `src/stech_mcp/services/research/brave_search_provider.py`
- Create: `src/stech_mcp/services/research/research_planner.py`
- Test: `tests/test_source_document_service.py`
- Test: `tests/test_brave_search_provider.py`
- Test: `tests/test_research_planner.py`

**Interfaces:**
- Consumes: `httpx`, `pypdf`, Task 4 repositories.
- Produces:
  - `SourceDocumentService.ingest(url: str, partnumber: str, source_type: str) -> dict`
  - `SearchProvider.search(query: str, domains: tuple[str, ...] = (), limit: int = 5) -> list[SearchResult]`
  - `ResearchPlanner.plan(partnumber, brand, category_code, pending_fields) -> list[ResearchQuery]`.

- [ ] **Step 1: Add failing dependency/config test**

```python
from pathlib import Path


def test_research_dependencies_and_env_are_declared():
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    env = Path(".env.example").read_text(encoding="utf-8")
    assert "httpx" in pyproject
    assert "pypdf" in pyproject
    assert "STECH_BRAVE_SEARCH_API_KEY" in env
```

- [ ] **Step 2: Add exact dependencies/config**

Add `httpx>=0.28,<1` and `pypdf>=5,<7`. Add `STECH_BRAVE_SEARCH_API_KEY=` and `STECH_SEARCH_COUNTRY=PE`.

- [ ] **Step 3: Write failing source-document tests**

```python
def test_pdf_is_extracted_per_page_and_reused(service, fake_http):
    first = service.ingest("https://brand.example/spec.pdf", "PN1", "OFFICIAL_DOCUMENT")
    second = service.ingest("https://brand.example/spec.pdf", "PN1", "OFFICIAL_DOCUMENT")
    assert first["sha256"] == second["sha256"]
    assert first["document_id"] == second["document_id"]
    assert first["pages"][0]["text"]
```

Implement max response size 25 MB, connect/read timeout 15 seconds, redirects enabled, only `http`/`https`, and HTML text extraction without executing scripts.

- [ ] **Step 4: Write failing Brave provider test**

```python
def test_brave_provider_sends_subscription_header(provider, http_mock):
    provider.search('"PN1" specifications', domains=("manufacturer.example",), limit=5)
    request = http_mock.last_request
    assert request.url.path == "/res/v1/web/search"
    assert request.headers["X-Subscription-Token"] == "secret"
    assert request.url.params["country"] == "PE"
```

Use exact endpoint `https://api.search.brave.com/res/v1/web/search`, query params `q`, `count`, `country`, `search_lang`, and header `X-Subscription-Token`.

- [ ] **Step 5: Write planner test and implement directed queries**

```python
def test_planner_only_queries_pending_fields(planner):
    plan = planner.plan("PN1", "JBL", "PORTABLE_SPEAKER", ["ip_rating", "speaker_power_w"])
    joined = " ".join(q.query for q in plan)
    assert "PN1" in joined
    assert "IP" in joined or "ip_rating" in joined
    assert "RAM" not in joined
```

Generate at most 2 search queries per pending field and inspect at most 3 strong candidate sources per field. Search official manufacturer domains first when known; then official documents; then authorized distributors.

- [ ] **Step 6: Run tests and commit**

```bash
pytest tests/test_source_document_service.py tests/test_brave_search_provider.py tests/test_research_planner.py -v
git add pyproject.toml .env.example src/stech_mcp/http/source_client.py src/stech_mcp/services/source_document_service.py src/stech_mcp/services/research tests/test_source_document_service.py tests/test_brave_search_provider.py tests/test_research_planner.py
git commit -m "feat: discover and ingest official product sources"
```

---

### Task 6: Candidate extraction, exact-PN validation, and promotion

**Files:**
- Create: `src/stech_mcp/services/fact_extractor.py`
- Create: `src/stech_mcp/services/fact_promotion.py`
- Modify: `src/stech_mcp/services/product_field_verification.py` source aliases only.
- Modify: `src/stech_mcp/domain/source_policy.py` variant field registry only.
- Test: `tests/test_fact_extractor.py`
- Test: `tests/test_fact_promotion.py`
- Modify: `tests/test_product_field_verification.py`

**Interfaces:**
- Consumes: ingested page text and candidate repository.
- Produces:
  - `FactExtractor.extract(document, target_fields, partnumber) -> list[dict]`
  - `FactPromotionService.evaluate_and_promote(partnumber, candidates) -> dict`.

- [ ] **Step 1: Write failing extractor test**

```python
def test_extractor_returns_evidence_not_approved_fact(extractor):
    items = extractor.extract(
        {"url": "https://brand/spec", "pages": [{"page": 1, "text": "PN1 Bluetooth 5.4, IP67, 30 W"}]},
        ["bluetooth_version", "ip_rating", "speaker_power_w"],
        "PN1",
    )
    assert {x["normalized_value"] for x in items} >= {"5.4", "IP67"}
    assert all(x["status"] == "PENDING" for x in items)
    assert all(x["evidence_text"] for x in items)
```

- [ ] **Step 2: Implement deterministic extractor**

Reuse Task 3 normalizers. If a target field cannot be extracted with a deterministic pattern, leave it missing; do not infer from nearby marketing language.

- [ ] **Step 3: Write failing promotion policy tests**

```python
def test_exact_manufacturer_beats_authorized_distributor(promotion):
    result = promotion.evaluate_and_promote("PN1", [
        candidate("bluetooth_version", "5.3", rank="B", source_partnumber="PN1"),
        candidate("bluetooth_version", "5.4", rank="A1", source_partnumber="PN1"),
    ])
    assert result["promoted"]["bluetooth_version"] == "5.4"


def test_variant_sensitive_other_pn_is_rejected(promotion):
    result = promotion.evaluate_and_promote("PN1", [
        candidate("ram_gb", 16, rank="A1", source_partnumber="PN2"),
    ])
    assert "ram_gb" not in result["promoted"]
    assert result["rejected"][0]["reason"] == "SOURCE_PARTNUMBER_MISMATCH"
```

Also test approved MANUAL/A1 cannot be overwritten by B/C and unresolved equal-strength conflict becomes `REVIEW_REQUIRED`.

- [ ] **Step 4: Implement promotion through existing verification/repository path**

Do not duplicate source ranking. Convert candidates into the existing verification evidence contract, call verification, then `EnrichmentRepository.upsert()` only for verified winners. Mark candidate rows `PROMOTED`, `REJECTED` or `CONFLICT`.

- [ ] **Step 5: Run tests and commit**

```bash
pytest tests/test_fact_extractor.py tests/test_fact_promotion.py tests/test_product_field_verification.py -v
git add src/stech_mcp/services/fact_extractor.py src/stech_mcp/services/fact_promotion.py src/stech_mcp/services/product_field_verification.py src/stech_mcp/domain/source_policy.py tests/test_fact_extractor.py tests/test_fact_promotion.py tests/test_product_field_verification.py
git commit -m "feat: validate and promote evidence-backed product facts"
```

---

### Task 7: Product enrichment orchestrator and worker handler

**Files:**
- Create: `src/stech_mcp/services/product_enrichment_engine.py`
- Create: `src/stech_mcp/services/handlers/__init__.py`
- Create: `src/stech_mcp/services/handlers/enrich_technical.py`
- Modify: `src/stech_mcp/services/product_work_dispatcher.py` handler registration.
- Test: `tests/test_product_enrichment_engine.py`
- Test: `tests/test_enrich_technical_handler.py`

**Interfaces:**
- Consumes: Tasks 1–6 plus Product Work Queue Plan.
- Produces:
  - `ProductEnrichmentEngine.enrich(partnumber: str, category_code: str | None, requested_fields: list[str] | None, progress) -> dict`
  - `EnrichTechnicalHandler.__call__(item: dict, progress) -> dict`.

- [ ] **Step 1: Write failing orchestrator tests**

```python
def test_complete_product_skips_web_search(engine, search_provider):
    result = engine.enrich("PN-COMPLETE", "LAPTOP", None, lambda *_: None)
    assert result["state"] == "COMPLETED"
    search_provider.search.assert_not_called()


def test_partial_product_searches_only_missing_fields(engine, planner):
    result = engine.enrich("PN-PARTIAL", "PORTABLE_SPEAKER", None, lambda *_: None)
    assert set(planner.last_pending_fields) == {"ip_rating", "speaker_power_w"}
    assert set(result["remaining_fields"]) <= {"ip_rating", "speaker_power_w"}
```

- [ ] **Step 2: Implement pipeline in exact order**

```text
LOAD_SOURCE_DATA
→ adapt Deltron candidates
→ validate/promote safe existing candidates
→ ANALYZE_MISSING_FIELDS
→ if none: rebuild/readiness and complete
→ RESEARCH missing/conflicts only
→ ingest HTML/PDF
→ extract candidates
→ VALIDATE/PROMOTE
→ recalculate missing/conflicts
→ REBUILD_PRODUCT_MASTER
```

Return exact keys `state`, `before`, `after`, `promoted_fields`, `remaining_fields`, `conflicts`, `sources_consulted`, `error_code`.

- [ ] **Step 3: Write handler state mapping test**

```python
def test_handler_maps_engine_review_to_queue_review(handler, engine):
    engine.enrich.return_value = {"state": "REVIEW_REQUIRED", "conflicts": [{"field_code": "battery_wh"}]}
    result = handler({"partnumber": "PN1", "input": {"category_code": "LAPTOP"}}, lambda *_: None)
    assert result["status"] == "REVIEW_REQUIRED"
```

Map temporary HTTP/search failures to `FAILED_RETRYABLE`; permanent invalid PN to `NO_DATA_FOUND` or `FAILED`; conflicts to `REVIEW_REQUIRED`; incomplete no-source results to `PARTIAL`.

- [ ] **Step 4: Register handler and run tests**

Run: `pytest tests/test_product_enrichment_engine.py tests/test_enrich_technical_handler.py tests/test_product_work_worker.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stech_mcp/services/product_enrichment_engine.py src/stech_mcp/services/handlers src/stech_mcp/services/product_work_dispatcher.py tests/test_product_enrichment_engine.py tests/test_enrich_technical_handler.py
git commit -m "feat: execute technical enrichment from product worker"
```

---

### Task 8: Multichannel readiness and MCP audit tools

**Files:**
- Modify: `src/stech_mcp/services/product_readiness.py` channel readiness calculation.
- Modify: `src/stech_mcp/services/marketplace_preview.py` generic channel contract.
- Create: `src/stech_mcp/tools/product_research.py`
- Modify: `src/stech_mcp/server.py` tool registration.
- Test: `tests/test_multichannel_readiness_v2.py`
- Test: `tests/test_server_product_research_tools.py`
- Test: `tests/test_product_enrichment_v2_integration.py`

**Interfaces:**
- Consumes: approved canonical facts and marketplace field requirements.
- Produces MCP tools `product_technical_missing_list`, `product_research_plan`, `product_source_ingest`, `product_fact_candidates`, `product_fact_promote`, `product_fact_promote_batch` plus readiness keyed by channel.

- [ ] **Step 1: Write failing readiness test**

```python
def test_same_master_has_independent_channel_readiness(service):
    result = service.get("PN1")
    assert set(result["channels"]) >= {"FALABELLA", "COOLBOX", "VTEX"}
    assert result["channels"]["FALABELLA"]["completion_pct"] != result["channels"]["COOLBOX"]["completion_pct"]
```

- [ ] **Step 2: Implement channel-neutral readiness**

Readiness may differ because templates require different fields, but no channel writes back a different canonical fact.

- [ ] **Step 3: Write MCP audit tool registration test**

```python
def test_research_audit_tools_registered(tool_names):
    required = {"product_technical_missing_list", "product_research_plan", "product_source_ingest", "product_fact_candidates", "product_fact_promote"}
    assert required <= set(tool_names)
```

Promotion tools must call `FactPromotionService`, never direct repository writes.

- [ ] **Step 4: Write final three-category integration test**

Use deterministic fake HTTP/search fixtures for LAPTOP, PORTABLE_SPEAKER and HEADPHONES. Assert only pending fields researched, documents reused by SHA, exact PN enforced, conflicts preserved, Product Workspace updated and before/after price/stock snapshots equal.

- [ ] **Step 5: Run focused and full suites**

```bash
pytest tests/test_multichannel_readiness_v2.py tests/test_server_product_research_tools.py tests/test_product_enrichment_v2_integration.py -v
pytest -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/stech_mcp/services/product_readiness.py src/stech_mcp/services/marketplace_preview.py src/stech_mcp/tools/product_research.py src/stech_mcp/server.py tests/test_multichannel_readiness_v2.py tests/test_server_product_research_tools.py tests/test_product_enrichment_v2_integration.py
git commit -m "feat: complete multichannel technical enrichment core"
```

## Definition of Done

- Product schemas are channel-neutral.
- Deltron, HTML, PDF and search produce candidates/evidence only.
- Brave discovery is configured externally and exact-PN/source policy is enforced.
- Only missing/conflicting fields are researched.
- Documents are cached/reused by hash.
- Facts promote through one verification path.
- Worker processes `ENRICH_TECHNICAL` and Product Workspace updates progressively.
- Falabella/Coolbox/VTEX readiness is independent.
- Price and stock are unchanged.
- Full MCP test suite passes.