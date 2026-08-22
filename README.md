# Relevamiento de Precios — Fase 1

Proxy de inflación argentina de alta frecuencia, con metodología trazable a
INDEC. Este repo es el arranque: **división 01 (Alimentos y bebidas no
alcohólicas), región GBA, fuente SEPA, disparo manual.** No es el sistema
completo — es la base sobre la que se construye el resto, ya validada.

## Empezá acá

Si nunca corriste esto, andá directo a **`docs/guia_de_uso.md`** — es un
paso a paso en prosa, desde "qué instalar" hasta "cómo consultar una
categoría". Lo que sigue es la referencia rápida.

## Qué hace este proyecto

Mide la inflación de categorías del IPC argentino, con el detalle de qué
productos mueven cada categoría, a partir de datos oficiales de precios
(SEPA). El objetivo **no** es clavar el índice general nacional —relevar
todo es inviable— sino tener cada categoría bien medida y su dinámica
interna, para complementar y contrastar contra otras fuentes de
relevamiento.

## Qué está validado hoy y qué no

| Componente | Estado |
|---|---|
| Motor de cálculo (`engine/`) | **Validado.** 20/20 tests, incluido un backtest contra los números que INDEC efectivamente publicó para GBA, julio 2026 (`tests/test_backtest_division01.py`) — ver resultado exacto abajo. |
| Parser e ingesta de SEPA (`collectors/sepa/`) | **Escrito y testeado contra un archivo sintético** que respeta el esquema documentado de Precios Claros/SEPA. **No probado contra un archivo real** — el entorno donde se escribió este código no tiene acceso de red. Ver el aviso en `collectors/sepa/schema.py`. |
| Mapeo producto → clase (`collectors/sepa/mapeo.py`) | Bootstrap por palabra clave, deliberadamente incompleto. Necesita una pasada de curado contra el primer archivo real. |
| Almacenamiento (`storage/`) | **Validado**, SQLite, corrida de punta a punta con datos sintéticos. |

## Instalación

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Correr los tests

```bash
# si tenés pytest instalado (recomendado):
pytest tests/ -v

# si no, el runner sin dependencias que se usó para validar esto:
python3 -m tests._runner
```

## Uso diario (mientras el disparo es manual)

```bash
# 1. Bajar el archivo del día desde
#    datos.produccion.gob.ar/dataset/sepa-precios
# 2. Cargarlo:
python -m scripts.correr_dia --archivo sepa_2026-08-16.csv --fecha 2026-08-16
```

## Consultar (cuando quieras, sin cargar nada)

```bash
# resumen de todas las categorías:
python -m scripts.consultar resumen --mes 2026-08 --contra 2026-07

# una categoría con el desglose de productos que la explican:
python -m scripts.consultar clase --clase 01.1.6 --mes 2026-08 --contra 2026-07

# comparar dos rangos de fechas (p.ej. semana contra semana):
python -m scripts.consultar rango --clase 01.1.6 \
    --desde 2026-08-08 --hasta 2026-08-14 \
    --desde-base 2026-08-01 --hasta-base 2026-08-07

# proyección no-lineal de cierre de mes (piso + rango):
python -m scripts.consultar proyeccion --clase 01.1.6 --mes 2026-08 --contra 2026-07
```

## Reporte visual para no técnicos (HTML sin servidor)

```bash
python -m scripts.generar_html --mes 2026-08 --contra 2026-07
```

Genera `reporte_2026-08.html`: un archivo que se abre con doble clic y
muestra las 12 divisiones del IPC (con su estado de cobertura) y el desglose
de productos de cada categoría medida. Se puede mandar por mail o dejar en
una carpeta compartida. No necesita servidor.

`correr_dia` es el único comando del sistema que carga datos. El día que
esto pase a correrse solo (ver "Gate de automatización" abajo), un workflow
de GitHub Actions va a llamar exactamente a ese comando — no hay una
versión "manual" y otra "automática" del código.

## Cómo iterar sobre esto conmigo

El proyecto está pensado para crecer pidiéndome cosas concretas. Ejemplos
de pedidos que puedo tomar y ejecutar sobre este mismo código:

