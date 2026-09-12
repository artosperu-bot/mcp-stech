# STECH ChatGPT Research Bridge V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir que Product Work entregue investigación externa a una tarea programada de ChatGPT mediante un buzón GitHub durable, sin API keys obligatorias y sin permitir cambios comerciales o publicación automática.

**Architecture:** Product Work conserva la fuente de verdad y agrega el estado no terminal `WAITING_EXTERNAL_RESEARCH`. Un proceso local `stech-chatgpt-bridge` exporta esos items como JSON append-only, sincroniza el buzón GitHub, valida resultados creados por ChatGPT e importa únicamente evidencia/candidatos a los repositorios existentes. Los resultados se vuelven `REVIEW_REQUIRED`, `COMPLETED`, `NO_DATA_FOUND` o retry solo después de una investigación externa real.

**Tech Stack:** Python 3.12, Pydantic 2, SQL Server 2019/pyodbc, git CLI, Product Work V2, GitHub Actions/pytest.

**Spec:** `docs/superpowers/specs/2026-09-11-chatgpt-research-bridge-v1-design.md`

## Global Constraints

- No OpenAI API key requerida.
- `STECH_BRAVE_SEARCH_API_KEY` permanece opcional y puede estar vacío.
- No modificar precio, stock, costo, promociones, publicación, categoría comercial ni estado VTEX.
- Imágenes externas se importan solo como candidatos; nunca se publican automáticamente.
- Identidad reutiliza validación GTIN/checksum y reglas existentes de fuente fuerte.
- Investigación técnica solo acepta campos del esquema técnico resuelto.
- Buzón GitHub append-only: `requests/`, `results/`, `receipts/`.
- Máximo 10 solicitudes exportadas por ciclo por defecto.
- Ningún merge antes de CI verde y prueba manual satisfactoria en PC020.

---

### Task 1: External research handoff state

**Files:**
- Modify: `src/stech_mcp/domain/product_work_models.py`
- Modify: `src/stech_mcp/db/product_work_repository.py`
- Modify: `src/stech_mcp/worker.py`
- Modify: `src/stech_mcp/services/handlers/research_images.py`
- Modify: `src/stech_mcp/services/handlers/enrich_technical.py`
- Modify: `src/stech_mcp/services/research/brave_image_search_provider.py`
- Create: `sql/012_chatgpt_research_bridge_v1.sql`
- Modify tests: `tests/test_product_work_models.py`, `tests/test_product_work_worker.py`, `tests/test_research_images_handler.py`, `tests/test_enrich_technical_handler.py`, `tests/test_brave_image_search_provider.py`

**Interfaces:**
- Produces item state `WAITING_EXTERNAL_RESEARCH`.
- Handler result uses `status="WAITING_EXTERNAL_RESEARCH"`, `error_code="EXTERNAL_RESEARCH_REQUIRED"`.
- Worker treats the state as a valid nonterminal handoff and releases the claim.

- [ ] **Step 1: Write failing tests** proving `WAITING_EXTERNAL_RESEARCH` is valid, nonterminal, accepts transitions from research stages, releases worker claim, and is returned when web search is unavailable and bridge mode is enabled.
- [ ] **Step 2: Run the new tests** through CI and verify they fail against the current implementation.
- [ ] **Step 3: Add SQL migration** that safely replaces the item status CHECK constraint and active-work index so waiting items remain active/deduplicated.
- [ ] **Step 4: Implement the state contract and repository claim-release behavior.** `transition_item()` must clear `claimed_by`, `claimed_at`, `claim_expires_at` for terminal states and for `WAITING_EXTERNAL_RESEARCH`, without setting `completed_at` for the waiting state.
- [ ] **Step 5: Make missing image search configuration explicit.** `BraveImageSearchProvider.search()` raises `SearchProviderNotConfigured` instead of returning `[]` when no key exists.
- [ ] **Step 6: Map provider-unavailable outcomes to external handoff only when `STECH_CHATGPT_BRIDGE_ENABLED=true`.** With bridge disabled, preserve current `PARTIAL/NO_DATA_FOUND` behavior for backward compatibility.
- [ ] **Step 7: Run focused tests and full CI.**

