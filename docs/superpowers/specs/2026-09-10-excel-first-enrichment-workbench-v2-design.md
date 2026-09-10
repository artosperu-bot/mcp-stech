# Excel-First Enrichment Workbench V2 — Diseño

**Fecha:** 2026-09-10  
**Repositorios:** `artosperu-bot/mcp-stech` + `artosperu-bot/scr`  
**Ramas de trabajo:** `feat/product-enrichment-engine-v2-current` + `feat/product-enrichment-workbench-v2`  
**Estado:** Diseño aprobado en conversación, pendiente de revisión escrita final antes de implementación

## 1. Objetivo

Convertir Product Workbench en un flujo de trabajo centrado en Excel, sencillo para operación comercial:

1. El usuario carga un `.xlsx`.
2. V8 reconoce la plantilla por su estructura, no por el nombre del archivo.
3. Detecta hoja, fila de encabezados, filas de productos y columnas que puede completar.
4. Detecta el Part Number de cada fila cuando está presente.
5. Si el Part Number falta, el usuario puede asignarlo en la misma pantalla; V8 también puede sugerirlo cuando haya una coincidencia única y verificable por EAN/UPC/SKU/modelo en el catálogo existente.
6. Con los Part Numbers resueltos, STECH consulta Product Workspace y determina qué información ya conoce y qué falta.
7. Se crea un `ENRICH_TECHNICAL` en la cola persistente existente `product_work_*`; no se crea otra cola para Excel.
8. El worker enriquece únicamente los campos faltantes o conflictivos.
9. Los hechos validados se guardan primero en Product Workspace / `product_enrichment` con evidencia.
10. Al finalizar, V8 genera una copia del mismo Excel y escribe únicamente las celdas permitidas por el template mapping.
11. Columnas comerciales, control, fórmulas no administradas y columnas desconocidas se conservan.

El flujo debe funcionar igual para 1, 10, 100 o miles de filas, deduplicando el trabajo técnico por Part Number aunque un mismo PN aparezca varias veces en el Excel.

## 2. Decisión de arquitectura

Se evaluaron tres enfoques.

### A. Internet → Excel directamente

El sistema investigaría cada fila y escribiría el resultado directamente en el libro.

Ventaja: implementación inicial aparentemente simple.

Problemas: repite investigación entre archivos/canales, no conserva una verdad maestra, dificulta auditoría, hace más probable sobrescribir datos correctos y vuelve a investigar el mismo Part Number muchas veces.

**Descartado.**

### B. Excel → Product Workspace → Excel

El Excel sirve como entrada y plantilla de salida. Product Workspace sigue siendo la verdad técnica. El motor investiga una sola vez por PN y después reutiliza el resultado para cualquier canal.

Ventajas: auditable, multicanal, reanudable, seguro y escalable.

**Elegido.**

### C. ETL separado por marketplace

Crear un proceso específico para Coolbox, otro para Falabella y otro para cada canal futuro.

Ventaja: cada proceso puede copiar exactamente su plantilla.

Problemas: duplica reglas, fuentes, validadores y mantenimiento; genera fichas contradictorias.

**Descartado.**

## 3. Modelo conceptual de canales

Coolbox no se tratará como una tecnología paralela a VTEX. Coolbox es un destino/canal comercial que opera sobre VTEX.

```text
                         PRODUCT WORKSPACE
                                |
              +-----------------+-----------------+
              |                                   |
              v                                   v
         FALABELLA                         CANALES SOBRE VTEX
                                                  |
                                      +-----------+-----------+
                                      |                       |
                                      v                       v
                              COOLBOX (VTEX)            S-TECH (VTEX)
```

El Excel de Coolbox representa una plantilla comercial de Coolbox. La integración técnica de publicación/sincronización puede usar VTEX, pero el enriquecimiento técnico del producto es independiente de la publicación.

## 4. Experiencia de usuario objetivo

La pestaña existente **Cargar Excel** se transforma en una **Carga Inteligente** tipo asistente, sin eliminar `Buscar / Editar`, `Enriquecimiento` ni `Jobs` para usos manuales/avanzados.

Pasos visibles:

