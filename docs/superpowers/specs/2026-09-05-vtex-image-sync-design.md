# VTEX Image Sync V1 Design

## Goal

Automatizar la sincronización de imágenes locales de productos S-TECH hacia VTEX usando STECH MCP como autoridad de imágenes y PC020 como origen físico de archivos, sin modificar la lógica ya congelada de identidad, categoría, atributos, pricing ni stock de `scr/v8-identity`.

## Confirmed environment

- STECH MCP corre físicamente en PC020.
- Raíz local de imágenes: `C:\STECH_IMAGENES`.
- La metadata de imágenes ya existe en `STECH_MCP.dbo.product_image`.
- El MCP ya se publica por Cloudflare Tunnel usando `mcp.artos.pe`.
- Los archivos de un producto siguen la convención `{PARTNUMBER}_01.jpg`, `{PARTNUMBER}_02.jpg`, etc.
- `_01` es SIEMPRE la imagen principal.
- Primera prueba real: `82YU00XYLM`.

## VTEX contract

VTEX asocia imágenes a SKUs. El flujo usa Catalog API clásico para archivos SKU:

- Resolver SKU ID por RefId: `GET /api/catalog_system/pvt/sku/stockkeepingunitidbyrefid/{refId}`.
- Leer imágenes actuales: `GET /api/catalog/pvt/stockkeepingunit/{skuId}/file`.
- Crear imagen: `POST /api/catalog/pvt/stockkeepingunit/{skuId}/file`.

Payload esperado:

```json
{
  "IsMain": true,
  "Label": "Main",
  "Name": "82YU00XYLM_01.jpg",
  "Url": "https://mcp.artos.pe/vtex-images/<signed-token>"
}
```

VTEX requiere que `Url` sea externa y legible públicamente durante la descarga.

## No separate hosting requirement

No se contratará hosting adicional. Cloudflare Tunnel ya conecta `mcp.artos.pe` con el servicio local de PC020. STECH MCP expondrá una ruta HTTP temporal:

`GET /vtex-images/{signed_token}`

La ruta servirá solamente el archivo exacto autorizado por el token. No habrá exploración de carpetas ni acceso por path arbitrario.

Si Cloudflare Access protege todo `mcp.artos.pe`, la ruta `/vtex-images/*` deberá quedar públicamente accesible para VTEX o se usará un hostname público separado que apunte al mismo Tunnel. No se requiere otro servidor.

## Signed image URL security

Cada URL temporal incluirá un token HMAC-SHA256 con:

- `product_image_id`
- `partnumber`
- expiración Unix

`VTEX_IMAGE_SIGNING_SECRET` es opcional. Si no se define, STECH MCP genera automáticamente un secreto criptográficamente seguro al arrancar y lo conserva durante la vida del proceso. Un reinicio invalida URLs temporales anteriores, lo cual es aceptable porque su TTL es corto. Si el operador define un secreto explícito, ese valor tiene prioridad.

Reglas:

- TTL por defecto: 900 segundos.
- Token inválido o vencido: HTTP 403.
- Imagen no encontrada: HTTP 404.
- `storage_path` debe resolver debajo de `STECH_IMAGE_ROOT`; cualquier escape se rechaza.
- Solo se sirven formatos aprobados (`jpg`, `jpeg`, `png`, `gif`).
- No se listan carpetas.

## Local image discovery

Nueva operación `product_images_sync_local(partnumber)`:

1. Normaliza Part Number a mayúsculas.
2. Escanea `STECH_IMAGE_ROOT` recursivamente por archivos cuyo Part Number sea exacto.
3. Solo acepta nombres `{PN}_NN.ext`.
4. `NN=01` => `position=1` y principal.
5. Orden posterior por `NN` ascendente.
6. Calcula SHA-256, tamaño de archivo, dimensiones y formato real.
7. Persiste/upserta en `dbo.product_image` con `source_type='LOCAL_PC020'`, `storage_path`, `sha256_hash`, dimensiones, formato, `position` e `is_approved=1` si el archivo pasa validación.
8. No duplica por `(partnumber, sha256_hash, variant_type)`.

Si existen `_02`, `_03`, etc. pero falta `_01`, el estado será `REVIEW` y no se subirá nada automáticamente.

## Validation

Nueva operación `product_images_validate(partnumber)` devuelve:

- `READY`: existe `_01` y todas las imágenes seleccionadas son válidas.
- `REVIEW`: hay imágenes pero falta `_01`, hay duplicados/conflictos o archivos no válidos.
- `NO_IMAGES`: no existen imágenes locales.
- `ERROR`: fallo de acceso o lectura.

Validaciones mínimas:

