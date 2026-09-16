# Identity Batch + VTEX Progress Implementation Plan

**Goal:** Implement Rule B identity promotion, persistent per-item results, and serialized VTEX EAN synchronization while preserving parallel research.

**Base:** `feat/selected-identity-research`
**Work branch:** `feat/identity-batch-vtex-progress-v1`

## Task 1 — Rule B consensus (TDD)

- [ ] Add failing tests in `tests/test_product_identity_research.py` / focused new test file:
  - manufacturer exact-PN strong evidence promotes;
  - two independent strong sources, at least one authorized distributor, same canonical GTIN promote;
  - retailer-only evidence does not promote;
  - two retailers do not promote;
  - conflicting strong codes require review;
  - invalid checksum / PN mismatch cannot promote.
- [ ] Add identity-specific consensus evaluator (prefer a focused `services/identity_consensus.py` over changing generic promotion semantics).
- [ ] Make identity research retain candidate evidence needed for decision while passing only consensus-qualified winner(s) into `FactPromotionService`.
- [ ] Keep retailer/marketplace-only result non-promoted.
- [ ] Run focused tests, then related identity tests.

## Task 2 — Persistent result_json (TDD)

- [ ] Add migration `sql/013_product_work_result_json.sql` that idempotently adds nullable `result_json NVARCHAR(MAX)` to `dbo.product_work_item`.
- [ ] Add schema test proving migration is additive/idempotent.
- [ ] Extend repository terminal transition to accept optional structured result and serialize it.
- [ ] Extend `get_job()` to select/decode `result_json` as item `result`.
- [ ] Add repository/service tests for round-trip result data and legacy NULL rows.

## Task 3 — Rich identity handler result (TDD)

- [ ] Extend identity handler tests so terminal output includes a non-secret structured result:
  - identity decision/state;
  - verified/promoted fields;
  - evidence summary;
  - VTEX state.
- [ ] Change handler to return `result` alongside `status/current_step`.
- [ ] Change worker to pass handler `result` into terminal repository transition.
- [ ] Verify other handler types remain compatible when no result payload is supplied.

## Task 4 — Serialize VTEX EAN sync only (TDD)

- [ ] Add concurrency test with two identity handler calls and a blocking fake VTEX service; assert max simultaneous `sync()` calls is 1 while research can complete independently.
- [ ] Add a process-wide EAN sync lock around the VTEX EAN critical section only.
- [ ] Preserve retry/permanent-state mapping and create-only/readback semantics.
- [ ] Run existing `test_vtex_ean_sync.py` and identity post-action tests.

## Task 5 — Result semantics

- [ ] Ensure `PARTIAL` candidate/no-result never calls VTEX.
- [ ] Ensure `REVIEW_REQUIRED` conflict never calls VTEX.
- [ ] Ensure `COMPLETED` verified result records `VTEX_EAN_SYNCED`, `VTEX_EAN_ALREADY_PRESENT`, or permanent block state in result JSON.
- [ ] Ensure no credentials/raw page bodies enter result JSON.

## Task 6 — Verification

- [ ] Run focused identity/VTEX/product-work tests.
- [ ] Run full `pytest -q` in GitHub Actions.
- [ ] Inspect diff for commercial-field changes (must be none).
- [ ] Open PR to `feat/selected-identity-research`.
- [ ] Merge only if full MCP CI is green.
