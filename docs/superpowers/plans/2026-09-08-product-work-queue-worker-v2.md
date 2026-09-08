# Product Work Queue + Worker V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a generic persistent product-work queue and a separate Windows worker that can process long-running `ENRICH_TECHNICAL` jobs without keeping the MCP request or V8 screen open.

**Architecture:** SQL Server is the single authority for jobs/items/events/attempts. STECH MCP only creates, reads, retries and cancels jobs; `stech-enrichment-worker` claims work atomically with leases and dispatches by `work_type`. The existing VTEX `product_loader_job` flow stays unchanged.

**Tech Stack:** Python 3.12, FastMCP, SQL Server 2019, pyodbc, pytest, pywin32 on Windows.

**Spec:** `docs/superpowers/specs/2026-09-08-product-enrichment-engine-v2-design.md`

## Global Constraints

- `ENRICH_TECHNICAL` MUST NOT write price or stock.
- Product Work Queue is separate from existing `product_loader_job` / VTEX loader tables.
- Queue state survives MCP/worker/PC restart.
- Active equivalent work for the same `partnumber + work_type + context_hash` must not be duplicated.
- Worker default concurrency is exactly `1` in V2; later scaling is configuration, not a redesign.
- Worker is installed on PC020 as a Windows Service using `pywin32`; no daemon thread inside MCP is considered production execution.
- Every state transition emits an event; every execution attempt has start/end/error data.

---

### Task 1: SQL queue contract

**Files:**
- Create: `sql/006_product_work_queue_v2.sql`
- Test: `tests/test_product_work_queue_schema.py`

**Interfaces:**
- Consumes: SQL Server 2019.
- Produces: `dbo.product_work_job`, `dbo.product_work_item`, `dbo.product_work_event`, `dbo.product_work_attempt`.

- [ ] **Step 1: Write the failing schema test**

```python
from pathlib import Path

SQL = Path("sql/006_product_work_queue_v2.sql")


def test_product_work_schema_has_required_contract():
    text = SQL.read_text(encoding="utf-8").upper()
    for token in (
        "PRODUCT_WORK_JOB", "PRODUCT_WORK_ITEM", "PRODUCT_WORK_EVENT",
        "PRODUCT_WORK_ATTEMPT", "CONTEXT_HASH", "CLAIMED_BY",
        "CLAIM_EXPIRES_AT", "NEXT_ATTEMPT_AT", "FAILED_RETRYABLE",
        "ENRICH_TECHNICAL",
    ):
        assert token in text
```

- [ ] **Step 2: Run the test and verify failure**

Run: `pytest tests/test_product_work_queue_schema.py -v`

Expected: FAIL because `sql/006_product_work_queue_v2.sql` does not exist.

- [ ] **Step 3: Implement the SQL schema**

Create four tables with these minimum columns:

```sql
CREATE TABLE dbo.product_work_job (
    product_work_job_id BIGINT IDENTITY(1,1) PRIMARY KEY,
    work_type NVARCHAR(40) NOT NULL,
    source_name NVARCHAR(260) NOT NULL,
    actor_source NVARCHAR(80) NOT NULL,
    status NVARCHAR(40) NOT NULL,
    priority INT NOT NULL DEFAULT 50,
    total_items INT NOT NULL DEFAULT 0,
    completed_items INT NOT NULL DEFAULT 0,
    review_items INT NOT NULL DEFAULT 0,
    failed_items INT NOT NULL DEFAULT 0,
    created_at DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
    started_at DATETIME2(3) NULL,
    finished_at DATETIME2(3) NULL,
    updated_at DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME()
);
```

`product_work_item` must include `partnumber`, `category_code`, optional `channel_code`, `context_hash CHAR(64)`, `input_json`, `status`, `current_step`, `progress_pct`, `priority`, `attempt_count`, `max_attempts`, `next_attempt_at`, `claimed_by`, `claimed_at`, `claim_expires_at`, errors and timestamps. Add a filtered unique index that prevents duplicate active `partnumber + work_type/context_hash` through a persisted work key or an equivalent transaction-safe unique strategy. Add claim index ordered by `status, next_attempt_at, priority DESC, product_work_item_id`.

- [ ] **Step 4: Run the test and verify pass**

Run: `pytest tests/test_product_work_queue_schema.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sql/006_product_work_queue_v2.sql tests/test_product_work_queue_schema.py
git commit -m "feat: add generic product work queue schema"
```

