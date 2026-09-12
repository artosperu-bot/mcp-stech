# STECH ChatGPT Research Bridge V1 — Diseño

## Objetivo

Permitir que STECH-MCP use investigación web realizada por una tarea programada de ChatGPT sin depender de Brave Search ni de una API key de OpenAI. El sistema debe mantener Product Work como fuente de verdad, ser recuperable, auditable e idempotente, y no debe permitir que la investigación modifique precio, stock, costo, promociones, publicación, categoría ni estado de VTEX.

## Alcance V1

V1 implementa un puente de investigación entre PC020 y ChatGPT usando GitHub como buzón durable. El contrato será genérico para tres tipos de trabajo existentes:

- `RESEARCH_IMAGES`
- `RESEARCH_IDENTITY`
- `ENRICH_TECHNICAL`

El primer caso de prueba end-to-end será `RESEARCH_IMAGES`, porque es el flujo que actualmente termina en `NO_DATA_FOUND` cuando no existe un proveedor web configurado.

V1 no elimina Brave del código existente. Brave queda opcional y desactivado cuando no hay clave. El puente ChatGPT es una vía adicional y no un reemplazo destructivo del worker actual.

## Arquitectura

```text
Product Work / Scanner / Worker en PC020
                |
                v
      stech-chatgpt-bridge.exe
                |
                | exporta solicitudes pendientes
                v
GitHub: research_bridge/requests/<request_id>.json
                |
                v
      Tarea programada de ChatGPT
                |
                | investiga con web disponible en ChatGPT
                v
GitHub: research_bridge/results/<request_id>.json
                |
                v
      stech-chatgpt-bridge.exe
                |
                | valida e importa evidencia
                v
STECH-MCP / candidatos / auditoría / Product Workspace
```

GitHub se usa solo como transporte durable de mensajes. No contiene secretos de SQL, credenciales VTEX, cookies, API keys ni contraseñas.

## Principios de seguridad

1. ChatGPT nunca escribe directamente en tablas comerciales ni en VTEX.
2. ChatGPT solo devuelve evidencia de investigación.
3. El bridge valida el esquema completo antes de aceptar un resultado.
4. El resultado debe corresponder al `request_id`, `partnumber` y `work_type` originales.
5. Cada resultado importado se marca con una recepción idempotente; importar el mismo resultado dos veces no duplica candidatos ni eventos.
6. Las URLs y valores devueltos se tratan como evidencia no confiable hasta que pasen las reglas específicas del tipo de investigación.
7. Los campos comerciales quedan explícitamente fuera del contrato: `price`, `stock`, `cost`, `promotion`, `publication`, `category`, `vtex_state` y equivalentes.
8. Ninguna imagen web se publica automáticamente. Se crea candidato y queda en `REVIEW_REQUIRED` salvo que una política existente más estricta permita otra cosa.
9. Identidad mantiene las reglas ya aprobadas: GTIN-8/12/13/14, checksum válido, PN exacto, etiqueta explícita EAN/UPC/GTIN y fuente fuerte para promoción automática.
10. Especificaciones técnicas se guardan como evidencia/candidatos y pasan por las reglas existentes de promoción y revisión.

## Contrato de solicitud

Cada solicitud es un archivo JSON append-only con nombre único:

`research_bridge/requests/<request_id>.json`

Ejemplo:

```json
{
  "schema_version": 1,
  "request_id": "rw_20260911_000001",
  "created_at": "2026-09-11T22:30:00-05:00",
  "product_work_item_id": 1234,
  "product_work_job_id": 140,
  "work_type": "RESEARCH_IMAGES",
  "partnumber": "910-006862",
  "brand": "LOGITECH",
  "model": null,
  "category_code": null,
  "requested_fields": ["images"],
  "research_policy": {
    "exact_partnumber_required": true,
    "prefer_official_sources": true,
    "max_sources": 5,
    "max_candidates": 10
  }
}
```

El bridge no exporta secretos ni datos innecesarios.

## Contrato de resultado

ChatGPT crea un archivo nuevo:

`research_bridge/results/<request_id>.json`

Ejemplo para imágenes:

```json
{
  "schema_version": 1,
  "request_id": "rw_20260911_000001",
  "partnumber": "910-006862",
  "work_type": "RESEARCH_IMAGES",
  "researched_at": "2026-09-11T22:40:00-05:00",
  "status": "EVIDENCE_FOUND",
  "sources": [
    {
      "page_url": "https://example.com/product",
      "source_domain": "example.com",
      "source_type": "WEB",
      "title": "Product page",
      "exact_partnumber_match": true
    }
  ],
  "image_candidates": [
    {
      "image_url": "https://example.com/image.jpg",
      "page_url": "https://example.com/product",
      "title": "Product image",
      "width": 1200,
      "height": 1200,
      "exact_partnumber_match": true
    }
  ],
  "identity_candidates": [],
  "technical_candidates": [],
  "notes": ""
}
```

