SET NOCOUNT ON;
SET XACT_ABORT ON;

/*
Product Work Queue V2
---------------------
Cola persistente genérica para trabajos largos de producto.

IMPORTANTE:
- NO reemplaza ni altera dbo.product_loader_job / dbo.product_loader_job_item.
- El flujo Product Loader / VTEX existente sigue siendo independiente.
- ENRICH_TECHNICAL no contiene ni administra precio o stock.
*/

IF OBJECT_ID(N'dbo.product_work_job', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.product_work_job (
        product_work_job_id BIGINT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_product_work_job PRIMARY KEY,
        work_type NVARCHAR(40) NOT NULL,
        source_name NVARCHAR(260) NOT NULL,
        actor_source NVARCHAR(80) NOT NULL
            CONSTRAINT DF_product_work_job_actor DEFAULT N'MCP',
        status NVARCHAR(40) NOT NULL
            CONSTRAINT DF_product_work_job_status DEFAULT N'PENDING',
        priority INT NOT NULL
            CONSTRAINT DF_product_work_job_priority DEFAULT 50,
        total_items INT NOT NULL
            CONSTRAINT DF_product_work_job_total DEFAULT 0,
        completed_items INT NOT NULL
            CONSTRAINT DF_product_work_job_completed DEFAULT 0,
        review_items INT NOT NULL
            CONSTRAINT DF_product_work_job_review DEFAULT 0,
        failed_items INT NOT NULL
            CONSTRAINT DF_product_work_job_failed DEFAULT 0,
        created_at DATETIME2(3) NOT NULL
            CONSTRAINT DF_product_work_job_created DEFAULT SYSUTCDATETIME(),
        started_at DATETIME2(3) NULL,
        finished_at DATETIME2(3) NULL,
        updated_at DATETIME2(3) NOT NULL
            CONSTRAINT DF_product_work_job_updated DEFAULT SYSUTCDATETIME(),
        CONSTRAINT CK_product_work_job_work_type CHECK (work_type IN (
            N'ENRICH_TECHNICAL',
            N'RESEARCH_IDENTITY',
            N'RESEARCH_IMAGES',
            N'PREPARE_CHANNEL',
            N'PUBLISH_CHANNEL'
        )),
        CONSTRAINT CK_product_work_job_status CHECK (status IN (
            N'PENDING', N'RUNNING', N'WAITING_REVIEW', N'COMPLETED',
            N'PARTIAL', N'FAILED', N'CANCELLED'
        )),
        CONSTRAINT CK_product_work_job_priority CHECK (priority BETWEEN 0 AND 100),
        CONSTRAINT CK_product_work_job_counts CHECK (
            total_items >= 0 AND completed_items >= 0
            AND review_items >= 0 AND failed_items >= 0
        )
    );
END;

IF OBJECT_ID(N'dbo.product_work_item', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.product_work_item (
        product_work_item_id BIGINT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_product_work_item PRIMARY KEY,
        product_work_job_id BIGINT NOT NULL,
        work_type NVARCHAR(40) NOT NULL,
        partnumber NVARCHAR(160) NOT NULL,
        category_code NVARCHAR(80) NULL,
        channel_code NVARCHAR(80) NULL,
        source_row_number INT NULL,
        context_hash CHAR(64) NOT NULL,
        input_json NVARCHAR(MAX) NOT NULL,
        status NVARCHAR(40) NOT NULL
            CONSTRAINT DF_product_work_item_status DEFAULT N'QUEUED',
        current_step NVARCHAR(100) NULL,
        progress_pct TINYINT NOT NULL
            CONSTRAINT DF_product_work_item_progress DEFAULT 0,
        priority INT NOT NULL
            CONSTRAINT DF_product_work_item_priority DEFAULT 50,
        attempt_count INT NOT NULL
            CONSTRAINT DF_product_work_item_attempt DEFAULT 0,
        max_attempts INT NOT NULL
            CONSTRAINT DF_product_work_item_max_attempts DEFAULT 3,
        next_attempt_at DATETIME2(3) NULL,
        claimed_by NVARCHAR(160) NULL,
        claimed_at DATETIME2(3) NULL,
        claim_expires_at DATETIME2(3) NULL,
        last_error_code NVARCHAR(100) NULL,
        last_error_detail NVARCHAR(2000) NULL,
        completed_at DATETIME2(3) NULL,
        created_at DATETIME2(3) NOT NULL
            CONSTRAINT DF_product_work_item_created DEFAULT SYSUTCDATETIME(),
        updated_at DATETIME2(3) NOT NULL
            CONSTRAINT DF_product_work_item_updated DEFAULT SYSUTCDATETIME(),
        active_work_key AS (
            CASE
                WHEN status IN (
                    N'COMPLETED', N'PARTIAL', N'REVIEW_REQUIRED', N'NO_DATA_FOUND',
                    N'FAILED', N'CANCELLED'
                ) THEN NULL
                ELSE CONVERT(NVARCHAR(260), UPPER(LTRIM(RTRIM(partnumber))) + N'|' + context_hash)
            END
        ) PERSISTED,
        CONSTRAINT FK_product_work_item_job FOREIGN KEY (product_work_job_id)
            REFERENCES dbo.product_work_job(product_work_job_id),
        CONSTRAINT CK_product_work_item_work_type CHECK (work_type IN (
            N'ENRICH_TECHNICAL',
            N'RESEARCH_IDENTITY',
            N'RESEARCH_IMAGES',
            N'PREPARE_CHANNEL',
            N'PUBLISH_CHANNEL'
        )),
        CONSTRAINT CK_product_work_item_status CHECK (status IN (
            N'QUEUED',
            N'LOADING_SOURCE_DATA',
            N'ANALYZING_MISSING_FIELDS',
            N'RESEARCHING',
            N'READING_DOCUMENTS',
            N'VALIDATING',
            N'PROMOTING_FACTS',
            N'REBUILDING_PRODUCT_MASTER',
            N'COMPLETED',
            N'PARTIAL',
            N'REVIEW_REQUIRED',
            N'NO_DATA_FOUND',
            N'FAILED_RETRYABLE',
            N'FAILED',
            N'CANCELLED'
        )),
        CONSTRAINT CK_product_work_item_progress CHECK (progress_pct BETWEEN 0 AND 100),
        CONSTRAINT CK_product_work_item_priority CHECK (priority BETWEEN 0 AND 100),
        CONSTRAINT CK_product_work_item_attempt CHECK (
            attempt_count >= 0 AND max_attempts > 0 AND attempt_count <= max_attempts
        ),
        CONSTRAINT CK_product_work_item_source_row CHECK (
            source_row_number IS NULL OR source_row_number > 0
        )
    );
END;

IF OBJECT_ID(N'dbo.product_work_event', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.product_work_event (
        product_work_event_id BIGINT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_product_work_event PRIMARY KEY,
        product_work_job_id BIGINT NOT NULL,
        product_work_item_id BIGINT NULL,
        partnumber NVARCHAR(160) NULL,
        event_type NVARCHAR(100) NOT NULL,
        actor_source NVARCHAR(80) NOT NULL
            CONSTRAINT DF_product_work_event_actor DEFAULT N'MCP',
        status NVARCHAR(40) NULL,
        detail_json NVARCHAR(MAX) NULL,
        created_at DATETIME2(3) NOT NULL
            CONSTRAINT DF_product_work_event_created DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_product_work_event_job FOREIGN KEY (product_work_job_id)
            REFERENCES dbo.product_work_job(product_work_job_id),
        CONSTRAINT FK_product_work_event_item FOREIGN KEY (product_work_item_id)
            REFERENCES dbo.product_work_item(product_work_item_id)
    );
END;

IF OBJECT_ID(N'dbo.product_work_attempt', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.product_work_attempt (
        product_work_attempt_id BIGINT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_product_work_attempt PRIMARY KEY,
        product_work_job_id BIGINT NOT NULL,
        product_work_item_id BIGINT NOT NULL,
        attempt_number INT NOT NULL,
        worker_id NVARCHAR(160) NOT NULL,
        started_at DATETIME2(3) NOT NULL
            CONSTRAINT DF_product_work_attempt_started DEFAULT SYSUTCDATETIME(),
        finished_at DATETIME2(3) NULL,
        outcome_status NVARCHAR(40) NULL,
        error_code NVARCHAR(100) NULL,
        error_detail NVARCHAR(2000) NULL,
        detail_json NVARCHAR(MAX) NULL,
        CONSTRAINT FK_product_work_attempt_job FOREIGN KEY (product_work_job_id)
            REFERENCES dbo.product_work_job(product_work_job_id),
        CONSTRAINT FK_product_work_attempt_item FOREIGN KEY (product_work_item_id)
            REFERENCES dbo.product_work_item(product_work_item_id),
        CONSTRAINT UQ_product_work_attempt_number UNIQUE (
            product_work_item_id, attempt_number
        ),
        CONSTRAINT CK_product_work_attempt_number CHECK (attempt_number > 0)
    );
END;

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.product_work_item')
      AND name = N'UX_product_work_item_active_key'
)
BEGIN
    -- SQL Server permits computed columns in index keys, but not in a filtered
    -- index predicate. Enforce the same active-work uniqueness using the base
    -- columns and a filter on the normal status column.
    CREATE UNIQUE INDEX UX_product_work_item_active_key
        ON dbo.product_work_item(partnumber, context_hash)
        WHERE status IN (
            N'QUEUED',
            N'LOADING_SOURCE_DATA',
            N'ANALYZING_MISSING_FIELDS',
            N'RESEARCHING',
            N'READING_DOCUMENTS',
            N'VALIDATING',
            N'PROMOTING_FACTS',
            N'REBUILDING_PRODUCT_MASTER',
            N'FAILED_RETRYABLE'
        );
END;

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.product_work_item')
      AND name = N'IX_product_work_item_claim'
)
BEGIN
    CREATE INDEX IX_product_work_item_claim
        ON dbo.product_work_item(
            status,
            next_attempt_at,
            priority DESC,
            product_work_item_id
        )
        INCLUDE (
            work_type,
            partnumber,
            category_code,
            channel_code,
            claimed_by,
            claim_expires_at,
            attempt_count,
            max_attempts
        );
END;

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.product_work_item')
      AND name = N'IX_product_work_item_job_status'
)
BEGIN
    CREATE INDEX IX_product_work_item_job_status
        ON dbo.product_work_item(product_work_job_id, status, product_work_item_id)
        INCLUDE (partnumber, progress_pct, current_step, updated_at);
END;

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.product_work_event')
      AND name = N'IX_product_work_event_job_item'
)
BEGIN
    CREATE INDEX IX_product_work_event_job_item
        ON dbo.product_work_event(
            product_work_job_id,
            product_work_item_id,
            product_work_event_id
        );
END;

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.product_work_attempt')
      AND name = N'IX_product_work_attempt_item'
)
BEGIN
    CREATE INDEX IX_product_work_attempt_item
        ON dbo.product_work_attempt(product_work_item_id, product_work_attempt_id);
END;
