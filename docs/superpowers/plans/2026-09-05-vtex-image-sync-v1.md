# VTEX Image Sync V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make STECH MCP discover, validate, publish, and verify local PC020 product images in VTEX, with `{PARTNUMBER}_01.*` always as the main image and with no changes to the frozen catalog/pricing/stock flow.

**Architecture:** `STECH_MCP.dbo.product_image` remains the local image authority. The MCP discovers files under `C:\STECH_IMAGENES`, serves only signed short-lived image URLs through the existing Cloudflare-exposed MCP process, and calls VTEX Classic Catalog SKU file endpoints. A new publication table tracks remote file IDs and idempotency per SKU/image.

**Tech Stack:** Python 3.12+, MCP Python SDK, Starlette ASGI app already used transitively by MCP, SQL Server/pyodbc, Python stdlib `urllib.request` for VTEX HTTP, Pillow for safe image metadata validation.

**Spec:** `docs/superpowers/specs/2026-09-05-vtex-image-sync-design.md`

## Global Constraints

- PC020 local root: `C:\STECH_IMAGENES`.
- `_01` is always the only main image.
- Missing `_01` => `REVIEW`; do not auto-upload `_02+`.
- V1 strategy is `MISSING_ONLY`; never delete/replace manual VTEX images.
- No changes to `scr/v8-identity` identity, category, attributes, BrandId, Pricing, Logistics, commercial dates, or REVIEW_FIRST.
- `VTEX_IMAGE_SIGNING_SECRET` is optional: when absent, generate a process-local cryptographically secure secret at MCP startup; URLs are short-lived so restart invalidation is acceptable.
- VTEX credentials may use dedicated `VTEX_APP_KEY/VTEX_APP_TOKEN` or aliases `CHN_CRED_VTEX_STECH_APP_KEY/CHN_CRED_VTEX_STECH_APP_TOKEN`.
- Do not write real credentials or generated secrets to Git.

---

### Task 1: Configuration and local image discovery

**Files:**
- Modify: `src/stech_mcp/config.py`
- Create: `src/stech_mcp/services/local_image_sync.py`
- Modify: `src/stech_mcp/db/product_master_repository.py`
- Test: `tests/test_vtex_image_config.py`
- Test: `tests/test_local_image_sync.py`

**Interfaces:**
- Produces `Settings.stech_image_root`, VTEX account/credential/image settings, and `Settings.vtex_image_signing_secret_value()`.
- Produces `LocalImageSyncService.sync(partnumber) -> dict` and `.validate(partnumber) -> dict`.
- Produces `ProductMasterRepository.upsert_local_image(...) -> dict`.

- [ ] **Step 1: Write failing tests for config aliases and automatic signing secret.**
- [ ] **Step 2: Run targeted tests and confirm RED because fields/method do not exist.**
- [ ] **Step 3: Implement config fields with credential aliases; generate a stable process-local secret lazily when env secret is empty.**
- [ ] **Step 4: Run config tests and confirm GREEN.**
- [ ] **Step 5: Write failing tests using `tmp_path` for exact `{PN}_NN.ext` discovery, numeric ordering, SHA-256, dimensions, `_01` main, and missing `_01 => REVIEW`.**
- [ ] **Step 6: Run targeted tests and confirm RED because service/repository API is absent.**
- [ ] **Step 7: Implement local discovery/validation. Use Pillow to open/verify format and dimensions; enforce <=5 MiB; reject files outside root and non-exact PN names.**
- [ ] **Step 8: Implement idempotent SQL upsert into existing `dbo.product_image`, preserving the existing `(partnumber, sha256_hash, variant_type)` uniqueness contract.**
- [ ] **Step 9: Run targeted tests and full suite.**

### Task 2: Signed temporary image URLs on the existing MCP HTTP app

**Files:**
- Create: `src/stech_mcp/services/image_signing.py`
- Create: `src/stech_mcp/http/image_route.py`
- Modify: `src/stech_mcp/server.py`
- Test: `tests/test_image_signing.py`
- Test: `tests/test_image_route.py`

**Interfaces:**
- Produces `ImageUrlSigner.sign(product_image_id, partnumber, expires_at) -> str` and `.verify(token) -> dict`.
- Produces `build_vtex_image_route(...)` for `/vtex-images/{token}`.

- [ ] **Step 1: Write failing HMAC tests for valid, tampered, and expired tokens.**
- [ ] **Step 2: Verify RED.**
- [ ] **Step 3: Implement compact URL-safe HMAC-SHA256 tokens with constant-time signature comparison.**
- [ ] **Step 4: Verify GREEN.**
- [ ] **Step 5: Write failing route tests: valid token returns exact file with image content type; expired token 403; unknown image 404; storage path outside root 403.**
- [ ] **Step 6: Implement route and register it before MCP routes in the existing ASGI app. No directory listing and no raw path parameter.**
- [ ] **Step 7: Run targeted tests and full suite.**

