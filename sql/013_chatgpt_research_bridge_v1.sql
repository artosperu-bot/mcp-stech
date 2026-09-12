SET NOCOUNT ON;
SET XACT_ABORT ON;

-- Required by SQL Server for filtered indexes. Keep these explicit so the
-- migration behaves the same from sqlcmd, SSMS, or any other client session.
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
SET ANSI_PADDING ON;
SET ANSI_WARNINGS ON;
SET ARITHABORT ON;
SET CONCAT_NULL_YIELDS_NULL ON;
SET NUMERIC_ROUNDABORT OFF;

/*
ChatGPT Research Bridge V1
--------------------------
Adds the non-terminal WAITING_EXTERNAL_RESEARCH state used when a Product Work
item needs scheduled ChatGPT research. The state remains part of active-work
deduplication and must not mark completed_at.
*/

IF OBJECT_ID(N'dbo.product_work_item', N'U') IS NULL
    THROW 51000, 'dbo.product_work_item does not exist. Apply 006_product_work_queue_v2.sql first.', 1;

BEGIN TRANSACTION;

IF EXISTS (
    SELECT 1
    FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.product_work_item')
      AND name = N'CK_product_work_item_status'
)
BEGIN
    ALTER TABLE dbo.product_work_item DROP CONSTRAINT CK_product_work_item_status;
END;

ALTER TABLE dbo.product_work_item WITH CHECK
ADD CONSTRAINT CK_product_work_item_status CHECK (status IN (
    N'QUEUED',
    N'LOADING_SOURCE_DATA',
    N'ANALYZING_MISSING_FIELDS',
    N'RESEARCHING',
    N'READING_DOCUMENTS',
    N'VALIDATING',
    N'PROMOTING_FACTS',
    N'REBUILDING_PRODUCT_MASTER',
    N'WAITING_EXTERNAL_RESEARCH',
    N'COMPLETED',
    N'PARTIAL',
    N'REVIEW_REQUIRED',
    N'NO_DATA_FOUND',
    N'FAILED_RETRYABLE',
    N'FAILED',
    N'CANCELLED'
));

IF EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.product_work_item')
      AND name = N'UX_product_work_item_active_key'
)
BEGIN
    DROP INDEX UX_product_work_item_active_key ON dbo.product_work_item;
END;

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
        N'WAITING_EXTERNAL_RESEARCH',
        N'FAILED_RETRYABLE'
    );

COMMIT TRANSACTION;
