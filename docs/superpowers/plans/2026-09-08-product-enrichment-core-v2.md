# Product Enrichment Core V2 — Implementation Plan

> **Para Steve:** REQUIRED SUB-SKILL: ejecutar con `superpowers:subagent-driven-development` o `superpowers:executing-plans`, con TDD y commits pequeños.

**Goal:** construir el motor técnico canónico que toma un PN, reutiliza Deltron + datos aprobados, detecta únicamente campos faltantes/conflictivos, obtiene evidencia web/documental, valida candidatos y promueve hechos seguros a Product Workspace sin tocar precio ni stock.

**Architecture:** category schemas definen qué atributos existen; adapters convierten fuentes a campos canónicos; research produce candidatos, nunca escribe directo; validación/promotion reutiliza `source_policy.py`, `product_field_verification.py` y `enrichment_repository.py`; el handler `ENRICH_TECHNICAL` conecta el motor con el worker del Plan A.

**Tech Stack:** Python 3.12, SQL Server/pyodbc, httpx, pypdf, pytest; servicios existentes de Product Workspace.

---

## Task 1: Schemas canónicos por categoría

**Files:**
- Create: `sql/007_product_attribute_schema_v2.sql`
- Create: `src/stech_mcp/domain/product_schema.py`
- Create: `src/stech_mcp/db/product_schema_repository.py`
- Create: `tests/test_product_schema_v2.py`
- Create: `tests/test_product_schema_repository.py`

**Step 1 — Pruebas fallando**

Exigir tablas `product_attribute_definition` y `category_attribute`, con `field_code`, tipo, unidad, required/recommended, variant_sensitive, reuse_policy y orden.

Seed inicial mínimo:
- `LAPTOP`
- `PORTABLE_SPEAKER`
- `HEADPHONES`

Probar que un category schema devuelve required/recommended ordenados y que campos sensibles a variante quedan marcados.

Run:
```bash
pytest tests/test_product_schema_v2.py tests/test_product_schema_repository.py -q
```
Expected: FAIL.

**Step 2 — Implementar**

No agregar todos estos atributos como columnas de `product_master`; son facts canónicos variables.

**Step 3 — Verificar y commit**
```bash
pytest tests/test_product_schema_v2.py tests/test_product_schema_repository.py -q
git add sql/007_product_attribute_schema_v2.sql src/stech_mcp/domain/product_schema.py src/stech_mcp/db/product_schema_repository.py tests/test_product_schema_v2.py tests/test_product_schema_repository.py
git commit -m "feat: add canonical category attribute schemas"
```

---

## Task 2: Category Schema Service + MCP status

**Files:**
- Create: `src/stech_mcp/services/product_schema_service.py`
- Create: `src/stech_mcp/services/product_technical_status.py`
- Create: `src/stech_mcp/tools/product_schema.py`
- Modify: `src/stech_mcp/server.py`
- Create: `tests/test_product_technical_status.py`
- Create: `tests/test_server_product_schema_tools.py`

**Step 1 — Prueba fallando**

Exigir:
- `product_schema_get(category)`;
- `product_technical_status(partnumber)`;
- cálculo `known_fields`, `missing_required`, `missing_recommended`, `conflicts`, `completion_pct`;
- no incluir price/stock como technical fields.

**Step 2 — Implementar**

`product_technical_status` combina `ProductRepository`, `EnrichmentRepository` y schema; no investiga todavía.

**Step 3 — Verificar y commit**
```bash
pytest tests/test_product_technical_status.py tests/test_server_product_schema_tools.py -q
git add src/stech_mcp/services/product_schema_service.py src/stech_mcp/services/product_technical_status.py src/stech_mcp/tools/product_schema.py src/stech_mcp/server.py tests/test_product_technical_status.py tests/test_server_product_schema_tools.py
git commit -m "feat: expose technical schema and missing fields"
```

---

## Task 3: Adapter Deltron → facts canónicos

**Files:**
- Create: `src/stech_mcp/services/deltron_fact_adapter.py`
- Create: `tests/test_deltron_fact_adapter.py`

**Step 1 — Pruebas fallando**

Con fixtures dict/JSON, probar mappings como RAM, almacenamiento, pantalla, Bluetooth, potencia, IP rating, dimensiones, peso y autonomía según categoría.

Reglas:
- preservar valor original + valor normalizado;
- no mapear un label ambiguo sin regla explícita;
- no enviar price/stock al enrichment técnico;
- emitir candidate/evidence metadata con source `DELTRON`.

