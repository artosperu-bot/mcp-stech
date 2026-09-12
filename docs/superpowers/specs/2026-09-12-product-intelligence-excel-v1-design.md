# STECH Product Intelligence + Excel Enrichment V1 — Diseño

## Estado

Diseño aprobado conceptualmente por el usuario el 2026-09-12. Esta especificación extiende el flujo actual de Product Workspace + Product Work + ChatGPT Research Bridge hacia un motor de enriquecimiento de producto orientado principalmente a tecnología.

La implementación debe mantenerse aislada del PR del Research Bridge. Rama de diseño/implementación: `feat/product-intelligence-excel-v1`.

No mergear esta rama ni el Research Bridge hasta completar pruebas locales en PC020 y confirmación explícita del usuario.

---

## 1. Objetivo

Construir un flujo en el que STECH pueda recibir una plantilla Excel de marketplace o canal comercial, interpretar su estructura sin depender de una categoría hardcodeada, reutilizar datos ya existentes en Product Workspace y Deltron, investigar solo los campos faltantes o insuficientes y completar únicamente valores sustentados.

El sistema debe permitir que el producto quede automáticamente en estado `LISTO` cuando los datos de producto requeridos estén completos y confiables, sin obligar a una revisión manual cuando no exista conflicto.

El objetivo no es que ChatGPT "rellene celdas" libremente. El objetivo es convertir Product Workspace en la fuente maestra de información de producto y tratar cada Excel como una salida/adaptador de canal.

---

## 2. Prioridad funcional

El sistema será genérico para poder interpretar categorías futuras, pero estará optimizado primero para productos tecnológicos:

- laptops y computadores;
- celulares y smartphones rugged;
- monitores;
- proyectores;
- audio y audífonos;
- periféricos;
- accesorios tecnológicos;
- impresoras;
- almacenamiento;
- redes y conectividad;
- componentes;
- productos electrónicos similares.

Las plantillas de sillas, tomacorrientes, pelador de ajo y cesto parrillero entregadas por el usuario se usan como evidencia de que el intérprete no debe depender de una única categoría. No constituyen la prioridad comercial del V1.

---

## 3. Archivos de ejemplo usados para definir el comportamiento

Se tomaron como referencia funcional los archivos proporcionados por el usuario:

- `Ficha_Comercial_Coolbox_COMPLETADA_CARGA2.xlsx`
- `FALABELLA-CELULARES ARMOR(6).xlsx`
- `FALABELLA-PELADOR DE AJO.xlsx`
- `FALABELLA-SILLAS.xlsx`
- `FALABELLA-TOMACORRIENTES_20260217 - blanco.xlsx`
- `CESTO PARRILLERO_v1.xlsx`
- `FALABELLA_PRUEBA_STECH_82YU00XYLM(1)(1)(1).xlsx`

Patrones confirmados en las plantillas Falabella:

- la hoja `Subir plantilla` contiene instrucciones, obligatoriedad, identificadores de atributos y filas de datos;
- la hoja `Categorías` contiene la categoría esperada;
- la hoja `Marcas` contiene valores permitidos de marca;
- la hoja `Opciones` contiene listas de valores admitidos para atributos categóricos;
- los encabezados usan identificadores como `Descripción #53`, `MemoriaRam #1540`, `Peso del paquete #8`, etc.;
- la fila de obligatoriedad puede marcar `( Optional )`;
- la descripción del propio atributo indica semántica, ejemplo y tipo esperado.

Patrones confirmados en Coolbox:

- existe una estructura de campos distinta a Falabella;
- la descripción puede requerir hasta aproximadamente 3000 caracteres;
- el campo `GAMA` usa valores como `Baja`, `Media`, `Alta`;
- existen campos separados para dimensiones/peso de empaque y dimensiones/peso del producto;
- la ficha permite una descripción comercial extensa y técnica.

---

## 4. Principio central: Product Workspace primero, Excel después

El Excel no será la base maestra de conocimiento.