---

### Task 2: Domain models and repository

**Files:**
- Create: `src/stech_mcp/domain/product_work_models.py`
- Create: `src/stech_mcp/db/product_work_repository.py`
- Test: `tests/test_product_work_models.py`
- Test: `tests/test_product_work_repository.py`
- Test: `tests/test_product_work_repository_transitions.py`

**Interfaces:**
- Consumes: tables from Task 1 and existing DB connection factory pattern.
- Produces:
  - `make_context_hash(work_type: str, partnumber: str, category_code: str | None, channel_code: str | None) -> str`
  - `ProductWorkRepository.create_job(...) -> dict[str, object]`
  - `ProductWorkRepository.claim_next(worker_id: str, lease_seconds: int) -> dict[str, object] | None`
  - `ProductWorkRepository.transition_item(...) -> dict[str, object]`
  - `ProductWorkRepository.schedule_retry(...) -> dict[str, object]`

- [ ] **Step 1: Write failing model tests**

```python
from stech_mcp.domain.product_work_models import make_context_hash, TERMINAL_ITEM_STATES


def test_context_hash_is_stable_and_case_normalized():
    a = make_context_hash("ENRICH_TECHNICAL", "82yu00xylm", "laptop", None)
    b = make_context_hash("ENRICH_TECHNICAL", "82YU00XYLM", "LAPTOP", None)
    assert a == b
    assert len(a) == 64


def test_terminal_states_do_not_include_retryable():
    assert "COMPLETED" in TERMINAL_ITEM_STATES
    assert "FAILED_RETRYABLE" not in TERMINAL_ITEM_STATES
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_product_work_models.py -v`

Expected: FAIL with import/module not found.

- [ ] **Step 3: Implement domain constants and hash**

Use exact work types:

```python
WORK_TYPES = {
    "ENRICH_TECHNICAL",
    "RESEARCH_IDENTITY",
    "RESEARCH_IMAGES",
    "PREPARE_CHANNEL",
    "PUBLISH_CHANNEL",
}
```

Use SHA-256 over normalized JSON containing only work type, PN, category and channel. Do not include price or stock.

- [ ] **Step 4: Write repository tests before repository code**

```python
def test_claim_prefers_high_priority(repo, seeded_jobs):
    item = repo.claim_next("worker-a", lease_seconds=120)
    assert item["priority"] == 100
    assert item["claimed_by"] == "worker-a"


def test_expired_lease_can_be_reclaimed(repo, expired_claim):
    item = repo.claim_next("worker-b", lease_seconds=120)
    assert item["item_id"] == expired_claim["item_id"]
```

Repository tests must also cover duplicate-active prevention, valid/invalid transitions, attempt history, retry backoff and job summary.

- [ ] **Step 5: Implement repository with atomic claim**

Use one transaction and SQL locking equivalent to:

```sql
;WITH next_item AS (
    SELECT TOP (1) i.product_work_item_id
    FROM dbo.product_work_item i WITH (UPDLOCK, READPAST, ROWLOCK)
    WHERE i.status IN (N'QUEUED', N'FAILED_RETRYABLE')
      AND (i.next_attempt_at IS NULL OR i.next_attempt_at <= SYSUTCDATETIME())
      AND (i.claim_expires_at IS NULL OR i.claim_expires_at <= SYSUTCDATETIME())
    ORDER BY i.priority DESC, i.product_work_item_id
)
UPDATE i
SET claimed_by = ?, claimed_at = SYSUTCDATETIME(),
    claim_expires_at = DATEADD(SECOND, ?, SYSUTCDATETIME()),
    updated_at = SYSUTCDATETIME()
OUTPUT INSERTED.*
FROM dbo.product_work_item i
JOIN next_item n ON n.product_work_item_id = i.product_work_item_id;
```

Implement explicit transition validation in Python before SQL update.

- [ ] **Step 6: Run repository tests**

Run: `pytest tests/test_product_work_models.py tests/test_product_work_repository.py tests/test_product_work_repository_transitions.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/stech_mcp/domain/product_work_models.py src/stech_mcp/db/product_work_repository.py tests/test_product_work_models.py tests/test_product_work_repository.py tests/test_product_work_repository_transitions.py
git commit -m "feat: persist and claim generic product work"
```

---

### Task 3: Fast MCP control surface