Estados válidos de resultado:

- `EVIDENCE_FOUND`
- `NO_VERIFIED_EVIDENCE`
- `CONFLICT`
- `TEMPORARY_RESEARCH_ERROR`

`NO_VERIFIED_EVIDENCE` significa que ChatGPT sí investigó y no pudo verificar evidencia suficiente. No se usará para representar que el bridge estaba desconectado o que la tarea no corrió.

## Flujo local del bridge

El ejecutable `stech-chatgpt-bridge` tendrá un ciclo simple:

1. Leer Product Work y detectar items elegibles para investigación externa.
2. No exportar un item si ya existe un request activo para ese `product_work_item_id`.
3. Crear el JSON de solicitud en el checkout local del buzón.
4. Sincronizar el buzón con GitHub usando Git instalado y credenciales ya configuradas en Windows; no se introduce una nueva API key.
5. Traer resultados nuevos desde GitHub.
6. Validar esquema, correspondencia e invariantes de seguridad.
7. Importar evidencia a los repositorios existentes.
8. Registrar una recepción durable/idempotente.
9. Dejar el Product Work en el estado correspondiente: `REVIEW_REQUIRED`, `PARTIAL`, `COMPLETED`, `NO_DATA_FOUND` o retry según las reglas existentes.

## GitHub como buzón

El buzón usa archivos append-only para minimizar conflictos:

```text
research_bridge/
  requests/
    <request_id>.json
  results/
    <request_id>.json
  receipts/
    <request_id>.json
```

No se reescribe un archivo de solicitud o resultado una vez publicado. Un receipt se crea solo después de que PC020 importe y confirme el resultado.

El branch del buzón será configurable con `STECH_RESEARCH_GIT_BRANCH`. V1 usará por defecto el mismo branch de prueba hasta validar el flujo local; antes de producción se moverá a un branch dedicado para separar mensajes de código.

## Tarea programada de ChatGPT

La tarea programada procesa un número pequeño de solicitudes por ejecución para evitar ráfagas y mantener trazabilidad. El prompt debe:

1. Revisar `research_bridge/requests/`.
2. Ignorar solicitudes que ya tengan archivo en `research_bridge/results/` o receipt.
3. Procesar como máximo 10 solicitudes por ejecución.
4. Investigar primero fuentes oficiales y luego fuentes públicas fuertes.
5. Verificar PN exacto siempre que el tipo lo requiera.
6. No inventar datos ni completar por similitud visual.
7. Crear exactamente un resultado por request.
8. No modificar código del repositorio.
9. No tocar archivos fuera de `research_bridge/results/`.

## Comportamiento por tipo de trabajo

### RESEARCH_IMAGES

Prioridad de evidencia:

1. fabricante oficial;
2. soporte oficial / ficha oficial;
3. distribuidor confiable;
4. otras páginas públicas solo como candidato manual.

Una imagen web nunca se publica directamente. El bridge la importa a `ProductImageCandidateRepository` con su página origen, dominio, dimensiones, coincidencia PN y evidencia.

### RESEARCH_IDENTITY

ChatGPT devuelve candidatos EAN/UPC/GTIN con etiqueta encontrada, URL de origen y evidencia. STECH-MCP vuelve a ejecutar checksum y las reglas de promoción existentes. Un resultado de ChatGPT no puede saltarse esas validaciones.

### ENRICH_TECHNICAL

ChatGPT devuelve pares `field_name` / `value` con fuente y evidencia. Solo se aceptan campos permitidos por el esquema técnico resuelto para el producto. Si no existe esquema soportado, el resultado queda para revisión y no se promociona automáticamente.

## Configuración

No se agrega ninguna API key obligatoria.

Variables previstas:

```env
STECH_CHATGPT_BRIDGE_ENABLED=false
STECH_RESEARCH_GIT_REPO=C:\DESAROLLO\mcp-stech
STECH_RESEARCH_GIT_BRANCH=feat/chatgpt-research-bridge-v1
STECH_RESEARCH_MAX_EXPORT_PER_CYCLE=10
STECH_RESEARCH_MAX_IMPORT_PER_CYCLE=20
STECH_RESEARCH_POLL_SECONDS=60
```

