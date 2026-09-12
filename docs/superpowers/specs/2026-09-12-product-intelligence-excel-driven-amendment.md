# STECH Product Intelligence V1 — Enmienda Excel-Driven

## Estado

Decisión aprobada conceptualmente por el usuario el 2026-09-12.

Esta enmienda corrige el principio de alcance del diseño `2026-09-12-product-intelligence-excel-v1-design.md`.

La implementación sigue en `feat/product-intelligence-excel-v1` y continúa prohibido mergear hasta prueba local completa en PC020 y confirmación explícita del usuario.

---

## 1. Decisión principal

STECH NO debe investigar "todo lo posible" de cada producto.

La plantilla Excel activa define **qué datos necesita el trabajo actual**.

Product Workspace conserva y reutiliza todo dato confiable que ya exista, pero la investigación nueva se limita a:

1. campos solicitados por la plantilla activa;
2. datos auxiliares estrictamente necesarios para derivar un campo solicitado;
3. identidad mínima necesaria para asegurar que se trabaja con el PN/variante exacta;
4. imágenes necesarias según las columnas o política de imágenes del canal.

No se debe iniciar investigación de campos irrelevantes para la plantilla solo con la intención de construir una ficha maestra exhaustiva.

---

## 2. Principio operativo

```text
PN seleccionado en Monitor / Product Workspace
                 +
        Plantilla Excel activa
                 |
                 v
       Requirement Set dinámico
                 |
                 v
       ¿qué pide este Excel?
                 |
        +--------+---------+
        |                  |
    ya existe            falta
        |                  |
        v                  v
   reutilizar        Deltron primero
                           |
                           v
                    investigación externa
                           |
                           v
                    derivar si aplica
                           |
                           v
                   validar opciones
                           |
                           v
                    completar Excel
```

El Excel manda sobre el **alcance**. Product Workspace manda sobre la **reutilización, validación y trazabilidad**.

---

## 3. Fuente del Part Number

El flujo principal V1 parte de la selección del usuario en la vista de Monitor/Product Workspace.

Ejemplo:

```text
[x] 82YU00XYLM
[x] 83GW005FLD
[x] JBLT530BTBLKAM

[ Completar para plantilla ]
```

Los PN seleccionados son el conjunto de productos objetivo.

El Excel no necesita contener previamente esos PN para actuar como esquema. Puede ser una plantilla vacía del canal.

También se permitirá un modo secundario donde el propio Excel ya tenga uno o más PN/SKU en sus filas y estos se tomen como entrada.

Regla de identidad:

- siempre trabajar con PN/MTM exacto;
- no mezclar variantes;
- si la identidad no es suficiente, crear trabajo de identidad antes de promover datos ambiguos.

---

## 4. Cómo se selecciona la plantilla Excel

V1 debe soportar dos modos simultáneos.

### 4.1 Carpeta de plantillas configurada

PC020 tendrá una carpeta configurable para plantillas, por ejemplo conceptualmente:

```text
C:\STECH\PLANTILLAS\
```

No se fija esa ruta en código; debe ser configuración.

La UI listará los Excel reconocidos de esa carpeta y mostrará información útil:

- nombre de archivo;
- canal detectado;
- categoría detectada;
- fecha/modificación si está disponible;
- cantidad de atributos detectados;
- cantidad de requeridos;
- estado de interpretación de la plantilla.

Este será el modo más rápido para operación diaria.

### 4.2 Selección manual

Debe existir un botón `Seleccionar Excel` / `Usar otra plantilla` para elegir un archivo fuera de la carpeta configurada.

Esto permite probar una plantilla nueva sin moverla antes al repositorio operativo.

### 4.3 Preferencia UX

La UI recomendará la plantilla compatible con la categoría de los PN seleccionados cuando exista una coincidencia clara, pero el usuario puede cambiarla manualmente.

No se debe usar una plantilla equivocada automáticamente solo porque el nombre del archivo parezca similar.

---

## 5. Registro de plantillas

El sistema mantendrá un `Template Registry` derivado de las plantillas inspeccionadas.

Cada plantilla conocida debe poder registrar al menos:

- `template_id` interno;
- archivo/ruta o referencia;
- canal;
- categoría detectada;
- versión/hash del esquema;
- hoja principal;
- atributos y IDs;
- obligatoriedad;
- listas/opciones válidas;
- campos de imagen;
- restricciones de longitud/tipo;
- última inspección.

Si cambia el archivo o su esquema, debe re-inspeccionarse.

No se debe depender solo del nombre del archivo.

---

## 6. Requirement Set dinámico

Al elegir una plantilla, `Template Inspector` construye un conjunto exacto de requisitos.

