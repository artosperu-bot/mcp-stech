# STECH MCP — Market Intelligence V1

**Fecha:** 2026-09-10  
**Rama base:** `feat/product-enrichment-engine-v2-current`  
**Rama de trabajo:** `feat/market-intelligence-v1`

## 1. Objetivo

Agregar a STECH MCP un subsistema de inteligencia comercial que responda, con datos trazables:

- qué productos conviene vender, comprar, publicar, mantener o liquidar;
- a qué precio conviene vender por canal;
- cómo cambia el precio, stock, promoción y posición de cada competidor;
- qué proveedor ofrece el mejor costo disponible;
- si competir contra el precio actual conserva el margen mínimo de S-TECH;
- dónde existen huecos de surtido y oportunidades de mercado;
- qué riesgos existen: guerra de precios, margen insuficiente, caída de precio, baja rotación, stock inmovilizado, proveedor sin stock o datos desactualizados.

V1 es un **motor de análisis y recomendación**. No cambia automáticamente precios, stock, publicaciones ni compras en marketplaces/ERP.

## 2. Principios de diseño

1. **Histórico primero.** Nunca sobrescribir una observación anterior. Cada captura de precio/stock/promoción queda versionada por fecha y fuente.
2. **PN/SKU exacto primero.** No comparar productos solo por nombre. Toda publicación externa debe mapearse a un Part Number/SKU interno con estado y confianza.
3. **Datos observados ≠ inferidos.** Mantener fuente, fecha, método de captura y calidad.
4. **Score ≠ confianza.** Un producto puede tener oportunidad 90/100 pero confianza 45/100 si faltan demanda o costos recientes.
5. **Políticas configurables.** Margen S-TECH, comisión del canal, costo de envío, impuestos y umbrales son datos vigentes por fecha/canal/categoría, no constantes en código.
6. **Sin SQL libre.** Todas las operaciones se hacen mediante repositorios y consultas parametrizadas.
7. **Aditivo.** No reemplaza Product Master, Product Work, V8, VTEX Images ni las tablas operativas actuales.
8. **No publicación automática en V1.** Las acciones `BAJAR_PRECIO`, `COMPRAR`, etc. son recomendaciones auditables hasta que exista un flujo de aprobación separado.

## 3. Arquitectura

Se sigue el patrón actual del repositorio:

```text
DB_DISTRIBUIDORES / fuentes externas / ERP
              ↓
        adapters / ingest
              ↓
      MarketRepository (STECH_MCP)
              ↓
       domain calculations
              ↓
    MarketIntelligenceService
              ↓
          MCP tools
              ↓
 ChatGPT / agente / SCR / reportes
```

Nuevos módulos previstos:

```text
src/stech_mcp/domain/market_models.py
src/stech_mcp/domain/market_math.py
src/stech_mcp/domain/opportunity_score.py
src/stech_mcp/db/market_repository.py
src/stech_mcp/services/market_intelligence.py
src/stech_mcp/tools/market_intelligence.py
sql/010_market_intelligence_v1.sql
```

El registro de tools será aditivo desde `server_authoritative.py`, igual que Product Work/Research V2.

## 4. Modelo de datos

### 4.1 `market_listing`

Identidad de una publicación externa o propia.

Campos principales:

- `market_listing_id`
- `source_code`: FALABELLA, MERCADOLIBRE, RIPLEY, COOLBOX, HIRAOKA, STECH, etc.
- `seller_name`
- `external_listing_id`
- `external_sku`
- `title`
- `url`
- `currency`
- `is_stech`
- `first_seen_at`, `last_seen_at`
- `created_at`, `updated_at`

Único lógico: `(source_code, external_listing_id)` cuando exista ID externo; fallback por clave de fuente controlada.

### 4.2 `market_product_match`

Mapeo entre listing externo y producto S-TECH.

- `market_listing_id`
- `partnumber`
- `match_status`: `VERIFIED`, `PROBABLE`, `REVIEW`, `REJECTED`
- `match_method`: `PN_EXACT`, `EAN_EXACT`, `UPC_EXACT`, `MODEL_EXACT`, `MANUAL`, `OTHER`
- `confidence_score` 0..100
- `evidence_json`
- `verified_by`, `verified_at`

Solo `VERIFIED` entra a recomendaciones automáticas de precio. `PROBABLE` puede mostrarse en investigación, pero no mezclarse con el mercado exacto.

### 4.3 `market_observation`

Serie temporal inmutable por listing.

