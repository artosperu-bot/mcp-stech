# Product Work Queue + Worker V2 — Implementation Plan

> **Para Steve:** REQUIRED SUB-SKILL: ejecutar con `superpowers:subagent-driven-development` o `superpowers:executing-plans` y verificar cada tarea antes de continuar.

**Goal:** crear una cola persistente genérica y un worker separado del proceso MCP para ejecutar trabajos largos de producto, empezando por `ENRICH_TECHNICAL`, con prioridad, leases, retries, reanudación e idempotencia.

**Architecture:** SQL Server es la autoridad del estado. STECH MCP crea/consulta/controla trabajos; un proceso `stech-enrichment-worker` reclama items mediante leases atómicos y ejecuta handlers por `work_type`. El flujo VTEX existente basado en `product_loader_job` queda intacto.

**Tech Stack:** Python 3.12, SQL Server, pyodbc, FastMCP, pytest; wrapper de ejecución Windows separado del servidor MCP.

---

## Task 1: Contrato SQL de cola genérica

**Files:**
- Create: `sql/006_product_work_queue_v2.sql`
- Create: `tests/test_product_work_queue_schema.py`

**Step 1 — Escribir prueba que falle**

Crear prueba de texto/contrato que exija las tablas `product_work_job`, `product_work_item`, `product_work_event`, `product_work_attempt`, sus estados, índices y campos de lease (`claimed_by`, `claimed_at`, `claim_expires_at`, `next_attempt_at`). También debe comprobar una protección contra duplicados activos por `partnumber + work_type + context_hash`.

Run:
```bash
pytest tests/test_product_work_queue_schema.py -q
```
Expected: FAIL porque `sql/006_product_work_queue_v2.sql` no existe.

**Step 2 — Implementar SQL mínimo**

Definir:
- job states: `PENDING`, `RUNNING`, `WAITING_REVIEW`, `COMPLETED`, `PARTIAL`, `FAILED`, `CANCELLED`;
- item states: `QUEUED`, `LOADING_SOURCE_DATA`, `ANALYZING_MISSING_FIELDS`, `RESEARCHING`, `READING_DOCUMENTS`, `VALIDATING`, `PROMOTING_FACTS`, `REBUILDING_PRODUCT_MASTER`, `COMPLETED`, `PARTIAL`, `REVIEW_REQUIRED`, `NO_DATA_FOUND`, `FAILED_RETRYABLE`, `FAILED`, `CANCELLED`;
- `priority`, `attempt_count`, `max_attempts`, `next_attempt_at`;
- lease fields;
- `input_json`, `context_hash`, `last_error_*`;
- índices de claim por estado/prioridad/next_attempt;
- índice filtrado/estrategia equivalente para impedir duplicados activos.

**Step 3 — Verificar**
```bash
pytest tests/test_product_work_queue_schema.py -q
```
Expected: PASS.

**Step 4 — Commit**
```bash
git add sql/006_product_work_queue_v2.sql tests/test_product_work_queue_schema.py
git commit -m "feat: add generic product work queue schema"
```

---

## Task 2: Modelos de dominio y normalización

**Files:**
- Create: `src/stech_mcp/domain/product_work_models.py`
- Create: `tests/test_product_work_models.py`

**Step 1 — Prueba fallando**

Probar:
- conjuntos válidos de `WORK_TYPES`, `JOB_STATES`, `ITEM_STATES`;
- `normalize_partnumber()`;
- cálculo determinístico de `context_hash` para evitar duplicados;
- estados terminales y retryables.

Run:
```bash
pytest tests/test_product_work_models.py -q
```
Expected: FAIL.

**Step 2 — Implementación mínima**

Definir `ENRICH_TECHNICAL`, `RESEARCH_IDENTITY`, `RESEARCH_IMAGES`, `PREPARE_CHANNEL`, `PUBLISH_CHANNEL`; helper de hash sobre `work_type`, PN, categoría, canal/contexto relevante; no incluir campos comerciales volátiles en el hash técnico.

**Step 3 — Verificar y commit**
```bash
pytest tests/test_product_work_models.py -q
git add src/stech_mcp/domain/product_work_models.py tests/test_product_work_models.py
git commit -m "feat: add product work domain contract"
```

---

## Task 3: Repositorio persistente con claim atómico

