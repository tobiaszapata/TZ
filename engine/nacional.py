"""
Agregacion por REGION y de region a NACIONAL.

EL PROCEDIMIENTO DE INDEC, EN DOS ETAPAS:

  1. Para cada una de las 6 regiones (GBA, Pampeana, Noroeste, Noreste,
     Cuyo, Patagonia), se calcula el indice usando los ponderadores DE ESA
     REGION. No son los mismos: Alimentos pesa 23,4% en GBA y 35,3% en el
     Noreste.

  2. El nivel nacional es el promedio de las 6 regiones, ponderado por la
     importancia relativa de cada una sobre el total del pais (GBA 44,7%,
     Pampeana 34,2%, Noroeste 6,9%, Cuyo 5,2%, Noreste 4,5%, Patagonia
     4,6% — Metodologia N32, Cuadro 6).

POR QUE NO ALCANZA CON PROMEDIAR TODOS LOS PRECIOS DEL PAIS JUNTOS:
Porque las regiones tienen estructuras de consumo distintas Y porque SEPA
no tiene la misma densidad de sucursales en cada region (sobre datos reales
hay 1.096 sucursales en GBA y 46 en el Noreste). Un promedio simple estaria
dominado por donde hay mas locales, no por donde vive la gente. Ponderar
por region corrige exactamente eso.

MANEJO DE REGIONES SIN DATOS: no se asumen en cero. Se excluyen del
promedio nacional y se renormaliza sobre las regiones que si tienen dato,
informando que porcentaje de la poblacion de referencia quedo cubierto.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from config.canasta import PESO_REGION_NACIONAL, REGIONES, peso


@dataclass
class ResultadoRegional:
    region: str
    variacion_pct: float | None
    peso_cubierto: float          # suma de pesos de clase con dato
    clases_con_dato: int


@dataclass
class ResultadoNacional:
    variacion_pct: float | None
    por_region: dict[str, ResultadoRegional] = field(default_factory=dict)
    cobertura_poblacional: float = 0.0   # % del pais representado
    regiones_sin_datos: list[str] = field(default_factory=list)


def indice_de_region(
    variaciones_por_clase: dict[str, float],
    region: str,
) -> ResultadoRegional:
    """Combina las clases medidas usando los ponderadores DE ESA REGION."""
    num = den = 0.0
    n = 0
    for codigo, var in variaciones_por_clase.items():
        if var is None:
            continue
        w = peso(codigo, region)
        if w <= 0:
            continue
        num += w * var
        den += w
        n += 1
    return ResultadoRegional(
        region=region,
        variacion_pct=(num / den) if den else None,
        peso_cubierto=den,
        clases_con_dato=n,
    )


def indice_nacional(
    variaciones_por_region_y_clase: dict[str, dict[str, float]],
) -> ResultadoNacional:
    """`variaciones_por_region_y_clase` es {region: {clase: variacion_pct}}.

    Devuelve el indice de cada region y el nacional agregado."""
    por_region: dict[str, ResultadoRegional] = {}
    for region in REGIONES:
        clases = variaciones_por_region_y_clase.get(region, {})
        por_region[region] = indice_de_region(clases, region)

    num = den = 0.0
    sin_datos = []
    for region, res in por_region.items():
        w = PESO_REGION_NACIONAL[region]
        if res.variacion_pct is None:
            sin_datos.append(region)
            continue
        num += w * res.variacion_pct
        den += w

    return ResultadoNacional(
        variacion_pct=(num / den) if den else None,
        por_region=por_region,
        cobertura_poblacional=den,
        regiones_sin_datos=sin_datos,
    )