- `market_observation_id`
- `market_listing_id`
- `observed_at`
- `price_regular`
- `price_offer`
- `price_effective`
- `stock_qty` nullable
- `stock_state`: `IN_STOCK`, `LOW_STOCK`, `OUT_OF_STOCK`, `UNKNOWN`
- `promotion_text`
- `promotion_type`
- `shipping_price`
- `seller_count` nullable
- `ranking_position` nullable
- `source_method`: API, COLLECTOR, WEB_RESEARCH, MANUAL
- `source_observation_key`
- `raw_fingerprint`
- `data_quality_score`
- `created_at`

La ingesta debe ser idempotente usando `source_observation_key` o fingerprint + ventana temporal controlada.

### 4.4 `supplier_observation`

Histórico de proveedores: Deltron primero, luego Ingram/Intcomex/u otros.

- `supplier_code`
- `partnumber`
- `observed_at`
- `cost_usd`
- `cost_pen` nullable
- `stock_qty`
- `stock_state`
- `warehouse_code` nullable
- `currency`
- `tax_included`
- `source_method`
- `source_key`

No duplica la fuente operativa si ya existe histórico suficiente: el repositorio puede leer la vista histórica V8 y normalizarla. Esta tabla se usa para fuentes que no tengan histórico compatible.

### 4.5 `market_pricing_policy`

Política configurable y temporal.

- `policy_id`
- `channel_code`
- `category_code` nullable
- `brand` nullable
- `stech_margin_pct`
- `minimum_margin_pct`
- `minimum_contribution_pen`
- `undercut_amount_pen` default 1.00
- `strategy`: `BALANCED`, `MARGIN`, `VOLUME`, `CLEARANCE`
- `effective_from`, `effective_to`
- `is_active`

Especificidad: canal+categoría+marca > canal+categoría > canal > default.

### 4.6 `market_channel_fee_rule`

- `channel_code`
- `category_code` nullable
- `commission_pct`
- `fixed_fee_pen`
- `payment_fee_pct`
- `shipping_cost_pen` nullable
- `free_shipping_threshold_pen` nullable
- `seller_absorbs_shipping_above_threshold`
- `effective_from`, `effective_to`

Permite representar las variaciones reales por categoría y fecha sin hardcodear Falabella/Mercado Libre.

### 4.7 `market_fx_rate`

Tipo de cambio usado por cálculo, con fuente y fecha. Si existe una fuente corporativa autorizada, el adapter la reutiliza en lugar de duplicarla.

### 4.8 `market_recommendation_snapshot`

Persistencia opcional de decisiones calculadas para auditoría/comparación.

- `partnumber`
- `channel_code`
- `calculated_at`
- `action_code`
- `opportunity_score`
- `confidence_score`
- `risk_score`
- `recommended_price_pen`
- `floor_price_pen`
- `market_min_price_pen`
- `market_median_price_pen`
- `expected_profit_pen`
- `expected_margin_pct`
- `reason_codes_json`
- `input_fingerprint`

## 5. Variaciones que debe calcular V1

Para precio, costo, stock y mercado se calcularán, cuando haya datos:

- cambio absoluto y porcentual desde observación anterior;
- variación 1d, 7d, 30d y 90d;
- mínimo, máximo, promedio, mediana y percentiles de precio;
- volatilidad de precio;
- días desde último cambio;
- frecuencia de cambios;
- inicio/fin de promociones;
- entrada/salida de stock;
- días consecutivos sin stock;
- variación del número de vendedores;
- cambio de posición relativa de precio;
- diferencia S-TECH vs mínimo, mediana y siguiente competidor;
- variación del costo de proveedor;
- variación del margen posible;
- spread `precio mercado - costo total`;
- detección de subcotización agresiva;
- indicios de guerra de precios: múltiples recortes cercanos dentro de una ventana;
- frescura de cada señal.

Cada resultado incluye `as_of`, número de observaciones y calidad/frescura.

## 6. Cálculo financiero

El cálculo no asume una única fórmula universal. Recibe la política vigente y devuelve el desglose completo.

Base inicial aprobada para costos USD sin IGV:

```text
costo_producto_pen = costo_usd × tipo_cambio × 1.18
```

Luego:

```text
comision_canal      = precio_venta × commission_pct
fee_pago             = precio_venta × payment_fee_pct
costo_envio_stech    = regla_envio(precio_venta, canal)
contribucion_pen     = precio_venta
                       - costo_producto_pen
                       - comision_canal
                       - fee_fijo
                       - fee_pago
                       - costo_envio_stech
                       - otros_costos_configurados

margen_contribucion_pct = contribucion_pen / precio_venta
```

