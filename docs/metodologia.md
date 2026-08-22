# Metodología — de la fórmula de INDEC a la función en código

Este documento existe para que cualquiera (vos, tu jefe, la próxima
persona que toque este código) pueda abrir la Metodología N°32 de INDEC en
una ventana y este archivo en la otra, y verificar renglón por renglón que
lo que hicimos es lo que dice el manual — no una interpretación libre.

## Tabla de correspondencia

| Metodología N°32 | Qué dice | Dónde está en código |
|---|---|---|
| §5.1, fórmula 7 | Precio promedio de una variedad = media geométrica simple de los precios de los artículos | `engine/index_elemental.py::media_geometrica` |
| §5.1, fórmula 8 | Combinación de estratos supermercado/tradicional con proporción fija de la ENGHo | **No implementado en fase 1** — ver "Simplificación deliberada" abajo |
| §5.1, fórmula 9 | Relativo = precio promedio del mes / precio promedio del mes anterior | `engine/index_elemental.py::relativo` |
| §5.1, fórmula 10 | Índice elemental = productoria encadenada de relativos | `engine/index_elemental.py::indice_elemental_encadenado` |
| §5.2, fórmula 11 | Índice de una agrupación = suma ponderada de los índices que la componen | `engine/agregacion.py::laspeyres` |
| §5.3, fórmula 13 | El nivel general es la misma fórmula 11 aplicada al nivel más alto | mismo código — no hay una función separada para "nivel general", es un caso particular |
| §6, fórmula 16 | Incidencia de una agrupación sobre el nivel general | `engine/agregacion.py::incidencia` |
| §5.1 + §5.2 (dos etapas) | Desglose de una clase en sus productos: promediar cada producto y combinarlos ponderados | `engine/reporte.py::calcular_clase_y_productos` — con la salvedad de los pesos, ver abajo |
| §6 (texto) | Efecto arrastre: un aumento a fin de mes pesa poco ese mes, pesa todo el mes siguiente | `engine/arrastre.py` — con la extensión propia explicada abajo |
| §7.1 | Imputación de faltantes en tres tramos según cobertura (>50%, 20-50%, <20%) | `engine/imputacion.py::resolver_relativo` |
| §7.2 | Ajustes de calidad ante reemplazo de artículo (cuantificable / no cuantificable) | **No implementado todavía** — solo aplica cuando haya que decidir reemplazos de EAN discontinuados; no es necesario mientras el mapeo sea por clase de producto genérico |

## Simplificación deliberada: un solo estrato de comercio

INDEC combina dos estratos (supermercados y negocios tradicionales) con una
proporción FIJA que sale de la ENGHo — no es la proporción real de ventas
de cada mes, es una constante (fórmula 8). La razón por la que existe esa
fórmula es que INDEC releva los dos estratos por separado con métodos
distintos (visitas físicas a cada uno).

SEPA es, estructuralmente, el estrato "supermercados" — cadenas grandes con
sistema de facturación centralizado. No tenemos (todavía) un panel
equivalente al de comercio tradicional. Fase 1 calcula el índice elemental
usando *solo* las observaciones de SEPA, sin aplicar la fórmula 8, lo cual
equivale a asumir implícitamente que el 100% de la ponderación de compra va
al estrato supermercado. Esto es una fuente de sesgo conocida y declarada,
no escondida: en la Metodología N°32 se ve que en julio de 2017 INDEC
relevaba más de 16.200 negocios tradicionales contra 500 supermercados —
son categorías donde ese sesgo puede pesar más (frutas, verduras, carne,
pan) que en otras (aceites, gaseosas, yerba, envasados en general).

Cuando haya una fuente de precios de comercio tradicional (o una forma de
aproximarlo), la fórmula 8 se agrega en `engine/index_elemental.py` sin
tocar el resto del motor — está pensado para que ese día solo haga falta
sumar una función, no reescribir la agregación.

## La pieza que no es de INDEC: el piso mensual y la proyección

`engine/arrastre.py` (piso) y `engine/proyeccion.py` (proyección no-lineal)
formalizan en fórmulas algo que INDEC no publica como tal. No los presentes
como "la fórmula de INDEC". Son extensiones nuestras:

- **Piso** (`arrastre.py`): variación del mes si los precios se congelan
  hoy. Es aritmética pura, sin supuestos, solo puede quedar corto hacia
  arriba. Es el número más defendible del sistema.
- **Proyección no-lineal** (`proyeccion.py`): estima el cierre del mes
  dividiendo la variación observada por la *fracción de la variación
  mensual que esa categoría suele tener realizada a esta altura del mes*
  (curva de realización intra-mensual). NO es lineal ni asume rendimientos
  constantes. PERO: la curva por defecto es genérica y preliminar hasta que
  haya varios meses cargados para estimarla por categoría — el módulo lo
  declara vía `estado_calibracion`, y la proyección siempre se reporta como
  un rango (banda), nunca como un número pelado. Ver el docstring del
  módulo para el detalle de por qué un modelo malo sería peor que el piso.

## El desglose por producto y los pesos que INDEC no publica

`engine/reporte.py` responde "¿qué producto mueve esta categoría?". El
cálculo de la variación de la categoría en sí es fiel a la metodología (dos
etapas: promediar cada producto, después combinarlos). Pero para combinar
los productos hace falta un peso por producto, y **INDEC no publica
ponderadores por debajo de la categoría** — no existe un dato oficial de
cuánto pesa la banana dentro de Frutas.

Por eso el reporte usa una proxy declarada: la participación de cada
producto en la cantidad de observaciones. El campo se llama
`peso_proxy_pct` y la contribución `incidencia_aproximada_pp`,
deliberadamente, para que nunca se confundan con los ponderadores y la
incidencia oficiales. Sirve muy bien para identificar quién mueve una
categoría; no sirve como afirmación de peso oficial. Es exactamente el tipo
de supuesto que el proyecto anterior tenía escondido y que acá está a la
vista, con nombre propio.

## Lo que el proyecto anterior hacía distinto (y por qué se cambió)

- **Comparaba punta contra punta** (precio de hoy vs. precio del día 1 del
  mes) en vez de promedio de mes contra promedio de mes. Con inflación de
  2-3% mensual, esa diferencia no es ruido — es sistemática. Corregido: el
  motor trabaja siempre sobre precios promedio mensuales (media geométrica
  de todas las observaciones del mes), nunca sobre un solo día.
- **Descartaba productos no matcheados** en vez de imputar. Corregido:
  `engine/imputacion.py` implementa las reglas de umbral de §7.1.
- **Winsorizaba al 15% de forma asimétrica** (solo bajas, nunca subas), lo
  que introduce un piso artificial. Corregido: no hay ningún recorte de
  outliers en el motor — la simetría de la media geométrica de relativos
  (ver docstring de `media_geometrica`) cumple ese rol sin sesgo.
- **El día base del mes era un punto único de falla**, con endpoints para
  parchearlo a mano (`replace-base-day-division`). Corregido: no existe
  ningún endpoint de edición — todo se recalcula desde `precios_raw`, que
  es append-only (ver `storage/db.py`).
