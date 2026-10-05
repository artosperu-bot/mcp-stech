# Product Enrichment Engine V2 — Diseño

**Fecha:** 2026-09-08  
**Repositorio:** `artosperu-bot/mcp-stech`  
**Rama:** `feat/product-enrichment-engine-v2`  
**Estado:** Diseño propuesto para revisión  

## 1. Objetivo

Construir una arquitectura multicanal para enriquecer productos de forma masiva e incremental desde Product Workbench, sin depender de VTEX, Coolbox o Falabella como fuente maestra.

La experiencia objetivo para el usuario es simple:

1. Abrir Product Workbench.
2. Buscar o filtrar productos.
3. Seleccionar uno o muchos Part Numbers.
4. Enviarlos a enriquecimiento.
5. Seguir trabajando mientras STECH procesa la cola.
6. Revisar el resultado progresivamente en Product Workspace.
7. Reutilizar la ficha maestra para Falabella, Coolbox, VTEX, Mercado Libre y futuros canales.

Este flujo de enriquecimiento técnico no modifica precio ni stock.

## 2. Principios de diseño

### 2.1 Product Workspace es la verdad maestra

Los marketplaces no definen lo que STECH sabe de un producto. STECH mantiene una ficha técnica canónica por Part Number y después mapea esos datos a cada canal.

Ejemplo:

- Campo canónico STECH: `battery_runtime_hours`.
- Falabella: “Duración de batería”.
- Coolbox: “Autonomía”.
- VTEX: “Duración batería”.
- Mercado Libre: atributo equivalente.

El dato se investiga y valida una sola vez.

### 2.2 Investigación solo de lo faltante

Para cada producto el motor primero lee:

- `DB_DISTRIBUIDORES` / V8.
- datos Deltron ya capturados.
- Product Workspace.
- `product_enrichment` aprobado.
- identidad ya conocida.

Después compara contra el esquema técnico de la categoría y genera `pending_fields` únicamente para los datos faltantes o en conflicto.

### 2.3 Evidencia por campo

Cada valor promovido debe conservar:

- Part Number objetivo.
- código de campo canónico.
- valor normalizado.
- fuente.
- URL o documento.
- Part Number encontrado en la fuente.
- fragmento de evidencia.
- tipo de fuente.
- confianza.
- fecha de verificación.

### 2.4 No sobrescribir evidencia fuerte con evidencia débil

Jerarquía base:

- A1: fabricante oficial con Part Number exacto.
- A2: documento oficial, soporte, PSREF, datasheet o manual con Part Number exacto.
- B: distribuidor autorizado con Part Number exacto.
- C: retailer confiable con SKU o Part Number exacto.
- D: mismo modelo o chasis, solo para atributos explícitamente reutilizables.
- E: regla determinística o estimación aprobada.

Los campos sensibles a variante no pueden heredarse de otro Part Number.

## 3. Arquitectura objetivo

```text
PRODUCT WORKBENCH / V8
        |
        | selección manual, filtro, lista o Excel
        v
PRODUCT WORK QUEUE (SQL SERVER)
        |
        v
STECH ENRICHMENT WORKER
        |
        +--> datos V8 / Deltron / enrichment existente
        +--> category schema
        +--> detección de faltantes
        +--> investigación y documentos
        +--> candidatos
        +--> validación y conflictos
        +--> promoción de hechos aprobados
        |
        v
PRODUCT WORKSPACE
        |
        +--> FALABELLA
        +--> COOLBOX
        +--> VTEX
        +--> MERCADO LIBRE
        +--> futuros canales
```

## 4. Responsabilidades por componente

### 4.1 V8 / Product Workbench

V8 no investiga Internet ni interpreta PDFs. Sus responsabilidades son:

- buscar y filtrar productos;
- permitir selección múltiple;
- importar Excel;
- mostrar qué plantilla fue reconocida;
- enviar productos a la cola;
- mostrar progreso, errores y estados;
- permitir reintentar;
- permitir prioridad alta;
- abrir el producto resultante en Product Workspace.