```text
1 Archivo
   ↓
2 Plantilla
   ↓
3 Part Numbers
   ↓
4 Analizar
   ↓
5 Enriquecer
   ↓
6 Exportar
```

### 4.1 Paso 1 — Archivo

El usuario arrastra o selecciona un `.xlsx`.

V8 guarda una copia de sesión del archivo original y calcula SHA-256. El análisis no modifica el archivo original.

Se muestran nombre, tamaño, hojas y hash corto para auditoría.

### 4.2 Paso 2 — Reconocimiento de plantilla

V8 construye un manifest pequeño del workbook y lo envía al MCP.

El recognizer evalúa:

- nombres de hojas;
- primeras 20 filas por hoja;
- encabezados;
- encabezados distintivos;
- orden relativo de columnas;
- columna identificadora;
- aliases conocidos.

El nombre del archivo aporta 0 puntos al score.

Scoring:

- encabezados ponderados: hasta 60;
- encabezados distintivos: hasta 20;
- nombre de hoja: hasta 10;
- orden relativo: hasta 5;
- identificador PN/SKU configurado: hasta 5.

Confianza:

- `HIGH`: `>= 90`;
- `MEDIUM`: `70..89`;
- `LOW`: `< 70`;
- si la diferencia entre las dos mejores plantillas es `< 8`, estado `AMBIGUOUS`.

Comportamiento:

- HIGH: se selecciona automáticamente.
- MEDIUM: se muestra recomendación y requiere `Confirmar plantilla`.
- LOW/AMBIGUOUS: no se crea un job automáticamente; el usuario puede elegir manualmente una plantilla conocida de la lista. Esa elección queda registrada en la sesión.

Plantillas iniciales:

- `COOLBOX_LAPTOP_V1` — canal Coolbox sobre VTEX.
- `FALABELLA_LAPTOP_V1`.

El registro queda preparado para agregar versiones/categorías sin cambiar el recognizer.

## 5. Detección de filas y Part Numbers

### 5.1 Filas de producto

La fila de encabezados proviene del reconocimiento. Las filas posteriores se consideran candidatas cuando contienen datos en campos configurados del template.

Se conservan siempre:

- número de fila Excel;
- valores originales;
- identificador de hoja;
- Part Number resuelto;
- origen de resolución del PN.

### 5.2 PN presente

Si la plantilla contiene una columna configurada como Part Number y la celda tiene valor, se normaliza a mayúsculas y se usa.

No se interpreta cualquier SKU como PN salvo que el template lo defina explícitamente.

### 5.3 PN vacío

La tabla de preview siempre muestra una columna editable **Part Number STECH**.

Para una fila vacía:

```text
Fila 17 | Producto ... | Part Number STECH [____________] | FALTA PN
```

El usuario puede escribir el PN y guardarlo sin editar manualmente el Excel.

Si existe una columna PN en la plantilla, el valor confirmado podrá escribirse en esa celda durante la exportación.

Si la plantilla no tiene columna PN, el vínculo fila→PN se conserva en la sesión de V8 y se usa para enriquecer/exportar los campos técnicos; no se inventa una columna nueva en el workbook.

### 5.4 Sugerencias automáticas de PN

Antes de pedir entrada manual, V8 puede buscar una coincidencia en `V_PRD_PRODUCTO_ACTUAL` usando datos ya presentes en la fila.

Orden de coincidencia automática permitido:

1. EAN exacto y único.
2. UPC exacto y único.
3. código externo / mini código exacto y único, si la plantilla lo identifica.
4. Part Number exacto en otra columna conocida.

Marca/modelo/nombre solo generan **sugerencias**, nunca confirmación automática.

Si hay una coincidencia exacta y única, se muestra:

```text
Sugerencia: 83HFS03B00
Motivo: EAN exacto
[Confirmar] [Cambiar]
```

Si hay múltiples candidatos, se requiere decisión humana.

## 6. Análisis previo al enriquecimiento

Una vez resueltos los PN, V8 consulta el MCP en lote.

Por fila debe mostrarse:

- PN;
- marca/producto;
- completitud maestra;
- campos técnicos faltantes;
- identidad faltante;
- contenido faltante;
- recomendación.