```text
Fuentes verificadas
      |
      v
Product Workspace / Product Master
      |
      +--> Adaptador Falabella --> Excel Falabella
      |
      +--> Adaptador Coolbox ----> Excel Coolbox
      |
      +--> futuro Mercado Libre
      |
      +--> futuro VTEX
      |
      +--> ERP / otros canales
```

Un Part Number exacto debe investigarse una sola vez siempre que la información siga vigente. Si el mismo producto aparece después en otra plantilla, el sistema debe reutilizar los hechos ya verificados y solo resolver diferencias de formato/canal.

---

## 5. Intérprete genérico de plantillas

### 5.1 Objetivo

Eliminar el supuesto actual de que Falabella equivale siempre a laptops. El código existente `falabella_preview.py` usa una lista y categoría hardcodeadas para portátiles; V1 debe evolucionar hacia un esquema leído desde la plantilla.

### 5.2 Descubrimiento de esquema

Para cada Excel, el intérprete debe detectar:

- hoja principal de carga;
- fila de grupos/secciones;
- fila de instrucciones;
- fila de obligatoriedad;
- fila de identificadores/nombres de atributos;
- primera fila de datos;
- hojas auxiliares de categorías, marcas y opciones;
- tipos esperados: texto, número, fecha, URL, lista cerrada;
- restricciones de longitud cuando la plantilla las documente;
- valores permitidos para campos de lista.

El identificador estable del atributo debe priorizar el ID incluido en el encabezado (`#53`, `#1540`, etc.) sobre la posición de columna.

### 5.3 No alterar estructura

Al completar una plantilla:

- no agregar columnas salvo que un modo explícito de auditoría lo pida;
- no cambiar nombres de hojas;
- no cambiar encabezados;
- no eliminar fórmulas;
- no cambiar validaciones;
- no modificar hojas `Opciones`, `Marcas`, `Categorías` salvo requerimiento explícito;
- conservar estilos y estructura original;
- escribir solo en las celdas de datos correspondientes.

---

## 6. Modelo de estados por campo

Cada dato de producto debe poder distinguir entre estado, origen y método.

Estados mínimos:

- `VERIFIED`: hecho sustentado por fuente aceptada;
- `DERIVED`: valor calculado por una regla reproducible;
- `MISSING`: no existe valor;
- `RESEARCH_REQUIRED`: requiere investigación;
- `REVIEW_REQUIRED`: evidencia conflictiva o insuficiente para resolver automáticamente;
- `CONFLICT`: dos fuentes fuertes no conciliadas;
- `NO_VERIFIED_EVIDENCE`: se investigó y no se encontró evidencia suficiente;
- `STALE`: el dato existe pero requiere actualización por antigüedad/política.

Un valor no debe tratarse como confiable solo porque la celda no esté vacía.

---

## 7. Jerarquía de fuentes

### 7.1 Regla general

1. Valor manual bloqueado/confirmado explícitamente por STECH.
2. Deltron como fuente principal operativa cuando el campo exista y sea razonablemente específico al PN.
3. Fabricante o soporte oficial del Part Number/MTM exacto.
4. Distribuidor autorizado o documentación técnica fuerte.
5. Otras fuentes públicas confiables como evidencia secundaria.

### 7.2 Conflictos

No se debe sobrescribir silenciosamente una fuente fuerte con otra.

El sistema tendrá una política configurable por campo/categoría. Ejemplo:

- ciertos campos pueden declarar `DELTRON_AUTHORITATIVE` por decisión comercial de STECH;
- identidad EAN/UPC/GTIN mantiene reglas especiales de checksum y evidencia explícita;
- cuando no exista una política de precedencia explícita, dos fuentes fuertes incompatibles producen `CONFLICT` / `REVIEW_REQUIRED`.

Si una política autorizada indica que Deltron prevalece, el valor puede salir al canal manteniendo una discrepancia registrada para auditoría.

---

## 8. Investigación ChatGPT programada

