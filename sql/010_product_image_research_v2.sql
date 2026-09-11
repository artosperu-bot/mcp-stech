USE [STECH_MCP];
GO

IF OBJECT_ID(N'dbo.product_image_candidate', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.product_image_candidate (
        product_image_candidate_id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_product_image_candidate PRIMARY KEY,
        partnumber NVARCHAR(120) NOT NULL,
        source_type NVARCHAR(60) NOT NULL,
        source_url NVARCHAR(2048) NOT NULL,
        source_domain NVARCHAR(255) NULL,
        source_page_url NVARCHAR(2048) NULL,
        title NVARCHAR(1000) NULL,
        thumbnail_url NVARCHAR(2048) NULL,
        image_width_px INT NULL,
        image_height_px INT NULL,
        exactness_policy NVARCHAR(40) NOT NULL CONSTRAINT DF_product_image_candidate_exactness DEFAULT(N'MANUAL_REVIEW'),
        partnumber_match NVARCHAR(40) NOT NULL CONSTRAINT DF_product_image_candidate_pn_match DEFAULT(N'UNKNOWN'),
        variant_match NVARCHAR(40) NOT NULL CONSTRAINT DF_product_image_candidate_variant_match DEFAULT(N'UNKNOWN'),
        confidence_score DECIMAL(5,2) NULL,
        state NVARCHAR(20) NOT NULL CONSTRAINT DF_product_image_candidate_state DEFAULT(N'PENDING'),
        evidence_json NVARCHAR(MAX) NULL,
        discovered_at DATETIME2(0) NOT NULL CONSTRAINT DF_product_image_candidate_discovered DEFAULT(SYSUTCDATETIME()),
        updated_at DATETIME2(0) NOT NULL CONSTRAINT DF_product_image_candidate_updated DEFAULT(SYSUTCDATETIME()),
        CONSTRAINT CK_product_image_candidate_state CHECK (state IN (N'PENDING',N'VERIFIED',N'REJECTED',N'CONFLICT',N'IMPORTED')),
        CONSTRAINT CK_product_image_candidate_exactness CHECK (exactness_policy IN (N'EXACT_PN_REQUIRED',N'MODEL_VARIANT_ALLOWED',N'SAME_PRODUCT_FAMILY_ALLOWED',N'MANUAL_REVIEW')),
        CONSTRAINT CK_product_image_candidate_confidence CHECK (confidence_score IS NULL OR confidence_score BETWEEN 0 AND 100),
        CONSTRAINT CK_product_image_candidate_size CHECK ((image_width_px IS NULL OR image_width_px > 0) AND (image_height_px IS NULL OR image_height_px > 0))
    );
END;
GO

-- source_url can be NVARCHAR(2048), which exceeds SQL Server's 1700-byte
-- nonclustered index key limit. Index a deterministic SHA-256 instead while
-- retaining the complete URL as evidence.
IF COL_LENGTH(N'dbo.product_image_candidate', N'source_url_hash') IS NULL
BEGIN
    ALTER TABLE dbo.product_image_candidate
        ADD source_url_hash AS CONVERT(BINARY(32), HASHBYTES('SHA2_256', CONVERT(VARBINARY(MAX), source_url))) PERSISTED;
END;
GO

IF EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.product_image_candidate') AND name=N'UX_product_image_candidate_url')
BEGIN
    DROP INDEX UX_product_image_candidate_url ON dbo.product_image_candidate;
END;
GO

CREATE UNIQUE INDEX UX_product_image_candidate_url
    ON dbo.product_image_candidate(partnumber, source_url_hash);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.product_image_candidate') AND name=N'IX_product_image_candidate_product_state')
BEGIN
    CREATE INDEX IX_product_image_candidate_product_state ON dbo.product_image_candidate(partnumber, state, confidence_score DESC);
END;
GO

IF OBJECT_ID(N'dbo.image_requirement_policy', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.image_requirement_policy (
        image_requirement_policy_id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_image_requirement_policy PRIMARY KEY,
        channel_code NVARCHAR(80) NOT NULL,
        category_code NVARCHAR(80) NOT NULL,
        version_code NVARCHAR(40) NOT NULL,
        required_min INT NOT NULL CONSTRAINT DF_image_requirement_policy_required DEFAULT(1),
        recommended_min INT NOT NULL CONSTRAINT DF_image_requirement_policy_recommended DEFAULT(4),
        require_main BIT NOT NULL CONSTRAINT DF_image_requirement_policy_main DEFAULT(1),
        min_width_px INT NULL,
        min_height_px INT NULL,
        exactness_policy NVARCHAR(40) NOT NULL CONSTRAINT DF_image_requirement_policy_exactness DEFAULT(N'EXACT_PN_REQUIRED'),
        active BIT NOT NULL CONSTRAINT DF_image_requirement_policy_active DEFAULT(1),
        created_at DATETIME2(0) NOT NULL CONSTRAINT DF_image_requirement_policy_created DEFAULT(SYSUTCDATETIME()),
        updated_at DATETIME2(0) NOT NULL CONSTRAINT DF_image_requirement_policy_updated DEFAULT(SYSUTCDATETIME()),
        CONSTRAINT UQ_image_requirement_policy UNIQUE(channel_code, category_code, version_code),
        CONSTRAINT CK_image_requirement_policy_counts CHECK(required_min >= 0 AND recommended_min >= required_min),
        CONSTRAINT CK_image_requirement_policy_exactness CHECK (exactness_policy IN (N'EXACT_PN_REQUIRED',N'MODEL_VARIANT_ALLOWED',N'SAME_PRODUCT_FAMILY_ALLOWED',N'MANUAL_REVIEW'))
    );
END;
GO

IF NOT EXISTS (SELECT 1 FROM dbo.image_requirement_policy WHERE channel_code=N'MASTER' AND category_code=N'DEFAULT' AND version_code=N'V1')
BEGIN
    INSERT dbo.image_requirement_policy(channel_code, category_code, version_code, required_min, recommended_min, require_main, exactness_policy)
    VALUES(N'MASTER', N'DEFAULT', N'V1', 1, 4, 1, N'EXACT_PN_REQUIRED');
END;
GO
