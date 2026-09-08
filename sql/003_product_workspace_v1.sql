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

IF OBJECT_ID(N'dbo.product_master', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.product_master (
        product_master_id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_product_master PRIMARY KEY,
        partnumber NVARCHAR(120) NOT NULL CONSTRAINT UQ_product_master_partnumber UNIQUE,
        source_product_id BIGINT NULL,
        distributor NVARCHAR(80) NULL,
        brand NVARCHAR(120) NULL,
        model NVARCHAR(240) NULL,
        product_name NVARCHAR(1000) NULL,
        ean NVARCHAR(32) NULL,
        upc NVARCHAR(32) NULL,
        mini_codigo NVARCHAR(80) NULL,
        category_code NVARCHAR(120) NULL,
        subcategory_code NVARCHAR(120) NULL,
        source_stock_value DECIMAL(18,4) NULL,
        source_stock_operator NVARCHAR(10) NULL,
        source_price_usd_sin_igv DECIMAL(18,4) NULL,
        source_observed_at DATETIME2(0) NULL,
        screen_inches DECIMAL(6,2) NULL,
        package_width_cm DECIMAL(8,2) NULL,
        package_length_cm DECIMAL(8,2) NULL,
        package_height_cm DECIMAL(8,2) NULL,
        package_weight_g INT NULL,
        package_status NVARCHAR(40) NULL,
        package_method NVARCHAR(40) NULL,
        package_source NVARCHAR(200) NULL,
        package_rule_code NVARCHAR(100) NULL,
        package_confidence_grade NVARCHAR(20) NULL,
        readiness_state NVARCHAR(40) NOT NULL CONSTRAINT DF_product_master_readiness DEFAULT (N'ENRIQUECIENDO'),
        identity_score INT NOT NULL CONSTRAINT DF_product_master_identity_score DEFAULT (0),
        technical_score INT NOT NULL CONSTRAINT DF_product_master_technical_score DEFAULT (0),
        image_score INT NOT NULL CONSTRAINT DF_product_master_image_score DEFAULT (0),
        package_score INT NOT NULL CONSTRAINT DF_product_master_package_score DEFAULT (0),
        coolbox_score INT NOT NULL CONSTRAINT DF_product_master_coolbox_score DEFAULT (0),
        created_at DATETIME2(0) NOT NULL CONSTRAINT DF_product_master_created DEFAULT (SYSUTCDATETIME()),
        updated_at DATETIME2(0) NOT NULL CONSTRAINT DF_product_master_updated DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT CK_product_master_scores CHECK (
            identity_score BETWEEN 0 AND 100 AND
            technical_score BETWEEN 0 AND 100 AND
            image_score BETWEEN 0 AND 100 AND
            package_score BETWEEN 0 AND 100 AND
            coolbox_score BETWEEN 0 AND 100
        )
    );
END;
GO

IF OBJECT_ID(N'dbo.channel_draft', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.channel_draft (
        channel_draft_id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_channel_draft PRIMARY KEY,
        partnumber NVARCHAR(120) NOT NULL,
        marketplace NVARCHAR(40) NOT NULL,
        template_name NVARCHAR(200) NOT NULL,
        draft_version INT NOT NULL,
        status NVARCHAR(40) NOT NULL,
        field_count INT NOT NULL CONSTRAINT DF_channel_draft_field_count DEFAULT (0),
        required_missing_count INT NOT NULL CONSTRAINT DF_channel_draft_required_missing DEFAULT (0),
        estimated_count INT NOT NULL CONSTRAINT DF_channel_draft_estimated DEFAULT (0),
        payload_json NVARCHAR(MAX) NULL,
        created_at DATETIME2(0) NOT NULL CONSTRAINT DF_channel_draft_created DEFAULT (SYSUTCDATETIME()),
        updated_at DATETIME2(0) NOT NULL CONSTRAINT DF_channel_draft_updated DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT UQ_channel_draft_version UNIQUE (partnumber, marketplace, draft_version),
        CONSTRAINT CK_channel_draft_counts CHECK (
            field_count >= 0 AND required_missing_count >= 0 AND estimated_count >= 0
        )
    );
END;
GO

IF OBJECT_ID(N'dbo.channel_draft_field', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.channel_draft_field (
        channel_draft_field_id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_channel_draft_field PRIMARY KEY,
        channel_draft_id BIGINT NOT NULL,
        field_position INT NOT NULL,
        field_name NVARCHAR(300) NOT NULL,
        value_text NVARCHAR(MAX) NULL,
        status NVARCHAR(40) NULL,
        source NVARCHAR(1000) NULL,
        method NVARCHAR(80) NULL,
        note NVARCHAR(2000) NULL,
        CONSTRAINT UQ_channel_draft_field_name UNIQUE (channel_draft_id, field_name),
        CONSTRAINT FK_channel_draft_field_draft FOREIGN KEY (channel_draft_id)
            REFERENCES dbo.channel_draft(channel_draft_id)
    );
END;
GO

IF OBJECT_ID(N'dbo.product_image', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.product_image (
        product_image_id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_product_image PRIMARY KEY,
        partnumber NVARCHAR(120) NOT NULL,
        source_type NVARCHAR(80) NOT NULL,
        source_url NVARCHAR(2000) NULL,
        source_domain NVARCHAR(255) NULL,
        is_official BIT NOT NULL CONSTRAINT DF_product_image_official DEFAULT (0),
        partnumber_match NVARCHAR(40) NULL,
        storage_path NVARCHAR(2000) NULL,
        variant_type NVARCHAR(40) NOT NULL CONSTRAINT DF_product_image_variant DEFAULT (N'ORIGINAL'),
        parent_image_id BIGINT NULL,
        sha256_hash CHAR(64) NULL,
        width_px INT NULL,
        height_px INT NULL,
        format NVARCHAR(20) NULL,
        background_status NVARCHAR(40) NULL,
        is_approved BIT NOT NULL CONSTRAINT DF_product_image_approved DEFAULT (0),
        position INT NOT NULL CONSTRAINT DF_product_image_position DEFAULT (0),
        created_at DATETIME2(0) NOT NULL CONSTRAINT DF_product_image_created DEFAULT (SYSUTCDATETIME()),
        updated_at DATETIME2(0) NOT NULL CONSTRAINT DF_product_image_updated DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT FK_product_image_parent FOREIGN KEY (parent_image_id)
            REFERENCES dbo.product_image(product_image_id),
        CONSTRAINT CK_product_image_dimensions CHECK (
            (width_px IS NULL OR width_px > 0) AND (height_px IS NULL OR height_px > 0)
        )
    );
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.product_image')
      AND name = N'IX_product_image_partnumber_position'
)
BEGIN
    CREATE INDEX IX_product_image_partnumber_position
        ON dbo.product_image(partnumber, is_approved DESC, position ASC, product_image_id ASC);
END;
GO

-- A binary image may legitimately be shared by different SKUs. Deduplicate only
-- within the same Part Number and variant class so cross-SKU reuse stays possible.
IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.product_image')
      AND name = N'UX_product_image_sha256_notnull'
)
BEGIN
    DROP INDEX UX_product_image_sha256_notnull ON dbo.product_image;
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.product_image')
      AND name = N'UX_product_image_partnumber_hash_variant'
)
BEGIN
    CREATE UNIQUE INDEX UX_product_image_partnumber_hash_variant
        ON dbo.product_image(partnumber, sha256_hash, variant_type)
        WHERE sha256_hash IS NOT NULL;
END;
GO

IF OBJECT_ID(N'dbo.product_audit_event', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.product_audit_event (
        event_id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_product_audit_event PRIMARY KEY,
        partnumber NVARCHAR(120) NOT NULL,
        event_type NVARCHAR(80) NOT NULL,
        actor_source NVARCHAR(120) NOT NULL,
        channel NVARCHAR(40) NULL,
        detail_json NVARCHAR(MAX) NULL,
        created_at DATETIME2(0) NOT NULL CONSTRAINT DF_product_audit_event_created DEFAULT (SYSUTCDATETIME())
    );
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
    cd.status AS coolbox_status,
    cd.field_count AS coolbox_field_count,
    cd.required_missing_count AS coolbox_required_missing_count,
    cd.estimated_count AS coolbox_estimated_count,
    (
        SELECT COUNT_BIG(1)
        FROM dbo.product_image pi
        WHERE pi.partnumber = pm.partnumber
    ) AS image_count
FROM dbo.product_master pm
OUTER APPLY (
    SELECT TOP (1)
        d.channel_draft_id,
        d.status,
        d.field_count,
        d.required_missing_count,
        d.estimated_count
    FROM dbo.channel_draft d
    WHERE d.partnumber = pm.partnumber
      AND d.marketplace = N'COOLBOX'
    ORDER BY d.draft_version DESC, d.channel_draft_id DESC
) cd;
GO