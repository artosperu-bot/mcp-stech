# STECH Product Master + Multichannel Publishing Platform

**Date:** 2026-09-04  
**Status:** Approved design, pending implementation plan  
**Repos involved:** `artosperu-bot/mcp-stech` and `artosperu-bot/scr` (`v8-identity`)  
**Primary persistence:** SQL Server 2019  
**First acceptance SKU:** `82YU00XYLM`

## 1. Goal

Build a scalable product-preparation and publishing platform where STECH can provide one or many Part Numbers, automatically consume the existing distributor/ERP data, enrich only missing data from trusted sources, prepare and manage product images, generate channel-specific drafts, preview the final result, require explicit approval, and publish through a single controlled publishing service.

The target channels are initially:

- Coolbox
- Falabella / Saga
- VTEX

The architecture must allow adding more channels later without reimplementing product research, evidence, images, or master product logic.

## 2. Guiding principle: database-first persistence

The majority of persistent state must live in SQL Server.

`DB_DISTRIBUIDORES` remains the operational source for distributor/product/stock/price/history data. Existing ERP databases remain authoritative for STECH commercial stock, cost, sales and related business data. `STECH_MCP` becomes the persistence layer for product-master enrichment, evidence, images metadata, drafts, jobs, approvals and publication audit.

The MCP must not become a second ERP and must not duplicate operational stock/history unnecessarily.

Image binaries may live in the existing image repository/filesystem/object storage, but SQL Server must store their metadata, hashes, provenance, status, ordering and product/channel relationships.

## 3. High-level architecture

```text
                    ChatGPT / STECH MCP
                            |
                            v
                     Product Service
                            |
           +----------------+----------------+
           |                |                |
           v                v                v
      Enrichment        Image Pipeline   Commercial Data
      + Evidence        + Editing         + Price/Stock
           |                |                |
           +----------------+----------------+
                            |
                            v
                     PRODUCT MASTER
                            |
             +--------------+--------------+
             |              |              |
             v              v              v
          Coolbox        Falabella        VTEX
          Adapter        Adapter          Adapter
             |              |              |
             +--------------+--------------+
                            |
                            v
                   Preview / Validation
                            |
                     LISTO_PARA_REVISAR
                            |
                    explicit approval
                            |
                            v
                     Publish Service
                            |
             +--------------+--------------+
             |              |              |
             v              v              v
          Coolbox        Falabella        VTEX
```

ChatGPT and SCR must never maintain separate publication logic. Both must call the same backend publishing service.

## 4. Existing systems to preserve and reuse

### `DB_DISTRIBUIDORES`

Use current controlled contracts such as:

- `dbo.V_PRD_PRODUCTO_ACTUAL`
- `dbo.V_HST_PRODUCTO_OBSERVACION_V8`

These remain read-only from the MCP side unless a later explicit synchronization contract is approved.

### `STECH_MCP`

Already contains/uses the Phase 1 enrichment/evidence architecture and packaging rules. Existing MCP tools must remain backward compatible.

### `scr/v8-identity`

Reuse the existing channel UI/backend instead of creating a parallel application. Falabella already has publication preview concepts and VTEX already has a dedicated channel module. The new Product Workspace must integrate with the current `/src` backend and `/web` interface patterns.

## 5. Product Master

The Product Master is the reusable canonical product state keyed primarily by Part Number.

It must represent at least:

### Identity
- Part Number
- brand
- model
- EAN / UPC / GTIN
- internal/distributor identifiers
- category/taxonomy

### Content
- master title
- master description
- technical attributes
- warranty
- box contents

### Logistics
- device dimensions
- device weight
- package dimensions
- package weight
- source/method for logistics values

### Images
- source originals
- STECH-edited variants
- marketplace-ready variants
- ordering/selection

### Commercial linkage
- cost reference
- sales price inputs
- stock inputs
- channel-specific price/stock rules

### State
- enrichment state
- image state
- readiness state
- approval state
- channel publication state

The canonical Product Master is not modified merely to satisfy a marketplace-specific requirement. Channel-specific transformations belong in drafts.

## 6. Field-level provenance and evidence

Every enriched field must have traceability. A field must not be stored only as a naked value when it came from research.