Nueva vista propuesta: **Enriquecimiento de productos**.

Columnas mínimas:

- selección;
- Part Number;
- marca;
- categoría;
- completitud de ficha maestra;
- estado de enriquecimiento;
- progreso;
- paso actual;
- prioridad;
- último error;
- última actualización.

Acciones mínimas:

- Enriquecer seleccionados.
- Importar Excel.
- Seleccionar todos los resultados filtrados.
- Prioridad alta.
- Reintentar.
- Ver faltantes.
- Abrir en Product Workspace.

### 4.2 STECH MCP

STECH MCP actúa como API y capa de reglas. No debe mantener una llamada abierta durante horas.

Responsabilidades:

- crear trabajos;
- consultar trabajos;
- validar entradas;
- exponer estados;
- leer ficha maestra;
- resolver esquema de categoría;
- validar candidatos;
- promover hechos aprobados;
- exponer fuentes y conflictos;
- generar readiness por canal.

### 4.3 STECH Enrichment Worker

Proceso persistente independiente del MCP, pensado para ejecutarse como servicio en PC020.

Responsabilidades:

- reclamar trabajos pendientes;
- procesar cada producto aisladamente;
- guardar cada transición;
- reintentar errores temporales;
- liberar trabajos abandonados;
- continuar después de reinicios;
- limitar concurrencia;
- respetar prioridades;
- nunca tocar precio ni stock en `ENRICH_TECHNICAL`.

El worker debe ser reiniciable e idempotente: ejecutar nuevamente un paso no debe duplicar hechos aprobados ni documentos.

## 5. Cola general de Product Work

No se reutilizará directamente `product_loader_job` como cola general porque su modelo actual está orientado al flujo de publicación VTEX.

Se propone una cola superior y genérica:

### 5.1 `product_work_job`

Campos mínimos:

- `product_work_job_id`.
- `work_type`.
- `source_name`.
- `actor_source`.
- `status`.
- `priority`.
- `total_items`.
- `completed_items`.
- `review_items`.
- `failed_items`.
- `created_at`.
- `started_at`.
- `finished_at`.
- `updated_at`.

### 5.2 `product_work_item`

Campos mínimos:

- `product_work_item_id`.
- `product_work_job_id`.
- `partnumber`.
- `category_code`.
- `channel_code` opcional.
- `input_json`.
- `status`.
- `current_step`.
- `progress_pct`.
- `priority`.
- `attempt_count`.
- `max_attempts`.
- `next_attempt_at`.
- `claimed_by`.
- `claimed_at`.
- `claim_expires_at`.
- `last_error_code`.
- `last_error_detail`.
- `created_at`.
- `updated_at`.
- `completed_at`.

Debe impedir duplicar el mismo trabajo activo para el mismo Part Number, tipo de trabajo y contexto.

### 5.3 `product_work_event`

Auditoría de todas las transiciones importantes.

### 5.4 `product_work_attempt`

Historial de cada intento de un item, útil para diagnósticos, reintentos y métricas.

## 6. Tipos de trabajo

La cola debe soportar al menos:

- `ENRICH_TECHNICAL`.
- `RESEARCH_IDENTITY`.
- `RESEARCH_IMAGES`.
- `PREPARE_CHANNEL`.
- `PUBLISH_CHANNEL`.

La primera implementación de V2 se concentra en `ENRICH_TECHNICAL`.

## 7. Estados de enriquecimiento técnico

Estados propuestos del item:

- `QUEUED`.
- `LOADING_SOURCE_DATA`.
- `ANALYZING_MISSING_FIELDS`.
- `RESEARCHING`.
- `READING_DOCUMENTS`.
- `VALIDATING`.
- `PROMOTING_FACTS`.
- `REBUILDING_PRODUCT_MASTER`.
- `COMPLETED`.
- `PARTIAL`.
- `REVIEW_REQUIRED`.
- `NO_DATA_FOUND`.
- `FAILED_RETRYABLE`.
- `FAILED`.
- `CANCELLED`.