Se guardará/desplegará también el detalle fiscal cuando posteriormente se configure una vista neta de IGV; V1 no mezclará ambos conceptos silenciosamente.

El `floor_price` es el menor precio que cumple simultáneamente:

- `minimum_margin_pct`;
- `minimum_contribution_pen`;
- costos/fees vigentes.

## 7. Precio recomendado

El servicio genera candidatos y explica por qué eligió uno.

Reglas base:

1. Nunca recomendar por debajo de `floor_price` salvo estrategia `CLEARANCE`, que debe señalar explícitamente la pérdida/margen excepcional.
2. No bajar precio solo para ser el más barato si ya existe una posición competitiva suficiente.
3. Si `market_min < floor_price`, devolver `NO_COMPETIR_PRECIO` o recomendar revisar costo/proveedor.
4. Si S-TECH está materialmente por debajo del mercado y puede subir sin perder el objetivo de posición, recomendar `SUBIR_PRECIO`.
5. Si no existe listing propio y el score/confianza cumplen umbral, recomendar `PUBLICAR`.
6. El resultado siempre incluye `floor`, `target`, competidores relevantes, margen esperado, score, confianza y razones.

Estrategias iniciales:

- `BALANCED`: equilibrio entre margen y posición competitiva.
- `MARGIN`: maximiza contribución dentro del rango razonable de mercado.
- `VOLUME`: intenta quedar cerca del precio líder sin romper el piso.
- `CLEARANCE`: prioriza salida de inventario; muestra explícitamente cualquier excepción al margen mínimo.

## 8. Opportunity Score y Confidence Score

### 8.1 Opportunity Score (0..100)

Pesos default configurables:

- rentabilidad: 30
- competitividad/precio alcanzable: 20
- disponibilidad de proveedor: 15
- demanda/rotación: 15
- estabilidad/tendencia de mercado: 10
- presión de inventario propio: 10

No se asigna cero a un factor desconocido. Los factores disponibles se normalizan y el resultado se acompaña de Confidence Score.

### 8.2 Confidence Score (0..100)

Considera:

- identidad exacta del producto;
- frescura de costo;
- frescura de precios de competencia;
- cantidad de competidores observados;
- profundidad del histórico;
- disponibilidad/calidad de ventas y rotación;
- porcentaje de inputs observados vs inferidos.

Una recomendación de compra automática futura nunca podrá basarse solo en Opportunity Score.

## 9. Risk Score y eventos

`risk_score` 0..100 combina:

- margen demasiado cercano al piso;
- volatilidad de precio;
- guerra de precios;
- proveedor con poco/no stock;
- caída acelerada del mercado;
- demasiados vendedores;
- datos viejos;
- producto sin rotación / envejecimiento cuando exista ese dato.

Eventos normalizados:

- `PRICE_DROP`, `PRICE_INCREASE`
- `PROMO_STARTED`, `PROMO_ENDED`
- `STOCK_OUT`, `RESTOCKED`
- `SUPPLIER_COST_DROP`, `SUPPLIER_COST_INCREASE`
- `COMPETITOR_ENTERED`, `COMPETITOR_LEFT`
- `PRICE_WAR_SIGNAL`
- `MARGIN_BELOW_FLOOR`
- `MARKET_GAP_FOUND`

## 10. Acciones comerciales

Salida controlada de recomendaciones:

- `COMPRAR`
- `PUBLICAR`
- `SUBIR_STOCK`
- `BAJAR_PRECIO`
- `SUBIR_PRECIO`
- `MANTENER`
- `LIQUIDAR`
- `NO_COMPETIR`
- `REVISAR_PROVEEDOR`
- `INVESTIGAR`

Toda recomendación trae `reason_codes` y valores que la justifican; no solo texto libre.

## 11. Tools MCP V1

### Datos/configuración

- `market_observation_ingest(...)`
- `market_product_match_upsert(...)`
- `market_pricing_policy_get(...)`
- `market_pricing_policy_upsert(...)`
- `market_channel_fee_rule_get(...)`
- `market_channel_fee_rule_upsert(...)`

### Consulta/variaciones

- `market_competitors_get(partnumber, channel=None)`
- `market_price_history(partnumber, channel=None, days=30)`
- `market_variations_get(partnumber, channel=None, windows=[1,7,30,90])`
- `market_data_quality(partnumber, channel=None)`

