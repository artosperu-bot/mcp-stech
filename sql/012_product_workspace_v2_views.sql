USE [STECH_MCP];
GO

-- Channel-neutral Workspace projection. V1 remains untouched for legacy callers.
CREATE OR ALTER VIEW dbo.V_PRODUCT_WORKSPACE_V2
AS
SELECT
    pm.product_master_id,
    pm.partnumber,
    pm.source_product_id,
    pm.distributor,
    pm.brand,
    pm.model,
    pm.product_name,
    pm.ean,
    pm.upc,
    pm.mini_codigo,
    pm.category_code,
    pm.subcategory_code,
    pm.readiness_state,
    pm.identity_score,
    pm.technical_score,
    pm.image_score,
    pm.package_score,
    pm.created_at,
    pm.updated_at,
    (SELECT COUNT_BIG(1) FROM dbo.product_image pi WHERE pi.partnumber=pm.partnumber) AS image_count,
    (SELECT COUNT_BIG(1) FROM dbo.product_image pi WHERE pi.partnumber=pm.partnumber AND pi.is_approved=1) AS approved_image_count,
    (SELECT COUNT_BIG(1) FROM dbo.product_fact_candidate fc WHERE fc.partnumber=pm.partnumber AND fc.state=N'CONFLICT') AS fact_conflict_count,
    (SELECT COUNT_BIG(1) FROM dbo.product_image_candidate ic WHERE ic.partnumber=pm.partnumber AND ic.state=N'PENDING') AS image_candidate_count,
    (SELECT COUNT_BIG(1) FROM dbo.product_work_item wi WHERE wi.partnumber=pm.partnumber AND wi.status NOT IN (N'COMPLETED',N'PARTIAL',N'REVIEW_REQUIRED',N'NO_DATA_FOUND',N'FAILED',N'CANCELLED')) AS active_work_count
FROM dbo.product_master pm;
GO