**Files:**
- Create: `src/stech_mcp/db/product_work_repository.py`
- Create: `tests/test_product_work_repository.py`
- Create: `tests/test_product_work_repository_transitions.py`

**Step 1 — Pruebas fallando**

Cubrir:
- crear un job con N items;
- si el mismo PN/contexto ya está activo, devolver `ALREADY_ACTIVE` y no duplicar;
- claim ordenado por mayor `priority`, luego antigüedad;
- claim solo si `next_attempt_at <= now`;
- lease atómico con `UPDLOCK, READPAST` o patrón SQL equivalente;
- renovar lease;
- recuperar leases vencidos;
- transición válida/inválida;
- retry incrementa `attempt_count` y programa `next_attempt_at`;
- registrar event y attempt;
- resumen del job.

Run:
```bash
pytest tests/test_product_work_repository.py tests/test_product_work_repository_transitions.py -q
```
Expected: FAIL.

**Step 2 — Implementar repository**

Métodos mínimos:
- `create_job(...)`
- `get_job(job_id)`
- `list_jobs(...)`
- `claim_next(worker_id, lease_seconds)`
- `renew_claim(item_id, worker_id, lease_seconds)`
- `transition_item(...)`
- `record_attempt_start/end(...)`
- `schedule_retry(...)`
- `release_expired_claims()`
- `retry_item(...)`
- `cancel_item(...)`
- `refresh_job_summary(...)`

No reutilizar `ProductLoaderRepository`; compartir solo helpers genéricos si realmente son neutrales.

**Step 3 — Verificar**
```bash
pytest tests/test_product_work_repository.py tests/test_product_work_repository_transitions.py -q
```
Expected: PASS.

**Step 4 — Commit**
```bash
git add src/stech_mcp/db/product_work_repository.py tests/test_product_work_repository.py tests/test_product_work_repository_transitions.py
git commit -m "feat: persist generic product work jobs"
```

---

## Task 4: Servicio de control de jobs

**Files:**
- Create: `src/stech_mcp/services/product_work_service.py`
- Create: `tests/test_product_work_service.py`

**Step 1 — Prueba fallando**

Validar que el servicio:
- normaliza PN;
- deduplica una lista repetida;
- crea un job `ENRICH_TECHNICAL` sin price/stock en `input_json`;
- permite prioridad 10/50/100;
- expone estados resumidos;
- permite retry/cancel solo en estados válidos.

**Step 2 — Implementar**

Este servicio es síncrono y rápido: nunca ejecuta el enrichment; solo persiste órdenes/control.

**Step 3 — Verificar y commit**
```bash
pytest tests/test_product_work_service.py -q
git add src/stech_mcp/services/product_work_service.py tests/test_product_work_service.py
git commit -m "feat: add product work job service"
```

---

## Task 5: Herramientas MCP de cola

**Files:**
- Create: `src/stech_mcp/tools/product_work.py`
- Modify: `src/stech_mcp/server.py`
- Create: `tests/test_server_product_work_tools.py`

**Step 1 — Prueba fallando**

Exigir herramientas:
- `product_work_job_create`
- `product_work_job_get`
- `product_work_job_list`
- `product_work_item_retry`
- `product_work_item_cancel`

Probar creación con varios PNs, deduplicación y que la respuesta regrese `job_id`, conteos y items sin esperar ejecución.

**Step 2 — Implementar y registrar tools**

El tool `product_work_job_create` acepta lista de PNs/rows, `work_type`, categoría opcional, contexto/canal opcional, prioridad y `actor_source`.

**Step 3 — Verificar**
```bash
pytest tests/test_server_product_work_tools.py tests/test_server_smoke.py -q
```
Expected: PASS.

**Step 4 — Commit**
```bash
git add src/stech_mcp/tools/product_work.py src/stech_mcp/server.py tests/test_server_product_work_tools.py
git commit -m "feat: expose generic product work MCP tools"
```

---

## Task 6: Worker loop independiente y dispatcher

**Files:**
- Create: `src/stech_mcp/services/product_work_dispatcher.py`
- Create: `src/stech_mcp/worker.py`
- Create: `tests/test_product_work_dispatcher.py`
- Create: `tests/test_product_work_worker.py`

**Step 1 — Pruebas fallando**

