# STECH MCP — Diseño de enriquecimiento maestro multicanal

Fecha: 2026-09-04
Estado: aprobado en conversación, pendiente revisión final del documento
Rama: feat/stech-mcp-v1

## Objetivo

Convertir STECH MCP en un motor maestro de producto que reutilice una sola investigación confiable para generar salidas hacia Coolbox, Falabella/Saga y VTEX, evitando investigar o mantener datos separados por canal.

## Principios

1. El dato técnico maestro se investiga una vez por Part Number exacto y luego se reutiliza en todos los canales.
2. Deltron/SQL es fuente operativa inicial, pero una fuente oficial exacta tiene prioridad cuando existe.
3. Nunca se presenta un dato estimado como oficial o verificado.
4. Campos sensibles a variante (RAM, SSD, CPU, GPU, SO, color, etc.) requieren Part Number exacto o evidencia fuerte equivalente.
5. Correcciones manuales aprobadas no se sobrescriben automáticamente.
6. Las exportaciones de marketplace son transformaciones del producto maestro, no bases de verdad independientes.

## Jerarquía de fuentes

- A1: fabricante + Part Number exacto
- A2: documento oficial / soporte / PSREF / PDF con Part Number exacto
- B: distribuidor autorizado con SKU/PN exacto
- C: retailer confiable con SKU exacto
- D: mismo modelo/chasis solo para campos invariantes de chasis
- E: regla determinística o estimación aprobada

Estados/métodos principales:

- VERIFIED
- DERIVED
- ESTIMATED
- MANUAL
- CONFLICT
- RESEARCH_REQUIRED

## Regla de empaque aprobada

Código propuesto: `LAPTOP_15_X_DEFAULT`

Aplicación:

- categoría: laptop
- pantalla: >= 15.0 y < 16.0 pulgadas
- usar solo cuando no exista empaque confiable de una fuente de mayor prioridad

Valores:

- ancho: 33 cm
- largo: 54 cm
- alto: 7 cm
- peso: 2500 g

Metadatos obligatorios:

- method = ESTIMATED
- source = REGLA_STECH_EMPAQUE
- rule_code = LAPTOP_15_X_DEFAULT
- nunca marcar como VERIFIED

Si aparece empaque oficial o de fuente superior, ese dato reemplaza la estimación para la salida final, conservando la trazabilidad histórica/evidencia de la estimación.

## Arquitectura

```text
DB_DISTRIBUIDORES / ERP
        |
        v
Producto actual + histórico
        |
        v
STECH_MCP producto maestro
        |
        +--> evidencia oficial / fabricante / distribuidores autorizados
        |
        v
Enrichment maestro aprobado
        |
        +--> Coolbox XLSX
        +--> Falabella/Saga XLSX
        +--> VTEX XLSX/JSON
```

## Fuentes ERP que ya están disponibles

- `dbo.V_PRD_PRODUCTO_ACTUAL`
- `dbo.V_HST_PRODUCTO_OBSERVACION_V8`

Estas cubren identidad, PN, GTIN cuando existe, atributos Deltron, stock/precio proveedor e histórico.

## Fuentes ERP adicionales a definir

No se dará acceso arbitrario a SQL. Se expondrán vistas estables de lectura para cada necesidad:

- `V_MCP_STOCK_VENTA`: stock realmente vendible S-TECH por SKU/PN
- `V_MCP_PRECIO_CANAL`: costo/precio/moneda/margen por producto/canal
- `V_MCP_SKU_CANAL`: relación SKU/PN interno con identificadores de Coolbox/Falabella/VTEX

Si la información ya existe en vistas/tablas actuales, estas vistas MCP encapsularán el contrato sin acoplar el MCP a tablas internas cambiantes.

## Modelo de datos STECH_MCP

### Mantener

`product_enrichment`
- un valor maestro por partnumber + field_code
- método, confianza, aprobación y timestamps

`product_evidence`
- URL/dominio/tipo de fuente
- Part Number observado en la fuente
- texto/evidencia
- ranking y fecha de recuperación

`processing_run`
- seguimiento de trabajos masivos

### Generalizar

La tabla específica `coolbox_template_field` evoluciona a un esquema genérico de marketplace.

Nuevas entidades propuestas:

`packaging_rule`
- rule_code
- category_code
- screen_min_inches / screen_max_inches
- width_cm / length_cm / height_cm / weight_g
- priority
- enabled

`marketplace_template`
- marketplace_code: COOLBOX, FALABELLA, VTEX
- template_code
- version
- category_code
- active

`marketplace_template_field`
- template_code
- field_code
- excel_column / json_path
- display_name
- required
- datatype
- unit
- allowed_values_json
- normalization_rule

