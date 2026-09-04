# STECH MCP

Servidor MCP de S-TECH para conectar ChatGPT/agentes con el SQL Server y los contratos reales de `artosperu-bot/scr` (`v8-identity`), y luego automatizar enriquecimiento/validación de fichas comerciales como Coolbox.

## Contrato real reutilizado de SCR V8

STECH MCP **no crea un catálogo paralelo**. Lee directamente la estructura operativa existente:

- Base por defecto: `DB_DISTRIBUIDORES`
- Configuración: mismas variables `DIST_SQL_*` de `scr/v8-identity`
- Catálogo actual: `dbo.V_PRD_PRODUCTO_ACTUAL`
- Part Number SQL: `part_number`
- Identificadores: `ean`, `upc`, `mini_codigo`, `codigo_externo`
- Histórico real: `dbo.HST_PRODUCTO_OBSERVACION`
- Taxonomía operativa: Categoría/Subcategoría STECH CAT_V2

La base separada `STECH_MCP` queda reservada para evidencia, reglas y datos específicos de los flujos MCP/Coolbox; no duplica productos, stock ni históricos.

## Herramientas MCP actuales

- `stech_health`
- `product_get`
- `product_search`
- `packaging_estimate_weight`
- `packaging_validate_dimensions`

No existe `execute_sql` libre. Las consultas son parametrizadas y el catálogo se consume a través de vistas/contratos controlados.

## Instalación rápida en la misma PC/red del monitor

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

### Reutilizar el `.env` de SCR V8

El MCP entiende directamente estas variables:

```env
DIST_SQL_SERVER=localhost
DIST_SQL_DATABASE=DB_DISTRIBUIDORES
DIST_SQL_TRUSTED_CONNECTION=yes
DIST_SQL_DRIVER=ODBC Driver 18 for SQL Server
DIST_SQL_ENCRYPT=no
DIST_SQL_USER=
DIST_SQL_PASSWORD=

ERP_PRODUCT_VIEW=dbo.V_PRD_PRODUCTO_ACTUAL
MCP_TRANSPORT=stdio
```

Si `scr/v8-identity` ya funciona en esa PC, usa en el `.env` de `mcp-stech` los mismos valores reales `DIST_SQL_*`. No subas el `.env` a GitHub.

## Prueba inmediata contra SQL real

No necesitas crear `V_MCP_PRODUCTO`. V8 ya tiene `dbo.V_PRD_PRODUCTO_ACTUAL`.

Ejecuta:

```powershell
stech-mcp-check 82YU00XYLM
```

La salida correcta debe mostrar:

```json
{
  "sql_source_status": "ok",
  "partnumber": "82YU00XYLM",
  "found": true,
  "product": {
    "part_number": "82YU00XYLM",
    "partnumber": "82YU00XYLM"
  }
}
```

También se puede levantar localmente:

```powershell
stech-mcp
```

## Qué obtiene `product_get`

Como lee `V_PRD_PRODUCTO_ACTUAL`, puede recibir la información que V8 ya consolida del producto: distribuidor, familia, marca, código externo, Part Number, EAN, UPC, mini código, nombre, identidad, categoría/subcategoría cuando estén en la vista, stock/precio actual y fechas disponibles en ese contrato.

El histórico detallado seguirá viniendo de `HST_PRODUCTO_OBSERVACION` mediante herramientas MCP específicas que se añadirán después, en lugar de reconstruirlo desde una vista duplicada.

## Base propia de evidencias Coolbox

Opcionalmente ejecutar:

```text
sql/001_create_stech_mcp.sql
```

Crea la base `STECH_MCP` para evidencia y enriquecimientos propios del MCP. No modifica las tablas de negocio de `DB_DISTRIBUIDORES`.

## Verificación

```powershell
pytest
```

GitHub Actions ejecuta los mismos tests en cada cambio del PR.

## Después de validar SQL local

Se habilitará:

```env
MCP_TRANSPORT=streamable-http
MCP_HOST=127.0.0.1
MCP_PORT=8765
```

y luego Cloudflare Tunnel hacia un hostname dedicado, por ejemplo `mcp.artos.pe`. Primero se valida SQL local; después se publica de forma segura.

## Siguiente incremento Coolbox

Después de confirmar `stech-mcp-check` con un SKU real:

- histórico/stock/precio/ubicaciones desde V8;
- `enrichment_get` / `enrichment_upsert` con evidencia confiable;
- esquema de la plantilla Coolbox;
- validación de todos los campos amarillos obligatorios;
- reglas de empaque como último recurso;
- carga + vista previa editable + aprobación;
- exportación del Excel original conservando estructura y validaciones.