- "Sumá la categoría Carnes con estas subcategorías" → toco
  `config/canasta.py`, no el motor.
- "El mapeo no reconoce 'zapallitos', arreglalo" → toco
  `collectors/sepa/mapeo.py`.
- "Quiero un collector para tal sitio que SEPA no cubre" → agrego una
  carpeta `collectors/<sitio>/` con la misma estructura que `sepa/`; cae en
  la misma base y pasa por el mismo motor.
- "Armá el reporte mensual en Word/Excel automáticamente" → nueva capa de
  salida sobre `scripts/consultar.py`.

Cada pedido es acotado justamente porque la arquitectura separa las cosas
que cambian seguido (qué se mide, de dónde) de las que no deberían cambiar
(cómo se calcula).

## Estructura

```
config/canasta.py        ← pesos y estructura COICOP (el único lugar con
                            números de ponderador — todo lo demás los
                            recibe como parámetro)
engine/
  index_elemental.py     ← media geométrica, relativos, encadenamiento
  imputacion.py          ← reglas de faltantes de Metodología 32 §7.1
  agregacion.py          ← Laspeyres + incidencia
  arrastre.py            ← piso mensual (extensión propia, no de INDEC)
collectors/sepa/
  schema.py               ← alias de columnas (ajustar acá, no en el parser)
  mapeo.py                ← producto → clase COICOP
  parser.py               ← csv crudo → observaciones tipadas
storage/db.py             ← SQLite append-only, sin endpoints de edición
scripts/
  correr_dia.py           ← entrada única del pipeline (carga un día)
  consultar.py            ← ver variación de categorías y productos (solo lee)
tests/                    ← incluye el backtest contra datos reales de INDEC
docs/
  primera_carga.md        ← EMPEZÁ ACÁ si es tu primera vez cargando datos
  guia_de_uso.md          ← paso a paso general desde cero
  metodologia.md          ← qué fórmula de INDEC implementa cada función
  decisiones.md           ← registro de decisiones y por qué
```

## El resultado del backtest, tal como salió al correrlo

```
[backtest división 01] reconstruido=2.4337%  publicado=2.4%  brecha=0.0337 pp  (cobertura 100%)
[backtest Alimentos, 7/9 clases] reconstruido=2.6425%  publicado=2.5%  brecha=+0.1425 pp  cobertura=96.1%
```

El primer número es el que importa: combinar los dos grupos de división 01
(Alimentos + Bebidas no alcohólicas) con sus pesos reales reproduce el
número que INDEC publicó, con una diferencia de 0,03 puntos explicable
enteramente por redondeo (los insumos que publica INDEC ya vienen
redondeados a un decimal). El segundo muestra, a propósito, el límite de lo
que se puede validar con datos 100% públicos a nivel clase: dos clases
menores (Pescados y mariscos, Otros alimentos — 0,8 pp de peso combinado)
no se publican por separado en los archivos de aperturas, así que ese 96%
de cobertura es el techo real de este tipo de validación, no un error.

## Próximos pasos (fuera del alcance de este entregable)

1. **Correr esto contra el primer archivo real de SEPA** y ajustar
   `ALIAS_COLUMNAS` en `schema.py` según haga falta (probablemente un
   nombre de columna, no una reescritura).
2. **Curar `mapeo.py`** con los EAN reales más frecuentes de cada clase.
3. **Cerrar el mes anterior en la base** para que el piso mensual
   (`engine/arrastre.py`) tenga contra qué compararse — hoy el script
   calcula el promedio parcial pero no la variación, porque no hay un mes
   anterior cerrado todavía.
4. Extender `config/canasta.py` a más clases de división 01
   (`CLASES_SIN_COBERTURA_SEPA`) o a otras divisiones, según el mapa de
   cobertura que armamos en la conversación.
5. **Gate de automatización**: cuando esto corra manualmente sin sorpresas
   durante un par de semanas y el backtest siga cerrando con datos reales
   (no solo con los números ya publicados de INDEC), recién ahí se agrega
   el workflow de GitHub Actions.
