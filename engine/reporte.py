"""
Capa de reporte y exploración — construida sobre engine/agregacion.py, no
es una fórmula nueva.

NOTA (nov-2026): el camino de producción usa ahora
`calcular_clase_y_productos_indec` (al final de este archivo), que sigue la
Metodología N°32 apartados 5.1 y 7.1 (media aritmética por negocio, media
GEOMÉTRICA entre artículos y entre productos, imputación que sí cambia el
número). `calcular_clase_y_productos`, descrita abajo, es el cálculo ANTERIOR
y se conserva solo para compararlo (scripts/comparar_metodo.py).

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
    imputacion_con_superior: bool = True  # False si hacia falta usar el agrupamiento superior pero no se pudo calcular (se uso la variacion propia)


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



# ==========================================================================
# CALCULO SEGUN METODOLOGIA N°32 (apartados 5.1 y 7.1) — "metodo INDEC".
#
# Reemplaza a `calcular_clase_y_productos` en el camino de produccion (esa
# funcion queda para poder comparar el metodo anterior contra este).
#
# QUE HACE, PASO A PASO (cada paso cita lo que dice INDEC):
#
#  1. Unidad de observacion: el ARTICULO-NEGOCIO = (producto/EAN, cadena,
#     region). SEPA ya trae un precio diario por cada uno.
#
#  2. Precio del articulo-negocio en el periodo: MEDIA ARITMETICA de los
#     precios positivos observados en el periodo (apartado 5.1, formula 6:
#     "primero se calcula la media aritmetica de los precios positivos
#     observados durante el mes"). SEPA son supermercados, que es justo el
#     caso al que INDEC aplica esa media.
#
#  3. Solo se comparan articulo-negocios presentes en AMBOS periodos
#     (panel). Los que faltan se tratan con el apartado 7.1 (paso 6).
#
#  4. Relativo de un producto = MEDIA GEOMETRICA SIMPLE de los relativos de
#     sus articulo-negocios (apartado 5.1, formula 7: media geometrica "sin
#     ponderaciones" entre informantes).
#
#  5. Relativo de la clase = MEDIA GEOMETRICA de los relativos de los
#     productos, con el peso proxy ya decidido (cantidad de observaciones
#     del producto en el periodo actual). INDEC no publica ponderadores por
#     producto/variedad dentro de una clase de SEPA, asi que ese peso sigue
#     siendo una PROXY, no un ponderador oficial. Esto reemplaza al promedio
#     aritmetico ponderado del metodo anterior: el apartado 5.1 usa media
#     geometrica en el nivel elemental, y la aritmetica (Laspeyres) recien
#     aparece arriba, entre variedades con ponderador de gasto (5.2).
#
#  6. Faltantes (apartado 7.1), medidos sobre articulo-negocios:
#       cobertura > 50%  -> variacion propia
#       20% a 50%        -> mezcla geometrica propia^c x superior^(1-c)
#       < 20%            -> variacion del agrupamiento superior
#     "Superior" = la variacion de las DEMAS clases del mismo grupo
#     (ver engine/consultas.py). Si no se pasa, se usa la propia y queda
#     marcado en `metodo_imputacion` que no se pudo aplicar el superior.
# ==========================================================================

import math as _math

from engine.imputacion import relativo_de_variedad


def _media_aritmetica_positivos(precios: list[float]) -> float | None:
    positivos = [p for p in precios if p > 0]
    return sum(positivos) / len(positivos) if positivos else None


def _media_geometrica_de_cocientes(valores: list[float]) -> float:
    return _math.exp(sum(_math.log(v) for v in valores) / len(valores))


def calcular_clase_y_productos_indec(
    panel_mes: dict[str, dict[tuple, list[float]]],
    panel_mes_anterior: dict[str, dict[tuple, list[float]]],
    nombres: dict[str, str] | None = None,
    variacion_grupo_superior: float | None = None,
) -> tuple[VariacionClase | None, list[ProductoDriver]]:
    """`panel_*` = {ean: {(comercio, region): [precios del periodo]}}.
    Devuelve (variacion de la clase, productos ordenados por incidencia)
    o (None, []) si no hay ningun articulo-negocio en comun."""
    nombres = nombres or {}

    precio_t: dict[str, dict[tuple, float]] = {}
    for ean, por_negocio in panel_mes.items():
        for clave, lista in por_negocio.items():
            m = _media_aritmetica_positivos(lista)
            if m is not None:
                precio_t.setdefault(ean, {})[clave] = m
    precio_0: dict[str, dict[tuple, float]] = {}
    for ean, por_negocio in panel_mes_anterior.items():
        for clave, lista in por_negocio.items():
            m = _media_aritmetica_positivos(lista)
            if m is not None:
                precio_0.setdefault(ean, {})[clave] = m

    pares_base = sum(len(v) for v in precio_0.values())
    comparables: dict[str, list[tuple]] = {}
    for ean in set(precio_t) & set(precio_0):
        comunes = [k for k in precio_t[ean] if k in precio_0[ean]]
        if comunes:
            comparables[ean] = comunes
    pares_validos = sum(len(v) for v in comparables.values())
    if not comparables:
        return None, []

    rel_ean: dict[str, float] = {}
    p_act: dict[str, float] = {}
    p_ant: dict[str, float] = {}
    for ean, claves in comparables.items():
        rel_ean[ean] = _media_geometrica_de_cocientes(
            [precio_t[ean][k] / precio_0[ean][k] for k in claves])
        p_act[ean] = _media_geometrica_de_cocientes([precio_t[ean][k] for k in claves])
        p_ant[ean] = _media_geometrica_de_cocientes([precio_0[ean][k] for k in claves])

    n_obs = {ean: sum(len(l) for l in panel_mes[ean].values()) for ean in comparables}
    total_obs = sum(n_obs.values())
    pesos = {ean: n_obs[ean] / total_obs for ean in comparables}

    S = sum(pesos[e] * _math.log(rel_ean[e]) for e in comparables)   # log del relativo propio
    relativo_propio = _math.exp(S)

    sup = (1 + variacion_grupo_superior / 100) if variacion_grupo_superior is not None else None
    res = relativo_de_variedad(pares_validos, pares_base, relativo_propio, sup)
    c = res.cobertura
    T = _math.log(res.relativo)                      # log del relativo final de la clase
    variacion_final = (res.relativo - 1) * 100

    # Reparto EXACTO de la variacion entre productos (en logaritmos):
    # la suma de las incidencias de los productos propios es la parte de la
    # variacion final que explican; con cobertura > 50% es toda.
    if res.metodo == MetodoImputacion.PROPIO or not res.uso_superior:
        peso_propio_en_T = 1.0
    elif res.metodo == MetodoImputacion.GRUPO_SUPERIOR_PARCIAL:
        peso_propio_en_T = c
    else:
        peso_propio_en_T = 0.0
    factor = (_math.exp(T) - 1) / T if abs(T) > 1e-12 else 1.0

    imputado = res.metodo != MetodoImputacion.PROPIO
    drivers = [
        ProductoDriver(
            ean_o_id=ean,
            nombre_producto=nombres.get(ean, ean),
            n_observaciones_mes=n_obs[ean],
            precio_mes=p_act[ean],
            precio_mes_anterior=p_ant[ean],
            variacion_pct=(rel_ean[ean] - 1) * 100,
            peso_proxy_pct=pesos[ean] * 100,
            incidencia_aproximada_pp=100 * factor * peso_propio_en_T * pesos[ean] * _math.log(rel_ean[ean]),
            es_imputado=False,
        )
        for ean in comparables
    ]

    productos_mes, productos_ant = set(precio_t), set(precio_0)
    faltantes = {e for e in productos_ant if e not in comparables and e not in productos_mes}
    if imputado:
        variacion_faltantes = (sup - 1) * 100 if sup is not None else variacion_final
        for ean in faltantes:
            drivers.append(ProductoDriver(
                ean_o_id=ean,
                nombre_producto=nombres.get(ean, ean) + " (sin dato — imputado)",
                n_observaciones_mes=0,
                precio_mes=float("nan"),
                precio_mes_anterior=float("nan"),
                variacion_pct=variacion_faltantes,
                peso_proxy_pct=0.0,
                incidencia_aproximada_pp=0.0,
                es_imputado=True,
            ))
    drivers.sort(key=lambda d: abs(d.incidencia_aproximada_pp), reverse=True)

    metodo_txt = res.metodo.value if imputado else None
    resultado = VariacionClase(
        clase_codigo="", mes="", mes_anterior="",
        variacion_pct=variacion_final,
        n_productos_comparados=len(comparables),
        n_productos_solo_mes_actual=len({e for e in productos_mes if e not in comparables and e not in productos_ant}),
        n_productos_solo_mes_anterior=len(faltantes),
        cobertura=c,
        metodo_imputacion=metodo_txt,
        imputacion_con_superior=res.uso_superior,
    )
    return resultado, drivers
