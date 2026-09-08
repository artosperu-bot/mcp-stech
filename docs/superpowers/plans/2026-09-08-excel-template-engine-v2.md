# Excel Template Engine V2 — Implementation Plan

> **Para Steve:** REQUIRED SUB-SKILL: ejecutar con `superpowers:subagent-driven-development` o `superpowers:executing-plans`, con TDD y commits pequeños.

**Goal:** reconocer automáticamente plantillas Excel de Falabella, Coolbox y futuros canales por estructura interna, mapear columnas a campos canónicos STECH, detectar Part Numbers y calcular qué falta antes de enviar productos a la cola de enriquecimiento.

**Architecture:** V8 hace I/O del archivo y extrae un manifest neutral; STECH MCP posee las reglas de reconocimiento/mapping/validación. El Excel es entrada/salida de canal, nunca la ficha maestra. Las columnas comerciales pueden conservarse para exportación pero quedan fuera de `ENRICH_TECHNICAL`.

**Tech Stack:** Python 3.12, openpyxl existente, SQL Server, FastMCP, pytest.

---

## Task 1: Registry SQL de plantillas y campos

**Files:**
- Create: `sql/009_marketplace_templates_v2.sql`
- Create: `tests/test_marketplace_template_schema.py`

**Step 1 — Prueba fallando**

Exigir tablas:
- `marketplace_template`
- `marketplace_template_field`
- `marketplace_field_alias`

Campos mínimos template:
- `template_code`, `channel_code`, `category_code`, `version_code`, `sheet_pattern`, `header_row_min/max`, `is_active`.

Campos mínimos field:
- posición opcional, nombre esperado, `field_code` canónico opcional, required flag, data scope (`TECHNICAL`, `IDENTITY`, `CONTENT`, `COMMERCIAL`, `CONTROL`), aliases y weight de reconocimiento.

Run:
```bash
pytest tests/test_marketplace_template_schema.py -q
```
Expected: FAIL.

**Step 2 — Implementar SQL**

Incluir índices por canal/categoría y template activo. No poner reglas de negocio de investigación en estas tablas.

**Step 3 — Verify/commit**
```bash
pytest tests/test_marketplace_template_schema.py -q
git add sql/009_marketplace_templates_v2.sql tests/test_marketplace_template_schema.py
git commit -m "feat: add marketplace Excel template registry"
```

---

## Task 2: Repositorio de templates y aliases

**Files:**
- Create: `src/stech_mcp/db/marketplace_template_repository.py`
- Create: `tests/test_marketplace_template_repository.py`

**Step 1 — Prueba fallando**

Probar:
- obtener templates activos;
- cargar campos/aliases;
- múltiples versiones por canal/categoría;
- template desactivado no participa;
- alias normalizado case/espacios/acentos.

**Step 2 — Implementar**

**Step 3 — Verify/commit**
```bash
pytest tests/test_marketplace_template_repository.py -q
git add src/stech_mcp/db/marketplace_template_repository.py tests/test_marketplace_template_repository.py
git commit -m "feat: read marketplace template definitions"
```

---

## Task 3: Workbook Manifest neutral

**Files:**
- Create: `src/stech_mcp/domain/excel_manifest.py`
- Create: `src/stech_mcp/services/excel_manifest_builder.py`
- Create: `tests/test_excel_manifest_builder.py`

**Step 1 — Prueba fallando**

Generar workbooks pequeños en memoria con openpyxl y probar que el manifest contiene:
- nombres de hojas;
- dimensiones aproximadas;
- candidatos de filas de encabezado;
- textos normalizados de encabezados;
- muestras limitadas de filas;
- tipos básicos;
- sin fórmulas ejecutadas ni macros.

**Step 2 — Implementar**

El builder debe aceptar bytes/stream local cuando se usa dentro de MCP, pero el contrato serializable principal será JSON para que V8 pueda construir el mismo manifest sin mover archivos grandes entre procesos.

Limitar tamaño de muestras para no mandar miles de filas al recognizer.

**Step 3 — Verify/commit**
```bash
pytest tests/test_excel_manifest_builder.py -q
git add src/stech_mcp/domain/excel_manifest.py src/stech_mcp/services/excel_manifest_builder.py tests/test_excel_manifest_builder.py
git commit -m "feat: build neutral workbook manifests"
```

---

## Task 4: Recognizer con scoring explicable

**Files:**
- Create: `src/stech_mcp/services/excel_template_recognizer.py`
- Create: `tests/test_excel_template_recognizer.py`

**Step 1 — Pruebas fallando**