**Files:**
- Create: `src/stech_mcp/services/product_work_service.py`
- Create: `src/stech_mcp/tools/product_work.py`
- Modify: `src/stech_mcp/server.py` in the existing tool-registration section.
- Test: `tests/test_product_work_service.py`
- Test: `tests/test_server_product_work_tools.py`

**Interfaces:**
- Consumes: `ProductWorkRepository` from Task 2.
- Produces:
  - `ProductWorkService.create_job(rows, work_type, source_name, actor_source, priority) -> dict`
  - MCP tools `product_work_job_create`, `product_work_job_get`, `product_work_job_list`, `product_work_item_retry`, `product_work_item_cancel`.

- [ ] **Step 1: Write failing service test**

```python
def test_create_enrichment_job_dedupes_and_strips_commercial_fields(service):
    result = service.create_job(
        rows=[
            {"partnumber": "PN1", "price": 99, "stock": 8},
            {"partnumber": "pn1", "price": 101, "stock": 2},
        ],
        work_type="ENRICH_TECHNICAL",
        source_name="PRODUCT_WORKBENCH",
        actor_source="SCR_UI",
        priority=50,
    )
    assert result["total_items"] == 1
    item_input = result["items"][0]["input"]
    assert "price" not in item_input
    assert "stock" not in item_input
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_product_work_service.py -v`

Expected: FAIL because service is missing.

- [ ] **Step 3: Implement service**

The allowed technical input keys are exactly `row_number`, `partnumber`, `category_code`, `channel_code`, `template_code`, `requested_fields`, `source_context`. Discard `price`, `stock`, dates and marketplace commercial values for `ENRICH_TECHNICAL`.

- [ ] **Step 4: Write failing MCP tool registration test**

```python
def test_product_work_tools_are_registered(tool_names):
    required = {
        "product_work_job_create", "product_work_job_get", "product_work_job_list",
        "product_work_item_retry", "product_work_item_cancel",
    }
    assert required <= set(tool_names)
```

- [ ] **Step 5: Implement and register tools**

Tools call `ProductWorkService` and return immediately after DB operations. No tool starts a daemon thread or waits for completion.

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_product_work_service.py tests/test_server_product_work_tools.py tests/test_server_smoke.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/stech_mcp/services/product_work_service.py src/stech_mcp/tools/product_work.py src/stech_mcp/server.py tests/test_product_work_service.py tests/test_server_product_work_tools.py
git commit -m "feat: expose product work queue through MCP"
```

---

### Task 4: Independent worker and dispatcher

**Files:**
- Create: `src/stech_mcp/services/product_work_dispatcher.py`
- Create: `src/stech_mcp/worker.py`
- Test: `tests/test_product_work_dispatcher.py`
- Test: `tests/test_product_work_worker.py`

**Interfaces:**
- Consumes: `ProductWorkRepository.claim_next()` and handler callable `handler(item: dict, progress: Callable[[str, int], None]) -> dict`.
- Produces:
  - `ProductWorkDispatcher.register(work_type: str, handler: Callable) -> None`
  - `ProductWorkWorker.run_once() -> bool`
  - `ProductWorkWorker.run_forever(stop_event) -> None`

- [ ] **Step 1: Write failing worker tests**

```python
def test_worker_failure_does_not_stop_next_item(worker, repo):
    assert worker.run_once() is True  # first handler raises permanent error
    assert worker.run_once() is True  # second item still runs
    assert repo.get_item(1)["status"] == "FAILED"
    assert repo.get_item(2)["status"] == "COMPLETED"


def test_retryable_failure_gets_backoff(worker, repo):
    worker.run_once()
    item = repo.get_item(1)
    assert item["status"] == "FAILED_RETRYABLE"
    assert item["next_attempt_at"] is not None
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_product_work_dispatcher.py tests/test_product_work_worker.py -v`

Expected: FAIL.

- [ ] **Step 3: Implement dispatcher and worker**

Backoff is deterministic: `min(60 * (2 ** max(attempt_count - 1, 0)), 3600)` seconds. Renew lease before each major handler progress callback. Unknown `work_type` becomes permanent `FAILED` with code `UNSUPPORTED_WORK_TYPE`.

Until Plan B registers the real enrichment handler, register an explicit handler that returns `REVIEW_REQUIRED` with code `ENRICHMENT_HANDLER_NOT_INSTALLED`; never report false completion.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_product_work_dispatcher.py tests/test_product_work_worker.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stech_mcp/services/product_work_dispatcher.py src/stech_mcp/worker.py tests/test_product_work_dispatcher.py tests/test_product_work_worker.py
git commit -m "feat: add independent persistent product worker"
```