`marketplace_field_mapping`
- template_code
- target_field_code
- master_field_code
- transform_rule
- priority

`marketplace_product_override`
- marketplace_code
- partnumber
- field_code
- override_value
- reason
- approved
- timestamps

`marketplace_export_run`
- export_id
- marketplace_code
- template_code/version
- product_count
- status
- source_filename/output_filename
- timestamps

## Flujo de enriquecimiento

Para cada producto:

1. Leer identidad actual desde SQL.
2. Leer enrichment previamente aprobado.
3. Determinar campos faltantes según categoría y plantilla destino.
4. Investigar primero fuentes A1/A2 y luego B/C.
5. Guardar evidencia y candidatos, no solo el valor final.
6. Resolver conflictos por prioridad, coincidencia exacta de PN y consistencia entre fuentes.
7. Aplicar reglas DERIVED/ESTIMATED únicamente cuando corresponda.
8. Marcar campos no demostrables como RESEARCH_REQUIRED.
9. Crear preview por marketplace.
10. Exportar solo después de validación/aprobación definida.

## Herramientas MCP objetivo

### Producto maestro / enrichment

- `enrichment_get(partnumber)`
- `enrichment_missing(partnumber, marketplace, category)`
- `enrichment_upsert(...)`
- `enrichment_evidence_add(...)`
- `enrichment_conflicts(partnumber=None)`
- `enrichment_progress(filters...)`

### Empaque

- mantener `packaging_estimate_weight`
- mantener `packaging_validate_dimensions`
- agregar `packaging_rule_get(screen_inches, category)`
- agregar `packaging_resolve(partnumber)` que prefiera fuente oficial y use regla solo como fallback

### Marketplaces

- `marketplace_schema_get(marketplace, category)`
- `marketplace_preview(partnumber, marketplace, category)`
- `marketplace_validate(partnumber, marketplace, category)`
- `marketplace_export(partnumbers, marketplace, template)`

Coolbox actual se migra internamente a este motor; su tool puede conservarse como alias compatible durante la transición.

## Exportación por canal

### Coolbox

- conservar formato, validaciones, fórmulas y hojas ocultas de la plantilla original
- mapear desde producto maestro
- distinguir VERIFIED/DERIVED/ESTIMATED/RESEARCH_REQUIRED

### Falabella/Saga

- cargar la plantilla real por categoría
- guardar versión de plantilla y sus columnas/validaciones
- aplicar reglas de título, descripción, atributos y restricciones reales de la plantilla/API

### VTEX

- soportar inicialmente plantilla/JSON según el flujo de carga que se defina
- separar producto (Product) de SKU/variantes cuando aplique
- usar la misma ficha maestra y solo transformar nombres/valores según el schema VTEX

## Seguridad

- no exponer SQL arbitrario
- tools parametrizados por intención
- escritura a catálogo/ERP separada de la investigación
- cambios persistentes sensibles requieren aprobación explícita o flujo aprobado
- no registrar contraseñas ni connection strings con secretos

## Estrategia de implementación

Fase 1 — núcleo maestro
- regla `LAPTOP_15_X_DEFAULT`
- repositorio de enrichment/evidencia
- esquema marketplace genérico
- `packaging_resolve`
- migrar `coolbox_preview` al motor maestro sin romper compatibilidad

Fase 2 — datos S-TECH
- identificar/crear vistas de stock vendible, precio/costo y SKU por canal
- exponer tools de lectura

Fase 3 — Falabella/Saga
- incorporar plantilla real
- mapear categoría laptop primero
- preview + validación + export XLSX

Fase 4 — VTEX
- definir schema real por categoría
- preview + validación + export JSON/XLSX

Fase 5 — procesamiento masivo
- lotes por marca/categoría
- cola de faltantes
- reanudación
- conflictos y aprobación
- métricas de avance

## Criterios de aceptación de Fase 1

1. Para una laptop 15.6" sin empaque oficial, `packaging_resolve` devuelve 33 x 54 x 7 cm y 2500 g como ESTIMATED.
2. Si existe un empaque oficial A1/A2 aprobado, `packaging_resolve` devuelve el oficial y no la regla.
3. `coolbox_preview` sigue funcionando para `82YU00XYLM` y usa el nuevo resolver maestro.
4. Cada campo del preview conserva valor, método, fuente/confianza y estado.
5. No se inventan SSD, GPU, Hz ni otros campos sensibles ausentes.
6. El modelo de plantillas permite registrar COOLBOX, FALABELLA y VTEX sin crear una tabla distinta por marketplace.
7. Todas las consultas SQL siguen siendo parametrizadas y sin SQL arbitrario.
8. La suite de pruebas existente sigue verde y se agregan pruebas de precedencia de fuentes y empaque.
