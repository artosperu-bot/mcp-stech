USE [STECH_MCP];
GO

IF OBJECT_ID(N'dbo.source_document', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.source_document (
        source_document_id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_source_document PRIMARY KEY,
        sha256 VARCHAR(64) NOT NULL,
        url NVARCHAR(2048) NOT NULL,
        document_type VARCHAR(40) NOT NULL,
        title NVARCHAR(500) NULL,
        content_type NVARCHAR(150) NULL,
        content_length BIGINT NULL,
        extracted_text NVARCHAR(MAX) NULL,
        page_text_json NVARCHAR(MAX) NULL,
        downloaded_at DATETIME2(0) NOT NULL CONSTRAINT DF_source_document_downloaded DEFAULT (SYSUTCDATETIME()),
        created_at DATETIME2(0) NOT NULL CONSTRAINT DF_source_document_created DEFAULT (SYSUTCDATETIME()),
        updated_at DATETIME2(0) NOT NULL CONSTRAINT DF_source_document_updated DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT UQ_source_document_sha256 UNIQUE (sha256),
        CONSTRAINT CK_source_document_length CHECK (content_length IS NULL OR content_length >= 0)
    );
END;
GO

IF OBJECT_ID(N'dbo.source_document_match', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.source_document_match (
        source_document_match_id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_source_document_match PRIMARY KEY,
        source_document_id BIGINT NOT NULL,
        partnumber NVARCHAR(120) NOT NULL,
        match_type VARCHAR(40) NOT NULL,
        matched_pages_json NVARCHAR(MAX) NULL,
        confidence_rank VARCHAR(10) NOT NULL,
        created_at DATETIME2(0) NOT NULL CONSTRAINT DF_source_document_match_created DEFAULT (SYSUTCDATETIME()),
        updated_at DATETIME2(0) NOT NULL CONSTRAINT DF_source_document_match_updated DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT FK_source_document_match_document FOREIGN KEY (source_document_id)
            REFERENCES dbo.source_document(source_document_id),
        CONSTRAINT UQ_source_document_match UNIQUE (source_document_id, partnumber)
    );
END;
GO

IF OBJECT_ID(N'dbo.product_fact_candidate', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.product_fact_candidate (
        product_fact_candidate_id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_product_fact_candidate PRIMARY KEY,
        partnumber NVARCHAR(120) NOT NULL,
        field_code NVARCHAR(100) NOT NULL,
        raw_value_text NVARCHAR(MAX) NULL,
        normalized_value_json NVARCHAR(MAX) NOT NULL,
        unit NVARCHAR(40) NULL,
        source_type VARCHAR(60) NOT NULL,
        source_name NVARCHAR(300) NULL,
        source_url NVARCHAR(2048) NULL,
        source_partnumber NVARCHAR(120) NULL,
        evidence_text NVARCHAR(MAX) NULL,
        page_number INT NULL,
        confidence_rank VARCHAR(10) NOT NULL,
        state VARCHAR(20) NOT NULL CONSTRAINT DF_product_fact_candidate_state DEFAULT ('PENDING'),
        source_document_id BIGINT NULL,
        created_at DATETIME2(0) NOT NULL CONSTRAINT DF_product_fact_candidate_created DEFAULT (SYSUTCDATETIME()),
        updated_at DATETIME2(0) NOT NULL CONSTRAINT DF_product_fact_candidate_updated DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT FK_product_fact_candidate_document FOREIGN KEY (source_document_id)
            REFERENCES dbo.source_document(source_document_id),
        CONSTRAINT CK_product_fact_candidate_state CHECK (
            state IN ('PENDING', 'VERIFIED', 'REJECTED', 'CONFLICT', 'PROMOTED')
        ),
        CONSTRAINT CK_product_fact_candidate_page CHECK (page_number IS NULL OR page_number > 0)
    );
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.source_document_match')
      AND name = N'IX_source_document_match_partnumber'
)
BEGIN
    CREATE INDEX IX_source_document_match_partnumber
        ON dbo.source_document_match(partnumber, confidence_rank);
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.product_fact_candidate')
      AND name = N'IX_product_fact_candidate_product_field'
)
BEGIN
    CREATE INDEX IX_product_fact_candidate_product_field
        ON dbo.product_fact_candidate(partnumber, field_code, state, confidence_rank);
END;
GO
