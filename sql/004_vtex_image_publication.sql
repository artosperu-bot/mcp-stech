USE [STECH_MCP];
GO

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'dbo.product_image_publication', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.product_image_publication (
        product_image_publication_id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_product_image_publication PRIMARY KEY,
        product_image_id BIGINT NOT NULL,
        partnumber NVARCHAR(120) NOT NULL,
        channel NVARCHAR(40) NOT NULL,
        account_code NVARCHAR(80) NOT NULL,
        remote_product_id BIGINT NULL,
        remote_sku_id BIGINT NOT NULL,
        remote_file_id BIGINT NULL,
        remote_archive_id BIGINT NULL,
        remote_url NVARCHAR(2000) NULL,
        position INT NOT NULL,
        is_main BIT NOT NULL CONSTRAINT DF_product_image_publication_main DEFAULT (0),
        status NVARCHAR(40) NOT NULL CONSTRAINT DF_product_image_publication_status DEFAULT (N'PENDING'),
        last_error NVARCHAR(4000) NULL,
        uploaded_at DATETIME2(0) NULL,
        last_verified_at DATETIME2(0) NULL,
        created_at DATETIME2(0) NOT NULL CONSTRAINT DF_product_image_publication_created DEFAULT (SYSUTCDATETIME()),
        updated_at DATETIME2(0) NOT NULL CONSTRAINT DF_product_image_publication_updated DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT FK_product_image_publication_image FOREIGN KEY (product_image_id)
            REFERENCES dbo.product_image(product_image_id),
        CONSTRAINT UQ_product_image_publication_remote UNIQUE (channel, account_code, remote_sku_id, product_image_id),
        CONSTRAINT CK_product_image_publication_position CHECK (position > 0),
        CONSTRAINT CK_product_image_publication_status CHECK (status IN (N'PENDING', N'UPLOADED', N'VERIFIED', N'ERROR'))
    );
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.product_image_publication')
      AND name = N'IX_product_image_publication_partnumber_status'
)
BEGIN
    CREATE INDEX IX_product_image_publication_partnumber_status
        ON dbo.product_image_publication(partnumber, account_code, status, position);
END;
GO