Cada atributo debe clasificarse como:

```text
TARGET_FIELD
```

Campo pedido directamente por el Excel.

```text
SUPPORT_FIELD
```

Dato no solicitado directamente, pero estrictamente necesario para derivar o validar un `TARGET_FIELD`.

```text
OUT_OF_SCOPE
```

Dato no requerido para este trabajo; no se investiga.

Ejemplo:

```text
TARGET_FIELD: Gama

SUPPORT_FIELD:
- CPU
- GPU
- RAM
- almacenamiento
- pantalla
- precio relativo Deltron si está disponible

OUT_OF_SCOPE:
- certificación que la plantilla no pide y no influye en Gama
```

Los support fields pueden guardarse en Product Workspace para reutilización posterior, pero no amplían automáticamente el scope de investigación.

---

## 7. Reutilización inteligente

Para cada `TARGET_FIELD` y `SUPPORT_FIELD` requerido:

1. consultar Product Workspace;
2. reutilizar el fact si está verificado/vigente;
3. consultar Deltron para el PN exacto;
4. aplicar política de precedencia por campo;
5. crear Product Work solo si sigue faltando o requiere verificación;
6. evitar solicitudes duplicadas activas;
7. persistir toda nueva evidencia aceptada.

Si mañana otro Excel pide el mismo dato, se reutiliza sin investigar de nuevo.

---

## 8. Datos derivados

Un campo solicitado por la plantilla puede ser derivado cuando la fuente no lo publica literalmente.

Ejemplos:

- gama;
- segmento;
- tipo de uso;
- equivalencia a una opción cerrada del canal;
- normalización de valores.

Todo derivado mantiene:

- regla versionada;
- inputs usados;
- explicación;
- confianza;
- timestamp.

No se permite opinión libre de IA como dato final.

---

## 9. Gama

`Gama` solo se calcula si la plantilla actual la solicita o si otra regla requerida depende de ella.

No se investiga Gama de todos los productos por defecto.

La clasificación puede usar facts ya conocidos y, cuando sea útil, precio Deltron ya capturado. ChatGPT no investiga precios web.

La salida al Excel debe respetar exactamente sus opciones válidas.

Ejemplo:

```text
clasificación interna = Media-Alta
opciones Excel = Baja / Media / Alta
salida canal = Media o Alta según regla de mapping versionada
```

---

## 10. Descripción

La descripción se genera solo si la plantilla la solicita.

Debe utilizar:

- facts verificados pedidos por la plantilla;
- facts de soporte ya obtenidos y relevantes;
- otros facts verificados ya existentes que aporten valor real sin contradecir el scope ni inventar datos.

Puede ser larga y rica cuando el canal lo permita, pero nunca se rellena texto por longitud.

Debe respetar límite de caracteres e identidad exacta del PN.

---

## 11. Imágenes

Las imágenes forman parte del mismo flujo de requisitos.

El sistema determina cuántas imágenes necesita la plantilla/canal.

Ejemplo:

```text
Excel solicita Imagen1..Imagen4
        |
        v
¿Product Workspace ya tiene 4 imágenes válidas para PN/variante exacta?
        |
   +----+----+
   |         |
  sí        no
   |         |
reusar   RESEARCH_IMAGES
```

No se investigarán 10 o 12 imágenes si el requisito actual es 4, salvo que una política explícita del canal establezca un buffer adicional.

Se mantiene la política existente de candidatos/validación; investigación no equivale a publicación automática.

---

## 12. Peso de producto vs empaque

Si la plantilla pide peso del producto:

- investigar/usar peso neto factual cuando sea verificable.

Si pide peso de paquete/empaque:

- usar solo evidencia factual confiable;
- no copiar peso neto como peso de paquete;
- no usar estimación como hecho verificado para completar automáticamente.

Si ese campo es obligatorio y no existe evidencia, el canal puede quedar bloqueado aunque otros campos estén listos.

---

## 13. Precio, stock, costo y promociones

Se mantienen fuera de investigación ChatGPT.

Pueden provenir de Deltron/ERP/conectores determinísticos cuando el flujo comercial los necesite.

El precio Deltron existente puede ser input secundario de una derivación como Gama, pero no se busca por web y no se inventa.

---

## 14. Estados de completitud

`LISTO` debe interpretarse dentro del requirement set activo.

Un PN está `LISTO` para esa plantilla cuando:

- todos los `TARGET_FIELD` obligatorios resolubles están completos y válidos;
- derivados requeridos tienen regla reproducible;
- valores de listas pertenecen a las opciones aceptadas;
- no existe conflicto bloqueante;
- identidad mínima necesaria está resuelta;
- imágenes requeridas cumplen la política del canal.