El Research Bridge ya validado será la vía para investigación externa sin Brave ni OpenAI API key.

### 8.1 Frecuencia

- PC020 / bridge local: ciclo operativo cada 20 minutos (`1200` segundos) o proceso permanente equivalente.
- ChatGPT programado: cada 1 hora, que es la frecuencia mínima soportada actualmente por tareas programadas.
- máximo inicial: 10 requests por ejecución de ChatGPT.

### 8.2 Flujo

```text
Product Work detecta faltante
        |
        v
WAITING_EXTERNAL_RESEARCH
        |
        v
Bridge PC020 exporta request
        |
        v
GitHub research_bridge/requests
        |
        v
ChatGPT programado investiga
        |
        v
GitHub research_bridge/results
        |
        v
Bridge PC020 valida/importa
        |
        v
Product Workspace
```

### 8.3 Regla de verdad

ChatGPT puede investigar y sintetizar evidencia, pero no puede convertir una suposición libre en hecho.

Deben diferenciarse tres clases:

```text
FACTUAL  -> requiere fuente/evidencia
DERIVED  -> requiere regla + inputs verificables
FREE_AI_OPINION -> prohibido como dato de catálogo
```

---

## 9. Datos factuales vs datos derivados

### 9.1 Factuales

Ejemplos:

- marca;
- modelo;
- Part Number;
- EAN/UPC/GTIN;
- CPU;
- GPU;
- RAM;
- almacenamiento;
- pantalla;
- resolución;
- tasa de refresco;
- puertos;
- conectividad;
- batería;
- dimensiones del producto;
- peso neto/producto;
- color;
- sistema operativo;
- cámara;
- garantía cuando esté sustentada;
- contenido de caja;
- certificaciones;
- imágenes y URLs de evidencia.

### 9.2 Derivados

Ejemplos:

- gama;
- segmento de uso;
- orientación del equipo;
- nivel de rendimiento;
- clasificación para un atributo del canal cuando la plantilla exige una opción que no aparece literalmente en la fuente;
- equivalencias normalizadas.

Todo derivado debe guardar:

- `rule_code`;
- `rule_version`;
- inputs usados;
- timestamp;
- confianza;
- explicación breve.

---

## 10. Motor de GAMA y clasificaciones derivadas

### 10.1 Objetivo

No depender de que la fuente diga literalmente `gama media`, `gama alta` o `gama baja`.

La clasificación debe derivarse de características técnicas y, cuando haya información suficiente, del precio relativo de Deltron dentro de su categoría/comparables.

### 10.2 No usar una sola regla para todo

Las reglas serán por familia tecnológica.

Ejemplos:

#### Laptops

Señales posibles:

- familia/generación/rendimiento de CPU;
- GPU integrada vs dedicada y nivel de GPU;
- RAM;
- almacenamiento;
- calidad/resolución/frecuencia de pantalla;
- construcción/serie comercial cuando sea verificable;
- antigüedad de plataforma;
- precio relativo Deltron como señal secundaria.

#### Smartphones

- SoC/chipset;
- RAM;
- almacenamiento;
- calidad de pantalla;
- cámaras;
- conectividad 4G/5G;
- batería/carga;
- resistencia/certificaciones cuando sean relevantes;
- precio relativo Deltron como señal secundaria.

#### Monitores

- tamaño;
- resolución;
- tipo de panel;
- frecuencia;
- tiempo de respuesta;
- HDR;
- conectividad;
- precio relativo.

Otras familias seguirán el mismo patrón mediante reglas configurables.

### 10.3 Valores de salida

El motor interno podrá producir una clasificación más rica si se necesita, pero el adaptador del canal debe mapear al vocabulario permitido por la plantilla.

Para Coolbox V1, `GAMA` se mapeará a:

- `Baja`
- `Media`
- `Alta`

Si una futura plantilla ofrece otras opciones, el adaptador debe usar exactamente las opciones de esa plantilla.

