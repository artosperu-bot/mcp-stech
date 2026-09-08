USE [STECH_MCP];
GO

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
SET ANSI_PADDING ON;
SET ANSI_WARNINGS ON;
SET ARITHABORT ON;
SET CONCAT_NULL_YIELDS_NULL ON;
SET NUMERIC_ROUNDABORT OFF;
GO

-- Local VTEX image identity is Part Number + numeric position. The same binary
-- may intentionally be assigned to more than one position (for example _01 and
-- _06), so the hash must not deduplicate different positions.
IF EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.product_image')
      AND name = N'UX_product_image_partnumber_hash_variant'
)
BEGIN
    DROP INDEX UX_product_image_partnumber_hash_variant ON dbo.product_image;
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.product_image')
      AND name = N'UX_product_image_partnumber_hash_variant_position'
)
BEGIN
    CREATE UNIQUE INDEX UX_product_image_partnumber_hash_variant_position
        ON dbo.product_image(partnumber, sha256_hash, variant_type, position)
        WHERE sha256_hash IS NOT NULL;
END;
GO
