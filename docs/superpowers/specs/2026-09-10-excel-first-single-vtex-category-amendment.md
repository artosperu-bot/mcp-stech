# Excel-First V2 — Simplificación de categoría VTEX

**Fecha:** 2026-09-10  
**Aplica a:** `2026-09-10-excel-first-enrichment-workbench-v2-design.md`

## Decisión aprobada

Cada archivo Excel cargado corresponde a **una sola categoría VTEX** para toda la carga.

No se implementará agrupación por categoría, selección por fila ni overrides individuales en esta fase.

## Flujo visible

```text
1. Cargar Excel
2. Reconocer plantilla
3. Resolver Part Numbers
4. Elegir UNA categoría VTEX
5. Analizar faltantes
6. Enriquecer
7. Revisar diferencias
8. Exportar Excel completado
```

## Selector de categoría

Después de cargar y reconocer el Excel, V8 mostrará un único selector de categoría para todo el archivo.

La lista debe provenir del **árbol real de categorías de la cuenta VTEX seleccionada**. No se usará una lista hardcodeada ni se pedirá al usuario memorizar/escribir un `CategoryId` manualmente.

Cada opción debe mostrar como mínimo:

- ruta completa de categoría;
- nombre de categoría;
- `CategoryId` real.

Ejemplo:

```text
Cuenta: COOLBOX (VTEX)

Categoría del archivo:
[ Buscar categoría VTEX... ]

Computación > Laptops > Notebooks   — ID 123
Computación > Laptops > Gaming      — ID 456
```

La categoría elegida se aplica a **todos los Part Numbers del Excel**.

## Categoría textual del Excel

Si el Excel trae un texto de categoría, se usa únicamente como pista para filtrar o preseleccionar una opción del árbol VTEX.

No se transforma automáticamente en `CategoryId` si no existe una coincidencia única y confiable.

## Separación de conceptos

La categoría técnica canónica STECH continúa separada de la categoría de publicación VTEX.

Ejemplo:

```text
Categoría técnica STECH: LAPTOP
Categoría Excel: Laptops
COOLBOX (VTEX): CategoryId 123
S-TECH (VTEX): CategoryId 891
```

La selección de CategoryId pertenece a la sesión/canal de carga y no modifica la categoría técnica maestra del producto.

## Protección de lógica existente

`ENRICH_TECHNICAL` no cambia por sí mismo la categoría de un producto ya publicado en VTEX. La categoría seleccionada se conserva como asignación de la carga y podrá ser utilizada posteriormente por el flujo de preparación/publicación correspondiente.

El flujo técnico sigue sin modificar precio, stock, costo, promociones, activación ni imágenes.

## Criterio de aceptación

Con un Excel de 1, 100 o 1000 filas de la misma categoría, el usuario debe escoger la categoría VTEX **una sola vez** y continuar con todo el lote.