# Product Loader History Support — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans and test-driven-development.

**Goal:** Add one bounded, read-only MCP capability that lets V8 list demonstrable historical Product Loader jobs and their exact items so Carga de Productos can reconstruct prior Excel loads safely.

**Architecture:** Reuse the existing `product_loader_job` / `product_loader_job_item` tables and `ProductLoaderRepository`. No new queue or schema is introduced. The new tool only reads history; V8 remains the owner of load grouping/control state.

**Tech Stack:** Python, existing MCP server/tool registration, SQL Server repository, pytest.

## Task 1 — Repository list API

**Files:**
- Modify: `tests/test_product_loader_repository.py`
- Modify: `src/stech_mcp/db/product_loader_repository.py`

Add `list_jobs(limit=50)` with integer clamp `1..500`, newest first. Each row returns actual job metadata/timestamps and item list with exact persisted row number, Part Number and status.

TDD:
1. Add failing tests for ordering/limit/items.
2. Verify failure is missing `list_jobs`.
3. Implement parameterized/bounded read.
4. Run repository tests.

## Task 2 — MCP tool contract

**Files:**
- Modify: `tests/test_server_product_workbench_tools.py`
- Modify: existing Product Loader tool module/server registration used by `product_loader_start` and `product_loader_job_get`.

Expose `product_loader_job_list(limit=50)` and return a bounded list. No writes and no fabricated fields.

TDD:
1. Add failing registration/handler test.
2. Implement using existing repository dependency pattern.
3. Run server/tool smoke tests.

## Verification

```bash
pytest tests/test_product_loader_repository.py tests/test_server_product_workbench_tools.py -v
pytest tests/test_product_loader_orchestrator.py tests/test_server_smoke.py -v
python -m compileall -q src tests
```

**Commit target:** `feat: expose product loader job history`