### Task 2: Strict bridge contracts and configuration

**Files:**
- Create: `src/stech_mcp/chatgpt_bridge/__init__.py`
- Create: `src/stech_mcp/chatgpt_bridge/contracts.py`
- Create: `src/stech_mcp/chatgpt_bridge/config.py`
- Create: `tests/test_chatgpt_bridge_contracts.py`
- Create: `tests/test_chatgpt_bridge_config.py`
- Modify: `.env.example`

**Interfaces:**
- `ResearchRequestV1` and `ResearchResultV1` Pydantic models.
- `BridgeConfig.from_settings()/from_env()` supplies repo path, branch, limits, poll interval and enabled flag.
- Result contract rejects unknown top-level commercial fields and invalid work type/PN/request id combinations before import.

- [ ] **Step 1: Write failing contract tests** for valid image request/result, prohibited commercial fields (`price`, `stock`, `cost`, `promotion`, `publication`, `category`, `vtex_state`), invalid URLs, excessive candidates, unsupported statuses and malformed IDs.
- [ ] **Step 2: Implement Pydantic contracts** with `extra="forbid"`, bounded list sizes, normalized PN/work type and explicit result status enum.
- [ ] **Step 3: Write failing config tests** for safe defaults and positive bounded limits.
- [ ] **Step 4: Implement bridge configuration and document `.env.example`.** No secret/API-key variable is added.
- [ ] **Step 5: Run focused tests.**

### Task 3: Durable mailbox and waiting-item export

**Files:**
- Create: `src/stech_mcp/chatgpt_bridge/mailbox.py`
- Create: `src/stech_mcp/chatgpt_bridge/exporter.py`
- Modify: `src/stech_mcp/db/product_work_query_repository.py`
- Create: `tests/test_chatgpt_bridge_mailbox.py`
- Create: `tests/test_chatgpt_bridge_exporter.py`

**Interfaces:**
- `ProductWorkQueryRepository.list_waiting_external(limit: int) -> list[dict]`.
- Deterministic request id: `rw_<item_id>_<context_hash_prefix>` so restart/re-export does not create duplicates.
- `Mailbox.write_request()` and `write_receipt()` are create-once/atomic locally; existing identical file is reused, conflicting content raises an error.

- [ ] **Step 1: Write failing repository/export tests** for listing only waiting items, max limit, dedupe by item, and no export of terminal/running work.
- [ ] **Step 2: Implement `list_waiting_external`** including decoded `input_json`.
- [ ] **Step 3: Implement request builder** by enriching the Product Work item with product brand/model from the product repository but never commercial fields.
- [ ] **Step 4: Implement filesystem mailbox** under `research_bridge/requests|results|receipts` with UTF-8 JSON, stable formatting and create-once semantics.
- [ ] **Step 5: Run focused tests.**

### Task 4: Idempotent result import and validation

**Files:**
- Create: `src/stech_mcp/chatgpt_bridge/importer.py`
- Modify: `src/stech_mcp/db/fact_candidate_repository.py`
- Create: `tests/test_chatgpt_bridge_importer.py`
- Modify: `tests/test_fact_candidate_repository.py`

**Interfaces:**
- `BridgeResultImporter.import_result(request, result) -> dict`.
- Image candidates use existing `ProductImageCandidateRepository.add_candidate()` idempotency `(partnumber, source_url)`.
- Fact candidates become idempotent by stable evidence tuple `(partnumber, field_code, normalized_value_json, source_url, source_partnumber)`.