**Step 2 — Implementar registry de aliases/mappers**

Evitar un gran `if category == ...`; usar mapping declarativo por `field_code` y normalizadores reutilizables.

**Step 3 — Verify/commit**
```bash
pytest tests/test_deltron_fact_adapter.py -q
git add src/stech_mcp/services/deltron_fact_adapter.py tests/test_deltron_fact_adapter.py
git commit -m "feat: normalize Deltron specs into canonical facts"
```

---

## Task 4: Documentos, hashes y candidatos persistentes

**Files:**
- Create: `sql/008_product_research_evidence_v2.sql`
- Create: `src/stech_mcp/db/source_document_repository.py`
- Create: `src/stech_mcp/db/fact_candidate_repository.py`
- Create: `tests/test_source_document_repository.py`
- Create: `tests/test_fact_candidate_repository.py`

**Step 1 — Pruebas fallando**

Exigir:
- `source_document` deduplicado por SHA-256/URL versionada;
- `source_document_match` por PN con match exact/model/family;
- `product_fact_candidate` con original/normalizado/unidad/source/source_partnumber/evidence/page/confidence/status;
- múltiples evidencias pueden coexistir;
- no sobrescribir candidatos silenciosamente.

**Step 2 — Implementar SQL + repositorios**

Estados candidate: `PENDING`, `VERIFIED`, `REJECTED`, `CONFLICT`, `PROMOTED`.

**Step 3 — Verificar/commit**
```bash
pytest tests/test_source_document_repository.py tests/test_fact_candidate_repository.py -q
git add sql/008_product_research_evidence_v2.sql src/stech_mcp/db/source_document_repository.py src/stech_mcp/db/fact_candidate_repository.py tests/test_source_document_repository.py tests/test_fact_candidate_repository.py
git commit -m "feat: persist source documents and fact candidates"
```

---

## Task 5: Descarga HTML/PDF y extracción reutilizable

**Files:**
- Modify: `pyproject.toml`
- Create: `src/stech_mcp/http/source_client.py`
- Create: `src/stech_mcp/services/source_document_service.py`
- Create: `tests/test_source_client.py`
- Create: `tests/test_source_document_service.py`

**Step 1 — Pruebas fallando**

Cubrir:
- HTTP timeout, redirect, content-type, max bytes;
- solo http/https;
- hash SHA-256;
- HTML → texto limpio;
- PDF → texto por página;
- segundo ingest del mismo documento reutiliza hash y no reprocesa;
- error de PDF no invalida todo el job, queda evidencia de fallo controlado.

**Step 2 — Dependencias**

Agregar rangos compatibles:
- `httpx>=0.28,<1`
- `pypdf>=5,<7`

No agregar browser automation al core.

**Step 3 — Implementar**

El servicio devuelve documento + páginas/texto, pero no promueve facts.

**Step 4 — Verificar/commit**
```bash
pytest tests/test_source_client.py tests/test_source_document_service.py -q
git add pyproject.toml src/stech_mcp/http/source_client.py src/stech_mcp/services/source_document_service.py tests/test_source_client.py tests/test_source_document_service.py
git commit -m "feat: ingest and cache official HTML and PDF sources"
```

---

## Task 6: Research providers y plan dirigido a pending_fields

**Files:**
- Create: `src/stech_mcp/services/research/__init__.py`
- Create: `src/stech_mcp/services/research/source_provider.py`
- Create: `src/stech_mcp/services/research/search_provider.py`
- Create: `src/stech_mcp/services/research/research_planner.py`
- Create: `src/stech_mcp/services/research/manufacturer_provider.py`
- Create: `src/stech_mcp/services/research/authorized_distributor_provider.py`
- Create: `tests/test_research_planner.py`
- Create: `tests/test_search_provider_contract.py`

**Step 1 — Pruebas fallando**

El planner recibe PN, marca, categoría, `pending_fields` y fuentes ya probadas. Debe:
- priorizar fabricante oficial;
- priorizar documentos oficiales;
- luego distribuidor autorizado;
- no buscar fields ya verificados con evidencia suficiente;
- limitar queries/fuentes por campo;
- no aceptar resultado de otro PN para variant-sensitive fields.

**Step 2 — Implementar interfaz SearchProvider**

Contrato vendor-neutral: `search(query, domains=None, limit=...)`. Configuración externa; nunca incrustar API keys. Si no existe provider configurado, el motor puede ingerir URLs ya conocidas y terminar `PARTIAL`/`REVIEW_REQUIRED`, no inventar resultados.