`STECH_BRAVE_SEARCH_API_KEY` puede permanecer vacío.

## Observabilidad

El bridge debe registrar sin secretos:

- request exportado;
- request omitido por deduplicación;
- resultado detectado;
- resultado rechazado y motivo;
- resultado importado;
- receipt creado;
- error Git temporal;
- error de esquema;
- error de correspondencia PN/work type.

Cada importación debe conservar `request_id`, `product_work_item_id`, fuente y timestamp para auditoría.

## Recuperación

- Si PC020 se apaga después de exportar un request, el archivo sigue en GitHub.
- Si ChatGPT genera resultado mientras PC020 está apagado, se importa al reiniciar.
- Si el bridge cae después de importar pero antes de crear receipt, la importación repetida debe ser idempotente.
- Si GitHub no está disponible, no se convierte en `NO_DATA_FOUND`; se reintenta después.
- Si la tarea programada no corre, el Product Work queda pendiente de investigación externa y no se falsifica un resultado terminal.

## Pruebas obligatorias antes de merge

1. Unit test del contrato request/result.
2. Unit test que rechace campos comerciales prohibidos.
3. Unit test de deduplicación por `product_work_item_id`.
4. Unit test de importación idempotente.
5. Unit test de mismatch de `request_id`, PN y `work_type`.
6. Unit test de mapeo `RESEARCH_IMAGES` a candidatos.
7. Unit test de identidad reutilizando las validaciones actuales.
8. Unit test técnico respetando esquema permitido.
9. Test de fallo Git temporal sin convertir a `NO_DATA_FOUND`.
10. Test end-to-end local con un PN real que antes terminaba `NO_DATA_FOUND`.
11. CI completo verde.
12. Prueba manual en PC020 antes de cualquier merge.

## Criterio de éxito V1

Para un PN real sin imágenes locales ni Deltron, el sistema debe:

1. crear una solicitud durable;
2. permitir que la tarea programada de ChatGPT investigue la web;
3. recibir al menos un resultado verificable o un `NO_VERIFIED_EVIDENCE` real;
4. importar candidatos sin tocar datos comerciales;
5. mostrar el resultado en Product Workspace;
6. sobrevivir a reinicios sin duplicar trabajo.

No se considera éxito que un item termine rápido en `NO_DATA_FOUND` únicamente porque Brave no está configurado.

## Aceptación local en PC020

No mergear antes de completar esta prueba.

```powershell
Set-Location "C:\DESAROLLO\mcp-stech"

git fetch origin
git switch feat/chatgpt-research-bridge-v1
git pull --ff-only origin feat/chatgpt-research-bridge-v1

.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Aplicar una sola vez la migración nueva en `STECH_MCP`:

```powershell
sqlcmd -S PC020 -d STECH_MCP -E -C -b -i ".\sql\013_chatgpt_research_bridge_v1.sql"
```

En `.env`, mantener Brave vacío si no se desea usarlo y activar el bridge:

```env
STECH_BRAVE_SEARCH_API_KEY=
STECH_CHATGPT_BRIDGE_ENABLED=true
STECH_RESEARCH_GIT_REPO=C:\DESAROLLO\mcp-stech
STECH_RESEARCH_GIT_BRANCH=feat/chatgpt-research-bridge-v1
STECH_RESEARCH_MAX_EXPORT_PER_CYCLE=10
STECH_RESEARCH_MAX_IMPORT_PER_CYCLE=20
STECH_RESEARCH_POLL_SECONDS=60
```

Reiniciar `stech-mcp.exe` y `stech-enrichment-worker.exe`. Probar primero un solo ciclo del bridge:

```powershell
.\.venv\Scripts\stech-chatgpt-bridge.exe --once
```

Después de reintentar un `RESEARCH_IMAGES` previamente fallido, el resultado esperado del primer ciclo es un item `WAITING_EXTERNAL_RESEARCH` y un archivo nuevo bajo `research_bridge/requests/`. La tarea programada de ChatGPT investiga ese request y crea `research_bridge/results/<request_id>.json`. En el siguiente ciclo local:

```powershell
.\.venv\Scripts\stech-chatgpt-bridge.exe --once
```

el resultado debe importarse como candidato y quedar `REVIEW_REQUIRED`; también debe crearse `research_bridge/receipts/<request_id>.json`. Ejecutar el mismo ciclo nuevamente no debe duplicar el candidato ni el receipt.

Solo después de validar este recorrido con un PN real en PC020 se puede considerar el V1 apto para merge.