---

### Task 5: PC020 Windows Service deployment

**Files:**
- Modify: `pyproject.toml` project dependencies and scripts sections.
- Modify: `.env.example` worker configuration section.
- Create: `src/stech_mcp/worker_windows_service.py`
- Create: `deploy/windows/INSTALL_ENRICHMENT_WORKER.ps1`
- Create: `deploy/windows/UNINSTALL_ENRICHMENT_WORKER.ps1`
- Test: `tests/test_worker_deployment_contract.py`

**Interfaces:**
- Consumes: `stech_mcp.worker:main` from Task 4.
- Produces: console command `stech-enrichment-worker` and Windows Service name `STECHEnrichmentWorker`.

- [ ] **Step 1: Write failing deployment contract test**

```python
from pathlib import Path


def test_worker_has_windows_service_contract():
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    install = Path("deploy/windows/INSTALL_ENRICHMENT_WORKER.ps1").read_text(encoding="utf-8")
    assert 'stech-enrichment-worker = "stech_mcp.worker:main"' in pyproject
    assert "pywin32" in pyproject
    assert "STECHEnrichmentWorker" in install
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_worker_deployment_contract.py -v`

Expected: FAIL.

- [ ] **Step 3: Implement exact Windows service strategy**

Add conditional dependency:

```toml
"pywin32>=306; sys_platform == 'win32'",
```

Add script:

```toml
[project.scripts]
stech-enrichment-worker = "stech_mcp.worker:main"
```

`worker_windows_service.py` subclasses `win32serviceutil.ServiceFramework`, service name `STECHEnrichmentWorker`, and runs the same worker loop. PowerShell install script executes `python -m stech_mcp.worker_windows_service install --startup auto` then `start`; uninstall executes `stop` then `remove` and tolerates already-stopped/not-installed state.

Required env values:

```text
STECH_WORKER_ENABLED=true
STECH_WORKER_POLL_SECONDS=5
STECH_WORKER_LEASE_SECONDS=300
STECH_WORKER_MAX_ATTEMPTS=3
STECH_WORKER_CONCURRENCY=1
```

- [ ] **Step 4: Run test**

Run: `pytest tests/test_worker_deployment_contract.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .env.example src/stech_mcp/worker_windows_service.py deploy/windows/INSTALL_ENRICHMENT_WORKER.ps1 deploy/windows/UNINSTALL_ENRICHMENT_WORKER.ps1 tests/test_worker_deployment_contract.py
git commit -m "feat: install enrichment worker as Windows service"
```

---

### Task 6: Crash recovery integration test

**Files:**
- Test: `tests/test_product_work_recovery_integration.py`

**Interfaces:**
- Consumes: complete queue + worker from Tasks 1–5.
- Produces: verified restart/retry behavior contract used by later plans.

- [ ] **Step 1: Write the integration test**

```python
def test_job_survives_abandoned_claim_and_partial_failure(integration_repo, worker_factory):
    job = integration_repo.seed_job(["PN1", "PN2", "PN3"])
    abandoned = integration_repo.claim_next("dead-worker", lease_seconds=1)
    integration_repo.force_claim_expired(abandoned["item_id"])

    worker = worker_factory("replacement-worker")
    while worker.run_once():
        pass

    final = integration_repo.get_job(job["job_id"])
    assert final["status"] == "PARTIAL"
    assert final["items"][0]["attempt_count"] >= 1
    assert final["events"]
```

Use deterministic fake handlers: PN1 succeeds, PN2 fails retryable once then succeeds, PN3 fails permanently.

- [ ] **Step 2: Run focused test**

Run: `pytest tests/test_product_work_recovery_integration.py -v`

Expected: PASS.

- [ ] **Step 3: Run full MCP regression suite**

Run: `pytest -q`

Expected: PASS; existing VTEX/ProductLoader tests remain green.

- [ ] **Step 4: Commit**

```bash
git add tests/test_product_work_recovery_integration.py
git commit -m "test: verify product work crash recovery"
```

## Definition of Done

- Generic queue persists jobs independently of VTEX loader.
- MCP creates/reads/controls jobs without long-running calls.
- Worker is a separate process and Windows Service on PC020.
- Leases, retry/backoff, priority, dedupe and crash recovery are tested.
- No technical-job payload contains price or stock.
- Existing full MCP suite passes.