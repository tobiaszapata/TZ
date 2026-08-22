"""
Agregación Laspeyres e incidencia — Metodología N°32, secciones 5.2 y 6.

Todo nivel por encima del índice elemental (clase, grupo, división, nivel
general) se calcula IGUAL: suma ponderada de los índices de nivel inferior
que lo componen (fórmula 11). No hay una fórmula distinta para "el índice
general" — el nivel general es, matemáticamente, la misma agregación
aplicada al nivel más alto (fórmula 13).

Esto es deliberado en el diseño de este módulo: una sola función,
`laspeyres`, sirve para agregar clases en un grupo, grupos en una división,
o divisiones en el nivel general. Si mañana agregamos otra división,
no se toca este archivo.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ResultadoAgregacion:
    variacion_pct: float
    peso_cubierto: float       # suma de los pesos de los componentes con dato
    peso_total_esperado: float  # suma de los pesos que DEBERÍAN estar (según canasta)
    cobertura: float            # peso_cubierto / peso_total_esperado


def laspeyres(
    variaciones_pct: dict[str, float],
    pesos: dict[str, float],
) -> ResultadoAgregacion:
    """Suma ponderada de variaciones porcentuales (fórmula 11, expresada en
    tasas en vez de índices — son equivalentes, ver fórmula de Laspeyres
    equivalente en el glosario de Metodología 32).

    IMPORTANTE — manejo de cobertura parcial:
    Si `pesos` tiene componentes que no aparecen en `variaciones_pct` (p.ej.
    "Pescados y mariscos" cuando todavía no lo medimos), esos componentes
    NO se asumen en cero ni se ignoran silenciosamente: se excluyen del
    cálculo y se reporta `cobertura` para que quede explícito cuánto peso
    de la canasta está realmente representado en el número. Un índice con
    cobertura del 85% y un índice con cobertura del 40% no son igual de
    confiables aunque den el mismo número — por eso este dato viaja
    siempre junto con el resultado, nunca se descarta.
    """
    peso_total_esperado = sum(pesos.values())
    codigos_con_dato = set(variaciones_pct) & set(pesos)
    peso_cubierto = sum(pesos[c] for c in codigos_con_dato)

    if peso_cubierto == 0:
        raise ValueError("ningún componente con peso tiene variación — no hay nada que agregar")

    numerador = sum(pesos[c] * variaciones_pct[c] for c in codigos_con_dato)
    variacion = numerador / peso_cubierto

    return ResultadoAgregacion(
        variacion_pct=variacion,
        peso_cubierto=peso_cubierto,
        peso_total_esperado=peso_total_esperado,
        cobertura=peso_cubierto / peso_total_esperado if peso_total_esperado else 0.0,
    )


def incidencia(
    indice_agrupacion_t: float,
    indice_agrupacion_t_1: float,
    indice_general_t_1: float,
    peso_agrupacion: float,
) -> float:
    """Fórmula 16. Cuántos puntos porcentuales del nivel general explica
    esta agrupación, si todo lo demás hubiera quedado constante.

    La suma de las incidencias de TODAS las agrupaciones de un mismo nivel
    (p.ej. las 9 clases de división 01) debe dar exactamente la variación
    del nivel general de esa división — es la identidad que se usa como
    test de consistencia (ver tests/test_agregacion.py). Si no cierra, hay
    un error de pesos o de cobertura en alguna parte.
    """
    return (indice_agrupacion_t - indice_agrupacion_t_1) / indice_general_t_1 * peso_agrupacion * 100


def nacional(
    variaciones_por_region: dict[str, float],
    pesos_region: dict[str, float],
) -> ResultadoAgregacion:
    """Combina los indices regionales en el indice nacional.

    Es la misma operacion que `laspeyres`, pero sobre regiones en vez de
    clases: cada region entra con su importancia relativa (Metodologia N32,
    Cuadro 6: GBA 44,7%, Pampeana 34,2%, Noroeste 6,9%, Cuyo 5,2%,
    Patagonia 4,6%, Noreste 4,5%).

    Si una region no tiene datos NO se asume cero: se excluye y se
    renormaliza, y `cobertura` informa que fraccion del pais quedo
    representada. Un nacional armado solo con GBA y Pampeana cubre el 79%
    del pais — util, pero hay que decirlo.
    """
    return laspeyres(variaciones_por_region, pesos_region)
