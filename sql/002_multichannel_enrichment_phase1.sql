USE [STECH_MCP];
GO

IF OBJECT_ID(N'dbo.packaging_rule', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.packaging_rule (
        rule_code NVARCHAR(100) NOT NULL CONSTRAINT PK_packaging_rule PRIMARY KEY,
        category_code NVARCHAR(80) NOT NULL,
        screen_min_inches DECIMAL(5,2) NULL,
        screen_max_inches DECIMAL(5,2) NULL,
        width_cm DECIMAL(8,2) NOT NULL,
        length_cm DECIMAL(8,2) NOT NULL,
        height_cm DECIMAL(8,2) NOT NULL,
        weight_g INT NOT NULL,
        priority INT NOT NULL,
        enabled BIT NOT NULL CONSTRAINT DF_packaging_rule_enabled DEFAULT (1),
        source_code NVARCHAR(100) NOT NULL,
        created_at DATETIME2(0) NOT NULL CONSTRAINT DF_packaging_rule_created DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT CK_packaging_rule_dimensions CHECK (
            width_cm > 0 AND length_cm > 0 AND height_cm > 0 AND weight_g > 0
        ),
        CONSTRAINT CK_packaging_rule_screen_range CHECK (
            screen_min_inches IS NULL OR screen_max_inches IS NULL OR screen_min_inches < screen_max_inches
        )
    );
END;
GO

IF NOT EXISTS (SELECT 1 FROM dbo.packaging_rule WHERE rule_code = N'LAPTOP_15_X_DEFAULT')
BEGIN
    INSERT dbo.packaging_rule (
        rule_code, category_code, screen_min_inches, screen_max_inches,
        width_cm, length_cm, height_cm, weight_g, priority, enabled, source_code
    )
    VALUES (
        N'LAPTOP_15_X_DEFAULT', N'LAPTOP', 15.00, 16.00,
        33.00, 54.00, 7.00, 2500, 100, 1, N'REGLA_STECH_EMPAQUE'
    );
END;
GO

IF OBJECT_ID(N'dbo.marketplace_template', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.marketplace_template (
        marketplace_code NVARCHAR(40) NOT NULL,
        template_code NVARCHAR(100) NOT NULL,
        template_version NVARCHAR(40) NOT NULL,
        category_code NVARCHAR(80) NOT NULL,
        active BIT NOT NULL CONSTRAINT DF_marketplace_template_active DEFAULT (1),
        created_at DATETIME2(0) NOT NULL CONSTRAINT DF_marketplace_template_created DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT PK_marketplace_template PRIMARY KEY (
            marketplace_code, template_code, template_version, category_code
        )
    );
END;
GO

IF OBJECT_ID(N'dbo.marketplace_template_field', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.marketplace_template_field (
        marketplace_code NVARCHAR(40) NOT NULL,
        template_code NVARCHAR(100) NOT NULL,
        template_version NVARCHAR(40) NOT NULL,
        category_code NVARCHAR(80) NOT NULL,
        field_code NVARCHAR(100) NOT NULL,
        excel_column NVARCHAR(10) NULL,
        json_path NVARCHAR(500) NULL,
        display_name NVARCHAR(200) NOT NULL,
        required BIT NOT NULL CONSTRAINT DF_marketplace_template_field_required DEFAULT (0),
        data_type VARCHAR(30) NOT NULL,
        unit NVARCHAR(30) NULL,
        allowed_values_json NVARCHAR(MAX) NULL,
        normalization_rule NVARCHAR(500) NULL,
        CONSTRAINT PK_marketplace_template_field PRIMARY KEY (
            marketplace_code, template_code, template_version, category_code, field_code
        ),
        CONSTRAINT FK_marketplace_template_field_template FOREIGN KEY (
            marketplace_code, template_code, template_version, category_code
        ) REFERENCES dbo.marketplace_template (
            marketplace_code, template_code, template_version, category_code
        )
    );
END;
GO

IF OBJECT_ID(N'dbo.marketplace_field_mapping', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.marketplace_field_mapping (
        marketplace_code NVARCHAR(40) NOT NULL,
        template_code NVARCHAR(100) NOT NULL,
        template_version NVARCHAR(40) NOT NULL,
        category_code NVARCHAR(80) NOT NULL,
        target_field_code NVARCHAR(100) NOT NULL,
        master_field_code NVARCHAR(100) NULL,
        transform_rule NVARCHAR(500) NULL,
        priority INT NOT NULL CONSTRAINT DF_marketplace_field_mapping_priority DEFAULT (100),
        enabled BIT NOT NULL CONSTRAINT DF_marketplace_field_mapping_enabled DEFAULT (1),
        CONSTRAINT PK_marketplace_field_mapping PRIMARY KEY (
            marketplace_code, template_code, template_version, category_code,
            target_field_code, priority
        )
    );
END;
GO

IF OBJECT_ID(N'dbo.marketplace_product_override', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.marketplace_product_override (
        marketplace_code NVARCHAR(40) NOT NULL,
        partnumber NVARCHAR(150) NOT NULL,
        field_code NVARCHAR(100) NOT NULL,
        override_value NVARCHAR(MAX) NULL,
        reason NVARCHAR(1000) NULL,
        approved BIT NOT NULL CONSTRAINT DF_marketplace_product_override_approved DEFAULT (0),
        created_at DATETIME2(0) NOT NULL CONSTRAINT DF_marketplace_product_override_created DEFAULT (SYSUTCDATETIME()),
        updated_at DATETIME2(0) NOT NULL CONSTRAINT DF_marketplace_product_override_updated DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT PK_marketplace_product_override PRIMARY KEY (marketplace_code, partnumber, field_code)
    );
END;
GO

IF OBJECT_ID(N'dbo.marketplace_export_run', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.marketplace_export_run (
        export_id UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_marketplace_export_run PRIMARY KEY,
        marketplace_code NVARCHAR(40) NOT NULL,
        template_code NVARCHAR(100) NOT NULL,
        template_version NVARCHAR(40) NOT NULL,
        category_code NVARCHAR(80) NOT NULL,
        product_count INT NOT NULL CONSTRAINT DF_marketplace_export_run_product_count DEFAULT (0),
        status VARCHAR(30) NOT NULL,
        source_filename NVARCHAR(500) NULL,
        output_filename NVARCHAR(500) NULL,
        started_at DATETIME2(0) NOT NULL CONSTRAINT DF_marketplace_export_run_started DEFAULT (SYSUTCDATETIME()),
        finished_at DATETIME2(0) NULL
    );
END;
GO
