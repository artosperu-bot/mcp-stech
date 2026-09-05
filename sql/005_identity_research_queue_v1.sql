USE [STECH_MCP];
GO

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'dbo.product_identity_research', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.product_identity_research (
        research_id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_product_identity_research PRIMARY KEY,
        producto_distribuidor_id BIGINT NOT NULL,
        partnumber NVARCHAR(120) NOT NULL,
        identifier_type NVARCHAR(10) NOT NULL,
        status NVARCHAR(40) NOT NULL CONSTRAINT DF_product_identity_research_status DEFAULT (N'PENDING'),
        attempt_count INT NOT NULL CONSTRAINT DF_product_identity_research_attempts DEFAULT (0),
        value_text NVARCHAR(32) NULL,
        confidence_grade NVARCHAR(20) NULL,
        source_type NVARCHAR(80) NULL,
        source_url NVARCHAR(2000) NULL,
        source_partnumber NVARCHAR(120) NULL,
        evidence_text NVARCHAR(2000) NULL,
        note NVARCHAR(2000) NULL,
        last_error NVARCHAR(2000) NULL,
        actor_source NVARCHAR(120) NULL,
        created_at DATETIME2(0) NOT NULL CONSTRAINT DF_product_identity_research_created DEFAULT (SYSUTCDATETIME()),
        updated_at DATETIME2(0) NOT NULL CONSTRAINT DF_product_identity_research_updated DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT UQ_product_identity_research UNIQUE (producto_distribuidor_id, identifier_type),
        CONSTRAINT CK_product_identity_research_type CHECK (identifier_type IN (N'EAN', N'UPC', N'GTIN')),
        CONSTRAINT CK_product_identity_research_status CHECK (
            status IN (
                N'PENDING', N'RESEARCHING', N'VERIFIED', N'PROMOTED',
                N'NO_ENCONTRADO', N'RESEARCH_REQUIRED', N'CONFLICTO',
                N'INVALID_IDENTITY', N'ERROR'
            )
        ),
        CONSTRAINT CK_product_identity_research_attempts CHECK (attempt_count >= 0)
    );
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.product_identity_research')
      AND name = N'IX_product_identity_research_status'
)
BEGIN
    CREATE INDEX IX_product_identity_research_status
        ON dbo.product_identity_research(status, producto_distribuidor_id, identifier_type)
        INCLUDE (partnumber, attempt_count, updated_at);
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.product_identity_research')
      AND name = N'IX_product_identity_research_partnumber'
)
BEGIN
    CREATE INDEX IX_product_identity_research_partnumber
        ON dbo.product_identity_research(partnumber, identifier_type, status);
END;
GO