`progress_pct` es informativo; la verdad del proceso siempre es el estado y los eventos persistidos.

## 8. Category Schema Registry

La lógica técnica no se programará con grandes bloques `if category == ...` dentro de Coolbox o Falabella.

Se creará un registro de atributos canónicos.

### 8.1 `product_attribute_definition`

Define cada campo:

- `field_code`.
- nombre.
- tipo: texto, entero, decimal, booleano, enum, dimensión, capacidad, etc.
- unidad canónica.
- normalizador.
- validador.
- sensibilidad a variante.
- política de reutilización.

### 8.2 `category_attribute`

Relaciona cada categoría con sus atributos:

- categoría.
- `field_code`.
- requerido o recomendado.
- orden.
- reglas específicas.

Ejemplos iniciales:

#### LAPTOP

- CPU.
- RAM.
- SSD / almacenamiento.
- pantalla.
- resolución.
- Wi-Fi.
- Bluetooth.
- batería.
- puertos.
- sistema operativo.
- peso.
- dimensiones.

#### PORTABLE_SPEAKER

- potencia.
- versión Bluetooth.
- autonomía.
- batería.
- IP rating.
- respuesta de frecuencia.
- conexiones.
- peso.
- dimensiones.
- contenido de caja.

#### HEADPHONES

- driver.
- ANC.
- transparencia.
- Bluetooth.
- codecs.
- micrófono.
- autonomía.
- tiempo de carga.
- impedancia.
- sensibilidad.
- respuesta de frecuencia.
- peso.

## 9. Investigación y fuentes

Orden operativo recomendado por campo faltante:

1. Deltron / datos ya almacenados.
2. página oficial del fabricante.
3. ficha técnica oficial.
4. PDF / datasheet oficial.
5. manual o página de soporte oficial.
6. distribuidor autorizado.
7. retailer confiable.

El motor debe detener la búsqueda de un campo cuando ya exista evidencia suficiente de mayor calidad y no haya conflicto.

La investigación debe ser dirigida a campos concretos. No debe volver a investigar toda la ficha cuando solo faltan tres atributos.

## 10. Documentos y PDFs

Se propone almacenar documentos reutilizables.

### 10.1 `source_document`

Campos mínimos:

- `source_document_id`.
- fabricante.
- tipo de documento.
- URL.
- título.
- hash SHA-256.
- fecha de descarga.
- estado de extracción.
- texto extraído o referencia al texto procesado.

### 10.2 `source_document_match`

Relaciona documentos con productos:

- documento.
- Part Number.
- tipo de coincidencia.
- páginas relevantes.
- nivel de confianza.

Un documento idéntico no debe descargarse y procesarse repetidamente si su hash ya existe.

## 11. Candidatos antes de promover

Los extractores HTML/PDF/web no escribirán directamente en `product_enrichment`.

Se propone `product_fact_candidate` con:

- Part Number.
- `field_code`.
- valor original.
- valor normalizado.
- unidad.
- fuente.
- source Part Number.
- evidencia.
- confidence rank.
- estado de validación.
- razón de rechazo o conflicto.

Después un `FactPromotionService` aplica las reglas de fuente, variante, consistencia y conflicto y solo entonces promueve a `product_enrichment`.

## 12. Conflictos

Ejemplo:

- fabricante exacto: Bluetooth 5.4, A1;
- distribuidor autorizado exacto: Bluetooth 5.3, B;
- retailer exacto: Bluetooth 5.3, C.

El sistema conserva todas las evidencias, marca el conflicto y aplica la política de resolución. Si la regla permite resolución automática, A1 gana. Si el campo o combinación es ambigua, pasa a `REVIEW_REQUIRED`.