Recomendaciones:

- `UP_TO_DATE` — no requiere investigación técnica.
- `ENRICH_LIGHT` — pocos campos faltantes y/o fuentes existentes suficientes.
- `ENRICH_DEEP` — requiere investigación web/documentos.
- `REVIEW_TEMPLATE` — mapeo/identidad insuficiente.
- `MISSING_PN` — no puede entrar a la cola todavía.

El usuario puede desmarcar filas antes de crear el job.

## 7. Creación del job

Solo los PN válidos y seleccionados se envían a `ProductWorkService` como:

```json
{
  "work_type": "ENRICH_TECHNICAL",
  "source_name": "V8_EXCEL_WORKBENCH",
  "actor_source": "SCR_UI",
  "priority": 50,
  "items": [
    {
      "partnumber": "82YU00XYLM",
      "category_code": "LAPTOP",
      "source_context": {
        "excel_session_id": "...",
        "sheet": "Laptops-All in one",
        "row_numbers": [3]
      }
    }
  ]
}
```

Si el mismo PN aparece en varias filas, se crea un solo item técnico. La sesión conserva todas las filas asociadas para completar cada una al exportar.

No se envían precio, stock, costo ni promociones al job técnico.

## 8. Procesamiento por el worker

El worker existente sigue siendo la única autoridad de ejecución en background.

Flujo:

```text
QUEUED
  ↓
LOADING_SOURCE_DATA
  ↓
ANALYZING_MISSING_FIELDS
  ↓
RESEARCHING / READING_DOCUMENTS
  ↓
VALIDATING
  ↓
PROMOTING_FACTS
  ↓
REBUILDING_PRODUCT_MASTER
  ↓
COMPLETED | PARTIAL | REVIEW_REQUIRED | NO_DATA_FOUND
```

Se reutilizan primero:

- V8 / `DB_DISTRIBUIDORES`;
- Deltron capturado;
- Product Workspace;
- `product_enrichment` aprobado;
- documentos/evidencias ya descargados.

Solo se investiga lo faltante/conflictivo.

El usuario puede cerrar V8. La cola y el worker continúan en SQL Server.

## 9. Política de escritura al Excel

La exportación parte de una copia del archivo original de la sesión.

Cada columna del template tiene `data_scope`:

- `TECHNICAL`;
- `IDENTITY`;
- `CONTENT`;
- `COMMERCIAL`;
- `CONTROL`.

Regla de escritura:

### 9.1 TECHNICAL / IDENTITY / CONTENT

- celda vacía + valor canónico validado → escribir;
- celda con mismo valor normalizado → conservar;
- celda con valor diferente → no sobrescribir automáticamente; marcar `DIFFERENCE` y mostrar al usuario la opción `Usar valor STECH`;
- sin valor canónico validado → conservar celda tal como está.

### 9.2 COMMERCIAL

Nunca modificar por `ENRICH_TECHNICAL`.

Ejemplos:

- Precio Lista;
- Precio Base;
- Stock;
- costo;
- fecha inicio/fin de promoción.

### 9.3 CONTROL y UNMAPPED

Preservar exactamente. No inferir semántica ni escribir por similitud.

### 9.4 Fórmulas y formato

La exportación carga el workbook con `data_only=False` y modifica exclusivamente las celdas objetivo autorizadas. Fórmulas fuera del mapping no se reemplazan. Se conserva el orden de hojas/columnas y estilos existentes en la medida soportada por `openpyxl` para `.xlsx`.

No se soporta `.xlsm` en esta fase para evitar pérdida de macros.

## 10. Diferencias y revisión

Antes de exportar, la UI presenta un resumen:

```text
25 filas
22 PN resueltos automáticamente/manualmente
3 pendientes de PN

18 productos enriquecidos
5 ya estaban completos
2 requieren revisión

147 celdas nuevas a completar
6 diferencias encontradas
0 campos comerciales modificados
```

Las diferencias se muestran por fila/campo:

```text
Fila 3 | RAM | Excel: 8 GB | STECH: 16 GB | Fuente STECH: A1
[Conservar Excel] [Usar STECH]
```

