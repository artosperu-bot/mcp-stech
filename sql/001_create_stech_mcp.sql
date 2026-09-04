IF DB_ID(N'STECH_MCP') IS NULL
BEGIN
    EXEC(N'CREATE DATABASE [STECH_MCP]');
END;
GO

USE [STECH_MCP];
GO

IF OBJECT_ID(N'dbo.product_enrichment', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.product_enrichment (
        enrichment_id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_product_enrichment PRIMARY KEY,
        partnumber NVARCHAR(150) NOT NULL,
        field_code NVARCHAR(100) NOT NULL,
        value_text NVARCHAR(MAX) NULL,
        value_number DECIMAL(18,6) NULL,
        unit NVARCHAR(30) NULL,
        method VARCHAR(20) NOT NULL,
        confidence_grade VARCHAR(2) NOT NULL,
        is_approved BIT NOT NULL CONSTRAINT DF_product_enrichment_is_approved DEFAULT (0),
        created_at DATETIME2(0) NOT NULL CONSTRAINT DF_product_enrichment_created_at DEFAULT (SYSUTCDATETIME()),
        updated_at DATETIME2(0) NOT NULL CONSTRAINT DF_product_enrichment_updated_at DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT UQ_product_enrichment_partnumber_field UNIQUE (partnumber, field_code),
        CONSTRAINT CK_product_enrichment_method CHECK (method IN ('VERIFIED','DERIVED','ESTIMATED','MANUAL')),
        CONSTRAINT CK_product_enrichment_confidence CHECK (confidence_grade IN ('A1','A2','B','C','D','E'))
    );
END;
GO

IF OBJECT_ID(N'dbo.product_evidence', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.product_evidence (
        evidence_id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_product_evidence PRIMARY KEY,
        enrichment_id BIGINT NOT NULL,
        source_url NVARCHAR(2048) NULL,
        source_domain NVARCHAR(255) NULL,
        source_type VARCHAR(30) NOT NULL,
        source_partnumber NVARCHAR(150) NULL,
        evidence_text NVARCHAR(MAX) NULL,
        retrieved_at DATETIME2(0) NOT NULL CONSTRAINT DF_product_evidence_retrieved_at DEFAULT (SYSUTCDATETIME()),
        rank_score INT NOT NULL,
        CONSTRAINT FK_product_evidence_enrichment FOREIGN KEY (enrichment_id)
            REFERENCES dbo.product_enrichment(enrichment_id),
        CONSTRAINT CK_product_evidence_source_type CHECK (
            source_type IN (
                'MANUFACTURER','OFFICIAL_DOCUMENT','AUTHORIZED_DISTRIBUTOR',
                'TRUSTED_RETAILER','SAME_CHASSIS','RULE','MANUAL'
            )
        )
    );
END;
GO

IF OBJECT_ID(N'dbo.coolbox_template_field', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.coolbox_template_field (
        category_code NVARCHAR(80) NOT NULL,
        field_code NVARCHAR(100) NOT NULL,
        excel_column NVARCHAR(10) NULL,
        display_name NVARCHAR(200) NOT NULL,
        required BIT NOT NULL CONSTRAINT DF_coolbox_template_field_required DEFAULT (0),
        data_type VARCHAR(30) NOT NULL,
        unit NVARCHAR(30) NULL,
        allowed_values_json NVARCHAR(MAX) NULL,
        normalization_rule NVARCHAR(200) NULL,
        CONSTRAINT PK_coolbox_template_field PRIMARY KEY (category_code, field_code)
    );
END;
GO

IF OBJECT_ID(N'dbo.enrichment_rule', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.enrichment_rule (
        rule_code NVARCHAR(100) NOT NULL CONSTRAINT PK_enrichment_rule PRIMARY KEY,
        category_code NVARCHAR(80) NOT NULL,
        field_code NVARCHAR(100) NOT NULL,
        priority INT NOT NULL,
        rule_type VARCHAR(30) NOT NULL,
        configuration_json NVARCHAR(MAX) NOT NULL,
        enabled BIT NOT NULL CONSTRAINT DF_enrichment_rule_enabled DEFAULT (1)
    );
END;
GO

IF OBJECT_ID(N'dbo.processing_run', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.processing_run (
        run_id UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_processing_run PRIMARY KEY,
        source_filename NVARCHAR(500) NULL,
        status VARCHAR(30) NOT NULL,
        total_products INT NOT NULL CONSTRAINT DF_processing_run_total DEFAULT (0),
        completed_products INT NOT NULL CONSTRAINT DF_processing_run_completed DEFAULT (0),
        started_at DATETIME2(0) NOT NULL CONSTRAINT DF_processing_run_started DEFAULT (SYSUTCDATETIME()),
        finished_at DATETIME2(0) NULL
    );
END;
GO