Nunca se elimina silenciosamente la evidencia perdedora.

## 13. Excel Template Engine

El Excel se considera una entrada y una salida de canal, no la base maestra.

Se crea un motor con tres responsabilidades:

1. **Recognizer:** identificar el tipo de Excel.
2. **Mapper:** relacionar columnas Excel con campos canónicos STECH.
3. **Validator:** calcular qué requiere esa plantilla para estar completa.

### 13.1 Reconocimiento

No se reconoce únicamente por nombre de archivo. Se analiza:

- nombres de hojas;
- posición y contenido de encabezados;
- campos distintivos;
- orden aproximado de columnas;
- aliases de encabezados;
- cantidad de coincidencias con esquemas conocidos.

Resultado:

- canal.
- template code.
- categoría.
- versión probable.
- confianza.
- hoja y fila de encabezados.
- columna Part Number / SKU detectada.

Umbrales propuestos:

- alta confianza: continuar automáticamente.
- confianza media: pedir confirmación en V8.
- baja confianza: plantilla desconocida y requerir mapeo asistido.

### 13.2 Registro de plantillas

Tablas conceptuales:

- `marketplace_template`.
- `marketplace_template_field`.
- `marketplace_field_alias`.

Debe permitir múltiples versiones de Falabella y Coolbox sin modificar el motor central.

### 13.3 Entrada masiva

Una carga puede venir de:

- selección directa en Product Workbench;
- filtro de resultados;
- lista de Part Numbers;
- Excel reconocido.

Todas terminan creando items en la misma `product_work_job`.

## 14. Multicanal y readiness

Product Workspace debe calcular readiness por combinación de canal + categoría.

Ejemplo:

```text
Ficha maestra STECH       96%
Falabella LAPTOP         100% READY
Coolbox LAPTOP            94% MISSING_FIELDS
VTEX LAPTOP              100% READY
Mercado Libre LAPTOP      82% MISSING_FIELDS
```

Ningún canal tiene prioridad arquitectónica sobre otro.

Falabella debe estar incluido desde V2 como consumidor de la ficha maestra, junto con Coolbox y VTEX.

## 15. MCP Tool Surface propuesta

Herramientas nuevas o generalizadas:

- `product_schema_get(category)`.
- `product_technical_status(partnumber)`.
- `product_technical_missing_list(...)`.
- `product_work_job_create(...)`.
- `product_work_job_get(job_id)`.
- `product_work_job_list(...)`.
- `product_work_item_retry(job_id, item_id)`.
- `product_work_item_cancel(job_id, item_id)`.
- `product_research_plan(partnumber)`.
- `product_source_ingest(partnumber, url, source_type)`.
- `product_fact_candidates(partnumber)`.
- `product_fact_promote(...)`.
- `product_fact_promote_batch(...)`.
- `product_enrich(partnumber, category=None)` como orquestación de un solo producto cuando se requiera ejecución síncrona.
- `marketplace_template_detect(...)`.
- `marketplace_readiness_get(partnumber, marketplace, category=None)`.

Las herramientas actuales de imágenes y publicación VTEX permanecen separadas.

## 16. Worker y concurrencia

Primera versión:

- un servicio de Windows en PC020;
- concurrencia configurable baja;
- `claim` transaccional en SQL Server;
- lease temporal mediante `claim_expires_at`;
- heartbeat del worker;
- reintentos con `next_attempt_at`;
- backoff para errores temporales;
- recuperación de leases vencidos al reiniciar.

Más adelante puede haber workers especializados, pero V2 no requiere una plataforma distribuida compleja.

## 17. Dedupe e idempotencia

El sistema debe evitar:

- dos `ENRICH_TECHNICAL` activos para el mismo PN y contexto;
- descargar dos veces el mismo documento;
- crear dos candidatos equivalentes de la misma evidencia;
- sobrescribir una aprobación manual con una automática;
- volver a investigar campos ya aprobados sin motivo.

