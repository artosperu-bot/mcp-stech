/*
  Ejecutar en la base operativa del ERP (por ejemplo DB_ST).
  Este script NO modifica datos. Solo devuelve estructura y muestra ejemplos.
*/

SELECT
    s.name AS schema_name,
    t.name AS table_name,
    c.column_id,
    c.name AS column_name,
    ty.name AS data_type,
    c.max_length,
    c.precision,
    c.scale,
    c.is_nullable
FROM sys.tables AS t
INNER JOIN sys.schemas AS s ON s.schema_id = t.schema_id
INNER JOIN sys.columns AS c ON c.object_id = t.object_id
INNER JOIN sys.types AS ty ON ty.user_type_id = c.user_type_id
WHERE t.name IN (
    N'PRD_PRODUCTO_DISTRIBUIDOR',
    N'HST_PRODUCTO_OBSERVACION',
    N'ST_STOCK',
    N'ST_STOCK_HST_CONSULTA',
    N'ST_ENTRADAS_CONS',
    N'TC_SUNAT'
)
ORDER BY t.name, c.column_id;

SELECT TOP (10) * FROM dbo.PRD_PRODUCTO_DISTRIBUIDOR;
SELECT TOP (10) * FROM dbo.HST_PRODUCTO_OBSERVACION ORDER BY producto_distribuidor_id DESC;

/*
  Resultado que necesita product_get:
  una vista o tabla configurada en ERP_PRODUCT_VIEW que contenga, como mínimo:

      partnumber

  Recomendado además:
      producto_distribuidor_id
      minicodigo
      marca
      familia
      nombre
      precio_usd_sin_igv
      stock_valor
      observado_at

  Una vez revisado el resultado de este script se crea dbo.V_MCP_PRODUCTO
  usando los nombres reales de columnas y relaciones del ERP.
*/
