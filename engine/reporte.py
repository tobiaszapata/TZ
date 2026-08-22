"""
Capa de reporte y exploración — construida sobre engine/agregacion.py, no
es una fórmula nueva.

QUÉ RESUELVE ESTE MÓDULO: la pregunta "¿por qué se movió así una clase?",
mostrando producto por producto. Antes de este módulo, `precios_de_clase_en_mes`
mezclaba todos los precios de una clase en una sola bolsa (banana y manzana
juntas) para calcular un promedio — lo cual funciona para tener un número
de referencia, pero no permite explicar nada, y además le da más peso
implícito al producto que más veces se haya observado, no al que más pesa
en el consumo. Ver el comentario en storage/db.py::precios_de_clase_en_mes.

CÓMO SE CALCULA ACÁ (dos etapas, igual que INDEC hace en dos etapas
artículo→variedad y variedad→clase, fórmulas 7 y 11 de Metodología 32):

  Etapa 1 — por producto: precio promedio del mes = media geométrica de
  todas las observaciones de ESE producto ese mes (no mezclado con otros).

  Etapa 2 — entre productos: la variación de la clase es la combinación
  ponderada (Laspeyres) de la variación de cada producto — reutilizando
  literalmente `engine.agregacion.laspeyres`, el mismo código que agrega
  clases en división. Es la misma operación en otra escala, no una nueva.

DOS LÍMITES DECLARADOS, A PROPÓSITO, PARA NO REPETIR EL ERROR DEL PROYECTO
ANTERIOR DE ESCONDER LOS SUPUESTOS:

1. **El peso no es el oficial de INDEC.** INDEC no publica ponderadores
   por debajo de clase — no existe un "peso oficial" de la banana dentro
   de Frutas. Acá se usa una PROXY: la participación del producto en la
   cantidad de observaciones de esa clase ese mes (cuántas veces aparece
   en el archivo, no cuánto se consume). Por eso el campo se llama
   `peso_proxy_pct`, nunca "ponderador", y la incidencia se llama
   `incidencia_aproximada_pp`, nunca "incidencia" a secas — para que
   nadie la confunda con la fórmula 16 real.

2. **Solo entran productos presentes en los dos meses que se comparan.**
   Es una simplificación deliberada de esta capa de diagnóstico —no del
   índice oficial de la clase, que sigue existiendo aparte y no tiene este
   problema. Un producto que aparece en un solo mes no entra en este
   desglose. Esto es, a chica escala, el mismo problema de "matched
   products" que le criticamos al proyecto anterior — la diferencia es
   que acá es una vista exploratoria adicional, no el número que se
   publica como oficial.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.agregacion import laspeyres
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


@dataclass
class VariacionClase:
    clase_codigo: str
    mes: str
    mes_anterior: str
    variacion_pct: float
    n_productos_comparados: int
    n_productos_solo_mes_actual: int      # aparecieron este mes pero no el anterior -> quedaron afuera
    n_productos_solo_mes_anterior: int    # el espejo


def calcular_clase_y_productos(
    precios_por_producto_mes: dict[str, list[float]],
    precios_por_producto_mes_anterior: dict[str, list[float]],
    nombres: dict[str, str] | None = None,
) -> tuple[VariacionClase | None, list[ProductoDriver]]:
    """Devuelve (variación de la clase, lista de productos ordenada por
    cuánto explican esa variación — mayor incidencia aproximada primero,
    en valor absoluto). Si no hay productos en común entre los dos meses,
    devuelve (None, [])."""
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

    agregado = laspeyres(variacion_pct_por_producto, pesos_proxy)

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
        )
        for p in comunes
    ]
    drivers.sort(key=lambda d: abs(d.incidencia_aproximada_pp), reverse=True)

    resultado = VariacionClase(
        clase_codigo="",  # lo completa quien llama, acá no se conoce
        mes="",
        mes_anterior="",
        variacion_pct=agregado.variacion_pct,
        n_productos_comparados=len(comunes),
        n_productos_solo_mes_actual=len(productos_mes - productos_mes_ant),
        n_productos_solo_mes_anterior=len(productos_mes_ant - productos_mes),
    )
    return resultado, drivers