Por defecto se conserva Excel cuando hay diferencia.

## 11. Exportación

Botón final:

**`Exportar Excel completado`**

Nombre sugerido:

`<nombre_original>_STECH_ENRIQUECIDO_<YYYYMMDD-HHMM>.xlsx`

El resultado incluye solo las modificaciones confirmadas y las celdas vacías completadas automáticamente.

No se añade una hoja auxiliar por defecto para no alterar la plantilla del marketplace. El reporte de diferencias queda visible/descargable por separado en V8 en una fase posterior si se requiere.

## 12. Persistencia de la sesión Excel

La sesión Excel no es una segunda cola.

V8 mantiene un `excel_session_id` con:

- archivo original;
- hash SHA-256;
- plantilla reconocida/confirmada;
- hoja y fila de encabezados;
- mapping de columnas;
- filas detectadas;
- PN originales y overrides confirmados;
- job_id asociado;
- decisiones de diferencias;
- fecha de creación/actualización.

Primera implementación: almacenamiento de sesión en disco bajo un root configurable de V8, usando escritura atómica de metadata JSON y copia inmutable del `.xlsx`. El root debe estar fuera de temporales del sistema para sobrevivir reinicios.

Variable propuesta:

`STECH_EXCEL_SESSION_ROOT`

Default local de desarrollo:

`data/product_workbench_excel_sessions`

En PC020 se configurará una ruta persistente dedicada.

La sesión puede reabrirse después de cerrar el navegador o reiniciar V8. La cola técnica sigue viviendo únicamente en STECH_MCP SQL Server.

## 13. Tablas MCP para templates

Los números `009` ya están ocupados por `009_product_workspace_technical_v2.sql`, por lo que este diseño corrige la numeración antigua del plan Excel.

Nuevos scripts:

- `010_marketplace_templates_v2.sql`.
- `011_seed_marketplace_templates_v2.sql`.

Tablas:

### `marketplace_template`

- `template_code`;
- `channel_code`;
- `platform_code` opcional (`VTEX` para Coolbox cuando corresponda);
- `category_code`;
- `version_code`;
- `sheet_pattern`;
- rango de fila de encabezados;
- activo.

### `marketplace_template_field`

- template;
- ordinal;
- `header_name`;
- `field_code` canónico nullable;
- `identifier_role` (`PARTNUMBER`, `EAN`, `UPC`, `EXTERNAL_SKU`, `NONE`);
- requerido;
- `data_scope`;
- peso de reconocimiento;
- distintivo.

### `marketplace_field_alias`

Aliases normalizados por template/campo.

## 14. MCP tools

Se incorporan de forma aditiva en `server_authoritative.py`:

- `excel_template_recognize(manifest)`;
- `excel_template_analyze(manifest, template_code?, row_pn_overrides?)`;
- `excel_template_export_values(partnumbers, template_code)`;

No se necesita `excel_template_job_create` como autoridad separada: V8 puede crear el job por `product_work_job_create` después de una resolución/confirmación válida del template y los PN. Si se mantiene el tool por compatibilidad, será un wrapper del mismo `ProductWorkService`, nunca otra cola.

## 15. API V8

Endpoints nuevos/revisados:

- `POST /api/product-workbench/excel-sessions` — cargar y analizar workbook;
- `GET /api/product-workbench/excel-sessions/{session_id}` — reabrir estado;
- `PUT /api/product-workbench/excel-sessions/{session_id}/rows/{row_number}/partnumber` — confirmar/cambiar PN;
- `POST /api/product-workbench/excel-sessions/{session_id}/analyze` — recalcular completitud/faltantes;
- `POST /api/product-workbench/excel-sessions/{session_id}/enrich` — crear un job `ENRICH_TECHNICAL` con los PN seleccionados;
- `POST /api/product-workbench/excel-sessions/{session_id}/differences/{difference_id}` — guardar decisión de conflicto;
- `POST /api/product-workbench/excel-sessions/{session_id}/export` — generar copia enriquecida.

Los endpoints de búsqueda manual y jobs V2 existentes se mantienen.

## 16. UI de Carga Inteligente