Estados esperados al insertar un producto ya conocido:

- `QUEUED` si necesita trabajo.
- `ALREADY_RUNNING` si ya existe un trabajo activo equivalente.
- `UP_TO_DATE` si no hay campos relevantes pendientes.

## 18. Límites de V2

Incluido en V2 inicial:

- cola general persistente;
- worker permanente;
- integración con Product Workbench;
- enrichment técnico sin precio/stock;
- category registry;
- Deltron como fuente inicial;
- ingestión HTML oficial;
- ingestión de PDF / manual oficial;
- evidencia y candidatos;
- resolución básica de conflictos;
- Product Workspace actualizado;
- readiness para Falabella, Coolbox y VTEX;
- reconocimiento de plantillas Excel conocidas;
- importación masiva por Excel y selección.

No incluido en la primera entrega:

- publicación automática completa a todos los marketplaces;
- navegador general autónomo contra cualquier sitio sin adaptador o proveedor de búsqueda;
- cambios de precio;
- cambios de stock;
- generación de promociones;
- modificación automática de datos manuales aprobados.

## 19. Categorías iniciales

Primera cobertura recomendada:

- `LAPTOP`.
- `PORTABLE_SPEAKER`.
- `HEADPHONES`.

Después se agregan por esquema y mapeo, sin cambiar el núcleo:

- MONITOR.
- MOUSE.
- KEYBOARD.
- PRINTER.
- PROJECTOR.
- SMARTPHONE.
- TABLET.
- otros.

## 20. Criterios de éxito

La V2 se considera correcta cuando:

1. Se pueden seleccionar 1 o muchos Part Numbers desde Product Workbench.
2. Se puede importar un Excel conocido y detectar canal, plantilla, categoría y PN.
3. El trabajo queda persistido aunque V8 se cierre.
4. El worker continúa aunque la llamada MCP ya terminó.
5. Reiniciar el worker no pierde el avance confirmado.
6. Un error en un producto no detiene el lote.
7. Solo se investigan campos faltantes o en conflicto.
8. Cada valor promovido conserva evidencia y fuente.
9. Product Workspace se actualiza progresivamente por producto.
10. Falabella, Coolbox y VTEX consumen la misma ficha maestra.
11. El flujo `ENRICH_TECHNICAL` no modifica precio ni stock.
12. No se duplican trabajos, documentos ni hechos aprobados.

## 21. Orden de implementación recomendado

Fase A — infraestructura:

- tablas de cola general;
- repository de jobs/items/events/attempts;
- worker persistente;
- recuperación, leases y reintentos;
- herramientas MCP de creación/consulta de jobs.

Fase B — enriquecimiento técnico:

- category registry;
- missing-fields engine;
- Deltron canonical mapper;
- candidatos;
- promoción y conflictos;
- actualización de Product Workspace.

Fase C — fuentes externas:

- source documents;
- HTML oficial;
- PDF/manual;
- caché y hash;
- adapters de fabricante/distribuidor.

Fase D — Excel y multicanal:

- Excel Template Engine;
- Falabella template mappings;
- Coolbox template mappings;
- readiness por canal;
- integración de carga masiva desde V8.

Fase E — interfaz:

- vista Enriquecimiento de productos;
- selección masiva;
- progreso;
- filtros;
- reintentos;
- detalle de evidencias y conflictos;
- acceso a Product Workspace.

## 22. Decisión arquitectónica final

La solución aprobada conceptualmente es:

**Product Workbench selecciona y controla; STECH MCP expone reglas y operaciones; SQL Server persiste la cola; STECH Enrichment Worker realiza el trabajo largo; Product Workspace guarda la ficha maestra; los marketplaces solamente consumen y transforman esa ficha.**

Esto permite que el flujo visible para el usuario sea simple —seleccionar Part Numbers y presionar Enriquecer— sin acoplar el conocimiento de producto a un marketplace particular.