### 10.4 Precio

ChatGPT no investiga precio web para clasificar gama.

Solo puede usarse como señal el precio ya capturado por un conector/tabla confiable (por ejemplo Deltron). El precio nunca será el único criterio de gama.

---

## 11. Motor de descripciones

### 11.1 Objetivo

Generar descripciones extensas, útiles, comerciales y técnicamente sólidas como las presentes en los ejemplos entregados, evitando texto vacío o relleno.

### 11.2 Reglas

Una descripción debe:

- corresponder al Part Number exacto;
- empezar explicando qué producto es y para qué tipo de uso resulta apropiado;
- incluir las características más relevantes de la categoría;
- separar bloques temáticos cuando la longitud lo justifique;
- explicar beneficios únicamente cuando se desprendan de las características verificadas;
- evitar superlativos no sustentados como `el mejor`, `profesional` o `ultrapotente` si no hay base objetiva;
- mencionar explícitamente limitaciones importantes, por ejemplo `sin sistema operativo`, cuando apliquen;
- no mezclar especificaciones de otra variante;
- no inventar expansión, accesorios, garantía, autonomía o compatibilidad;
- respetar el límite de caracteres del canal;
- evitar repetir la misma característica varias veces solo para alargar el texto.

### 11.3 Estructura recomendada para tecnología

Cuando el canal permita una descripción larga:

1. introducción y posicionamiento de uso;
2. rendimiento y memoria;
3. pantalla/experiencia visual;
4. gráficos o cámaras según categoría;
5. conectividad y puertos;
6. seguridad/teclado/herramientas si aplica;
7. batería/dimensiones/peso neto;
8. sistema operativo y contenido relevante;
9. cierre breve vinculado al uso real.

El target de Coolbox puede acercarse a 3000 caracteres cuando exista información suficiente. No se debe forzar 3000 caracteres si los hechos disponibles no lo justifican.

Falabella debe recibir una descripción rica pero adaptada a su límite y estructura real.

### 11.4 Identidad al final

Cuando el canal/plantilla lo permita y no genere duplicación perjudicial, puede incluirse al final:

- modelo;
- Part Number;
- EAN/UPC/GTIN.

---

## 12. Peso y empaque

### 12.1 Peso neto/producto

Sí forma parte del enriquecimiento automático cuando existe evidencia confiable.

Debe distinguirse claramente de peso bruto/empaque.

### 12.2 Peso/dimensiones de empaque

Quedan fuera del completado automático V1 salvo que exista un dato factual confiable de fuente aceptada.

No se deben rellenar automáticamente usando estimaciones solo para lograr `LISTO`.

El código existente posee reglas de estimación de empaque para laptops; esas estimaciones deben quedar en un modo logístico separado y no considerarse hechos verificados de producto.

### 12.3 Separar estados de producto y canal

Un producto puede estar:

```text
PRODUCT_DATA_STATUS = LISTO
CHANNEL_EXPORT_STATUS = BLOCKED_LOGISTICS
```

si toda su ficha técnica está completa pero Falabella exige peso/dimensiones de paquete todavía no resueltos.

Esto evita que la falta de empaque impida considerar terminada la investigación de producto.

---

## 13. Precio, stock, costo y promociones

### 13.1 Fuera de investigación ChatGPT

ChatGPT no debe investigar ni rellenar:

- stock;
- precio de venta;
- costo;
- promociones;
- fechas promocionales.

### 13.2 Futuro motor comercial

Estos datos se automatizarán posteriormente por una vía determinística:

```text
Deltron / distribuidores / ERP
        |
        v
API / scraper / SQL
        |
        v
precio + stock + timestamp + almacén
        |
        v
reglas comerciales ERP
        |
        v
canales
```

El diseño V1 debe evitar acoplar Product Intelligence a esa futura implementación.

---

## 14. Lógica de completado de Excel

Por cada fila/producto:

1. resolver Part Number/SKU exacto;
2. cargar Product Workspace;
3. cargar facts Deltron disponibles;
4. mapear hechos conocidos al esquema de la plantilla;
5. detectar campos faltantes, incompletos o inválidos;
6. generar Product Work solo para esos faltantes;
7. importar nueva evidencia;
8. ejecutar normalización y derivaciones;
9. validar valores categóricos contra `Opciones`/listas del template;
10. escribir solo valores aceptados en el Excel;
11. preservar todo valor existente confirmado que no deba ser reemplazado;
12. calcular estado de producto y estado de exportación por canal.

---

## 15. Validación de opciones del canal

Si una plantilla define lista cerrada, el resultado debe coincidir exactamente con un valor permitido.

Ejemplo conceptual:

```text
Fuente: "notebook convencional"
Opciones Falabella:
- 2 en 1
- Macbook
- Laptop
- Laptop Gamer

Salida válida: Laptop
```

La normalización debe estar sustentada por una regla de mapeo; no por coincidencia libre de texto.

Si no hay una opción defendible, no escribir el valor y marcar `REVIEW_REQUIRED` para ese campo.

---

## 16. Estado automático LISTO

El usuario aprobó que `LISTO` sea automático.

### 16.1 `PRODUCT_DATA_STATUS = LISTO`

Se asigna cuando:

- todos los campos de producto obligatorios definidos por la política interna/categoría están completos;
- los valores factuales usados son `VERIFIED` o existe una política explícita de fuente;
- los valores derivados tienen regla versionada;
- no hay conflicto bloqueante abierto;
- identidad requerida es válida;
- no existe faltante crítico de producto.

Los campos de precio/stock no forman parte de este estado.

Los campos logísticos de paquete tampoco bloquean `PRODUCT_DATA_STATUS` cuando se hayan declarado fuera del V1.

### 16.2 Estado de canal

Separado de `LISTO` de producto:

- `READY`
- `BLOCKED_REQUIRED_FIELD`
- `BLOCKED_LOGISTICS`
- `BLOCKED_IDENTITY`
- `BLOCKED_IMAGES`
- `REVIEW_REQUIRED`

De esta manera un producto puede estar técnicamente `LISTO` pero todavía no exportable a un marketplace concreto.

---

## 17. Auditoría y trazabilidad

Cada valor promovido debe permitir responder:

- ¿de dónde salió?;
- ¿cuándo se verificó?;
- ¿era factual o derivado?;
- ¿qué regla se usó?;
- ¿qué fuente ganó si hubo discrepancia?;
- ¿qué valor estaba antes?;
- ¿qué Excel/canal lo consumió?

Para datos derivados, ejemplo conceptual:

```text
field: gama
value: Media
method: DERIVED
rule_code: LAPTOP_GAMA_V1
rule_version: 1
confidence: 0.86
inputs:
  cpu: AMD Ryzen 5 7520U
  ram_gb: 16
  storage_gb: 512
  gpu: Radeon 610M
  price_source: DELTRON
explanation: "CPU/RAM/SSD de nivel medio; GPU integrada limita clasificación alta"
```

---

## 18. Idempotencia

El mismo producto/template no debe generar investigación duplicada innecesaria.

- si el fact ya está verificado y vigente, reutilizarlo;
- si un request ya está activo, no crear otro igual;
- si un result ya fue importado, no duplicar candidatos;
- si el Excel se procesa otra vez sin cambios, la salida debe ser estable;
- un cambio de template puede requerir nuevo mapeo, pero no nueva investigación de todos los facts.

---

## 19. Arquitectura propuesta