### Task 3: VTEX client and publication traceability

**Files:**
- Create: `sql/004_vtex_image_publication.sql`
- Create: `src/stech_mcp/db/image_publication_repository.py`
- Create: `src/stech_mcp/services/vtex_image_client.py`
- Test: `tests/test_image_publication_repository.py`
- Test: `tests/test_vtex_image_client.py`

**Interfaces:**
- Produces `VtexImageClient.resolve_sku_id(ref_id)`, `.list_sku_files(sku_id)`, `.create_sku_file(sku_id, payload)`.
- Produces repository methods `get_publications`, `upsert_publication`, and `mark_verified`.

- [ ] **Step 1: Write failing SQL/repository contract tests for additive idempotent migration and unique `(channel, account_code, remote_sku_id, product_image_id)`.**
- [ ] **Step 2: Verify RED.**
- [ ] **Step 3: Add migration and repository.**
- [ ] **Step 4: Verify GREEN.**
- [ ] **Step 5: Write failing VTEX client tests with a fake opener, asserting exact endpoints, auth headers, JSON payload, and useful error body propagation.**
- [ ] **Step 6: Implement stdlib HTTP client for Classic Catalog endpoints.**
- [ ] **Step 7: Run targeted tests and full suite.**

### Task 4: MCP orchestration tools and idempotent sync

**Files:**
- Create: `src/stech_mcp/services/vtex_image_sync.py`
- Modify: `src/stech_mcp/server.py`
- Modify: `.env.example`
- Modify: `README.md`
- Test: `tests/test_vtex_image_sync.py`
- Test: `tests/test_server_vtex_image_tools.py`

**Interfaces:**
- Exposes MCP tools:
  - `product_images_sync_local(partnumber)`
  - `product_images_validate(partnumber)`
  - `vtex_images_status(partnumber, account_code="VTEX_STECH")`
  - `vtex_images_sync(partnumber, account_code="VTEX_STECH")`

- [ ] **Step 1: Write failing orchestration test for four images `_01.._04`: resolve `{PN}-S`, GET remote files, POST four in order, `_01 IsMain=true`, read-back, persist VERIFIED.**
- [ ] **Step 2: Write failing idempotency test: second execution performs GET/read-back but zero POSTs for already VERIFIED/local publications.**
- [ ] **Step 3: Write failing safety test: missing `_01` returns REVIEW and performs no VTEX POST.**
- [ ] **Step 4: Verify RED.**
- [ ] **Step 5: Implement sync service and MCP tool wrappers.**
- [ ] **Step 6: Update `.env.example`: only `STECH_IMAGE_ROOT`, account/credential fields, optional public base/secret/TTL/timeout. Document that secret auto-generates if omitted.**
- [ ] **Step 7: Update README with the one-time local setup, Cloudflare requirement for public `/vtex-images/*`, migration command, and real acceptance commands for `82YU00XYLM`.**
- [ ] **Step 8: Run all tests and compile checks.**
- [ ] **Step 9: Open PR against `feat/product-workspace-v1`; verify GitHub Actions passes before merge.**

## Acceptance on PC020 after merge

```powershell
cd C:\DESAROLLO\mcp-stech
git fetch origin
git checkout feat/product-workspace-v1
git pull origin feat/product-workspace-v1
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
sqlcmd -S PC020 -E -C -i ".\sql\004_vtex_image_publication.sql"
```

Required `.env` values for the real VTEX test:

```env
STECH_IMAGE_ROOT=C:\STECH_IMAGENES
VTEX_ACCOUNT_NAME=ststore227
VTEX_APP_KEY=<real key>
VTEX_APP_TOKEN=<real token>
VTEX_IMAGE_PUBLIC_BASE=https://mcp.artos.pe/vtex-images
```

Optional values:

```env
# Leave blank/omit to auto-generate securely on each process start.
VTEX_IMAGE_SIGNING_SECRET=
VTEX_IMAGE_URL_TTL_SECONDS=900
VTEX_HTTP_TIMEOUT_SECONDS=30
```

Then restart MCP and invoke:

```text
product_images_sync_local(partnumber="82YU00XYLM")
product_images_validate(partnumber="82YU00XYLM")
vtex_images_status(partnumber="82YU00XYLM")
vtex_images_sync(partnumber="82YU00XYLM")
```

Expected final state: four local images discovered, `_01` main, VTEX read-back confirms uploaded files, second sync creates no duplicates.