- archivo existe y es legible;
- extensión/formato válido;
- máximo 5 MB por archivo;
- dimensiones mayores que 0;
- Part Number exacto;
- posición derivada del sufijo `_NN`;
- `_01` única principal.

## VTEX synchronization

Nueva operación `vtex_images_sync(partnumber)`:

1. Ejecuta `product_images_sync_local`.
2. Ejecuta `product_images_validate`.
3. Resuelve SKU RefId como `{PARTNUMBER}-S` por defecto.
4. Obtiene `sku_id` real desde VTEX.
5. Lee `GET .../{skuId}/file` antes de escribir.
6. Compara contra publicaciones ya registradas y contra archivos remotos existentes.
7. En modo V1 usa estrategia `MISSING_ONLY`: no borra ni reemplaza imágenes manuales existentes.
8. Genera URL temporal firmada por cada imagen faltante.
9. Publica en orden ascendente.
10. `_01` se manda con `IsMain=true`; las demás con `false`.
11. Vuelve a leer `GET .../{skuId}/file`.
12. Registra resultado y auditoría.

No activa/desactiva productos en V1. La activación se tratará después.

## Publication traceability

Se agrega una tabla aditiva `dbo.product_image_publication` en `STECH_MCP`:

- `product_image_publication_id`
- `product_image_id`
- `partnumber`
- `channel` (`VTEX`)
- `account_code`
- `remote_product_id` nullable
- `remote_sku_id`
- `remote_file_id` nullable
- `remote_archive_id` nullable
- `remote_url` nullable
- `position`
- `is_main`
- `status` (`PENDING`, `UPLOADED`, `VERIFIED`, `ERROR`)
- `last_error`
- `uploaded_at`
- `last_verified_at`
- `created_at`
- `updated_at`

Unique key: `(channel, account_code, remote_sku_id, product_image_id)`.

La tabla existente `dbo.product_image` sigue siendo la fuente maestra de imagen local; la nueva tabla solo registra publicación por canal.

## MCP tools

V1 expone:

- `product_images_sync_local(partnumber)`
- `product_images_validate(partnumber)`
- `vtex_images_status(partnumber)`
- `vtex_images_sync(partnumber, account_code="VTEX_STECH")`

`product_images_get(partnumber)` se conserva y deberá incluir la metadata local sincronizada.

Batch automático (`vtex_images_sync_batch`) y búsqueda/edición de imágenes faltantes quedan fuera de V1 hasta validar un producto real de extremo a extremo.

## Configuration

Variables nuevas de `.env`:

```env
STECH_IMAGE_ROOT=C:\STECH_IMAGENES

VTEX_ACCOUNT_NAME=ststore227
VTEX_ENVIRONMENT=vtexcommercestable.com.br
VTEX_APP_KEY=
VTEX_APP_TOKEN=

VTEX_IMAGE_PUBLIC_BASE=https://mcp.artos.pe/vtex-images
# Opcional; si se omite, STECH MCP genera uno seguro al arrancar.
VTEX_IMAGE_SIGNING_SECRET=
VTEX_IMAGE_URL_TTL_SECONDS=900
VTEX_HTTP_TIMEOUT_SECONDS=30
```

Las credenciales también aceptan los aliases ya usados por V8:

```env
CHN_CRED_VTEX_STECH_APP_KEY=
CHN_CRED_VTEX_STECH_APP_TOKEN=
```

`VTEX_IMAGE_PUBLIC_BASE` NO implica hosting adicional: apunta al mismo MCP expuesto por Cloudflare Tunnel.

No se debe subir `.env`, AppKey, AppToken ni un secreto explícito a GitHub.

## Frozen boundaries

Este trabajo NO modifica:

- identidad Product/SKU de `scr/v8-identity`;
- categoría Seller Portal;
- atributos Excel;
- BrandId;
- Pricing;
- stock/Logistics;
- fechas comerciales;
- REVIEW_FIRST;
- publicación de catálogo existente.

STECH MCP será autoridad para descubrimiento, validación, metadata y subida de imágenes. V1 no cambia el comportamiento de V8.

## Acceptance test

Con `82YU00XYLM` y archivos locales `_01`..`_04`:

1. `product_images_sync_local("82YU00XYLM")` encuentra 4 imágenes.
2. `_01` queda `position=1` y principal.
3. `product_images_validate` devuelve `READY`.
4. `vtex_images_sync` resuelve el SKU real.
5. VTEX recibe solo imágenes faltantes.
6. `_01` queda como `IsMain=true`.
7. GET de read-back devuelve las imágenes publicadas.
8. La ejecución repetida es idempotente: no crea duplicados.
9. Pricing, stock, categoría y atributos no se modifican.