- [ ] **Step 1: Write failing tests** for request-id/PN/work-type mismatch, duplicate import, prohibited technical field, invalid GTIN, image evidence import, real `NO_VERIFIED_EVIDENCE`, conflict and temporary error.
- [ ] **Step 2: Add idempotency to fact candidates** without collapsing genuine conflicting values.
- [ ] **Step 3: Implement image import.** Add candidates with `source_type="CHATGPT_WEB_IMAGE"`, evidence containing request id/source page, exact PN policy when proven, otherwise manual review.
- [ ] **Step 4: Implement identity import.** Revalidate GTIN/checksum and convert result rows to fact candidates; invoke existing promotion service only when its existing rules permit it.
- [ ] **Step 5: Implement technical import.** Resolve category schema and reject fields outside it; add evidence candidates and use existing promotion rules.
- [ ] **Step 6: Transition Product Work after import.** Evidence found -> `REVIEW_REQUIRED` unless existing promotion proves `COMPLETED`; verified no evidence -> `NO_DATA_FOUND`; conflict -> `REVIEW_REQUIRED`; temporary error -> `FAILED_RETRYABLE` with delay.
- [ ] **Step 7: Write receipt only after successful import.** Re-running after a crash must not duplicate evidence.
- [ ] **Step 8: Run focused tests.**

### Task 5: Git transport and executable runner

**Files:**
- Create: `src/stech_mcp/chatgpt_bridge/git_transport.py`
- Create: `src/stech_mcp/chatgpt_bridge/runner.py`
- Create: `tests/test_chatgpt_bridge_git_transport.py`
- Create: `tests/test_chatgpt_bridge_runner.py`
- Modify: `pyproject.toml`
- Modify: `README.md`

**Interfaces:**
- CLI executable: `stech-chatgpt-bridge`.
- Git transport uses the existing local repository authentication only; no token is stored in bridge config.
- `run_once()` order: pull -> import pending results -> export waiting requests -> commit/push mailbox changes.

- [ ] **Step 1: Write failing tests** mocking `subprocess.run` for pull/add/commit/push, no-change commit behavior, conflict/error behavior and no conversion of Git failure into `NO_DATA_FOUND`.
- [ ] **Step 2: Implement safe Git transport** with argument arrays (no shell interpolation), timeout, branch verification and useful sanitized errors.
- [ ] **Step 3: Implement runner cycle and loop.** Disabled config exits cleanly; `--once` executes a single cycle for local testing.
- [ ] **Step 4: Register `stech-chatgpt-bridge` in `pyproject.toml` and document startup commands.
- [ ] **Step 5: Run focused tests and full suite.**

### Task 6: Scheduled ChatGPT mailbox worker, CI and PC020 acceptance

**Files:**
- GitHub: draft PR `feat/chatgpt-research-bridge-v1` -> `feat/selected-identity-research`
- Runtime mailbox: `research_bridge/requests`, `research_bridge/results`, `research_bridge/receipts`

**Interfaces:**
- Scheduled ChatGPT task runs hourly, processes at most 10 unresolved requests, researches public web, writes only matching result JSON files, and does not edit source code.

- [ ] **Step 1: Open/maintain draft PR** so every implementation commit receives GitHub Actions CI.
- [ ] **Step 2: Verify complete pytest suite green in CI.** Do not call the work complete if the run is red.
- [ ] **Step 3: Create scheduled ChatGPT task** with the exact mailbox-only prompt and hourly condition watch.
- [ ] **Step 4: Prepare PC020 commands:** pull branch, install editable package, apply `sql/012_chatgpt_research_bridge_v1.sql`, enable bridge, restart MCP/worker, start bridge with `--once` first.
- [ ] **Step 5: Retry one real previous image `NO_DATA_FOUND` item.** Expected: `WAITING_EXTERNAL_RESEARCH` -> request JSON -> ChatGPT result -> candidate import -> `REVIEW_REQUIRED` in Product Workspace.
- [ ] **Step 6: Verify restart/idempotency** by running bridge twice and confirming no duplicate image/fact candidates or second receipt.
- [ ] **Step 7: Keep PR draft/unmerged until the user confirms PC020 acceptance.**

## Self-review

- Spec coverage: request/result contracts, three work types, safety, append-only mailbox, recovery, idempotency, scheduled task, first image E2E and no-merge rule are all mapped above.
- Placeholder scan: no TBD/TODO steps are used.
- Type consistency: `WAITING_EXTERNAL_RESEARCH`, `ResearchRequestV1`, `ResearchResultV1`, `BridgeResultImporter`, `Mailbox` and `stech-chatgpt-bridge` are the canonical names used throughout the plan.
