"""
Imputación de faltantes — Metodología N°32, sección 7.1.

ESTO ES LO QUE REEMPLAZA AL "matched products" DEL PROYECTO ANTERIOR.

El sistema de tu amigo solo comparaba productos que aparecían en AMBAS
fechas (día base y hoy) y descartaba el resto. Eso suena razonable pero no
es lo que hace INDEC, y la diferencia importa: descartar sesga la muestra
hacia los productos que sobrevivieron sin cambios, que no son una muestra
aleatoria de la canasta (los que desaparecen suelen ser justamente los que
tuvieron un salto de precio o un problema de stock).

INDEC nunca descarta. Metodología 32 es textual: "a priori, no se excluye
ningún precio relevado". Cuando falta un precio, se IMPUTA, con una regla
de tres tramos según cuánta cobertura hay:

  cobertura > 50%  -> se usa la variación PROPIA de los precios que sí
                       se relevaron dentro de la misma variedad.
  20% <= cobertura <= 50% -> se imputa con la variación del agrupamiento
                       inmediato SUPERIOR (la clase, si es la variedad la
                       que falta; el grupo, si es la clase).
  cobertura < 20%  -> se descartan los pocos precios que hay y se aplica
                       al valor del mes anterior la variación del
                       agrupamiento superior completo.

En los tres casos el producto sigue "adentro" del índice — lo que cambia
es de dónde sale su variación ese mes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MetodoImputacion(str, Enum):
    PROPIO = "propio"                       # cobertura > 50%
    GRUPO_SUPERIOR_PARCIAL = "grupo_superior_parcial"  # 20% <= cobertura <= 50%
    GRUPO_SUPERIOR_TOTAL = "grupo_superior_total"      # cobertura < 20%


@dataclass
class ResultadoImputacion:
    relativo_a_usar: float
    metodo: MetodoImputacion
    cobertura: float


def resolver_relativo(
    n_precios_validos: int,
    n_precios_exigidos: int,
    relativo_propio: float | None,
    relativo_grupo_superior: float,
) -> ResultadoImputacion:
    """Decide qué relativo usar para una variedad en un mes dado.

    `n_precios_exigidos` es el tamaño de panel esperado para esa variedad
    (cuántos comercios/artículos debería haber, según el diseño muestral).
    `relativo_propio` puede ser None si la cobertura es tan baja que ni
    siquiera tiene sentido calcularlo.
    """
    if n_precios_exigidos <= 0:
        raise ValueError("n_precios_exigidos debe ser positivo")

    cobertura = n_precios_validos / n_precios_exigidos

    if cobertura > 0.5:
        if relativo_propio is None:
            raise ValueError("cobertura >50% pero no se pasó relativo_propio")
        return ResultadoImputacion(relativo_propio, MetodoImputacion.PROPIO, cobertura)

    if cobertura >= 0.2:
        return ResultadoImputacion(
            relativo_grupo_superior, MetodoImputacion.GRUPO_SUPERIOR_PARCIAL, cobertura
        )

    return ResultadoImputacion(
        relativo_grupo_superior, MetodoImputacion.GRUPO_SUPERIOR_TOTAL, cobertura
    )
