"""
Capa de reporte y exploración — construida sobre engine/agregacion.py, no
es una fórmula nueva.

QUÉ RESUELVE ESTE MÓDULO: la pregunta "¿por qué se movió así una clase?",
mostrando producto por producto.

CÓMO SE CALCULA ACÁ (dos etapas, igual que INDEC hace en dos etapas
artículo→variedad y variedad→clase, fórmulas 7 y 11 de Metodología 32):

  Etapa 1 — por producto: precio promedio del mes = media geométrica de
  todas las observaciones de ESE producto ese mes (no mezclado con otros).

  Etapa 2 — entre productos: la variación de la clase es la combinación
  ponderada (Laspeyres) de la variación de cada producto — reutilizando
  literalmente `engine.agregacion.laspeyres`.

IMPUTACIÓN DE FALTANTES (Metodología N°32, sección 7.1) — CONECTADA:
INDEC nunca descarta un producto solo porque no se pudo relevar en un
período: le IMPUTA un valor, con una regla de tres tramos según cuánta
cobertura hay (ver engine/imputacion.py, ya escrito con esos tres tramos
pero que hasta esta versión NUNCA se llamaba desde ningún lado real —
se agrega acá la conexión real):

  cobertura > 50%  -> se usa solo la variación PROPIA de los productos
                       que sí se relevaron en ambos períodos (esto era
                       lo único que hacía el sistema hasta ahora).
  20% <= cobertura <= 50% -> a los productos que faltan se les imputa
                       la variación del agrupamiento superior (la clase
                       completa, calculada con lo que sí está).
  cobertura < 20%  -> se descartan los pocos productos comunes que hay
                       y toda la clase usa la variación del agrupamiento
                       superior (que debe pasarse desde afuera, ya que
                       "superior a la clase" es el grupo, y ese cálculo
                       no lo hace este módulo).

`cobertura` se mide como: productos comunes entre los dos períodos /
productos vistos en el período anterior (cuántos de los que existían
antes siguen estando ahora — el mismo espíritu que "cantidad de precios
válidos / cantidad exigida" de la fórmula original, adaptado a que acá
no hay un panel fijo de informantes sino productos que aparecen y
desaparecen de la venta).

DOS LÍMITES QUE SIGUEN DECLARADOS, A PROPÓSITO:

1. **El peso no es el oficial de INDEC.** Se usa una PROXY: la
   participación del producto en la cantidad de observaciones de esa
   clase ese mes. Por eso el campo se llama `peso_proxy_pct`, nunca
   "ponderador".

2. **La imputación de tramo medio/bajo usa la variación de LA MISMA
   CLASE** (no la del grupo superior real) cuando no se provee
   explícitamente `variacion_grupo_superior` — es una aproximación
   razonable (la clase es lo más cercano al "agrupamiento inmediato
   superior" de una variedad que tenemos disponible sin pasar
   parámetros adicionales por todo el sistema), documentada así para no
   esconder el supuesto.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.agregacion import laspeyres
from engine.imputacion import MetodoImputacion, resolver_relativo
from engine.index_elemental import media_geometrica


@dataclass
class ProductoDriver:
    ean_o_id: str
    nombre_producto: str
    n_observaciones_mes: int
    precio_mes: float
    precio_mes_anterior: float
    variacion_pct: float
    peso_proxy_pct: float          # participación en las observaciones de la clase, NO peso oficial
    incidencia_aproximada_pp: float  # peso_proxy * variacion — la suma de todas da la variación de la clase
    es_imputado: bool = False      # True si este producto no tenía dato propio y se le imputó (sección 7.1)


@dataclass
class VariacionClase:
    clase_codigo: str
    mes: str
    mes_anterior: str
    variacion_pct: float
    n_productos_comparados: int
    n_productos_solo_mes_actual: int      # aparecieron este mes pero no el anterior -> quedaron afuera
    n_productos_solo_mes_anterior: int    # productos que existían y ya no se ven (candidatos a imputar)
    cobertura: float = 1.0                # productos comunes / productos del período anterior
    metodo_imputacion: str | None = None  # None si no hizo falta imputar nada (cobertura > 50%)


def calcular_clase_y_productos(
    precios_por_producto_mes: dict[str, list[float]],
    precios_por_producto_mes_anterior: dict[str, list[float]],
    nombres: dict[str, str] | None = None,
    variacion_grupo_superior: float | None = None,
) -> tuple[VariacionClase | None, list[ProductoDriver]]:
    """Devuelve (variación de la clase, lista de productos ordenada por
    cuánto explican esa variación). Si no hay productos en común entre
    los dos meses, devuelve (None, []).

    `variacion_grupo_superior`: variación (en %) del agrupamiento
    inmediato superior a esta clase (ver sección 7.1 de la Metodología
    N°32), usada para imputar cuando la cobertura de productos comunes
    es baja. Si no se pasa (None) y hace falta imputar, se usa la
    variación de la propia clase (calculada solo con los productos
    comunes) como aproximación — ver nota en el docstring del módulo."""
    nombres = nombres or {}
    productos_mes = set(precios_por_producto_mes)
    productos_mes_ant = set(precios_por_producto_mes_anterior)
    comunes = productos_mes & productos_mes_ant

    if not comunes:
        return None, []

    precio_actual = {p: media_geometrica(precios_por_producto_mes[p]) for p in comunes}
    precio_anterior = {p: media_geometrica(precios_por_producto_mes_anterior[p]) for p in comunes}
    variacion_pct_por_producto = {
        p: (precio_actual[p] / precio_anterior[p] - 1) * 100 for p in comunes
    }

    total_obs = sum(len(precios_por_producto_mes[p]) for p in comunes)
    pesos_proxy = {p: len(precios_por_producto_mes[p]) / total_obs for p in comunes}

    agregado_propio = laspeyres(variacion_pct_por_producto, pesos_proxy)

    # Cobertura: de los productos que existían en el período anterior,
    # cuántos siguen estando ahora. Es la base para decidir si hace falta
    # imputar (sección 7.1).
    cobertura = len(comunes) / len(productos_mes_ant) if productos_mes_ant else 1.0
    faltantes = productos_mes_ant - productos_mes  # existían antes, ya no se ven

    variacion_superior = (
        variacion_grupo_superior if variacion_grupo_superior is not None
        else agregado_propio.variacion_pct
    )

    resultado_imputacion = resolver_relativo(
        n_precios_validos=len(comunes),
        n_precios_exigidos=len(productos_mes_ant) if productos_mes_ant else len(comunes),
        relativo_propio=agregado_propio.variacion_pct,
        relativo_grupo_superior=variacion_superior,
    )

    drivers = [
        ProductoDriver(
            ean_o_id=p,
            nombre_producto=nombres.get(p, p),
            n_observaciones_mes=len(precios_por_producto_mes[p]),
            precio_mes=precio_actual[p],
            precio_mes_anterior=precio_anterior[p],
            variacion_pct=variacion_pct_por_producto[p],
            peso_proxy_pct=pesos_proxy[p] * 100,
            incidencia_aproximada_pp=pesos_proxy[p] * variacion_pct_por_producto[p],
            es_imputado=False,
        )
        for p in comunes
    ]

    # Productos que existían antes y no se ven más: se listan igual (para
    # que se sepa que existen y quedaron afuera de la venta), marcados
    # como imputados, con la variación resuelta según el tramo de
    # cobertura — NUNCA se los descarta en silencio, a diferencia de
    # antes de esta corrección.
    if resultado_imputacion.metodo != MetodoImputacion.PROPIO:
        for p in faltantes:
            drivers.append(ProductoDriver(
                ean_o_id=p,
                nombre_producto=nombres.get(p, p) + " (sin dato — imputado)",
                n_observaciones_mes=0,
                precio_mes=float("nan"),
                precio_mes_anterior=float("nan"),
                variacion_pct=resultado_imputacion.relativo_a_usar,
                peso_proxy_pct=0.0,
                incidencia_aproximada_pp=0.0,
                es_imputado=True,
            ))

    drivers.sort(key=lambda d: abs(d.incidencia_aproximada_pp), reverse=True)

    variacion_final = (
        agregado_propio.variacion_pct if resultado_imputacion.metodo == MetodoImputacion.PROPIO
        else resultado_imputacion.relativo_a_usar
    )

    resultado = VariacionClase(
        clase_codigo="",  # lo completa quien llama, acá no se conoce
        mes="",
        mes_anterior="",
        variacion_pct=variacion_final,
        n_productos_comparados=len(comunes),
        n_productos_solo_mes_actual=len(productos_mes - productos_mes_ant),
        n_productos_solo_mes_anterior=len(faltantes),
        cobertura=cobertura,
        metodo_imputacion=(
            None if resultado_imputacion.metodo == MetodoImputacion.PROPIO
            else resultado_imputacion.metodo.value
        ),
    )
    return resultado, drivers