```text
                    +-------------------+
Excel entrada ----->| Template Inspector |
                    +---------+---------+
                              |
                              v
                    +--------------------+
                    | Channel Schema     |
                    | attributes/options |
                    +---------+----------+
                              |
                              v
+---------+      +------------+-------------+      +----------------+
| Deltron |----->| Product Intelligence     |<-----| Product Workspace|
+---------+      | Resolver                 |      +----------------+
                 +------------+-------------+
                              |
                       faltantes reales
                              |
                              v
                    +--------------------+
                    | Product Work       |
                    +---------+----------+
                              |
                              v
                    +--------------------+
                    | ChatGPT Bridge     |
                    +---------+----------+
                              |
                              v
                    +--------------------+
                    | Fact Validation    |
                    +---------+----------+
                              |
                              v
                    +--------------------+
                    | Derived Rules      |
                    | gama/mapeos/etc.   |
                    +---------+----------+
                              |
                              v
                    +--------------------+
                    | Channel Adapter    |
                    +---------+----------+
                              |
                              v
                      Excel completado
```

---

## 20. Componentes propuestos

Nombres orientativos, no contrato final de archivos hasta elaborar el plan:

- `template_inspector`: descubre estructura y restricciones del Excel;
- `channel_schema`: representación normalizada de campos/opciones;
- `product_fact_resolver`: combina Product Workspace + Deltron + evidencia;
- `derived_rules`: reglas versionadas por categoría;
- `description_builder`: descripción extensa basada solo en facts aprobados;
- `channel_value_mapper`: adapta hechos a opciones exactas del canal;
- `excel_writer`: escribe sin romper formato/estructura;
- `readiness_evaluator`: calcula `LISTO` de producto y readiness de canal.

Se deben reutilizar los servicios existentes (`deltron_fact_adapter`, fact candidates/promotion, Product Work, Research Bridge) en lugar de duplicarlos.

---

## 21. Migración desde código actual

### 21.1 `falabella_preview.py`

Actualmente está acoplado a portátiles mediante:

- `TEMPLATE_NAME` fijo;
- `CATEGORY_VALUE` fijo;
- `FALABELLA_FIELDS` fijo;
- `_REQUIRED_FIELDS` fijo.

V1 debe mantener compatibilidad con la salida actual de laptops mientras introduce un camino genérico basado en el esquema leído del Excel.

### 21.2 `coolbox_preview.py`

Actualmente contiene reglas útiles de normalización, título, enriquecimientos y descripción, pero también:

- una función de gama basada principalmente en familia de CPU;
- estimaciones logísticas de empaque.

V1 debe:

- sustituir la gama simplificada por motor derivado versionado;
- mantener el título y mapeos reutilizables;
- separar estimaciones de empaque del estado factual del producto;
- evolucionar la descripción hacia un builder basado en facts aprobados.

---

## 22. Criterios de calidad de descripción

Una descripción se considera aceptable si:

1. corresponde al PN exacto;
2. no incluye hechos no aprobados;
3. no mezcla variantes;
4. explica uso y características sin exageración;
5. incluye los datos relevantes de la categoría;
6. mantiene buena lectura comercial;
7. respeta el límite del canal;
8. no repite frases genéricas para completar longitud;
9. las limitaciones importantes aparecen visibles;
10. puede regenerarse determinísticamente desde el mismo conjunto de facts.

---

## 23. Pruebas obligatorias

### 23.1 Template Inspector

- detectar hojas Falabella;
- detectar columnas por ID aunque cambie posición;
- detectar obligatoriedad;
- leer categoría;
- leer opciones;
- leer marcas;
- detectar tipo de campo;
- preservar libro sin modificar estructura.

### 23.2 Tecnología prioritaria

Fixtures mínimas:

- laptop Lenovo del ejemplo;
- smartphone Ulefone del ejemplo;
- al menos una plantilla no laptop para probar genericidad.

### 23.3 Gama derivada

- laptop entrada -> `Baja`;
- laptop media -> `Media`;
- laptop gaming/alto rendimiento -> `Alta`;
- precio alto no debe convertir por sí solo un equipo débil en `Alta`;
- inputs insuficientes -> no inventar clasificación o usar regla de fallback explícita.

### 23.4 Descripciones

