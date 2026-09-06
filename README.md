# STECH MCP

Servidor MCP de S-TECH para conectar ChatGPT/agentes con SQL Server y los contratos reales de `artosperu-bot/scr` (`v8-identity`). El objetivo es mantener una sola ficha maestra enriquecida por Part Number y reutilizarla en Coolbox, Falabella/Saga y VTEX sin duplicar investigación ni inventar atributos.

## Contrato real reutilizado de SCR V8

STECH MCP **no crea un catálogo operativo paralelo**. Lee directamente la estructura existente:

- Base operativa: `DB_DISTRIBUIDORES`
- Configuración: reutiliza `DIST_SQL_*` de `scr/v8-identity`, con override opcional `STECH_SQL_*`
- Catálogo actual: `dbo.V_PRD_PRODUCTO_ACTUAL`
- Part Number SQL: `part_number`
- Identificadores: `ean`, `upc`, `mini_codigo`, `codigo_externo`
- Histórico MCP: `dbo.V_HST_PRODUCTO_OBSERVACION_V8`

La base separada `STECH_MCP` se usa para Product Master, evidencia, enrichment, reglas, drafts, metadata de imágenes y auditoría. No reemplaza el catálogo, stock ni histórico operativo.

## Jerarquía de fuentes

La ficha maestra sigue esta prioridad:

1. **A1** — fabricante + Part Number exacto.
2. **A2** — documento oficial, soporte, PSREF o PDF con Part Number exacto.
3. **B** — distribuidor autorizado con SKU/PN exacto.
4. **C** — retailer confiable con SKU exacto.
5. **D** — mismo modelo/chasis, solo para atributos realmente invariantes.
6. **E** — regla determinística o estimación aprobada.

Los campos sensibles a variante (RAM, SSD, CPU, GPU, sistema operativo, color y equivalentes) no se adivinan. Un valor manual aprobado no se sobrescribe automáticamente.

## Regla de empaque aprobada para laptops 15.x

Cuando una laptop tiene pantalla `>= 15.0` y `< 16.0` pulgadas y **no existe un empaque completo aprobado de una fuente superior**, se usa este fallback:

```text
Ancho: 33 cm
Largo: 54 cm
Alto: 7 cm
Peso: 2500 g
method: ESTIMATED
source: REGLA_STECH_EMPAQUE
rule_code: LAPTOP_15_X_DEFAULT
confidence_grade: E
```

Si existen los cuatro valores de empaque aprobados (`package_width_cm`, `package_length_cm`, `package_height_cm`, `package_weight_g`) en `product_enrichment`, el resolver usa esos valores y no mezcla dimensiones oficiales parciales con la estimación.

## Herramientas MCP

Herramientas operativas existentes:

- `stech_health`
- `product_get`
- `product_search`
- `product_history`
- `coolbox_preview`
- `packaging_estimate_weight`
- `packaging_validate_dimensions`
- `packaging_rule_get(screen_inches, category="LAPTOP")`
- `packaging_resolve(partnumber, category="LAPTOP")`
- `marketplace_preview(partnumber, marketplace, category="LAPTOP")`

Product Workspace V1 agrega:

- `product_prepare(partnumber, category="LAPTOP")`
- `product_master_get(partnumber)`
- `product_readiness_get(partnumber)`
- `channel_draft_get(partnumber, marketplace="COOLBOX")`

VTEX Image Sync V1 agrega:

- `product_images_sync_local(partnumber)`
- `product_images_validate(partnumber)`
- `vtex_images_status(partnumber, account_code="VTEX_STECH")`
- `vtex_images_sync(partnumber, account_code="VTEX_STECH")`

`product_prepare` es el punto único de preparación usado tanto por ChatGPT como por SCR. En V1 persiste el Product Master, resuelve el empaque, calcula readiness, genera un draft Coolbox versionado de 81 campos y registra auditoría. **No publica en ningún marketplace.**

`marketplace_preview` soporta actualmente `COOLBOX/LAPTOP`. **Falabella/Saga y VTEX no tienen mappings inventados**: se incorporan después de revisar sus plantillas/esquemas reales y validaciones por categoría.

No existe `execute_sql` libre. Las consultas usan contratos controlados y parámetros.

## Instalación / actualización

Para Product Workspace V1:

