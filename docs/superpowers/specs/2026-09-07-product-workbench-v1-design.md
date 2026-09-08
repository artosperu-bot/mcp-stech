# Product Workbench V1 — Diseño MCP

**Fecha:** 2026-09-07  
**Estado:** Diseño aprobado en conversación; pendiente revisión antes del plan de implementación  
**Repositorio compañero:** `artosperu-bot/scr` rama `feat/product-workbench-v1`

## Propósito

Este documento fija la responsabilidad de `mcp-stech` dentro del Product Workbench V1. La UI vive en SCR/V8. `mcp-stech` aporta los servicios reutilizables de dominio, orquestación, imágenes y VTEX.

El Workbench debe servir tanto para **cargar productos nuevos desde Excel** como para **buscar y editar productos existentes**, sin duplicar pipelines.

## Arquitectura

```text
SCR / V8
  Product Workbench UI
  Jobs / progreso / edición
        |
        v
MCP-STECH
  ProductLoaderOrchestrator
  Product Master
  Validación
  Image Pipeline
  VTEX Product/SKU Ensure
        |
        +--> SQL Server
        +--> C:\STECH_IMAGENES
        +--> VTEX
```

SCR no implementa lógica paralela de imágenes ni creación VTEX. Llama contratos MCP específicos.

## Reutilización obligatoria

Se preservan y reutilizan los contratos existentes, especialmente:

- `LocalImageSyncService`
- `ProductImageRepository`
- `ImagePublicationRepository`
- `VtexImageSyncService`
- `VtexImageClient`
- Product Master / preparación / aprobación existentes

El flujo de imágenes ya validado no se reemplaza.

## ProductLoaderOrchestrator

Se agrega un orquestador persistente e idempotente que coordina, no duplica:

```text
Excel item / Part Number
  -> Product Master prepare/reuse
  -> local image inventory
  -> Deltron image reuse when available
  -> image validation
  -> VTEX identity check
      -> exists: update/check mode
      -> missing: ensure Product + SKU
  -> VTEX image sync
  -> read-back
  -> final state
```

Un error de un Part Number no detiene el lote.

## VTEX Ensure Product/SKU

Se agrega un servicio especializado para creación segura e idempotente.

Convención inicial:

```text
Product RefId = <PARTNUMBER>
SKU RefId     = <PARTNUMBER>-S
```

Orden obligatorio cuando falta el producto:

1. validar datos mínimos (identidad, brand, categoría y campos VTEX requeridos);
2. buscar Product existente por identidad exacta;
3. crear Product solamente si no existe;
4. read-back y confirmar ProductId/RefId;
5. buscar SKU existente exacto;
6. crear SKU solamente si no existe;
7. read-back y confirmar SkuId/RefId;
8. persistir identidad/auditoría;
9. continuar con imágenes.

Si Product se creó pero SKU falló, el reintento debe reutilizar el Product confirmado, nunca duplicarlo.

## Edición de productos existentes

El mismo dominio soporta edición modular. No habrá un `update everything` genérico.

Operaciones separadas por responsabilidad:

- producto/contenido;
- categoría;
- EAN/UPC/GTIN;
- SKU/logística;
- imágenes;
- activación (explícita y separada);
- otros módulos que ya tengan contrato verificado.

Toda escritura remota relevante debe hacer read-back.

Precio y stock no son efectos colaterales de la edición de producto/imágenes.

## Imágenes y variantes

Variantes canónicas:

- `ORIGINAL`
- `EDITED_STECH`
- `MARKETPLACE`

Reglas:

1. originales nunca se destruyen ni sobrescriben;
2. una edición crea variante hija (`parent_image_id`);
3. SHA-256 evita duplicados;
4. `_01` conserva prioridad de principal;
5. orden persistido explícitamente;
6. imagen ya correcta no se vuelve a subir;
7. no borrar imágenes VTEX existentes en V1;
8. sincronizar imágenes no modifica precio, stock, categoría, atributos, EAN/UPC, activación ni título/descripción;
9. la receta visual automática S-TECH queda fuera de V1 hasta que se apruebe un perfil visual concreto.

## Jobs persistentes

Entidades finales se ajustarán a las convenciones SQL existentes, manteniendo responsabilidades equivalentes a:

- `product_loader_job`
- `product_loader_job_item`
- `product_loader_job_event`

Estados de item mínimos:

- `PENDING`
- `VALIDATING`
- `PREPARING`
- `IMAGES_LOCAL`
- `RESEARCH_REQUIRED`
- `VTEX_CHECK`
- `VTEX_CREATE_PRODUCT`
- `VTEX_CREATE_SKU`
- `VTEX_IMAGES`
- `VERIFYING`
- `COMPLETED`
- `REVIEW_REQUIRED`
- `BLOCKED`
- `FAILED`

Idempotencia por Part Number + canal + operación. Los pasos confirmados no se repiten innecesariamente.

## Contratos MCP esperados

Los nombres finales deben reutilizar herramientas existentes cuando ya cubran la responsabilidad. Capacidades requeridas:

- preview de importación;
- iniciar job;
- consultar job/items;
- reintentar item;
- preparar/releer producto;
- editar módulo;
- sincronizar/validar imágenes locales;
- asegurar Product/SKU VTEX;
- consultar/sincronizar imágenes VTEX.

No se agrega un endpoint SQL genérico.

## Web Research

No se implementa investigación web automática en V1. Si local + Deltron no alcanzan para completar imágenes, el item queda `RESEARCH_REQUIRED` y continúa el lote.

## Seguridad y auditoría

Persistir:

- Part Number;
- job/item/paso;
- ProductId/SkuId/RefIds confirmados;
- imágenes/hashes/posiciones;
- operación solicitada;
- resultado de read-back;
- error y clasificación;
- actor/origen;
- timestamps.

Nunca registrar secretos VTEX, cookies ni credenciales.

## Compatibilidad

- Se parte de `feat/product-workspace-v1`.
- Los servicios existentes siguen siendo backward compatible.
- Las migraciones son aditivas.
- El pipeline VTEX de imágenes validado se conserva.
- Primero se prueba con un Part Number controlado antes de lotes grandes.

## Criterio de éxito MCP V1

Para un PN existente debe poder preparar/releer, inventariar imágenes, resolver VTEX y sincronizar imágenes con read-back sin tocar dominios no solicitados.

Para un PN inexistente en VTEX debe poder crear Product + SKU de forma idempotente y recuperable, confirmar identidad y continuar con imágenes.

Para un lote debe poder persistir progreso, continuar ante errores por item y reanudar sin duplicar productos, SKUs ni imágenes ya correctas.