### Decisión

- `market_profit_simulate(partnumber, channel, sale_price_pen, ...)`
- `market_recommended_price(partnumber, channel, strategy="BALANCED")`
- `market_product_analyze(partnumber, channel=None)`
- `market_risk_analyze(partnumber, channel=None)`
- `market_opportunities_find(channel=None, category=None, limit=30)`
- `market_assortment_gaps(channel=None, category=None, limit=30)`
- `market_supplier_opportunities(supplier=None, category=None, limit=30)`
- `market_channel_opportunities(channel, category=None, limit=30)`
- `market_strategy(channel=None, category=None, budget_pen=None, limit=30)`
- `market_weekly_actions(channel=None, category=None, limit=50)`

Los tools de escritura solo escriben observaciones/mapeos/políticas de inteligencia comercial. Ninguno toca precios o stock operativo.

## 12. Ingesta y fuentes

Market Intelligence no debe depender de un scraper monolítico.

V1 acepta observaciones normalizadas desde:

- históricos existentes de Deltron/DB_DISTRIBUIDORES;
- futuros adapters Ingram/Intcomex;
- APIs oficiales de marketplaces cuando existan y estén autorizadas;
- collectors externos controlados;
- Product Research/Web Research para descubrimiento puntual;
- captura manual auditada.

Cada adapter transforma su fuente al mismo contrato de observación. Esto permite agregar un competidor sin modificar el motor financiero.

## 13. Seguridad y calidad

- límites de `limit`, `days` y ventanas para evitar consultas masivas accidentales;
- SQL parametrizado;
- ningún secreto en respuestas;
- URLs externas se almacenan como evidencia, no se ejecutan desde SQL;
- mappings `PROBABLE/REVIEW` no alimentan pricing automático;
- datos más antiguos que el umbral de frescura degradan Confidence Score;
- valores negativos/imposibles se rechazan en la capa de dominio;
- porcentajes se validan en rango;
- moneda explícita en toda observación;
- auditoría de cambios de políticas.

## 14. Pruebas requeridas

### Dominio

- matemática financiera y redondeos;
- floor price;
- variaciones 1/7/30/90;
- volatilidad;
- score/confidence/risk;
- detección de guerra de precios;
- estrategia de precio recomendado.

### Repository

- ingesta idempotente;
- histórico inmutable;
- resolución de política por especificidad/fecha;
- mappings exactos;
- consultas paginadas y parametrizadas.

### Service

- análisis con datos completos;
- análisis con datos parciales;
- competidor debajo del floor;
- oportunidad alta pero confianza baja;
- proveedor sin stock;
- listing propio demasiado barato/caro.

### MCP

- registro de todos los tools;
- validación de argumentos;
- ninguna tool de análisis modifica tablas operativas.

### Migración

`sql/010_market_intelligence_v1.sql` debe ser aditiva e idempotente.

## 15. Criterios de aceptación V1

Con un PN que tenga costo de proveedor, política de canal y al menos dos observaciones de competencia, STECH MCP debe poder responder en una sola llamada de análisis:

- costo actual y variación;
- mínimo/mediana/máximo de mercado;
- variación 1/7/30/90 disponible;
- posición de precio S-TECH si existe;
- floor price;
- precio recomendado;
- utilidad y margen estimados;
- Opportunity Score;
- Confidence Score;
- Risk Score;
- acción recomendada y razones estructuradas.

Con múltiples PNs debe ordenar oportunidades de mayor a menor score, pero permitir desempatar por confianza, utilidad o riesgo.

## 16. Fuera de alcance de V1

- publicar automáticamente un precio en Falabella/Mercado Libre/VTEX;
- emitir órdenes de compra automáticas;
- inventar demanda cuando no hay datos;
- asumir que publicaciones con títulos parecidos son el mismo producto;
- crawling masivo específico por retailer dentro del core del MCP;
- machine learning opaco sin explicación. V1 usa reglas/fórmulas determinísticas auditables.

## 17. Evolución prevista

Después de V1 pueden añadirse, sin cambiar el contrato principal:

- scheduler/worker periódico de captura;
- alertas automáticas por eventos;
- forecasting de demanda;
- elasticidad de precio;
- recomendación de unidades a comprar;
- optimización de presupuesto por cartera;
- integración aprobada de escritura hacia marketplaces;
- aprendizaje de pesos basado en resultados reales, manteniendo explicabilidad y control.