```powershell
cd C:\DESAROLLO\mcp-stech
git fetch origin
git checkout feat/product-workspace-v1
git pull origin feat/product-workspace-v1
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

El `.env` puede reutilizar el acceso real de SCR V8:

```env
DIST_SQL_SERVER=PC020
DIST_SQL_DATABASE=DB_DISTRIBUIDORES
DIST_SQL_TRUSTED_CONNECTION=yes
DIST_SQL_DRIVER=ODBC Driver 18 for SQL Server
DIST_SQL_ENCRYPT=no

ERP_PRODUCT_VIEW=dbo.V_PRD_PRODUCTO_ACTUAL
MCP_SQL_DATABASE=STECH_MCP

MCP_TRANSPORT=streamable-http
MCP_HOST=127.0.0.1
MCP_PORT=8765
MCP_PUBLIC_HOST=mcp.artos.pe
```

No subas `.env` ni credenciales a GitHub.

## Migraciones de `STECH_MCP`

Ejecutar en orden:

```text
sql/001_create_stech_mcp.sql
sql/002_multichannel_enrichment_phase1.sql
sql/003_product_workspace_v1.sql
sql/004_vtex_image_publication.sql
```

Si `001`, `002` y `003` ya están aplicadas, para VTEX Image Sync basta:

```powershell
sqlcmd -S PC020 -E -C -i ".\sql\004_vtex_image_publication.sql"
```

`003_product_workspace_v1.sql` es aditiva e idempotente. Crea:

- `dbo.product_master`
- `dbo.channel_draft`
- `dbo.channel_draft_field`
- `dbo.product_image`
- `dbo.product_audit_event`
- `dbo.V_PRODUCT_WORKSPACE_V1`

`004_vtex_image_publication.sql` es aditiva e idempotente y agrega solamente `dbo.product_image_publication` para registrar qué imagen local fue publicada/verificada en qué SKU VTEX.

No elimina tablas operativas ni publica productos.

Validación de objetos:

```powershell
sqlcmd -S PC020 -E -C -Q "SELECT OBJECT_ID('STECH_MCP.dbo.product_master') AS product_master_id, OBJECT_ID('STECH_MCP.dbo.channel_draft') AS channel_draft_id, OBJECT_ID('STECH_MCP.dbo.product_image') AS product_image_id, OBJECT_ID('STECH_MCP.dbo.V_PRODUCT_WORKSPACE_V1') AS workspace_view_id;"
```

Los cuatro valores deben ser distintos de `NULL`.

## Aceptación real de Product Workspace V1

Después de aplicar `003` y reiniciar `stech-mcp`, el servidor debe exponer las herramientas de Product Workspace.

Preparar el producto real desde un cliente MCP o desde SCR debe ejecutar:

```text
product_prepare(partnumber="82YU00XYLM", category="LAPTOP")
```

El resultado persistido esperado incluye:

```text
partnumber = 82YU00XYLM
brand = LENOVO
package = 33 x 54 x 7 cm
package_weight_g = 2500
package_status = ESTIMATED
package_source = REGLA_STECH_EMPAQUE
package_rule_code = LAPTOP_15_X_DEFAULT
coolbox_field_count = 81
```

Validación SQL:

```powershell
sqlcmd -S PC020 -E -C -Q "SELECT partnumber, brand, model, readiness_state, package_width_cm, package_length_cm, package_height_cm, package_weight_g, package_status, coolbox_field_count FROM STECH_MCP.dbo.V_PRODUCT_WORKSPACE_V1 WHERE partnumber=N'82YU00XYLM';"
```

La vista SCR lee este estado directamente desde SQL Server para que la previsualización sea rápida. El botón **Preparar / Actualizar** llama al mismo `product_prepare` del MCP y luego vuelve a leer el estado persistido; no existe una segunda lógica de preparación dentro de SCR.

## VTEX Image Sync V1

La primera versión sincroniza imágenes que ya existen físicamente en PC020. No busca imágenes en Internet, no las edita y no modifica precio, stock, categoría, atributos ni activación de producto.

Convención:

```text
C:\STECH_IMAGENES\...\82YU00XYLM\82YU00XYLM_01.jpg  -> principal siempre
C:\STECH_IMAGENES\...\82YU00XYLM\82YU00XYLM_02.jpg
C:\STECH_IMAGENES\...\82YU00XYLM\82YU00XYLM_03.jpg
C:\STECH_IMAGENES\...\82YU00XYLM\82YU00XYLM_04.jpg
```

Si falta `_01`, el estado es `REVIEW` y no se sube automáticamente `_02+`.

Configuración mínima real en `.env`:

```env
STECH_IMAGE_ROOT=C:\STECH_IMAGENES
VTEX_ACCOUNT_NAME=ststore227
VTEX_APP_KEY=<APP KEY REAL>
VTEX_APP_TOKEN=<APP TOKEN REAL>
VTEX_IMAGE_PUBLIC_BASE=https://mcp.artos.pe/vtex-images
```

Si el mismo `.env` ya contiene estas variables del canal V8, también sirven y no es necesario duplicarlas:

```env
CHN_CRED_VTEX_STECH_APP_KEY=<APP KEY REAL>
CHN_CRED_VTEX_STECH_APP_TOKEN=<APP TOKEN REAL>
```

El secreto de URL temporal no requiere intervención manual. Si `VTEX_IMAGE_SIGNING_SECRET` no existe o queda vacío, el MCP genera uno seguro automáticamente al arrancar. Opcionalmente se pueden fijar:

```env
VTEX_IMAGE_SIGNING_SECRET=
VTEX_IMAGE_URL_TTL_SECONDS=900
VTEX_HTTP_TIMEOUT_SECONDS=30
```

`VTEX_IMAGE_PUBLIC_BASE` no requiere hosting adicional: `/vtex-images/{token}` lo sirve el mismo proceso `stech-mcp` de PC020 y Cloudflare Tunnel lo expone por `mcp.artos.pe`. La ruta no permite navegar carpetas; un token HMAC temporal autoriza solo un `product_image_id` y Part Number concretos.

Cloudflare debe permitir que VTEX haga GET público a `/vtex-images/*`. Si Cloudflare Access exige login para todo `mcp.artos.pe`, se debe excluir esa ruta del login o usar otro hostname público del mismo Tunnel.

Prueba real, después de aplicar `004` y reiniciar MCP:

```text
product_images_sync_local(partnumber="82YU00XYLM")
product_images_validate(partnumber="82YU00XYLM")
vtex_images_status(partnumber="82YU00XYLM")
vtex_images_sync(partnumber="82YU00XYLM")
```

Resultado esperado para cuatro archivos `_01.._04`:

```text
local state     = READY
local images    = 4
SKU RefId       = 82YU00XYLM-S
_01 IsMain      = true
uploaded        = solo faltantes
read-back       = verificado
segunda corrida = 0 duplicados
```

La estrategia V1 es `MISSING_ONLY`: no borra ni reemplaza imágenes manuales existentes en VTEX.

## Prueba base contra producto real

```powershell
stech-mcp-check 82YU00XYLM
```

Debe mantener `sql_source_status=ok` y encontrar el producto desde `dbo.V_PRD_PRODUCTO_ACTUAL`.

Mientras no exista un empaque oficial completo aprobado, `packaging_resolve("82YU00XYLM")` debe devolver:

```json
{
  "width_cm": 33,
  "length_cm": 54,
  "height_cm": 7,
  "weight_g": 2500,
  "status": "ESTIMATED",
  "method": "ESTIMATED",
  "source": "REGLA_STECH_EMPAQUE",
  "rule_code": "LAPTOP_15_X_DEFAULT",
  "confidence_grade": "E"
}
```

`coolbox_preview("82YU00XYLM")` debe seguir entregando exactamente 81 campos y usar ese mismo empaque resuelto como fallback. Si posteriormente se guarda empaque oficial completo y aprobado, el preview debe usar el oficial.

## Verificación automática

```powershell
pytest
```

GitHub Actions ejecuta la misma suite para el PR de MCP. SCR mantiene su propia suite de backend, JavaScript, PowerShell y empaquetado Windows.

## Roadmap multicanal

La siguiente etapa no parte de supuestos. Para cada canal se revisa primero su documentación/plantilla real:

- **Coolbox:** mantener las 81 columnas reales, completar evidencia faltante y exportar preservando formato/validaciones.
- **Falabella/Saga:** incorporar la plantilla real por categoría, sus campos obligatorios, límites, listas permitidas y reglas comerciales reales.
- **VTEX:** reutilizar Product Workspace y sus imágenes aprobadas sin alterar el flujo de catálogo/precio/stock ya estabilizado en SCR V8.

La misma ficha maestra y sus evidencias se reutilizan en los tres canales.
