# STECH MCP

Servidor MCP de S-TECH para conectar ChatGPT/agentes con SQL Server y los contratos reales de `artosperu-bot/scr` (`v8-identity`). El objetivo es mantener una sola ficha maestra enriquecida por Part Number y reutilizarla en Coolbox, Falabella/Saga y VTEX sin duplicar investigación ni inventar atributos.

## Contrato real reutilizado de SCR V8

STECH MCP **no crea un catálogo paralelo**. Lee directamente la estructura operativa existente:

- Base operativa: `DB_DISTRIBUIDORES`
- Configuración: reutiliza `DIST_SQL_*` de `scr/v8-identity`, con override opcional `STECH_SQL_*`
- Catálogo actual: `dbo.V_PRD_PRODUCTO_ACTUAL`
- Part Number SQL: `part_number`
- Identificadores: `ean`, `upc`, `mini_codigo`, `codigo_externo`
- Histórico MCP: `dbo.V_HST_PRODUCTO_OBSERVACION_V8`

La base separada `STECH_MCP` se usa únicamente para evidencia, enrichment, reglas de empaque y metadatos de marketplaces. No duplica el catálogo, stock ni histórico operativo.

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

Herramientas agregadas en la Fase 1 multicanal:

- `packaging_rule_get(screen_inches, category="LAPTOP")`
- `packaging_resolve(partnumber, category="LAPTOP")`
- `marketplace_preview(partnumber, marketplace, category="LAPTOP")`

`marketplace_preview` soporta en esta fase únicamente `COOLBOX/LAPTOP`. **Falabella/Saga y VTEX no tienen mappings inventados**: se incorporarán después de revisar sus plantillas/esquemas reales y sus validaciones por categoría.

No existe `execute_sql` libre. Las consultas usan contratos controlados y parámetros.

## Instalación / actualización

```powershell
cd C:\DESAROLLO\mcp-stech
git checkout feat/stech-mcp-v1
git pull
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

La Fase 1 requiere ejecutar las migraciones en orden.

Primera instalación:

```text
sql/001_create_stech_mcp.sql
sql/002_multichannel_enrichment_phase1.sql
```

Si `001_create_stech_mcp.sql` ya fue ejecutada anteriormente, basta ejecutar `002_multichannel_enrichment_phase1.sql`.

En SSMS con **SQLCMD Mode** se puede ejecutar desde la raíz del repo:

```sql
:r .\sql\002_multichannel_enrichment_phase1.sql
```

La migración es aditiva e idempotente. Crea `packaging_rule` y metadatos genéricos de marketplace, y registra `LAPTOP_15_X_DEFAULT`. No elimina `coolbox_template_field` ni modifica tablas de negocio de `DB_DISTRIBUIDORES`.

Validación SQL:

```sql
SELECT rule_code, category_code, screen_min_inches, screen_max_inches,
       width_cm, length_cm, height_cm, weight_g, priority, enabled, source_code
FROM STECH_MCP.dbo.packaging_rule
WHERE rule_code = N'LAPTOP_15_X_DEFAULT';
```

Esperado: `LAPTOP`, `15.00`, `16.00`, `33`, `54`, `7`, `2500`, habilitada y fuente `REGLA_STECH_EMPAQUE`.

## Prueba contra producto real

```powershell
stech-mcp-check 82YU00XYLM
```

Debe mantener `sql_source_status=ok` y encontrar el producto desde `dbo.V_PRD_PRODUCTO_ACTUAL`.

Después de aplicar la migración y reiniciar `stech-mcp`, el endpoint público debe exponer 10 herramientas: las 7 anteriores más `packaging_rule_get`, `packaging_resolve` y `marketplace_preview`.

Para `82YU00XYLM` (15.6 pulgadas), mientras no exista un empaque oficial completo aprobado en `product_enrichment`, `packaging_resolve` debe devolver:

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

GitHub Actions ejecuta la misma suite para el PR.

## Roadmap multicanal

La siguiente etapa no parte de supuestos. Para cada canal se revisa primero su documentación/plantilla real:

- **Coolbox:** mantener las 81 columnas reales, completar evidencia faltante y exportar preservando formato/validaciones.
- **Falabella/Saga:** incorporar la plantilla real por categoría, sus campos obligatorios, límites, listas permitidas y reglas comerciales reales.
- **VTEX:** revisar el schema real de Product/SKU y el mecanismo de carga elegido (JSON/API/XLSX) antes de mapear.

La misma ficha maestra y sus evidencias se reutilizan en los tres canales.