La pestaña actual `Cargar Excel` será el flujo principal y por defecto al entrar a Product Workbench.

La pantalla tendrá:

- dropzone + selector de archivo;
- stepper 1–6;
- tarjeta de template reconocido con confianza;
- tabla de filas con PN editable;
- filtros: Todos / Listos / Falta PN / Necesita enriquecimiento / Completo / Revisión;
- selección múltiple;
- botón `Buscar PN sugerido` en filas sin PN;
- botón `Analizar información`;
- botón `Enriquecer seleccionados`;
- progreso del job en vivo cada 5 segundos;
- resumen de diferencias;
- botón `Exportar Excel completado`.

La pestaña `Buscar / Editar` sigue disponible para un producto individual. `Enriquecimiento`/`Jobs` siguen disponibles como vistas avanzadas de control.

## 17. Seguridad e invariantes

Obligatorio:

- no modificar precio;
- no modificar stock;
- no modificar costo;
- no modificar promociones;
- no activar/desactivar productos;
- no publicar VTEX por cargar/enriquecer Excel;
- no borrar ni cambiar imágenes;
- no reutilizar la cola legacy V8 para V2;
- no crear una segunda fuente maestra;
- no promover un candidato sin pasar por la verificación existente;
- no convertir una sugerencia de PN ambigua en confirmación automática;
- no sobrescribir un valor Excel diferente sin decisión explícita;
- no depender del nombre del archivo para reconocer una plantilla.

## 18. Pruebas obligatorias

### MCP

- reconocimiento independiente del filename;
- HIGH/MEDIUM/LOW/AMBIGUOUS;
- Coolbox identificado como canal con `platform_code=VTEX`;
- mapping técnico/comercial;
- PN/EAN/UPC identifier roles;
- campos comerciales jamás entran a `ENRICH_TECHNICAL`;
- no colisionar con `009_product_workspace_technical_v2.sql`;
- regresión completa del motor y Product Loader/VTEX existente.

### SCR/V8

- workbook con encabezado en fila 2/3/otra dentro de primeras 20;
- workbook con múltiples hojas;
- PN presente;
- PN vacío y override manual;
- sugerencia EAN/UPC única;
- sugerencia ambigua exige confirmación;
- PN duplicado en múltiples filas crea un solo item técnico;
- cierre/reapertura de sesión;
- job continúa aunque se cierre V8;
- export llena celdas técnicas vacías;
- export preserva precio/stock/promoción/control/unmapped;
- diferencia técnica no se sobrescribe por defecto;
- fórmulas fuera del mapping se conservan;
- `node --check` del módulo UI;
- suite completa existente.

### E2E mínimo de aceptación

Usar un workbook real de laptop con al menos dos filas:

1. una con PN completo;
2. una con PN vacío pero EAN/identidad suficiente para sugerencia o entrada manual.

Resultado esperado:

- template detectado/confirmado;
- ambos PN resueltos;
- job creado y procesado;
- Product Workspace actualizado con hechos validados;
- Excel exportado;
- al menos una celda técnica vacía completada;
- precio y stock comparados byte/valor a valor y sin cambios;
- ninguna publicación VTEX disparada.

## 19. Orden de implementación

1. MCP Template Registry (`010/011`).
2. Recognizer + mapper + manifest contracts.
3. Excel analysis tools MCP.
4. V8 persistent Excel session store.
5. V8 upload/recognition/PN resolution API.
6. Carga Inteligente UI.
7. Job handoff/polling.
8. Export engine con política de diferencias.
9. Product Workspace/readiness visible desde la sesión.
10. E2E con workbook real y regresión completa.

## 20. Criterio de terminado

La función se considera lista para prueba operativa cuando el usuario puede, desde una sola pestaña:

```text
Cargar Excel
→ reconocer plantilla
→ resolver PN faltantes
→ analizar faltantes
→ enriquecer
→ cerrar/volver y ver progreso
→ revisar diferencias
→ exportar el mismo Excel completado
```

sin modificar precio, stock, promociones, imágenes, activación ni publicación VTEX, y con toda la información técnica nueva primero consolidada en Product Workspace.
