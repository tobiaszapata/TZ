# Guía de uso — paso a paso

Esta guía asume que nunca corriste el proyecto y que no querés tener que
adivinar nada. Va en orden. Si algo no funciona, el problema casi siempre
es uno de los primeros tres pasos.

---

## Parte 1 — Qué necesitás instalar (una sola vez)

**1. Python 3.11 o más nuevo.**
Para saber si ya lo tenés, abrí una terminal y escribí:

```bash
python3 --version
```

Si te dice `Python 3.11.x` o superior, listo. Si dice `command not found`
o una versión más vieja, instalá Python desde python.org (en Windows,
tildá la casilla "Add Python to PATH" durante la instalación).

**2. Nada más es obligatorio para la Fase 1.**
El proyecto está hecho a propósito para correr con lo que viene dentro de
Python, sin instalar librerías externas. La razón está en
`docs/decisiones.md`: mientras esto sea un proceso que corrés vos una vez
al día, no hace falta ni una base de datos que administrar (usamos SQLite,
que es un archivo) ni paquetes de terceros.

**Opcional pero recomendado**: si querés que los tests se vean más
prolijos, `pip install pytest`. No es necesario — hay un runner propio que
no depende de nada.

---

## Parte 2 — Preparar el proyecto (una sola vez)

**1. Descomprimí** el `.zip` en una carpeta cualquiera. Te va a quedar una
carpeta `relevamiento-precios`.

**2. Entrá a esa carpeta desde la terminal:**

```bash
cd ruta/donde/lo/pusiste/relevamiento-precios
```

Todo lo que sigue se corre **desde adentro de esta carpeta**. Es el error
más común: correr los comandos desde otro lado. Si un comando falla con
`No module named ...`, casi seguro estás parado en la carpeta equivocada.

**3. Verificá que todo esté sano corriendo los tests:**

```bash
python3 -m tests._runner
```

Tenés que ver `Total: 25   OK: 25   Fallidos: 0` al final, y en el medio
un par de líneas de "backtest" con números. Ese backtest es la prueba de
que el motor reproduce lo que INDEC publicó — si eso pasa, el corazón del
sistema funciona. Si algo falla acá, no sigas: avisame antes de cargar
datos.

---

## Parte 3 — El relevamiento: de dónde salen los precios

Antes del "cómo se corre", conviene entender **qué está pasando**, porque
es la parte que más se malinterpreta.

**El sistema no entra a ninguna página web a mirar precios.** No hay un
robot que abre supermercados uno por uno. En vez de eso, usa **SEPA**: una
base de datos que la Secretaría de Comercio de la Nación publica todos los
días, con los precios que las propias cadenas están obligadas a reportar.
Es información oficial, agregada y descargable — miles de productos, por
comercio, con código de barras. Es la misma información que un scraper
intentaría juntar sitio por sitio, pero servida en un archivo, sin que
nadie te bloquee ni te limite.

**El flujo diario, entonces, es:**

1. Se **descarga** el archivo del día desde
   `datos.produccion.gob.ar/dataset/sepa-precios`.
   (Este paso hoy lo hacés vos a mano; ver "Sobre la descarga" abajo.)
2. El sistema **lee** ese archivo, se queda solo con los productos que le
   interesan (los de la canasta que estamos midiendo) y **clasifica** cada
   uno en su categoría INDEC (esto lo hace `collectors/sepa/mapeo.py`).
3. Los guarda en la base, **sumándolos** a los de los días anteriores del
   mes — nunca pisando nada.
4. Cuando querés, **consultás** la base para ver cómo viene cada categoría.

**Sobre la descarga (importante y honesto):** el paso 1 todavía es manual.
El archivo de SEPA es un ZIP grande y la forma exacta de descargarlo y
descomprimirlo conviene ajustarla contra el archivo real la primera vez
(está anotado en `collectors/sepa/schema.py`). Una vez que eso esté
resuelto y andando, se automatiza junto con el resto — pero recién cuando
lo hayamos visto funcionar a mano varias veces. El motivo de no
automatizar antes está en `docs/decisiones.md` y es la lección central del
proyecto anterior: automatizar antes de validar da un sistema que produce
números malos solo, todos los días, sin que nadie los mire.

