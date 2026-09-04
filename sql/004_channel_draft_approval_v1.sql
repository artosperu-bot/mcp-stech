USE [STECH_MCP];
GO

IF COL_LENGTH(N'dbo.channel_draft', N'approval_status') IS NULL
BEGIN
    ALTER TABLE dbo.channel_draft
        ADD approval_status NVARCHAR(20) NOT NULL
            CONSTRAINT DF_channel_draft_approval_status DEFAULT (N'PENDIENTE') WITH VALUES;
END;
GO

IF COL_LENGTH(N'dbo.channel_draft', N'approved_by') IS NULL
BEGIN
    ALTER TABLE dbo.channel_draft ADD approved_by NVARCHAR(120) NULL;
END;
GO

IF COL_LENGTH(N'dbo.channel_draft', N'approved_at') IS NULL
BEGIN
    ALTER TABLE dbo.channel_draft ADD approved_at DATETIME2(0) NULL;
END;
GO

IF COL_LENGTH(N'dbo.channel_draft', N'approval_note') IS NULL
BEGIN
    ALTER TABLE dbo.channel_draft ADD approval_note NVARCHAR(1000) NULL;
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.channel_draft')
      AND name = N'CK_channel_draft_approval_status'
)
BEGIN
    ALTER TABLE dbo.channel_draft WITH CHECK
        ADD CONSTRAINT CK_channel_draft_approval_status
        CHECK (approval_status IN (N'PENDIENTE', N'APROBADO', N'RECHAZADO'));
END;
GO

CREATE OR ALTER VIEW dbo.V_PRODUCT_WORKSPACE_V1
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
    pm.source_stock_value,
    pm.source_stock_operator,
    pm.source_price_usd_sin_igv,
    pm.source_observed_at,
    pm.screen_inches,
    pm.package_width_cm,
    pm.package_length_cm,
    pm.package_height_cm,
    pm.package_weight_g,
    pm.package_status,
    pm.package_method,
    pm.package_source,
    pm.package_rule_code,
    pm.package_confidence_grade,
    pm.readiness_state,
    pm.identity_score,
    pm.technical_score,
    pm.image_score,
    pm.package_score,
    pm.coolbox_score,
    pm.created_at,
    pm.updated_at,
    cd.channel_draft_id AS coolbox_draft_id,
    cd.draft_version AS coolbox_draft_version,
    cd.status AS coolbox_status,
    cd.field_count AS coolbox_field_count,
    cd.required_missing_count AS coolbox_required_missing_count,
    cd.estimated_count AS coolbox_estimated_count,
    cd.approval_status AS coolbox_approval_status,
    cd.approved_by AS coolbox_approved_by,
    cd.approved_at AS coolbox_approved_at,
    cd.approval_note AS coolbox_approval_note,
    (
        SELECT COUNT_BIG(1)
        FROM dbo.product_image pi
        WHERE pi.partnumber = pm.partnumber
    ) AS image_count,
    (
        SELECT COUNT_BIG(1)
        FROM dbo.product_image pi
        WHERE pi.partnumber = pm.partnumber
          AND pi.is_approved = 1
    ) AS approved_image_count
FROM dbo.product_master pm
OUTER APPLY (
    SELECT TOP (1)
        d.channel_draft_id,
        d.draft_version,
        d.status,
        d.field_count,
        d.required_missing_count,
        d.estimated_count,
        d.approval_status,
        d.approved_by,
        d.approved_at,
        d.approval_note
    FROM dbo.channel_draft d
    WHERE d.partnumber = pm.partnumber
      AND d.marketplace = N'COOLBOX'
    ORDER BY d.draft_version DESC, d.channel_draft_id DESC
) cd;
GO