Cubrir:
- dispatcher selecciona handler por `work_type`;
- work type desconocido → FAILED controlado;
- excepción temporal → `FAILED_RETRYABLE` + backoff;
- excepción permanente → `FAILED`;
- lease se renueva durante item largo;
- un fallo no detiene el siguiente item;
- al arrancar se liberan claims expirados;
- `run_once()` es determinístico y testeable;
- `run_forever()` solo envuelve polling y shutdown limpio.

**Step 2 — Implementar**

Inicialmente registrar un handler placeholder explícito para `ENRICH_TECHNICAL` que será reemplazado por el Plan B; si se invoca antes, debe devolver `REVIEW_REQUIRED`/error de capacidad controlado, nunca fingir enriquecimiento.

Configurar:
- `worker_id` estable por host/proceso;
- poll interval;
- lease seconds;
- exponential backoff con techo;
- stop event para apagado limpio.

**Step 3 — Verificar**
```bash
pytest tests/test_product_work_dispatcher.py tests/test_product_work_worker.py -q
```
Expected: PASS.

**Step 4 — Commit**
```bash
git add src/stech_mcp/services/product_work_dispatcher.py src/stech_mcp/worker.py tests/test_product_work_dispatcher.py tests/test_product_work_worker.py
git commit -m "feat: add persistent product work worker"
```

---

## Task 7: Configuración y ejecución en Windows/PC020

**Files:**
- Modify: `.env.example`
- Modify: `pyproject.toml`
- Create: `deploy/windows/INSTALL_ENRICHMENT_WORKER.ps1`
- Create: `deploy/windows/UNINSTALL_ENRICHMENT_WORKER.ps1`
- Create: `deploy/windows/RUN_ENRICHMENT_WORKER.ps1`
- Create: `tests/test_worker_deployment_contract.py`

**Step 1 — Prueba fallando**

Exigir variables documentadas:
- `STECH_WORKER_ENABLED`
- `STECH_WORKER_POLL_SECONDS`
- `STECH_WORKER_LEASE_SECONDS`
- `STECH_WORKER_MAX_ATTEMPTS`
- `STECH_WORKER_CONCURRENCY` (V2 inicial = 1 por defecto)

El script de instalación debe usar una estrategia Windows explícita y reversible. Preferencia: wrapper de servicio documentado; si se usa `pywin32`, dejar dependencia Windows condicional y servicio con auto-start.

**Step 2 — Implementar**

Agregar entry point de consola, por ejemplo:
```toml
[project.scripts]
stech-enrichment-worker = "stech_mcp.worker:main"
```

Instalación debe ser idempotente y no instalar el MCP server como worker.

**Step 3 — Verificar**
```bash
pytest tests/test_worker_deployment_contract.py -q
```
Expected: PASS.

**Step 4 — Commit**
```bash
git add .env.example pyproject.toml deploy/windows tests/test_worker_deployment_contract.py
git commit -m "feat: add Windows enrichment worker deployment"
```

---

## Task 8: Prueba de recuperación extremo a extremo de la cola

**Files:**
- Create: `tests/test_product_work_recovery_integration.py`
- Modify only if needed: queue/worker files from prior tasks.

**Step 1 — Crear escenario**

1. job con 3 PNs;
2. worker reclama item 1;
3. simular proceso muerto dejando lease expirar;
4. worker nuevo recupera item 1;
5. item 1 termina;
6. item 2 falla retryable y luego pasa;
7. item 3 falla permanente;
8. job termina `PARTIAL`;
9. eventos/intentos conservan historia.

**Step 2 — Run**
```bash
pytest tests/test_product_work_recovery_integration.py -q
```
Expected: PASS.

**Step 3 — Regresión completa**
```bash
pytest -q
```
Expected: PASS sin alterar el flujo existente de `product_loader_job`/VTEX.

**Step 4 — Commit**
```bash
git add tests/test_product_work_recovery_integration.py
git commit -m "test: verify product work crash recovery"
```

## Definition of Done

- La cola es genérica y persistente.
- No depende de threads daemon del MCP.
- Reiniciar MCP no pierde trabajos.
- Reiniciar worker permite recuperar leases vencidos.
- No se duplican trabajos activos equivalentes.
- Retry/backoff/prioridad funcionan.
- Herramientas MCP crean/consultan/controlan, pero no bloquean esperando el trabajo.
- `product_loader_job` VTEX existente permanece funcional.
- Suite completa verde.