**Step 3 — Implementar providers**

Los providers transforman search results/documentos a `EvidenceCandidate`; no escriben a DB directamente.

**Step 4 — Verificar/commit**
```bash
pytest tests/test_research_planner.py tests/test_search_provider_contract.py -q
git add src/stech_mcp/services/research tests/test_research_planner.py tests/test_search_provider_contract.py
git commit -m "feat: add directed technical research providers"
```

---

## Task 7: Extracción de candidatos desde evidencia

**Files:**
- Create: `src/stech_mcp/services/fact_extractor.py`
- Create: `src/stech_mcp/services/fact_normalizers.py`
- Create: `tests/test_fact_extractor.py`
- Create: `tests/test_fact_normalizers.py`

**Step 1 — Pruebas fallando**

Probar extractores determinísticos para patterns comunes: unidades, dimensiones, batería/autonomía, Bluetooth, IP rating, frecuencia, potencia, peso, RAM/storage, resolución.

Cuando texto libre no sea seguro, producir `PENDING` candidate con evidencia en vez de adivinar.

**Step 2 — Implementar**

Separar parsing de normalización. Guardar siempre evidence snippet y document/page.

**Step 3 — Verificar/commit**
```bash
pytest tests/test_fact_extractor.py tests/test_fact_normalizers.py -q
git add src/stech_mcp/services/fact_extractor.py src/stech_mcp/services/fact_normalizers.py tests/test_fact_extractor.py tests/test_fact_normalizers.py
git commit -m "feat: extract normalized candidates from source evidence"
```

---

## Task 8: Validación, conflictos y promoción

**Files:**
- Modify: `src/stech_mcp/services/product_field_verification.py`
- Modify: `src/stech_mcp/domain/source_policy.py`
- Create: `src/stech_mcp/services/fact_promotion.py`
- Create: `tests/test_fact_promotion.py`
- Extend: `tests/test_product_field_verification.py`

**Step 1 — Pruebas fallando**

Casos obligatorios:
- A1 exact PN vence B/C conflictivo;
- manual A2 exact PN válido;
- otro PN no promueve RAM/SSD/CPU/color/battery variant-sensitive;
- evidence débil no sobrescribe approved manual/A1;
- conflicto irresoluble → `REVIEW_REQUIRED`;
- todas las evidencias permanecen auditables;
- promoción idempotente no duplica.

**Step 2 — Implementar reutilizando reglas existentes**

No crear una segunda jerarquía de confianza. Extender aliases/source types solo cuando sea necesario.

**Step 3 — Verificar/commit**
```bash
pytest tests/test_fact_promotion.py tests/test_product_field_verification.py -q
git add src/stech_mcp/services/fact_promotion.py src/stech_mcp/services/product_field_verification.py src/stech_mcp/domain/source_policy.py tests/test_fact_promotion.py tests/test_product_field_verification.py
git commit -m "feat: validate and promote technical facts by evidence strength"
```

---

## Task 9: Orquestador de enriquecimiento por PN

**Files:**
- Create: `src/stech_mcp/services/product_enrichment_engine.py`
- Create: `tests/test_product_enrichment_engine.py`

**Step 1 — Pruebas fallando**

Pipeline esperado:
1. load source product;
2. load approved facts;
3. adapt Deltron;
4. promote deterministic/strong existing candidates;
5. calculate pending fields;
6. research only pending/conflicts;
7. ingest docs;
8. extract candidates;
9. validate/promote;
10. recalculate status;
11. rebuild Product Workspace/readiness.

Probar producto completo: no web research. Producto parcial: solo 3 pending fields. Producto no encontrado: controlled `NO_DATA_FOUND`. Conflicto: `REVIEW_REQUIRED`.

Asegurar spy/assertion de que no hay writes de price/stock.

**Step 2 — Implementar**

Retorno estructurado con `state`, `before`, `after`, `promoted_fields`, `remaining_fields`, `sources_consulted`, `conflicts`.

**Step 3 — Verify/commit**
```bash
pytest tests/test_product_enrichment_engine.py -q
git add src/stech_mcp/services/product_enrichment_engine.py tests/test_product_enrichment_engine.py
git commit -m "feat: orchestrate missing-field technical enrichment"
```

---

## Task 10: Conectar ENRICH_TECHNICAL al worker