Minimum provenance attributes:

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
partnumber_match
confidence
is_approved
approved_by / approved_at when applicable
created_at
updated_at
```

### Source priority

1. Approved manual override
2. A1: manufacturer + exact Part Number
3. A2: official support/PDF + exact Part Number
4. B: authorized distributor + exact SKU
5. C: trusted retailer + exact SKU
6. Deltron / distributor operational data
7. Derived deterministic values
8. Estimated fallback

Approved manual values are not overwritten automatically. New evidence creates a reviewable conflict/update candidate.

### Variant-sensitive fields

The following require exact Part Number or unequivocal exact-SKU evidence:

- CPU
- RAM
- SSD
- GPU
- operating system
- color
- GTIN

Family-level inference is not allowed for these fields.

## 7. Packaging rule approved in Phase 1

For laptops with screen size `>= 15.0` and `< 16.0`, when no approved official package is available:

```text
Width: 33 cm
Length: 54 cm
Height: 7 cm
Weight: 2500 g
Method: ESTIMATED
Source: REGLA_STECH_EMPAQUE
Rule: LAPTOP_15_X_DEFAULT
Confidence grade: E
```

Official/approved package values override this fallback.

## 8. Image pipeline

Images are a first-class subsystem, independent from technical enrichment.

### Source sequence

1. Reuse valid Deltron images already captured by the existing system.
2. If insufficient, search manufacturer official sites/support/media/CDN using exact Part Number/model evidence.
3. Preserve all source originals.
4. Produce STECH-edited variants only from approved originals.
5. Produce channel-specific marketplace variants when necessary.

### Image states

- `ORIGINAL`
- `EDITED_STECH`
- `MARKETPLACE`

### Image metadata in SQL Server

At minimum:

```text
image_id
partnumber
source_type
source_url
source_domain
is_official
partnumber_match
storage_path
variant_type
parent_image_id
sha256_hash
width_px
height_px
format
background_status
approved
position
created_at
updated_at
```

Hashes must be used for duplicate detection.

### Editing profile

The final S-TECH marketplace editing recipe is intentionally not fixed yet. It will be created from user-provided visual examples. Original images must never be destroyed.

## 9. Commercial data separation

Technical enrichment must not mutate commercial values.

Content and technical attributes are one domain; price and stock are another.

Commercial data may come from ERP, SQL views, user-provided Excel, or approved channel rules. Channel-specific price/stock/date fields remain explicit seller/commercial inputs unless a controlled automatic rule is defined.

## 10. Channel drafts

Each Product Master can have multiple independent channel drafts.

Example:

```text
82YU00XYLM
|- master
|- COOLBOX draft
|- FALABELLA draft
|- VTEX draft
```

A draft stores transformed channel-specific content, required attributes, selected images, commercial fields, validation results, errors and readiness.

Changing a Falabella title must not change the master title or VTEX title.

## 11. Marketplace adapters

Each channel is implemented as an adapter over the shared Product Master.

### Coolbox adapter

- preserve current 81-column laptop contract
- map Product Master values into the real workbook schema
- preserve formatting, validations, formulas and hidden sheets when exporting XLSX

### Falabella adapter

- use real Falabella category/schema/template/API definitions
- map required attributes from Product Master
- support title/description/images/GTIN/category/price/stock fields according to actual channel contract
- integrate with existing SCR Falabella preview UI

### VTEX adapter

- use real VTEX catalog/SKU/specification/image/pricing/inventory contracts
- continue current safe read capability until write permissions and endpoint contracts are verified
- later publish through the shared Publish Service

No guessed marketplace schema is allowed. Every channel implementation must be based on real templates, APIs or documents supplied/verified for that channel.

## 12. Product Workspace in SCR

The first visible system result will be a Product Workspace integrated into existing SCR views.

For each product it should show:

```text
Product / Part Number / readiness
Main image + thumbnails
Identity completeness
Technical completeness
Image readiness
Packaging source/status
Price readiness
Stock readiness
Per-channel draft state
Preview / Edit / Approve / Publish controls
```

Representative states:

- `ENRIQUECIENDO`
- `FALTAN_DATOS`
- `FALTAN_IMAGENES`
- `LISTO_PARA_REVISAR`
- `APROBADO`
- `PUBLICANDO`
- `PUBLICADO`
- `ERROR_CANAL`

Each field must expose its provenance when requested, e.g. `VERIFIED A1 Lenovo`, or `ESTIMATED REGLA_STECH_EMPAQUE`.

## 13. Jobs and scalability

Large batches must execute as persistent jobs rather than long synchronous requests.

A job can represent requests such as:

```text
Prepare 500 Lenovo products for Falabella
```

Job progress must persist in SQL Server and support restart/retry.

Suggested job states:

- `PENDING`
- `RUNNING`
- `WAITING_RESEARCH`
- `WAITING_IMAGES`
- `WAITING_REVIEW`
- `COMPLETED`
- `FAILED`
- `CANCELLED`

Per-product job items must allow individual retry without restarting the entire batch.

Idempotency is required: requesting the same Part Number twice must reuse/update the existing Product Master and existing trusted evidence rather than duplicate it.

## 14. Approval model

Nothing is published automatically without explicit approval.

Approval can originate from:

- ChatGPT/MCP command such as "approve and publish"
- SCR UI button

Both must create the same approval record and invoke the same Publish Service.

Approval must capture at minimum:

```text
approval_id
partnumber
channel
draft_version
approved_by
approved_at
approval_source
```

Any material draft change after approval invalidates that approval and requires re-approval.

## 15. Single Publish Service

All publication writes go through one backend service.

Before publishing it must validate:

- product/draft is approved
- mandatory channel fields are complete
- images are valid/approved
- price is valid when required
- stock is valid when required
- channel credentials/configuration are available
- draft version still matches approved version

Publication must be idempotent where the channel supports it, and must persist request/response identifiers and outcome.

ChatGPT and SCR do not write to marketplace APIs directly; they call this service.

## 16. Audit trail

Persist important events in SQL Server.

Examples:

```text
product imported from distributor
field enriched from official source
field conflict detected
image discovered
image edited
channel draft generated
draft approved
publication attempted
publication accepted/rejected
```

Audit must identify actor/source, timestamp, Part Number, channel when relevant, and associated draft/publication/job identifiers.

## 17. Proposed persistent entities in `STECH_MCP`

Existing Phase 1 tables remain. Add/extend normalized tables approximately along these boundaries:

- `product_master`
- `product_enrichment`
- `product_evidence`
- `product_image`
- `product_image_channel`
- `packaging_rule`
- `marketplace_template`
- `marketplace_template_field`
- `marketplace_field_mapping`
- `channel_draft`
- `channel_draft_field`
- `channel_draft_image`
- `channel_validation_result`
- `product_job`
- `product_job_item`
- `product_approval`
- `publication_attempt`
- `product_audit_event`

Names may be adjusted to match existing SQL naming conventions during implementation, but responsibilities must stay separate.

## 18. MCP capabilities to add incrementally

Potential focused tools:

### Product preparation
- `product_prepare`
- `product_prepare_batch`
- `product_master_get`
- `product_readiness_get`

### Enrichment
- `enrichment_missing_list`
- `enrichment_get`
- `enrichment_save`
- `enrichment_conflicts_list`
- `enrichment_approve`

### Images
- `product_images_get`
- `product_images_save_source`
- `product_image_approve`
- `product_image_set_position`

### Drafts
- `channel_draft_generate`
- `channel_draft_get`
- `channel_draft_validate`
- `channel_draft_approve`

### Jobs
- `job_get`
- `job_items_get`

### Publishing
- `channel_publish`

No generic `execute_sql` tool is added.

## 19. First implementation milestone: Product Workspace V1

The first tangible milestone must work end-to-end for `82YU00XYLM` without yet publishing to a live marketplace.

Acceptance target:

1. Read the real product from `DB_DISTRIBUIDORES`.
2. Persist/create its Product Master state in `STECH_MCP`.
3. Show existing Deltron data.
4. Resolve package as `33 x 54 x 7 cm / 2500 g` with `ESTIMATED` provenance when no official package exists.
5. Display existing images and their source metadata if available.
6. Show missing technical fields requiring research.
7. Generate the existing Coolbox 81-field draft.
8. Show a Product Workspace preview in SCR with readiness sections and field provenance.
9. Do not publish anything.

This creates an immediately visible result while establishing the base needed for bulk enrichment, image editing, Falabella and VTEX publishing.

## 20. Implementation sequence

### Milestone A — SQL Product Master + read model
- create additive SQL migration
- product master repository/services
- readiness calculation
- idempotent creation/update

### Milestone B — Product Workspace V1 in SCR
- backend endpoints
- product detail/readiness UI
- field evidence display
- Coolbox draft preview

### Milestone C — image inventory integration
- reuse existing Deltron image capture
- persist image metadata/hash
- show gallery/source/readiness in Product Workspace

### Milestone D — research/enrichment jobs
- missing-field queues
- evidence persistence
- conflict handling
- batch jobs/retries

### Milestone E — S-TECH image editing profile
- derive recipe from user examples
- non-destructive edited variants
- approval workflow

### Milestone F — Falabella adapter
- consume real category/template/API rules
- draft/validation/preview
- approval only; live publishing after write contract is verified

### Milestone G — VTEX adapter
- consume real Catalog/SKU/spec/image/pricing/inventory contracts
- draft/validation/preview
- write/publish only after permissions are verified

### Milestone H — unified Publish Service
- approval version checks
- channel writes
- idempotency
- audit and retries

## 21. Non-goals for the first milestone

The first Product Workspace milestone will not:

- auto-publish to live Falabella or VTEX
- guess channel-specific fields without real schemas
- auto-approve researched values
- overwrite approved manual values
- destroy/replace original images
- move operational stock/history out of existing authoritative databases

## 22. Testing strategy

Use TDD for production changes.

Required classes of tests:

- SQL repository parameterization and idempotency
- provenance/source-priority resolver tests
- Product Master readiness tests
- package official-vs-estimated precedence tests
- image duplicate/hash tests
- draft version/approval invalidation tests
- channel adapter schema mapping tests
- Publish Service approval/precondition tests
- SCR API/UI smoke tests

Every milestone must keep existing MCP tools backward compatible and CI green.

## 23. Security and operational controls

- no arbitrary SQL MCP endpoint
- marketplace secrets remain server-side only
- no live publication without approval
- public MCP endpoint must ultimately use compatible authentication before production exposure of sensitive internal data
- audit every write to Product Master approvals/publications
- preserve original images and original source evidence

## 24. Success definition

The platform is successful when the user can provide a list of Part Numbers and obtain:

1. automatically loaded distributor/ERP information,
2. trusted enrichment only where needed,
3. traceable source/evidence per field,
4. reusable and editable product images,
5. accurate channel-specific previews,
6. explicit readiness/errors before publication,
7. approval from ChatGPT or SCR,
8. a single controlled publication mechanism,
9. persistent SQL audit/history,
10. scalable processing from individual products to large batches.