Casos:
- nombre de archivo incorrecto pero headers Coolbox correctos → reconocer Coolbox;
- hoja renombrada pero 95% headers → seguir reconociendo;
- dos columnas nuevas → no romper;
- Falabella vs Coolbox con campos parecidos → usar distinctive fields/weights;
- score alto/medio/bajo;
- empate cercano → `AMBIGUOUS`, no escoger silenciosamente.

Scoring recomendado:
- headers/aliases: peso principal;
- campos distintivos: bonus fuerte;
- hoja: bonus, nunca único criterio;
- orden aproximado: bonus menor;
- PN/SKU candidate: bonus;
- nombre de archivo: señal débil opcional.

**Step 2 — Implementar salida explicable**

Retornar:
- `template_code`, channel, category, version;
- confidence 0-100;
- matched headers;
- missing distinctive headers;
- header row/sheet;
- razones del score;
- alternativas cercanas.

**Step 3 — Verify/commit**
```bash
pytest tests/test_excel_template_recognizer.py -q
git add src/stech_mcp/services/excel_template_recognizer.py tests/test_excel_template_recognizer.py
git commit -m "feat: recognize marketplace Excel templates by structure"
```

---

## Task 5: Mapper columnas → campos canónicos

**Files:**
- Create: `src/stech_mcp/services/excel_template_mapper.py`
- Create: `tests/test_excel_template_mapper.py`

**Step 1 — Pruebas fallando**

Ejemplos:
- `Memoria RAM`, `Capacidad RAM`, `RAM` → `ram_gb`;
- `Autonomía`, `Duración de batería` → `battery_runtime_hours`;
- `Sku code ref` / seller SKU definido por template → campo de identidad/PN apropiado;
- columnas price/stock → scope `COMMERCIAL`, jamás pending technical;
- columna desconocida → `UNMAPPED`, preservada para revisión.

**Step 2 — Implementar**

No transformar valores marketplace todavía; solo resolver la identidad del campo y su scope.

**Step 3 — Verify/commit**
```bash
pytest tests/test_excel_template_mapper.py -q
git add src/stech_mcp/services/excel_template_mapper.py tests/test_excel_template_mapper.py
git commit -m "feat: map Excel headers to canonical product fields"
```

---

## Task 6: Detector de PN y extracción de filas de producto

**Files:**
- Create: `src/stech_mcp/services/excel_product_rows.py`
- Create: `tests/test_excel_product_rows.py`

**Step 1 — Pruebas fallando**

Cubrir:
- PN exacto desde columna configurada;
- trim/uppercase sin alterar caracteres significativos;
- filas vacías ignoradas;
- PN duplicado reportado, no duplicado en queue input;
- filas con SKU marketplace distinto al PN necesitan mapping explícito, no inferencia ciega;
- conservar `row_number` y valores originales para export posterior.

**Step 2 — Implementar**

**Step 3 — Verify/commit**
```bash
pytest tests/test_excel_product_rows.py -q
git add src/stech_mcp/services/excel_product_rows.py tests/test_excel_product_rows.py
git commit -m "feat: extract product rows from recognized templates"
```

---

## Task 7: Validator contra Product Workspace/readiness

**Files:**
- Create: `src/stech_mcp/services/excel_template_validator.py`
- Create: `tests/test_excel_template_validator.py`

**Step 1 — Pruebas fallando**

Para cada PN/template calcular:
- required fields total;
- ya disponibles en Product Workspace;
- missing technical;
- missing content/identity;
- commercial fields fuera de alcance;
- readiness del template.

Caso clave: producto maestro completo pero template pide un campo específico del canal → missing channel field sin reinvestigar toda la ficha.

**Step 2 — Implementar**

Usar facts canónicos y mappings; no leer directamente `coolbox_preview.py` como verdad maestra.

**Step 3 — Verify/commit**
```bash
pytest tests/test_excel_template_validator.py -q
git add src/stech_mcp/services/excel_template_validator.py tests/test_excel_template_validator.py
git commit -m "feat: validate template readiness against Product Workspace"
```

---

## Task 8: Seeds iniciales Coolbox y Falabella

**Files:**
- Create: `sql/010_seed_marketplace_templates_v2.sql`
- Create: `tests/test_marketplace_template_seeds.py`

**Step 1 — Prueba fallando**

Seed mínimo:
- Coolbox `Laptops-All in one` usando los headers conocidos de la ficha actual;
- Falabella LAPTOP a partir de los contratos/campos ya existentes en V8, sin inventar atributos no confirmados.

Para Coolbox, clasificar `Precio Lista`, `Precio Base`, `Fecha de Inicio`, `Fecha Fin`, `Stock` como `COMMERCIAL`; recognizer puede detectarlos, enrichment técnico los ignora.

