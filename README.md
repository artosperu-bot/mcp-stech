# STECH MCP

Servidor MCP de S-TECH para conectar ChatGPT/agentes con SQL Server y automatizar enriquecimiento de fichas comerciales (Coolbox y otros canales) sin exponer SQL libre.

## Estado V1

La rama `feat/stech-mcp-v1` ya incluye:

- conexión segura a SQL Server mediante `pyodbc`;
- configuración por `.env`;
- consultas parametrizadas por Part Number;
- política de prioridad de fuentes confiables;
- reglas controladas para peso/dimensiones de empaque;
- base SQL separada `STECH_MCP` para enriquecimientos/evidencias;
- servidor MCP basado en el SDK oficial MCP Python 2.x;
- herramientas iniciales:
  - `stech_health`
  - `product_get`
  - `packaging_estimate_weight`
  - `packaging_validate_dimensions`
- tests automáticos y GitHub Actions CI.

## Arquitectura

```text
ChatGPT / MCP Client
        |
        v
    STECH MCP
        |
        +--> ERP SQL Server (solo lectura)
        |      `dbo.V_MCP_PRODUCTO`
        |
        +--> Base `STECH_MCP`
               enriquecimientos / evidencias / reglas
```

El MCP no ofrece una herramienta `execute_sql` genérica. El acceso al ERP se hace mediante repositorios y vistas controladas.

## Requisitos Windows

- Python 3.12+
- Microsoft ODBC Driver 18 for SQL Server
- acceso de red al SQL Server S-TECH

## Instalación rápida

```powershell
git clone https://github.com/artosperu-bot/mcp-stech.git
cd mcp-stech
git checkout feat/stech-mcp-v1

py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"

Copy-Item .env.example .env
```

Editar `.env` con el servidor/base reales. Para autenticación Windows:

```env
STECH_SQL_SERVER=PC005
STECH_SQL_DATABASE=DB_ST
STECH_SQL_AUTH=windows
ERP_PRODUCT_VIEW=dbo.V_MCP_PRODUCTO
MCP_TRANSPORT=stdio
```

Para autenticación SQL:

```env
STECH_SQL_AUTH=sql
STECH_SQL_USER=stech_mcp_ro
STECH_SQL_PASSWORD=<secreto-local>
```

Nunca subir `.env` al repositorio.

## 1. Descubrir estructura real del ERP

Ejecutar en SSMS, sobre la base operativa:

```text
sql/900_discover_erp_schema.sql
```

Ese script es solo lectura y devuelve columnas de las tablas principales. Con ese resultado se construye `dbo.V_MCP_PRODUCTO` usando los nombres y relaciones reales del ERP, sin asumir estructura.

La vista configurada en `ERP_PRODUCT_VIEW` debe contener al menos:

```text
partnumber
```

Recomendado:

```text
producto_distribuidor_id
partnumber
minicodigo
marca
familia
nombre
precio_usd_sin_igv
stock_valor
observado_at
```

## 2. Crear base propia del MCP

Ejecutar en SSMS:

```text
sql/001_create_stech_mcp.sql
```

Esto crea `STECH_MCP` y las tablas de enriquecimiento/evidencia. No modifica tablas operativas del ERP.

## 3. Probar

```powershell
pytest
```

## 4. Levantar MCP local por stdio

```powershell
stech-mcp
```

También se puede ejecutar:

```powershell
python -m stech_mcp.server
```

## 5. Levantar por Streamable HTTP (preparación para túnel)

Cambiar:

```env
MCP_TRANSPORT=streamable-http
MCP_HOST=127.0.0.1
MCP_PORT=8765
```

Luego:

```powershell
stech-mcp
```

La publicación mediante Cloudflare Tunnel y la lista segura de hosts se configura después de validar SQL y las herramientas localmente.

## Política de fuentes

Orden base:

1. `A1`: fabricante + Part Number exacto
2. `A2`: PDF/documentación oficial + Part Number exacto
3. `B`: distribuidor autorizado + Part Number exacto
4. `C`: retailer confiable + Part Number exacto
5. `D`: mismo modelo/chasis para atributos estructurales compatibles
6. `E`: estimación por regla, únicamente como último recurso

Los campos específicos de variante (RAM, SSD, CPU, sistema operativo, color, GPU) no se heredan automáticamente desde otro SKU/chasis.

## Siguiente incremento

Después de validar `product_get` contra el SQL real:

- `product_search`
- `enrichment_get`
- `enrichment_upsert`
- `coolbox_schema_get`
- `product_validate`
- `coolbox_export`
- vista web para cargar, editar, aprobar y exportar Excel.
