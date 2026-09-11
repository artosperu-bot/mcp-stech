USE [STECH_MCP];
GO

-- Extend the existing marketplace template registry instead of creating a
-- parallel requirements system. Legacy columns and primary keys remain valid.
IF COL_LENGTH(N'dbo.marketplace_template', N'platform_code') IS NULL
    ALTER TABLE dbo.marketplace_template ADD platform_code NVARCHAR(40) NULL;
GO
IF COL_LENGTH(N'dbo.marketplace_template', N'valid_from') IS NULL
    ALTER TABLE dbo.marketplace_template ADD valid_from DATETIME2(0) NULL;
GO
IF COL_LENGTH(N'dbo.marketplace_template', N'valid_to') IS NULL
    ALTER TABLE dbo.marketplace_template ADD valid_to DATETIME2(0) NULL;
GO

IF COL_LENGTH(N'dbo.marketplace_template_field', N'requirement_level') IS NULL
BEGIN
    ALTER TABLE dbo.marketplace_template_field
        ADD requirement_level NVARCHAR(20) NOT NULL
            CONSTRAINT DF_marketplace_template_field_requirement_level DEFAULT(N'OPTIONAL') WITH VALUES;
    UPDATE dbo.marketplace_template_field
       SET requirement_level = CASE WHEN required = 1 THEN N'REQUIRED' ELSE N'OPTIONAL' END;
END;
GO
IF COL_LENGTH(N'dbo.marketplace_template_field', N'data_scope') IS NULL
    ALTER TABLE dbo.marketplace_template_field ADD data_scope NVARCHAR(20) NOT NULL CONSTRAINT DF_marketplace_template_field_scope DEFAULT(N'TECHNICAL') WITH VALUES;
GO
IF COL_LENGTH(N'dbo.marketplace_template_field', N'master_field_code') IS NULL
    ALTER TABLE dbo.marketplace_template_field ADD master_field_code NVARCHAR(100) NULL;
GO
IF COL_LENGTH(N'dbo.marketplace_template_field', N'identifier_role') IS NULL
    ALTER TABLE dbo.marketplace_template_field ADD identifier_role NVARCHAR(30) NOT NULL CONSTRAINT DF_marketplace_template_field_identifier DEFAULT(N'NONE') WITH VALUES;
GO
IF COL_LENGTH(N'dbo.marketplace_template_field', N'auto_fill') IS NULL
    ALTER TABLE dbo.marketplace_template_field ADD auto_fill BIT NOT NULL CONSTRAINT DF_marketplace_template_field_autofill DEFAULT(1) WITH VALUES;
GO
IF COL_LENGTH(N'dbo.marketplace_template_field', N'image_role') IS NULL
    ALTER TABLE dbo.marketplace_template_field ADD image_role NVARCHAR(60) NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.marketplace_template_field')
      AND name = N'CK_marketplace_template_field_requirement_level'
)
BEGIN
    ALTER TABLE dbo.marketplace_template_field WITH CHECK ADD CONSTRAINT CK_marketplace_template_field_requirement_level
        CHECK (requirement_level IN (N'REQUIRED', N'RECOMMENDED', N'OPTIONAL'));
END;
GO
IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.marketplace_template_field')
      AND name = N'CK_marketplace_template_field_data_scope'
)
BEGIN
    ALTER TABLE dbo.marketplace_template_field WITH CHECK ADD CONSTRAINT CK_marketplace_template_field_data_scope
        CHECK (data_scope IN (N'TECHNICAL', N'IDENTITY', N'CONTENT', N'COMMERCIAL', N'CONTROL', N'IMAGE'));
END;
GO

CREATE OR ALTER VIEW dbo.V_CHANNEL_REQUIREMENT_V2
AS
SELECT
    mt.marketplace_code AS channel_code,
    mt.platform_code,
    mt.template_code,
    mt.template_version AS version_code,
    mt.category_code,
    mt.active,
    mt.valid_from,
    mt.valid_to,
    mf.field_code AS target_field_code,
    COALESCE(mf.master_field_code, mapx.master_field_code, mf.field_code) AS master_field_code,
    mf.display_name,
    mf.requirement_level AS requirement,
    mf.data_scope,
    mf.data_type,
    mf.unit,
    mf.excel_column,
    mf.json_path,
    mf.allowed_values_json,
    COALESCE(mapx.transform_rule, mf.normalization_rule) AS transform_rule,
    mf.identifier_role,
    mf.auto_fill,
    mf.image_role
FROM dbo.marketplace_template mt
JOIN dbo.marketplace_template_field mf
  ON mf.marketplace_code = mt.marketplace_code
 AND mf.template_code = mt.template_code
 AND mf.template_version = mt.template_version
 AND mf.category_code = mt.category_code
OUTER APPLY (
    SELECT TOP (1) m.master_field_code, m.transform_rule
    FROM dbo.marketplace_field_mapping m
    WHERE m.marketplace_code = mf.marketplace_code
      AND m.template_code = mf.template_code
      AND m.template_version = mf.template_version
      AND m.category_code = mf.category_code
      AND m.target_field_code = mf.field_code
      AND m.enabled = 1
    ORDER BY m.priority ASC
) mapx;
GO