**Step 2 — Implementar seeds idempotentes**

**Step 3 — Verify/commit**
```bash
pytest tests/test_marketplace_template_seeds.py -q
git add sql/010_seed_marketplace_templates_v2.sql tests/test_marketplace_template_seeds.py
git commit -m "feat: seed Coolbox and Falabella Excel templates"
```

---

## Task 9: Servicio coordinador Excel Template Engine

**Files:**
- Create: `src/stech_mcp/services/excel_template_service.py`
- Create: `tests/test_excel_template_service.py`

**Step 1 — Prueba fallando**

`analyze_manifest()` debe devolver:
- recognition;
- product rows;
- duplicates/errors;
- template field mapping;
- per-product readiness;
- queue recommendation (`UP_TO_DATE`, `ENRICH_LIGHT`, `ENRICH_DEEP`, `REVIEW_TEMPLATE`).

No crear job automáticamente en análisis; la creación es acción explícita del usuario/V8.

**Step 2 — Implementar**

**Step 3 — Verify/commit**
```bash
pytest tests/test_excel_template_service.py -q
git add src/stech_mcp/services/excel_template_service.py tests/test_excel_template_service.py
git commit -m "feat: coordinate Excel recognition and readiness analysis"
```

---

## Task 10: MCP tools para análisis/importación

**Files:**
- Create: `src/stech_mcp/tools/excel_template.py`
- Modify: `src/stech_mcp/server.py`
- Create: `tests/test_server_excel_template_tools.py`

**Tools iniciales:**
- `excel_template_recognize(manifest)`
- `excel_template_analyze(manifest)`
- `excel_template_job_create(analysis_id or rows, priority=...)`

`excel_template_job_create` debe terminar usando `ProductWorkService` y crear `ENRICH_TECHNICAL`, no una cola Excel paralela.

**Step 1 — Pruebas fallando**

Comprobar alta/media/baja confianza y que job creation deduplica PN.

**Step 2 — Implementar**

**Step 3 — Verify/commit**
```bash
pytest tests/test_server_excel_template_tools.py tests/test_server_product_work_tools.py -q
git add src/stech_mcp/tools/excel_template.py src/stech_mcp/server.py tests/test_server_excel_template_tools.py
git commit -m "feat: expose Excel template analysis through MCP"
```

---

## Task 11: Export mapping contract

**Files:**
- Create: `src/stech_mcp/services/marketplace_export_mapping.py`
- Create: `tests/test_marketplace_export_mapping.py`

**Step 1 — Pruebas fallando**

Dado PN + template, producir valores para columnas desde Product Workspace manteniendo:
- orden original del template;
- columnas desconocidas/no administradas sin destrucción;
- commercial values sin tocar salvo que otro flujo los provea;
- transformación de unidad/enum específica del canal solo en mapper de salida.

**Step 2 — Implementar contrato**

El archivo físico puede generarlo V8; MCP devuelve mapping/values y readiness.

**Step 3 — Verify/commit**
```bash
pytest tests/test_marketplace_export_mapping.py -q
git add src/stech_mcp/services/marketplace_export_mapping.py tests/test_marketplace_export_mapping.py
git commit -m "feat: map canonical facts back to marketplace templates"
```

---

## Task 12: Integración Excel → cola → Product Workspace → export

**Files:**
- Create: `tests/test_excel_template_engine_v2_integration.py`

**Scenario:** workbook Coolbox/Falabella generado en test con 3 PNs:
- PN A completo;
- PN B con 3 faltantes;
- PN C con conflicto.

Assertions:
- template reconocido por headers aunque filename sea genérico;
- PN A = up to date;
- PN B genera enrichment solo para faltantes;
- PN C requiere review;
- job usa cola genérica;
- después de enriquecer, export mapping completa campos técnicos;
- price/stock originales no se modifican.

Run:
```bash
pytest tests/test_excel_template_engine_v2_integration.py -q
pytest -q
```
Expected: PASS.

Commit:
```bash
git add tests/test_excel_template_engine_v2_integration.py
git commit -m "test: validate Excel template enrichment flow"
```

## Definition of Done

- Reconocimiento no depende del nombre del archivo.
- Cambios menores de headers/orden no rompen la detección.
- Ambigüedad se muestra, no se adivina.
- PN/SKU se detecta por contrato del template.
- Campos Excel se mapean a facts canónicos.
- Price/stock son COMMERCIAL y quedan fuera del enrichment técnico.
- Falabella y Coolbox son templates pares.
- Importación usa la misma cola `product_work_job`.
- Export puede reconstruir la plantilla desde Product Workspace sin convertir el Excel en master.
- Suite completa verde.