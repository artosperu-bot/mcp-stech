# VTEX Images MCP â€” Resultado validado en producciÃ³n

**Fecha de validaciÃ³n:** 2026-09-06
**Repositorio:** `artosperu-bot/mcp-stech`
**Canal:** `VTEX_STECH`
**Cuenta VTEX:** `ststore227`

## Objetivo validado

Se validÃ³ el flujo de publicaciÃ³n de imÃ¡genes VTEX desde STECH MCP usando las imÃ¡genes locales existentes, sin depender del endpoint Classic Catalog PVT que devolvÃ­a HTTP 500 en esta cuenta.

El transporte que funcionÃ³ fue:

1. `Catalog System` para resolver SKU y contexto.
2. `Catalog Seller Portal / CatalogV2` para leer y actualizar el producto.
3. `vtex.catalog-images` para guardar los assets.
4. Read-back final para verificar el orden y la publicaciÃ³n.

## Producto principal validado: `82YU00XYLM`

Datos identificados en VTEX:

- Product RefId: `82YU00XYLM`
- SKU RefId: `82YU00XYLM-S`
- ProductId / SKUId: `251`
- EAN: `0197528523880`
- Marca: LENOVO
- CategorÃ­a VTEX: Laptops

ImÃ¡genes locales detectadas y validadas:

- `82YU00XYLM_01.jpg`
- `82YU00XYLM_02.jpg`
- `82YU00XYLM_03.jpg`
- `82YU00XYLM_04.jpg`

Resultado real de sincronizaciÃ³n:

- Estado final: `SYNCED`
- ImÃ¡genes remotas: `4`
- ImÃ¡genes verificadas: `4`
- ImÃ¡genes nuevas subidas: `3`
- Assets reutilizados: `1`
- `product_update_performed=true`
- Errores: `0`
- `_01` quedÃ³ como imagen principal (`is_main=true`)

El asset `_01` ya existÃ­a en VTEX Assets y fue reutilizado. El MCP subiÃ³ `_02`, `_03` y `_04`, luego asociÃ³ las cuatro imÃ¡genes al producto y verificÃ³ por read-back que `_01` quedara primero/principal.

## URLs VTEX Assets verificadas para `82YU00XYLM`

- `_01`: `https://ststore227.vtexassets.com/assets/vtex.catalog-images/products/82YU00XYLM_01___da4a579c26e9e4210d43e0e6beff18ba.jpg`
- `_02`: `https://ststore227.vtexassets.com/assets/vtex.catalog-images/products/82YU00XYLM_02___d2e4a515c11dcad4026e7d4508e37dbe.jpg`
- `_03`: `https://ststore227.vtexassets.com/assets/vtex.catalog-images/products/82YU00XYLM_03___a9f44f56764022396304a1eaa577643f.jpg`
- `_04`: `https://ststore227.vtexassets.com/assets/vtex.catalog-images/products/82YU00XYLM_04___74be6f33dd3f2159bbc1ccd6c4537850.jpg`

## Reglas de seguridad que se respetaron

Durante el flujo de imÃ¡genes:

- No se modificÃ³ precio.
- No se modificÃ³ stock.
- No se modificÃ³ categorÃ­a.
- No se modificaron atributos.
- No se activaron ni desactivaron productos/SKUs.
- No se borraron imÃ¡genes existentes.
- `_01` se mantuvo como principal.
- Se preservaron los campos no-imagen del producto.
- Se hizo verificaciÃ³n por read-back antes de considerar la sincronizaciÃ³n correcta.

## Problema del Classic Catalog PVT

El endpoint clÃ¡sico:

`/api/catalog/pvt/stockkeepingunit/{skuId}/file`

devolvÃ­a HTTP 500 en esta cuenta incluso en operaciones GET y tambiÃ©n en otros endpoints `/api/catalog/pvt`.

El mismo producto sÃ­ respondÃ­a correctamente por `Catalog System` y `Catalog Seller Portal`.

Por eso el flujo definitivo no depende de Classic Catalog PVT para la sincronizaciÃ³n de imÃ¡genes.

## CorrecciÃ³n del login local de VTEX

El login para obtener el token local de VTEX debÃ­a usar HTTPS directamente:

`https://api.vtexcommercestable.com.br/api/vtexid/apptoken/login?an=ststore227`

El uso de `http://` producÃ­a una redirecciÃ³n HTTP 307 que el cliente MCP no seguÃ­a correctamente.

## Funciones MCP disponibles para el flujo de imÃ¡genes

Flujo individual:

- `product_images_sync_local`
- `product_images_validate`
- `vtex_images_status`
- `vtex_images_sync`

Flujo masivo:

- `vtex_images_missing_list`
- `vtex_images_sync_batch`

## Resultado observado del modo masivo

En una ejecuciÃ³n masiva se detectaron 245 registros candidatos.

La mayorÃ­a no llegÃ³ a escritura porque VTEX devolviÃ³ situaciones como:

- `SKU not found` (HTTP 404)
- `AccountInvalidError` (HTTP 500)
- `catalog_system_product_ref_mismatch`

Esto confirma que el batch respeta el bloqueo previo a escritura cuando el producto no puede resolverse de forma segura en VTEX.

### `82YU00X4LM`

Este Part Number apareciÃ³ en el batch y se verificÃ³ que ya conservaba:

- 4 imÃ¡genes remotas
- `_01` como principal
- 0 imÃ¡genes eliminadas
- 0 imÃ¡genes nuevas subidas en ese intento
- 4 assets existentes reutilizados

El intento de actualizaciÃ³n fue bloqueado por `seller_portal_payload_invalid` debido a ausencia de `slug`, por lo que `product_update_performed=false`.

Importante: aunque el batch lo clasificÃ³ como bloqueado, el estado visual de sus imÃ¡genes ya era correcto. Esto queda documentado como una limitaciÃ³n de clasificaciÃ³n/idempotencia del batch, no como un fallo de publicaciÃ³n de imÃ¡genes.

### `C11CJ80201`

Este producto conservÃ³ 5 imÃ¡genes existentes. Su imagen antigua `_2.jpg` seguÃ­a como principal porque el intento de reordenar para poner `_01` fue bloqueado por ausencia de `slug`. No se borrÃ³ ni alterÃ³ ninguna imagen.

## ConclusiÃ³n validada

El flujo individual de imÃ¡genes VTEX quedÃ³ probado en producciÃ³n con `82YU00XYLM`:

- carga de assets: OK
- reutilizaciÃ³n de asset existente: OK
- asociaciÃ³n en Seller Portal: OK
- `_01` principal: OK
- read-back: OK
- preservaciÃ³n de imÃ¡genes existentes: OK
- sin tocar datos comerciales ni activaciÃ³n: OK

El modo masivo tambiÃ©n quedÃ³ operativo a nivel de detecciÃ³n, guardas, continuidad ante errores y reporte, pero todavÃ­a conserva casos de clasificaciÃ³n que deben tratarse como una mejora separada (por ejemplo, productos ya correctos que se bloquean por `slug`, SKUs inexistentes que no deberÃ­an contarse como pendientes accionables y errores de cuenta/RefId).