- incluir PN correcto;
- incluir especificaciones verificadas;
- omitir atributos sin evidencia;
- respetar límite;
- reflejar `sin sistema operativo` cuando aplique;
- no mezclar datos de otra variante;
- estabilidad/idempotencia con mismos inputs.

### 23.5 Excel

- solo modificar celdas de datos;
- preservar hojas auxiliares;
- preservar encabezados;
- preservar fórmulas y formatos relevantes;
- validar valores de lista;
- no completar precio/stock mediante investigación;
- no completar empaque estimado como factual.

### 23.6 Readiness

- `PRODUCT_DATA_STATUS=LISTO` sin depender de stock/precio;
- `LISTO` puede coexistir con `BLOCKED_LOGISTICS` del canal;
- conflicto fuerte bloquea auto-listo salvo política explícita de precedencia;
- derivados con regla válida sí pueden formar parte de `LISTO`.

### 23.7 Research Bridge

- request solo por campos realmente faltantes;
- no reinvestigar facts ya vigentes;
- importación idempotente;
- fallo Git/web temporal no significa dato inexistente.

---

## 24. Aceptación V1 en PC020

La aceptación debe usar al menos un Excel real aportado por el usuario.

Flujo objetivo:

1. cargar Excel;
2. detectar automáticamente categoría/esquema;
3. identificar PN;
4. cargar facts Deltron/Product Workspace;
5. detectar faltantes;
6. generar Product Work para faltantes;
7. dejar que el bridge y ChatGPT resuelvan al menos un faltante real;
8. importar resultado;
9. ejecutar derivaciones;
10. generar descripción;
11. escribir Excel completado;
12. comprobar que precio/stock no fueron inventados;
13. comprobar que empaque estimado no fue tratado como factual;
14. comprobar que el libro conserva estructura;
15. volver a procesarlo y comprobar idempotencia.

No mergear hasta completar la prueba local y recibir confirmación explícita del usuario.

---

## 25. Fases sugeridas de implementación

### Fase A — Esquema genérico de Excel

- inspector;
- modelo normalizado;
- lectura de opciones/categorías;
- pruebas con los Excels suministrados.

### Fase B — Resolver de facts

- reutilización Product Workspace;
- Deltron primero;
- gap analysis por campo;
- Product Work solo para faltantes.

### Fase C — Derivaciones

- motor de reglas versionado;
- primera regla real de gama para laptops;
- normalizadores de opciones del canal.

### Fase D — Descripciones

- builder por categoría;
- laptop y smartphone primero;
- reglas de longitud y evidencia.

### Fase E — Escritura Excel + readiness

- completar celdas;
- `PRODUCT_DATA_STATUS`;
- channel readiness separado;
- idempotencia.

### Fase F — Operación desatendida

- bridge PC020 cada 20 minutos;
- ChatGPT horario;
- heartbeat;
- pendientes antiguos;
- métricas básicas de cola.

---

## 26. Fuera de alcance V1

- publicación automática de precio;
- publicación automática de stock;
- cálculo automático de costo;
- promociones;
- sustitución del ERP;
- publicación automática de imágenes candidatas sin las políticas existentes;
- rellenar campos con opiniones libres de IA;
- automatización definitiva de empaque estimado;
- scraping masivo adicional que no sea necesario para los facts faltantes.

---

## 27. Resultado esperado

El usuario podrá entregar una plantilla nueva de una categoría tecnológica y el sistema deberá poder:

```text
entender la plantilla
      ↓
reutilizar datos existentes
      ↓
usar Deltron primero
      ↓
investigar solo lo faltante
      ↓
validar hechos
      ↓
derivar lo que corresponda mediante reglas
      ↓
generar descripción rica y factual
      ↓
llenar solo datos sustentados
      ↓
marcar producto LISTO automáticamente
      ↓
señalar aparte cualquier bloqueo del canal
```

La meta de confiabilidad es que "LISTO" signifique que STECH puede explicar de dónde salió cada dato y por qué cualquier dato derivado fue clasificado de esa manera.