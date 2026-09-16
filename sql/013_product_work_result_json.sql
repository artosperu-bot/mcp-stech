USE [STECH_MCP];
GO

IF COL_LENGTH(N'dbo.product_work_item', N'result_json') IS NULL
BEGIN
    ALTER TABLE dbo.product_work_item
    ADD result_json NVARCHAR(MAX) NULL;
END;
GO
