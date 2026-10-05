# Product Enrichment Engine V2 Execution Index

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Coordinate the four executable plans that deliver persistent background enrichment from V8 selection/Excel intake through STECH MCP/worker into channel-neutral Product Workspace data.

**Architecture:** The implementation is split by stable subsystem boundary: persistent queue/worker, technical enrichment core, Excel Template Engine, and V8 UI/API integration. STECH_MCP DB owns background-job state; Product Workspace owns canonical product facts; V8 owns user interaction and physical Excel I/O.

**Tech Stack:** Python 3.12, FastMCP, SQL Server 2019, pyodbc, pytest, openpyxl, httpx, pypdf, Brave Search API, pywin32, SCR vanilla web UI.

**Spec:** `docs/superpowers/specs/2026-09-08-product-enrichment-engine-v2-design.md`

## Global Constraints

- `ENRICH_TECHNICAL` never modifies price or stock.
- Product Workspace is the master; Falabella, Coolbox and VTEX are peer consumers.
- V8 does not own a second V2 enrichment queue.
- Existing VTEX `product_loader_job` remains intact.
- Research targets only missing/conflicting canonical fields.
- Automatic promotion requires source-policy validation and preserves evidence.
- Background work survives MCP/UI/worker restarts through SQL leases.
- PC020 worker is a Windows Service implemented with pywin32.
- General web discovery uses Brave Search API via externally configured `STECH_BRAVE_SEARCH_API_KEY`.

## Executable Plans

- [ ] **Plan A — Persistent queue + worker**

Read and execute: `docs/superpowers/plans/2026-09-08-product-work-queue-worker-v2.md`

Exit gate: generic jobs can be created/read/retried/cancelled; worker claims atomically, survives abandoned leases, and runs as `STECHEnrichmentWorker` on PC020 without daemon threads inside MCP.

- [ ] **Plan B — Technical enrichment core**

Read and execute: `docs/superpowers/plans/2026-09-08-product-enrichment-core-v2.md`

Consumes Plan A. Exit gate: LAPTOP, PORTABLE_SPEAKER and HEADPHONES can reuse Deltron, research only missing fields, ingest HTML/PDF/search evidence, validate exact PN/source strength, promote safe facts and update Product Workspace.

- [ ] **Plan C — Excel Template Engine**

Read and execute: `docs/superpowers/plans/2026-09-08-excel-template-engine-v2.md`

Consumes Plan A and Product Technical Status from Plan B. Exit gate: Coolbox/Falabella workbook structure is recognized independently of filename, PN rows are extracted/deduped, technical missing fields are calculated, and job handoff uses the generic queue.

- [ ] **Plan D — V8 Product Enrichment Workbench**

Repository: `artosperu-bot/scr`

Branch: `feat/product-enrichment-workbench-v2`

Read and execute: `docs/superpowers/plans/2026-09-08-v8-product-enrichment-workbench-v2.md`

Consumes stable MCP contracts from A–C. Exit gate: user selects products/imports Excel, submits enrichment, closes the view, returns later to progress/results, and opens Product Workspace with Falabella/Coolbox/VTEX readiness.

## Integration Gate

- [ ] Run full MCP suite: `pytest -q` in `artosperu-bot/mcp-stech`.
- [ ] Run full SCR suite: `pytest -q` in `artosperu-bot/scr`.
- [ ] Run a controlled three-category batch and interrupt/restart the worker during an active item.
- [ ] Verify the item is reclaimed after lease expiry and the job continues.
- [ ] Verify only missing/conflicting technical fields were researched.
- [ ] Verify source URL/document/page/evidence remains auditable for promoted facts.
- [ ] Verify Product Workspace updates progressively before the whole batch completes.
- [ ] Verify Falabella, Coolbox and VTEX readiness are independent views over one canonical master.
- [ ] Snapshot price and stock before/after the controlled batch and assert equality.

No branch is merged until all applicable gates above pass.