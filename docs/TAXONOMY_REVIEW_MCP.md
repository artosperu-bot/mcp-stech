# STECH MCP - Taxonomy Review Queue V1

## Objective

Complement the existing V8 CAT_V2 deterministic classifier.

V8 continues classifying products it already understands. STECH MCP handles only
the unresolved gaps: missing category, missing subcategory, or generic categories
(COMPONENTE, COMPONENTES, PRODUCTO, OTROS).

The MCP never invents taxonomy silently and the scheduler never writes taxonomy
back to DB_DISTRIBUIDORES.

## Source of truth

- Source products: DB_DISTRIBUIDORES.dbo.PRD_PRODUCTO_DISTRIBUIDOR
- Existing taxonomy catalog: distinct categoria/subcategoria pairs from that table
- Review queue/audit: STECH_MCP.dbo.taxonomy_review
- Deterministic V8 classifier: CAT_V2 in the SCR project

## Workflow

1. taxonomy_review_sync detects unresolved products and queues them.
2. taxonomy_catalog_get returns the existing STECH taxonomy.
3. ChatGPT/HERMES reviews product evidence and calls taxonomy_propose.
4. The proposal is labeled EXISTING_PAIR, NEW_SUBCATEGORY or NEW_CATEGORY.
5. taxonomy_sql_preview shows the guarded SQL and exact source product id.
6. The user explicitly approves with taxonomy_approve.
7. Only then taxonomy_apply writes missing/generic source fields.

If a category/subcategory changed manually after proposal, apply stops instead of
overwriting that newer source value.

## Source write policy

taxonomy_apply updates by producto_distribuidor_id, never by Part Number.
It may replace a generic category, but it does not overwrite a meaningful category
or subcategory that appeared after review.

Approved metadata is written to atributos_json with:

- clasificacion_version = CAT_V2
- clasificacion_fuente = MCP_REVISION_APROBADA
- clasificacion_confianza
- clasificacion_evidencia_mcp

## MCP tools

- taxonomy_missing_list
- taxonomy_catalog_get
- taxonomy_review_sync
- taxonomy_review_list
- taxonomy_review_get
- taxonomy_propose
- taxonomy_sql_preview
- taxonomy_approve
- taxonomy_reject
- taxonomy_apply

## Install

1. Apply sql/013_taxonomy_review_queue.sql to database STECH_MCP.
2. Install the Windows scheduler:

    powershell -ExecutionPolicy Bypass -File .\deploy\windows\INSTALL_TAXONOMY_TASK.ps1

Default cadence: every 240 minutes and at Windows logon.
The scheduled task performs detection/queueing only. It never approves or applies taxonomy.