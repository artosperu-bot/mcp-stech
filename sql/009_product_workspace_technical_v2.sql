USE [STECH_MCP];
GO

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

-- Product Workspace V2 technical fact surface.
-- This is read-only: it reuses Product Workspace V1 identity/commercial snapshots
-- and exposes only approved canonical enrichment facts. It does not update price,
-- stock, Product Loader, channel drafts or publication state.
CREATE OR ALTER VIEW dbo.V_PRODUCT_WORKSPACE_TECHNICAL_FACT_V2
AS
SELECT
    pw.product_master_id,
    pw.partnumber,
    pw.source_product_id,
    pw.distributor,
    pw.brand,
    pw.model,
    pw.product_name,
    pw.ean,
    pw.upc,
    pw.mini_codigo,
    pw.category_code,
    pw.subcategory_code,

    -- Existing Product Workspace commercial snapshots remain visible only for
    -- comparison/audit. Technical enrichment never writes them.
    pw.source_stock_value,
    pw.source_stock_operator,
    pw.source_price_usd_sin_igv,
    pw.source_observed_at,

    pw.readiness_state,
    pw.identity_score,
    pw.technical_score,
    pw.image_score,
    pw.package_score,
    pw.coolbox_score,
    pw.image_count,

    pe.enrichment_id,
    pe.field_code,
    pe.value_text,
    pe.value_number,
    pe.unit,
    pe.method,
    pe.confidence_grade,
    pe.created_at AS technical_fact_created_at,
    pe.updated_at AS technical_fact_updated_at
FROM dbo.V_PRODUCT_WORKSPACE_V1 AS pw
LEFT JOIN dbo.product_enrichment AS pe
    ON pe.partnumber = pw.partnumber
   AND pe.is_approved = 1;
GO
