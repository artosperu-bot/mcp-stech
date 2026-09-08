# STECH MCP â€” SincronizaciÃ³n de imÃ¡genes VTEX

## Estado

Flujo validado con la cuenta VTEX `ststore227` y el producto de prueba `82YU00XYLM`.

El flujo de imÃ¡genes ya no depende de Classic Catalog PVT (`/api/catalog/pvt/stockkeepingunit/{skuId}/file`) porque, en esta cuenta, esa familia de endpoints devuelve HTTP 500 del backend VTEX.

El transporte operativo es:

1. **Catalog Seller Portal / CatalogV2** para leer el producto y asociar imÃ¡genes.
2. **vtex.catalog-images** para almacenar las imÃ¡genes en VTEX Assets.
3. **Read-back de Seller Portal** para verificar el resultado final.

## Reglas de seguridad

El flujo de imÃ¡genes cumple estas reglas:

- No modifica precio.
- No modifica stock.
- No modifica categorÃ­a.
- No modifica atributos.
- No activa ni desactiva producto/SKU.
- No borra imÃ¡genes existentes.
- `_01` es siempre la imagen principal.
- Solo se agregan imÃ¡genes faltantes.
- La sincronizaciÃ³n es idempotente: una segunda ejecuciÃ³n no debe volver a subir imÃ¡genes ya presentes.
- Si una operaciÃ³n crÃ­tica falla, el producto queda reportado como `ERROR`/`BLOCKED` y se conserva la evidencia del error.
- DespuÃ©s de escribir, se realiza read-back para verificar las imÃ¡genes remotas.

## Identidad VTEX confirmada en la prueba

Para `82YU00XYLM`:

- Product ID: `251`
- Product externalId / ProductRefId: `82YU00XYLM`
- SKU ID: `251`
- SKU externalId / RefId: `82YU00XYLM-S`
- EAN: `0197528523880`
- Transporte: `catalog_seller_portal`

## Herramientas MCP individuales

### `product_images_sync_local(partnumber)`

Descubre las imÃ¡genes locales exactas del Part Number y persiste su metadata.

### `product_images_validate(partnumber)`

Valida el inventario local. `_01` es obligatoria y se considera principal.

### `vtex_images_status(partnumber, account_code="VTEX_STECH")`

Consulta el estado local/remoto sin escribir en VTEX.

Estados principales:

- `READY`: hay trabajo pendiente y se puede sincronizar.
- `SYNCED`: todas las imÃ¡genes locales estÃ¡n verificadas en VTEX.
- `BLOCKED`: existe una condiciÃ³n que impide escribir de forma segura.
- `ERROR`: ocurriÃ³ un error durante el proceso.

### `vtex_images_sync(partnumber, account_code="VTEX_STECH")`

Sincroniza solamente las imÃ¡genes faltantes y verifica el resultado por read-back.

## Herramientas MCP masivas

### `vtex_images_missing_list(...)`

Lista productos locales que todavÃ­a no estÃ¡n completamente sincronizados con VTEX.

ParÃ¡metros:

- `after_partnumber`: cursor lexicogrÃ¡fico para continuar una ejecuciÃ³n.
- `limit`: cantidad mÃ¡xima de pendientes devueltos.
- `account_code`: por defecto `VTEX_STECH`.
- `include_blocked`: incluye productos bloqueados para diagnÃ³stico.

La funciÃ³n es de lectura respecto de VTEX: no publica imÃ¡genes.

### `vtex_images_sync_batch(...)`

Sincroniza un conjunto explÃ­cito de Part Numbers o toma automÃ¡ticamente los pendientes accionables.

ParÃ¡metros:

- `partnumbers`: lista opcional de PNs exactos.
- `after_partnumber`: cursor para ejecuciÃ³n masiva paginada.
- `limit`: mÃ¡ximo por lote.
- `account_code`: por defecto `VTEX_STECH`.
- `stop_on_error`: si es `true`, detiene el lote ante el primer error.

Cada producto reutiliza las mismas protecciones de `vtex_images_sync`.

## Ejemplos de uso desde ChatGPT

El usuario no necesita llamar las funciones por nombre. Puede escribir instrucciones naturales como:

- `Completa las imÃ¡genes VTEX del producto 82YU00XYLM.`
- `Revisa 82YU00XYLM y sube solamente las imÃ¡genes que falten.`
- `MuÃ©strame los productos que tienen imÃ¡genes pendientes en VTEX.`
- `Completa todas las imÃ¡genes VTEX que falten.`
- `Sincroniza las imÃ¡genes de estos PNs: PN1, PN2, PN3.`
- `ContinÃºa desde el Ãºltimo producto pendiente.`

ChatGPT utiliza las herramientas MCP correspondientes detrÃ¡s de la instrucciÃ³n natural.

## Flujo tÃ©cnico actual

```text
ImÃ¡genes locales C:\STECH_IMAGENES
        |
        v
product_images_sync_local
        |
        v
product_images_validate
        |
        v
Catalog Seller Portal GET
        |
        +--> ya existe -> reutilizar / omitir
        |
        +--> falta -> obtener VTEX local token
                    -> vtex.catalog-images
                    -> VTEX Assets URL
        |
        v
Catalog Seller Portal PUT (objeto protegido)
        |
        v
Catalog Seller Portal GET / read-back
        |
        v
VERIFIED / SYNCED
```

## Hallazgo tÃ©cnico importante

En `ststore227`, Classic Catalog PVT respondiÃ³ HTTP 500 incluso desde clientes HTTP independientes y credenciales vÃ¡lidas. Catalog Seller Portal respondiÃ³ HTTP 200 para el mismo producto y `vtex.catalog-images` respondiÃ³ HTTP 200 al almacenar la imagen.

Por eso el flujo de producciÃ³n de imÃ¡genes utiliza Seller Portal/CatalogV2.

## Despliegue local

El proyecto usa layout `src`. DespuÃ©s de cambiar cÃ³digo, mantener el entorno instalado en modo editable:

```powershell
cd C:\DESAROLLO\mcp-stech
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m stech_mcp.server
```

Esto evita ejecutar una copia vieja instalada en `site-packages` y garantiza que `python -m stech_mcp.server` cargue `src\stech_mcp\server.py` del repositorio actual.
## Resolucion Seller Portal por ProductId

Para sincronizar imagenes no se usa como fuente autoritativa el GET de Seller Portal por `external-id`, porque en algunos productos puede fallar o devolver una forma incompleta sin campos requeridos como `slug`.

El flujo seguro es:

1. Resolver el SKU por `Catalog System` usando el RefId `{PARTNUMBER}-S`.
2. Leer el contexto del SKU y obtener su `ProductId` real.
3. Leer el producto completo con `GET /api/catalog-seller-portal/products/{productId}`.
4. Validar que ProductId, ProductRefId y SKU correspondan al Part Number esperado.
5. Construir el PUT preservando todos los campos no-imagen, incluido `slug`.
6. Cambiar solamente `images` del producto y del SKU.
7. Hacer read-back y verificar que `_01` quede primero/principal.

Si el producto completo sigue sin un campo obligatorio, la escritura se bloquea con `seller_portal_payload_invalid`.

`vtex_images_missing_list` tambien expone, cuando VTEX devuelve un error:

- `error_operation`
- `status_http`
- `error_detail`
- `vtex_error`

Esto permite diferenciar errores de Catalog System, Seller Portal y red sin ocultarlos bajo un motivo generico.
## Resultado validado en produccion - 2026-09-06

El flujo real de imagenes VTEX fue validado en produccion con `82YU00XYLM`.

Resultado confirmado:

- 4 imagenes remotas y 4 verificadas.
- `_01` quedo como principal.
- 3 assets nuevos subidos.
- 1 asset existente reutilizado.
- Asociacion del producto via Catalog Seller Portal.
- Read-back final correcto.
- Sin borrar imagenes existentes.
- Sin modificar precio, stock, categoria, atributos ni activacion.
- Classic Catalog PVT no se usa para este flujo porque en esta cuenta devolvia HTTP 500.
- El transporte funcional es `Catalog System + Catalog Seller Portal + vtex.catalog-images`.

La evidencia completa, URLs VTEX Assets, reglas de seguridad, resultados del modo masivo y limitaciones conocidas estan documentadas en:

`docs/VTEX_IMAGES_VALIDACION_PRODUCCION_2026-09-06.md`