---

## Parte 4 — Cargar un día

Una vez que tenés el archivo del día como CSV (llamémoslo
`sepa_2026-08-16.csv`), lo cargás con **un solo comando**:

```bash
python3 -m scripts.correr_dia --archivo sepa_2026-08-16.csv --fecha 2026-08-16
```

Qué vas a ver: un reporte que te dice cuántas filas leyó, cuántas pudo
clasificar (la "tasa de mapeo") y cuántas quedaron sin clasificar. **Mirá
ese número de "sin mapear" todos los días.** Si un día cae mucho respecto
de los anteriores, es la señal de que cambió el formato del archivo o
aparecieron productos nuevos que las reglas no reconocen — y es
exactamente cuando me tenés que avisar para ajustar el mapeo.

Este comando es **idempotente**: si lo corrés dos veces con el mismo
archivo, no duplica nada. Podés re-correrlo tranquilo.

Repetís esto cada día hábil. Cada día se suma al mes en curso.

---

## Parte 5 — Consultar: cómo viene cada categoría y por qué

Esto es lo que vas a usar para escribir los reportes. No carga ni cambia
nada — solo lee lo que ya está.

**Ver todas las categorías de un vistazo** (mitad de mes contra el mes
cerrado anterior, por ejemplo):

```bash
python3 -m scripts.consultar --resumen --mes 2026-08 --contra 2026-07
```

Te lista cada clase con su variación. De un vistazo ves cuál se está
moviendo.

**Meterte adentro de una categoría** para ver qué productos la explican
—que es exactamente lo que pediste—:

```bash
python3 -m scripts.consultar --clase 01.1.6 --mes 2026-08 --contra 2026-07
```

`01.1.6` es Frutas. Vas a ver algo así:

```
FRUTAS — agosto vs julio: +23.33%

producto               var %   peso*  aporte pp
Banana x kg           +60.0%   33.3%    +20.00
Naranja x kg          +10.0%   33.3%     +3.33
Manzana roja x kg      +0.0%   33.3%     +0.00
```

Se lee así: **Frutas subió 23,33%, y de esos ~23 puntos, 20 los explica la
banana.** La columna "aporte pp" es cuántos puntos de la suba total pone
cada producto, y la suma de esa columna da la variación de la categoría.
Eso te deja decir en un reporte, con respaldo: "la suba de frutas de este
mes es casi toda banana".

Los códigos de cada categoría están en `config/canasta.py`. Los que más
vas a usar:

| código | categoría |
|--------|-----------|
| 01.1.1 | Pan y cereales |
| 01.1.2 | Carnes y derivados |
| 01.1.4 | Leche, productos lácteos y huevos |
| 01.1.6 | Frutas |
| 01.1.7 | Verduras, tubérculos y legumbres |

---

## Parte 6 — Una advertencia sobre la columna "peso"

En el desglose por producto, la columna "peso" **no es el ponderador
oficial de INDEC**. INDEC no publica pesos por debajo de la categoría — no
existe un dato oficial de cuánto pesa la banana dentro de Frutas. Lo que
usamos es una aproximación (cuántas veces aparece cada producto en los
datos). Sirve perfectamente para identificar quién mueve la categoría,
pero no la presentes como si fuera un peso oficial. Está explicado en
detalle en el encabezado de `engine/reporte.py`.

Esto conecta con el objetivo del proyecto: no buscamos clavar el número
nacional (eso es imposible de relevar completo), sino tener cada categoría
bien medida y su dinámica interna, para cruzarla contra lo que te pasa la
otra consultora y saber en cuáles confiar. El desglose por producto es
justamente lo que te da el argumento de por qué una categoría se movió como
se movió.
