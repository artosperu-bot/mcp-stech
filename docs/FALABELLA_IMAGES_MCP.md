# STECH MCP — Falabella Image Bridge

## Objetivo

Preparar y publicar temporalmente imágenes de producto para plantillas de Falabella Seller Center sin modificar los originales.

- Fuente: `C:\\STECH_IMAGENES`
- Salida: `C:\\STECH_IMAGENES_CHANNELS\\FALABELLA\\{PARTNUMBER}`
- URL: `https://mcp.artos.pe/falabella-images/{signed-token}`

Cloudflare Tunnel expone por HTTPS el archivo que sigue almacenado en PC020; no se guarda la imagen en Cloudflare.

## Reglas implementadas

- JPEG, 72 DPI.
- 1500 x 1500 px.
- Máximo 150 KB.
- Hasta 8 imágenes.
- `_01` es principal.
- Proporción preservada y producto centrado.
- Lienzo blanco.
- Originales nunca se sobrescriben.
- Fondo fuente no blanco/transparente: se genera la variante pero queda advertencia `source_background_requires_review`.
- V1 no hace eliminación de fondo con IA.

## Seguridad

Cada URL usa un token HMAC-SHA256 con `product_image_id`, Part Number y expiración. Solo se sirven variantes aprobadas cuyo `variant_type` comienza con `FALABELLA_` y cuyo archivo está dentro de `STECH_CHANNEL_IMAGE_ROOT`.

TTL por defecto: 172800 segundos (48 horas). Si `FALABELLA_IMAGE_SIGNING_SECRET` queda vacío, la clave se genera una vez y se persiste fuera de Git en `C:\\STECH_IMAGENES_CHANNELS\\.falabella-image-signing-secret`.

## Herramientas MCP

- `falabella_images_prepare(partnumber, max_images=8)` prepara un PN y devuelve URLs firmadas.
- `falabella_images_prepare_batch(partnumbers, max_images=8)` procesa hasta 500 PNs.

## Llenado automático de Excel

Script: `scripts/falabella_fill_excel_images.py`.

Busca en la fila 4 `SKU del vendedor #29` e `Imagen principal #IM1` hasta `Imagen8 #IM8`, prepara imágenes y completa las URLs. No reemplaza URLs existentes salvo que se use `--overwrite`.

Flujo recomendado sin escribir rutas:

1. Copiar el Excel a `C:\\DESAROLLO\\mcp-stech\\EXCEL\\FALABELLA\\ENTRADA`.
2. Ejecutar `.\\RUN_FALABELLA_EXCEL.ps1` o hacer doble clic en `FALABELLA_EXCEL.bat`.
3. El sistema toma automáticamente el `.xlsx` más reciente de ENTRADA.
4. El resultado queda en `C:\\DESAROLLO\\mcp-stech\\EXCEL\\FALABELLA\\SALIDA`.

También se mantiene el argumento de ruta opcional para usos avanzados.

La salida se nombra `<archivo_original>_IMAGENES_FALABELLA.xlsx`.

## Configuración

    STECH_IMAGE_ROOT=C:\\STECH_IMAGENES
    STECH_CHANNEL_IMAGE_ROOT=C:\\STECH_IMAGENES_CHANNELS
    FALABELLA_IMAGE_PUBLIC_BASE=https://mcp.artos.pe/falabella-images
    FALABELLA_IMAGE_SIGNING_SECRET=
    FALABELLA_IMAGE_SIGNING_SECRET_FILE=
    FALABELLA_IMAGE_URL_TTL_SECONDS=172800
    FALABELLA_IMAGE_CANVAS_PX=1500
    FALABELLA_IMAGE_MAX_BYTES=153600
    FALABELLA_IMAGE_MIN_SOURCE_PX=500
    FALABELLA_IMAGE_MARGIN_PX=30

## Cloudflare

La ruta `/falabella-images/*` debe poder descargarse sin login o desafío interactivo de Cloudflare Access, porque Falabella Seller Center realiza la descarga. Las demás rutas del MCP pueden mantener sus controles normales.

## Flujo

    Excel -> Seller SKU/PN -> C:\\STECH_IMAGENES -> preparación Falabella ->
    C:\\STECH_IMAGENES_CHANNELS\\FALABELLA -> token firmado -> Cloudflare -> IM1..IM8
