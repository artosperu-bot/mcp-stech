/*
  Ejecutar EN LA BASE OPERATIVA DEL ERP (ej. DB_ST).

  Objetivo:
  Crear dbo.V_MCP_PRODUCTO usando el último registro disponible de
  dbo.HST_PRODUCTO_OBSERVACION por producto_distribuidor_id.

  Seguridad:
  - No modifica filas de negocio.
  - Solo crea/altera una VIEW.
  - Antes valida que existan todas las columnas requeridas.
*/

SET NOCOUNT ON;

DECLARE @missing NVARCHAR(MAX);

;WITH required_columns AS (
    SELECT N'producto_distribuidor_id' AS column_name UNION ALL
    SELECT N'observado_at' UNION ALL
    SELECT N'partnumber' UNION ALL
    SELECT N'minicodigo' UNION ALL
    SELECT N'marca' UNION ALL
    SELECT N'familia' UNION ALL
    SELECT N'nombre' UNION ALL
    SELECT N'precio_usd_sin_igv' UNION ALL
    SELECT N'stock_valor'
), missing_columns AS (
    SELECT r.column_name
    FROM required_columns AS r
    WHERE COL_LENGTH(N'dbo.HST_PRODUCTO_OBSERVACION', r.column_name) IS NULL
)
SELECT @missing = STRING_AGG(column_name, N', ')
FROM missing_columns;

IF OBJECT_ID(N'dbo.HST_PRODUCTO_OBSERVACION', N'U') IS NULL
BEGIN
    THROW 51000, 'No existe dbo.HST_PRODUCTO_OBSERVACION en la base actual.', 1;
END;

IF @missing IS NOT NULL
BEGIN
    DECLARE @message NVARCHAR(2048) = N'No se crea V_MCP_PRODUCTO. Faltan columnas en HST_PRODUCTO_OBSERVACION: ' + @missing;
    THROW 51001, @message, 1;
END;
GO

CREATE OR ALTER VIEW dbo.V_MCP_PRODUCTO
AS
WITH ranked AS (
    SELECT
        h.producto_distribuidor_id,
        h.partnumber,
        h.minicodigo,
        h.marca,
        h.familia,
        h.nombre,
        h.precio_usd_sin_igv,
        h.stock_valor,
        h.observado_at,
        ROW_NUMBER() OVER (
            PARTITION BY h.producto_distribuidor_id
            ORDER BY h.observado_at DESC
        ) AS rn
    FROM dbo.HST_PRODUCTO_OBSERVACION AS h
    WHERE h.partnumber IS NOT NULL
)
SELECT
    producto_distribuidor_id,
    partnumber,
    minicodigo,
    marca,
    familia,
    nombre,
    precio_usd_sin_igv,
    stock_valor,
    observado_at
FROM ranked
WHERE rn = 1;
GO

SELECT TOP (20) *
FROM dbo.V_MCP_PRODUCTO
ORDER BY observado_at DESC;