**Files:**
- Modify: `src/stech_mcp/services/product_work_dispatcher.py`
- Create: `src/stech_mcp/services/handlers/enrich_technical.py`
- Create: `src/stech_mcp/services/handlers/__init__.py`
- Create: `tests/test_enrich_technical_handler.py`

**Step 1 — Pruebas fallando**

El handler mapea estados engine → work item:
- completo → `COMPLETED`;
- parcial con faltantes no críticos → `PARTIAL`;
- conflicto/manual review → `REVIEW_REQUIRED`;
- fuente temporal caída → `FAILED_RETRYABLE`;
- error permanente → `FAILED`.

Debe actualizar `current_step`/progress durante las etapas.

**Step 2 — Implementar y registrar**

**Step 3 — Verificar/commit**
```bash
pytest tests/test_enrich_technical_handler.py tests/test_product_work_worker.py -q
git add src/stech_mcp/services/handlers src/stech_mcp/services/product_work_dispatcher.py tests/test_enrich_technical_handler.py
git commit -m "feat: execute technical enrichment from persistent worker"
```

---

## Task 11: Readiness multicanal desde ficha maestra

**Files:**
- Modify: `src/stech_mcp/services/product_readiness.py`
- Modify: `src/stech_mcp/services/marketplace_preview.py`
- Create: `tests/test_multichannel_readiness_v2.py`

**Step 1 — Pruebas fallando**

Para el mismo PN devolver readiness separado por `FALABELLA`, `COOLBOX`, `VTEX`, sin que uno cambie la ficha maestra de otro.

**Step 2 — Implementar**

Mantener compatibilidad con consumidores actuales; agregar contrato V2, no romper previews existentes.

**Step 3 — Verificar/commit**
```bash
pytest tests/test_multichannel_readiness_v2.py tests/test_product_readiness.py tests/test_marketplace_preview.py -q
git add src/stech_mcp/services/product_readiness.py src/stech_mcp/services/marketplace_preview.py tests/test_multichannel_readiness_v2.py
git commit -m "feat: calculate channel-neutral product readiness"
```

---

## Task 12: Herramientas MCP de investigación y auditoría

**Files:**
- Create: `src/stech_mcp/tools/product_research.py`
- Modify: `src/stech_mcp/server.py`
- Create: `tests/test_server_product_research_tools.py`

**Tools:**
- `product_technical_missing_list`
- `product_research_plan`
- `product_source_ingest`
- `product_fact_candidates`
- `product_fact_promote`
- `product_fact_promote_batch`

**Step 1 — Pruebas fallando**

Validar inputs y que ninguna tool permite promoción sin pasar política de verificación.

**Step 2 — Implementar**

**Step 3 — Verificar/commit**
```bash
pytest tests/test_server_product_research_tools.py tests/test_server_smoke.py -q
git add src/stech_mcp/tools/product_research.py src/stech_mcp/server.py tests/test_server_product_research_tools.py
git commit -m "feat: expose technical research audit tools"
```

---

## Task 13: Integración controlada de 3 categorías

**Files:**
- Create: `tests/test_product_enrichment_v2_integration.py`
- Modify only as failures reveal genuine gaps.

**Scenario:**
- LAPTOP con mayoría de datos Deltron;
- PORTABLE_SPEAKER con PDF oficial;
- HEADPHONES con conflicto distribuidor vs fabricante.

**Assertions:**
- solo pending fields se investigan;
- exact PN enforced;
- documents reused by hash;
- candidates/evidence auditables;
- correct promotion/conflict;
- Product Workspace updated;
- price/stock unchanged.

Run:
```bash
pytest tests/test_product_enrichment_v2_integration.py -q
pytest -q
```
Expected: PASS.

Commit:
```bash
git add tests/test_product_enrichment_v2_integration.py
git commit -m "test: validate Product Enrichment Engine V2 end to end"
```

## Definition of Done

- Category schemas no dependen de Coolbox.
- Deltron alimenta facts canónicos, no columnas marketplace.
- Se investiga únicamente lo faltante/conflictivo.
- HTML/PDF se guarda y reutiliza por hash.
- Extractores producen candidatos, no escrituras directas.
- Fuente/PN/evidencia/confianza quedan persistidos.
- Conflictos se resuelven por política o pasan a revisión.
- Worker puede ejecutar `ENRICH_TECHNICAL`.
- Product Workspace se actualiza progresivamente.
- Falabella/Coolbox/VTEX tienen readiness independiente.
- Precio y stock permanecen fuera del flujo técnico.
- Suite completa verde.