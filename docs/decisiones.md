# Registro de decisiones

Cada decisión de esta lista fue una alternativa entre varias, no la única
opción posible. Se documenta el motivo para que si en seis meses alguien
(incluido vos) se pregunta "¿por qué está armado así?", la respuesta esté
acá y no haya que reconstruirla de memoria.

## Alcance: división 01, GBA, un solo estrato de comercio

**Alternativa descartada**: replicar las 9 divisiones que cubría el
proyecto anterior desde el arranque.

**Por qué no**: reconstruyendo los pesos reales del proyecto anterior
contra los archivos de INDEC, el sistema medía genuinamente ~38% de la
canasta pero le asignaba el peso de ~78% — es decir, cerca de la mitad del
número final salía de una redistribución de pesos sin que quedara declarado
en ningún lado. Empezar angosto y validado es mejor que empezar ancho y
no saber cuánto de lo ancho es real.

**Por qué división 01 específicamente**: es la única división donde (a)
SEPA tiene cobertura razonable, y (b) INDEC publica el detalle hasta nivel
clase en `sh_ipc_aperturas`, con lo cual cada clase se puede validar por
separado, no solo el total.

## SQLite en vez de Postgres/Railway

Ver el docstring de `storage/db.py`. Resumen: hoy es un batch diario de una
persona, no una API 24/7. Postgres+Railway resuelve un problema (servir un
dashboard público) que todavía no existe. Cuando exista, se reevalúa —
migrar de SQLite a Postgres más adelante es un cambio acotado (misma
estructura de tablas, otro driver) precisamente porque `storage/db.py` es
la única capa que sabe qué motor de base hay debajo.

DuckDB queda anotado como la opción natural para cuando la ingesta pase del
recorte de división 01 al dump nacional completo de SEPA (varios GB por
día) — ese volumen sí se beneficia de un motor columnar. No se implementó
ahora porque el entorno donde se escribió este código no tenía forma de
instalarlo ni probarlo, y prefiero entregar algo corrido y verificado a
algo que solo se ve bien en el papel.

## SEPA en vez de scraping de sitios de supermercados uno por uno

Ya lo hablamos en la conversación: SEPA es la fuente oficial y agregada de
lo que el proyecto anterior scrapeaba a mano, sin rate limiting, sin IPs
bloqueadas, con identificador de producto más estable. El costo es que
llega como un archivo de descarga masiva en vez de una API liviana — de ahí
que la arquitectura de `collectors/sepa/` esté pensada como
"archivo del día → parser → mapeo", no como "requests HTTP a N sitios".

## Reglas de palabra clave en vez de un mapeo EAN inventado

Podría haber armado una tabla de EAN → clase con códigos que parecen
reales. No lo hice a propósito: cualquier EAN que yo tipeara acá sería
falso, porque los reales solo se conocen mirando un archivo real de SEPA, y
no tuve forma de descargar uno. Prefiero un mapeo por texto que sabemos que
es aproximado (y que el propio sistema mide con `n_sin_mapear` en cada
corrida) a una tabla que parece precisa pero no lo es. Ver el ejemplo real
de "Zapallitos verdes" sin mapear en el README — quedó así a propósito
para mostrar cómo se ve el sistema fallando de forma visible, que es
preferible a que falle en silencio.

## Sin endpoints de edición / sin "día base"

El proyecto anterior tenía `POST /admin/replace-base-day-division` como
mecanismo permanente para cuando un collector fallaba un día. Achica el
código pero rompe la propiedad más importante de una serie que se va a
usar para escribir reportes: que el dato de la semana pasada no cambie
salvo que cambie el método (y eso se versiona en git, con su porqué). Acá
no hay ningún camino para "pisar" un número — la única forma de corregir
algo es agregar una fila nueva a `precios_raw` y recalcular desde ahí.

## Validación de fuentes: los dos archivos de INDEC coinciden

Antes de confiar en los números que alimentan el backtest, se comprobó
que `sh_ipc_aperturas.xls` y `sh_ipc_08_26.xls` (dos publicaciones
separadas de INDEC) dan exactamente el mismo valor para "Alimentos y
bebidas no alcohólicas", región GBA, julio 2026: 2,4% en ambos. No es un
chequeo exhaustivo pero sí es una señal de que la extracción de datos de
este proyecto no tiene un error de lectura básico (columna corrida, mes
mal alineado, etc.) antes de construir nada encima.

## Las 12 divisiones desde el inicio, con estado de cobertura

**Alternativa descartada**: mostrar solo Alimentos hasta tener las demás
medidas.

**Por qué se cambió**: es más útil y más honesto mostrar las 12 divisiones
que INDEC publica (le resultan familiares a cualquiera que conozca el IPC)
con una etiqueta de estado por cada una: `MEDIDA_SEPA`, `PENDIENTE`,
`NO_SCRAPEABLE`. Así la estructura completa está a la vista desde el día
uno, pero sin fingir que medimos lo que no medimos. Es exactamente la
corrección del error del proyecto anterior: él mostraba números de división
que en realidad eran fracciones; acá cada casilla dice de dónde sale su
número, o admite que está vacía. El costo de agregar las 12 fue trivial
(son datos en `config/canasta.py`), y el motor de cálculo no cambió.

## Proyección de cierre: por qué no-lineal y por qué preliminar

Se pidió una proyección de cómo cierra el mes que no fuera lineal. Se
construyó (`engine/proyeccion.py`) con el enfoque de nowcasting que usan los
bancos centrales: estimar qué fracción de la variación mensual suele estar
realizada a cada altura del mes, por categoría, y escalar la observación
por esa fracción. No es lineal ni asume rendimientos constantes.

Pero se tomaron dos decisiones para no vender lo que no es: (1) la curva
arranca genérica y marcada como preliminar, porque estimarla de verdad
necesita meses de historia diaria que todavía no existen — se calibra sola
cuando los haya, sin tocar el resto; (2) la proyección siempre se reporta
como un rango, con el piso (dato duro) como límite inferior. Un cierre
proyectado sin banda mentiría sobre la incertidumbre real, sobre todo a
principio de mes. Ver docstring del módulo.

## Reporte HTML estático (sin servidor)

Se pidió una forma de que una persona no técnica vea los datos. Se resolvió
con `scripts/generar_html.py`, que produce un `.html` autocontenido que se
abre con doble clic — sin servidor, sin costo. Un servidor solo hace falta
para que se actualice solo sin intervención, y ese es el mismo gate de
automatización del resto del proyecto. El HTML estático que se genera ahora
es el mismo que se serviría en esa etapa: no se tira nada.

## Qué significa "gate de automatización" en concreto

No es una fecha, es una condición. Se pasa a GitHub Actions cuando:
1. El pipeline corrió manualmente contra archivos reales de SEPA sin que
   `tasa_mapeo` caiga de forma inexplicable de un día a otro.
2. Hubo al menos un cierre de mes real comparado contra el dato que INDEC
   termine publicando para ese mismo mes (no contra datos ya publicados
   como el backtest de hoy, sino un backtest "en vivo": corrido antes de
   que salga el dato oficial, y confirmado después).
3. `mapeo.py` tiene EAN fijados para los productos de mayor peso de cada
   clase, no solo reglas de texto.

Hasta que las tres se cumplan, el valor de que una persona mire la salida
todos los días es mayor que el costo de tener que ejecutar un comando.