Estados sugeridos del trabajo de plantilla:

- `PENDING`
- `PROCESSING`
- `WAITING_EXTERNAL_RESEARCH`
- `REVIEW_REQUIRED`
- `BLOCKED_REQUIRED_FIELD`
- `BLOCKED_LOGISTICS`
- `LISTO`

No se debe declarar que el producto está "completo universalmente". Está listo respecto del requisito/plantilla actual.

---

## 15. Selecciones de múltiples categorías

Si el usuario selecciona PN de categorías diferentes:

1. agrupar por categoría detectada;
2. intentar encontrar plantilla compatible para cada grupo;
3. procesar grupos con plantilla inequívoca;
4. dejar grupos sin plantilla en `TEMPLATE_REQUIRED`;
5. no mezclar productos de categorías incompatibles en una plantilla sin confirmación explícita.

Para V1 la UI puede recomendar seleccionar productos de una misma categoría para una operación más clara.

---

## 16. Escritura del Excel

La salida debe generarse como una copia nueva; el original no se modifica.

El writer debe:

- conservar hojas;
- estilos;
- fórmulas;
- validaciones;
- opciones;
- encabezados;
- estructura;
- IDs de atributos.

Solo escribe las celdas objetivo.

Nombre de salida sugerido:

```text
<plantilla>_COMPLETADA_<timestamp>.xlsx
```

La convención exacta puede configurarse.

---

## 17. UX objetivo en Monitor / Product Workspace

Flujo recomendado:

```text
Product Workspace

[x] PN1
[x] PN2
[x] PN3

Plantilla:
[ Falabella - Laptops - versión X v ]
[ Seleccionar otro Excel ]

[ ANALIZAR REQUISITOS ]
```

Después del análisis:

```text
PN1
Solicitados: 42
Ya disponibles: 31
Deltron resolvió: 5
Derivables: 2
Investigación pendiente: 3
Bloqueado: peso empaque
Imágenes: 4/4
Estado: PROCESANDO
```

La UI debe permitir revisar el progreso sin que el usuario tenga que lanzar manualmente EAN, técnica e imágenes por separado cuando esas tareas son necesarias para la plantilla activa.

El orquestador crea automáticamente únicamente los trabajos faltantes.

---

## 18. Orquestación automática

Al ejecutar `Completar para plantilla`:

1. tomar PN seleccionados del Monitor/Product Workspace;
2. inspeccionar/resolver plantilla;
3. construir Requirement Set;
4. consultar facts existentes;
5. consultar Deltron;
6. resolver valores directos;
7. calcular support fields necesarios;
8. crear jobs de identidad/técnicos/imágenes solo donde falten;
9. esperar/importar Research Bridge cuando corresponda;
10. ejecutar derivaciones;
11. validar opciones del canal;
12. generar descripción si está solicitada;
13. evaluar readiness;
14. cuando esté listo, generar copia Excel completada.

La operación debe ser persistente: cerrar la pantalla no debe cancelar jobs ya creados.

---

## 19. Aceptación local PC020

La prueba final debe hacerse desde la vista real del Monitor.

Caso mínimo:

1. colocar o seleccionar una plantilla real Falabella/Coolbox;
2. seleccionar uno o más PN reales en Product Workspace;
3. ejecutar `Completar para plantilla`;
4. verificar que se detecten los atributos del Excel;
5. verificar que no se investiguen datos fuera del scope;
6. verificar reutilización de facts existentes;
7. verificar Deltron primero;
8. provocar al menos un faltante técnico real;
9. provocar/verificar un faltante de identidad o imagen si aplica;
10. dejar que Product Work + Research Bridge lo resuelvan;
11. verificar datos derivados solicitados, como Gama, si aplica;
12. verificar descripción si la plantilla la solicita;
13. generar Excel copia;
14. comparar estructura contra original;
15. volver a ejecutar y comprobar idempotencia;
16. no mergear hasta aprobación explícita del usuario.

---

## 20. Decisión final de arquitectura

La fórmula V1 queda:

```text
PLANTILLA = define QUÉ necesito
PRODUCT WORKSPACE = recuerda QUÉ ya sé
DELTRON = primera fuente operativa
PRODUCT WORK = organiza QUÉ falta
CHATGPT BRIDGE = investiga solo faltantes autorizados
DERIVED RULES = calcula lo que la plantilla pide pero una fuente no expresa literalmente
EXCEL WRITER = entrega el resultado sin alterar el original
```

Esta enmienda prevalece sobre cualquier sección del diseño anterior que sugiera investigar una ficha maestra exhaustiva antes de conocer los requisitos del Excel.
