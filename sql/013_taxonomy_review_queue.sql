USE [STECH_MCP];
GO

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
SET XACT_ABORT ON;
GO

IF OBJECT_ID(N'dbo.taxonomy_review', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.taxonomy_review (
        taxonomy_review_id BIGINT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_taxonomy_review PRIMARY KEY,
        producto_distribuidor_id BIGINT NOT NULL,
        distributor_code NVARCHAR(40) NULL,
        partnumber NVARCHAR(120) NULL,
        brand NVARCHAR(120) NULL,
        product_name NVARCHAR(1000) NULL,
        current_category NVARCHAR(160) NULL,
        current_subcategory NVARCHAR(200) NULL,
        proposed_category NVARCHAR(160) NULL,
        proposed_subcategory NVARCHAR(200) NULL,
        proposal_kind VARCHAR(30) NULL,
        confidence VARCHAR(20) NULL,
        reason NVARCHAR(1500) NULL,
        evidence_json NVARCHAR(MAX) NULL,
        status VARCHAR(30) NOT NULL
            CONSTRAINT DF_taxonomy_review_status DEFAULT ('PENDING'),
        proposed_by NVARCHAR(120) NULL,
        approved_by NVARCHAR(120) NULL,
        applied_by NVARCHAR(120) NULL,
        source_observed_at DATETIME2(0) NULL,
        detected_at DATETIME2(0) NOT NULL
            CONSTRAINT DF_taxonomy_review_detected DEFAULT (SYSUTCDATETIME()),
        last_detected_at DATETIME2(0) NOT NULL
            CONSTRAINT DF_taxonomy_review_last_detected DEFAULT (SYSUTCDATETIME()),
        proposed_at DATETIME2(0) NULL,
        approved_at DATETIME2(0) NULL,
        applied_at DATETIME2(0) NULL,
        updated_at DATETIME2(0) NOT NULL
            CONSTRAINT DF_taxonomy_review_updated DEFAULT (SYSUTCDATETIME()),
        last_error NVARCHAR(1900) NULL,
        CONSTRAINT UQ_taxonomy_review_source_product UNIQUE (producto_distribuidor_id),
        CONSTRAINT CK_taxonomy_review_status CHECK (
            status IN (
                'PENDING','PROPOSED','APPROVED','APPLIED',
                'REJECTED','RESOLVED_EXTERNALLY','ERROR'
            )
        ),
        CONSTRAINT CK_taxonomy_review_kind CHECK (
            proposal_kind IS NULL OR proposal_kind IN (
                'EXISTING_PAIR','NEW_SUBCATEGORY','NEW_CATEGORY'
            )
        ),
        CONSTRAINT CK_taxonomy_review_confidence CHECK (
            confidence IS NULL OR confidence IN ('ALTA','MEDIA','BAJA')
        )
    );
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.taxonomy_review')
      AND name = N'IX_taxonomy_review_status'
)
BEGIN
    CREATE INDEX IX_taxonomy_review_status
        ON dbo.taxonomy_review(status, updated_at, taxonomy_review_id)
        INCLUDE(producto_distribuidor_id, partnumber, proposed_category, proposed_subcategory);
END;
GO
