SET NOCOUNT ON;
SET XACT_ABORT ON;

IF OBJECT_ID(N'dbo.product_loader_job', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.product_loader_job (
        product_loader_job_id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_product_loader_job PRIMARY KEY,
        source_name NVARCHAR(260) NOT NULL,
        channel NVARCHAR(40) NOT NULL CONSTRAINT DF_product_loader_job_channel DEFAULT N'VTEX',
        actor_source NVARCHAR(80) NOT NULL CONSTRAINT DF_product_loader_job_actor DEFAULT N'SCR_UI',
        status NVARCHAR(40) NOT NULL CONSTRAINT DF_product_loader_job_status DEFAULT N'PENDING',
        total_items INT NOT NULL CONSTRAINT DF_product_loader_job_total DEFAULT 0,
        completed_items INT NOT NULL CONSTRAINT DF_product_loader_job_completed DEFAULT 0,
        review_items INT NOT NULL CONSTRAINT DF_product_loader_job_review DEFAULT 0,
        blocked_items INT NOT NULL CONSTRAINT DF_product_loader_job_blocked DEFAULT 0,
        failed_items INT NOT NULL CONSTRAINT DF_product_loader_job_failed DEFAULT 0,
        created_at DATETIME2(3) NOT NULL CONSTRAINT DF_product_loader_job_created DEFAULT SYSUTCDATETIME(),
        started_at DATETIME2(3) NULL,
        finished_at DATETIME2(3) NULL,
        updated_at DATETIME2(3) NOT NULL CONSTRAINT DF_product_loader_job_updated DEFAULT SYSUTCDATETIME(),
        CONSTRAINT CK_product_loader_job_status CHECK (status IN (
            N'PENDING', N'RUNNING', N'WAITING_REVIEW', N'COMPLETED', N'PARTIAL', N'FAILED', N'CANCELLED'
        ))
    );
END;

IF OBJECT_ID(N'dbo.product_loader_job_item', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.product_loader_job_item (
        product_loader_job_item_id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_product_loader_job_item PRIMARY KEY,
        product_loader_job_id BIGINT NOT NULL,
        row_number INT NOT NULL,
        partnumber NVARCHAR(160) NOT NULL,
        input_json NVARCHAR(MAX) NOT NULL,
        status NVARCHAR(40) NOT NULL CONSTRAINT DF_product_loader_job_item_status DEFAULT N'PENDING',
        current_step NVARCHAR(80) NULL,
        retry_count INT NOT NULL CONSTRAINT DF_product_loader_job_item_retry DEFAULT 0,
        product_id_vtex BIGINT NULL,
        sku_id_vtex BIGINT NULL,
        product_ref_id_vtex NVARCHAR(160) NULL,
        sku_ref_id_vtex NVARCHAR(180) NULL,
        last_error_code NVARCHAR(80) NULL,
        last_error_detail NVARCHAR(2000) NULL,
        claimed_at DATETIME2(3) NULL,
        completed_at DATETIME2(3) NULL,
        created_at DATETIME2(3) NOT NULL CONSTRAINT DF_product_loader_job_item_created DEFAULT SYSUTCDATETIME(),
        updated_at DATETIME2(3) NOT NULL CONSTRAINT DF_product_loader_job_item_updated DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_product_loader_job_item_job FOREIGN KEY (product_loader_job_id)
            REFERENCES dbo.product_loader_job(product_loader_job_id),
        CONSTRAINT UQ_product_loader_job_item_row UNIQUE (product_loader_job_id, row_number),
        CONSTRAINT CK_product_loader_job_item_row CHECK (row_number > 0),
        CONSTRAINT CK_product_loader_job_item_retry CHECK (retry_count >= 0),
        CONSTRAINT CK_product_loader_job_item_status CHECK (status IN (
            N'PENDING', N'VALIDATING', N'PREPARING', N'IMAGES_LOCAL', N'RESEARCH_REQUIRED',
            N'VTEX_CHECK', N'VTEX_CREATE_PRODUCT', N'VTEX_CREATE_SKU', N'VTEX_IMAGES',
            N'VERIFYING', N'COMPLETED', N'REVIEW_REQUIRED', N'BLOCKED', N'FAILED'
        ))
    );
END;

IF OBJECT_ID(N'dbo.product_loader_job_event', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.product_loader_job_event (
        product_loader_job_event_id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_product_loader_job_event PRIMARY KEY,
        product_loader_job_id BIGINT NOT NULL,
        product_loader_job_item_id BIGINT NULL,
        partnumber NVARCHAR(160) NULL,
        event_type NVARCHAR(80) NOT NULL,
        actor_source NVARCHAR(80) NOT NULL CONSTRAINT DF_product_loader_job_event_actor DEFAULT N'MCP',
        status NVARCHAR(40) NULL,
        detail_json NVARCHAR(MAX) NULL,
        created_at DATETIME2(3) NOT NULL CONSTRAINT DF_product_loader_job_event_created DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_product_loader_job_event_job FOREIGN KEY (product_loader_job_id)
            REFERENCES dbo.product_loader_job(product_loader_job_id),
        CONSTRAINT FK_product_loader_job_event_item FOREIGN KEY (product_loader_job_item_id)
            REFERENCES dbo.product_loader_job_item(product_loader_job_item_id)
    );
END;

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.product_loader_job_item')
      AND name = N'IX_product_loader_job_item_job_status'
)
BEGIN
    CREATE INDEX IX_product_loader_job_item_job_status
        ON dbo.product_loader_job_item(product_loader_job_id, status, product_loader_job_item_id)
        INCLUDE (partnumber, row_number, product_id_vtex, sku_id_vtex, updated_at);
END;

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.product_loader_job_event')
      AND name = N'IX_product_loader_job_event_job_item'
)
BEGIN
    CREATE INDEX IX_product_loader_job_event_job_item
        ON dbo.product_loader_job_event(product_loader_job_id, product_loader_job_item_id, product_loader_job_event_id);
END;
