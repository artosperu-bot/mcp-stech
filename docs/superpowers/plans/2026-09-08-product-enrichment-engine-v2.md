# Product Enrichment Engine V2 — Plan maestro de implementación

> **Para Steve:** implementar este plan usando `superpowers:subagent-driven-development` o `superpowers:executing-plans`, tarea por tarea, con verificación antes de declarar cada fase completa.

**Objetivo:** convertir Product Workbench + STECH MCP + Product Workspace en un flujo masivo, persistente y multicanal donde el usuario selecciona Part Numbers o importa un Excel, envía los productos a enriquecimiento y un worker independiente completa progresivamente la ficha maestra sin tocar precio ni stock.

**Arquitectura:** V8 actúa como interfaz y cliente; STECH MCP mantiene reglas, contratos, schemas, evidencias y herramientas; SQL Server mantiene la cola persistente; un worker separado ejecuta `ENRICH_TECHNICAL`; Product Workspace conserva la ficha maestra; Falabella, Coolbox, VTEX y futuros canales consumen esa ficha mediante mappings propios.

**Stack:** Python 3.12, FastMCP, SQL Server/pyodbc, pytest, openpyxl, HTTP/PDF ingestion en MCP, frontend web actual de SCR/V8.

## Orden de ejecución

### Plan A — Cola persistente y worker

Archivo: `docs/superpowers/plans/2026-09-08-product-work-queue-worker-v2.md`

Entrega una cola genérica independiente de VTEX, leases de trabajo, retries, prioridad, eventos, recuperación tras reinicio, herramientas MCP de control y un worker ejecutable por separado.

**Criterio de salida:** se pueden enviar 1, 100 o 1000 PN a `ENRICH_TECHNICAL`; cerrar/reiniciar el MCP no pierde la cola; el worker retoma trabajos vencidos y procesa cada item aisladamente.

### Plan B — Motor técnico de enriquecimiento

Archivo: `docs/superpowers/plans/2026-09-08-product-enrichment-core-v2.md`

Entrega category schemas canónicos, detección de campos faltantes, adaptación de Deltron, documentos/PDF reutilizables, candidatos, validación, conflictos, promoción a `product_enrichment` y reconstrucción/readiness de Product Workspace.

**Criterio de salida:** para un PN, el motor sabe qué campos ya existen, qué falta, investiga únicamente faltantes, conserva evidencia y nunca sobrescribe una evidencia más fuerte con una más débil.

### Plan C — Excel Template Engine

Archivo: `docs/superpowers/plans/2026-09-08-excel-template-engine-v2.md`

Entrega reconocimiento de Excel por estructura, aliases y scoring; mapping de columnas a campos STECH; validación por canal/categoría; importación masiva a la misma cola; y base para exportar Falabella/Coolbox/otros sin convertir el Excel en fuente maestra.

**Criterio de salida:** un workbook conocido puede reconocerse sin depender del nombre de archivo, detecta canal/categoría/hoja/fila de encabezados/PN y calcula campos faltantes contra Product Workspace.

### Plan D — Vista V8 y conexión Product Workbench

Repositorio: `artosperu-bot/scr`

Rama: `feat/product-enrichment-workbench-v2`

Archivo: `docs/superpowers/plans/2026-09-08-v8-product-enrichment-workbench-v2.md`

Entrega la nueva vista de enriquecimiento, selección masiva, importación Excel, creación de trabajos MCP, progreso, prioridad, retry, faltantes y enlace a Product Workspace.

**Criterio de salida:** el usuario puede buscar/filtrar productos, seleccionar varios, pulsar `Enriquecer seleccionados`, cerrar la vista y posteriormente ver el avance y los resultados en Product Workspace.

## Dependencias entre planes

```text
A. Cola + Worker
      |
      v
B. Enrichment Core
      |
      +------------------+
      |                  |
      v                  v
C. Excel Engine      D. V8 UI/API
      |                  |
      +--------+---------+
               v
       Flujo extremo a extremo
```

C y D pueden avanzar en paralelo cuando los contratos MCP del Plan A estén estabilizados; la validación final de ambos depende del Plan B.

## Reglas que aplican a todos los planes

1. `ENRICH_TECHNICAL` no modifica precio ni stock.
2. Product Workspace es la ficha maestra; ningún marketplace es la fuente maestra.
3. Falabella, Coolbox y VTEX son consumidores pares de la ficha maestra.
4. No duplicar una segunda cola en V8: V8 presenta y controla; STECH MCP/SQL mantiene el trabajo largo.
5. No reutilizar `product_loader_job` como cola técnica general; se conserva para su flujo VTEX actual.
6. Investigación dirigida a `pending_fields`, no a toda la ficha si no es necesario.
7. Campos sensibles a variante requieren Part Number exacto y política de fuente fuerte.
8. Toda promoción conserva evidencia y trazabilidad.
9. Los trabajos deben ser idempotentes y recuperables tras reinicios.
10. Toda funcionalidad nueva se implementa con prueba fallando primero, cambio mínimo, prueba pasando y commit pequeño.

## Validación extrema a extremo

Cuando A+B+C+D estén completos, ejecutar una prueba controlada con tres productos de categorías distintas, por ejemplo LAPTOP, PORTABLE_SPEAKER y HEADPHONES:

1. Crear/importar una selección desde V8.
2. Confirmar que el trabajo se crea en la cola genérica.
3. Detener y reiniciar el worker durante un item para validar recuperación.
4. Confirmar que solo se investigan campos faltantes.
5. Confirmar que fuentes, documentos y candidatos quedan auditables.
6. Confirmar que Product Workspace se actualiza progresivamente.
7. Confirmar readiness independiente para Falabella, Coolbox y VTEX.
8. Confirmar mediante auditoría/DB que precio y stock permanecieron sin cambios.

Comando final MCP esperado:

```bash
pytest -q
```

Comando final V8 esperado:

```bash
pytest -q
```

Ambos deben terminar sin regresiones antes de integrar las ramas.