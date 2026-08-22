"""
Capa de consulta reutilizable: TODO el calculo que necesita una interfaz.

POR QUE ESTE MODULO EXISTE SEPARADO DE LA INTERFAZ:
La aplicacion de Streamlit no hace cuentas. Llama a las funciones de aca.
Eso tiene tres consecuencias buenas:

 1. Se puede TESTEAR sin levantar Streamlit (que necesita un servidor y un
    navegador). Los tests de este archivo corren en la suite normal.
 2. Si mañana la interfaz cambia (Streamlit, un HTML, un notebook, una API),
    el calculo no se toca.
 3. Elimina la duplicacion Python/JavaScript que existia con la app HTML
    estatica: habia que mantener la misma formula en dos lenguajes.

Todas las funciones son REGION-AWARE: reciben una region y usan los
ponderadores de esa region (ver config/canasta.py).

--------------------------------------------------------------------------
SOBRE LOS "OVERRIDES" (valores manuales / simulacion):

`division_completa`, `indice_region` y `resumen_divisiones` aceptan un
parametro opcional `overrides`: un diccionario {codigo_de_clase: valor_pct}.
Si una clase esta en ese diccionario, se usa ESE valor en vez del calculado
desde la base — por ejemplo, para probar "¿como quedaria la division si en
vez de nuestro dato de Frutas usamos el 8% que publico la consultora?".

ESTO NUNCA TOCA LA BASE DE DATOS. Es una sustitucion que vive solo en la
memoria de la sesion de Streamlit mientras la estas mirando. Cerrás la
pestaña y el valor real —el que releva el sistema— sigue intacto. Cada fila
que resulta de un override queda marcada `es_manual=True` para que la
interfaz la pinte distinto y nadie la confunda con un dato medido.
--------------------------------------------------------------------------
"""

from __future__ import annotations

from dataclasses import dataclass, field

from config.canasta import (
    CANASTA,
    CLASES_CON_COBERTURA_SEPA,
    PESO_REGION,
    Cobertura,
    clases_de_division,
    divisiones,
)
from engine.reporte import calcular_clase_y_productos
from storage.db import (
    nombres_de_productos,
    precios_por_producto_en_rango,
)


@dataclass
class FilaClase:
    codigo: str
    nombre: str
    peso: float                 # ponderador oficial en la region, en %
    variacion_pct: float | None
    n_productos: int
    aporte_pp: float | None = None
    es_manual: bool = False     # True si este valor vino de un override, no de la base


@dataclass
class ResultadoDivision:
    codigo: str
    nombre: str
    peso: float
    variacion_pct: float | None
    cobertura: float            # fraccion del peso de la division con dato
    clases: list[FilaClase]
    tiene_manuales: bool = False


def variacion_clase(con, clase, desde, hasta, desde_base, hasta_base, region=None):
    """Variacion de una clase entre dos ventanas de fechas, con el detalle
    por producto. Devuelve (resultado, drivers) o (None, []) si no hay
    productos comparables. Esto SIEMPRE lee de la base — los overrides se
    aplican una capa mas arriba (division_completa), nunca aca."""
    p_act = precios_por_producto_en_rango(con, clase, desde, hasta, region)
    p_base = precios_por_producto_en_rango(con, clase, desde_base, hasta_base, region)
    eans = list(set(p_act) | set(p_base))
    if not eans:
        return None, []
    return calcular_clase_y_productos(p_act, p_base, nombres_de_productos(con, eans))


def division_completa(con, div_codigo, desde, hasta, desde_base, hasta_base,
                      region="GBA", overrides: dict[str, float] | None = None) -> ResultadoDivision:
    """Calcula una division: cada clase con cobertura, y el agregado
    ponderado con los pesos de la region indicada.

    `overrides`: {codigo_clase: valor_pct} para pisar el dato medido de esa
    clase con un valor manual, solo en esta consulta. Ver docstring del
    modulo — nunca escribe en la base."""
    overrides = overrides or {}
    div = CANASTA[div_codigo]
    filas: list[FilaClase] = []
    num = den = 0.0
    tiene_manuales = False

    for clase in clases_de_division(div_codigo):
        if clase.cobertura != Cobertura.MEDIDA_SEPA:
            continue
        peso = clase.peso(region) * 100

        if clase.codigo in overrides:
            v = overrides[clase.codigo]
            n = 0
            es_manual = True
            tiene_manuales = True
        else:
            res, _ = variacion_clase(con, clase.codigo, desde, hasta,
                                     desde_base, hasta_base, region)
            v = res.variacion_pct if res else None
            n = res.n_productos_comparados if res else 0
            es_manual = False

        filas.append(FilaClase(clase.codigo, clase.nombre, peso, v, n, es_manual=es_manual))
        if v is not None:
            num += peso * v
            den += peso

    variacion = num / den if den else None
    for f in filas:
        f.aporte_pp = (f.peso / den * f.variacion_pct) if (den and f.variacion_pct is not None) else None

    peso_total = sum(c.peso(region) * 100 for c in clases_de_division(div_codigo)
                     if c.cobertura == Cobertura.MEDIDA_SEPA)
    return ResultadoDivision(
        codigo=div_codigo, nombre=div.nombre, peso=div.peso(region) * 100,
        variacion_pct=variacion,
        cobertura=(den / peso_total) if peso_total else 0.0,
        clases=filas,
        tiene_manuales=tiene_manuales,
    )


def indice_region(con, desde, hasta, desde_base, hasta_base, region="GBA",
                  overrides: dict[str, float] | None = None):
    """Indice de una region: todas las clases medidas, ponderadas con los
    pesos de esa region. Devuelve (variacion, cobertura_sobre_canasta).
    Acepta los mismos `overrides` que division_completa."""
    overrides = overrides or {}
    num = den = 0.0
    for cod in CLASES_CON_COBERTURA_SEPA:
        peso = CANASTA[cod].peso(region) * 100
        if cod in overrides:
            v = overrides[cod]
        else:
            res, _ = variacion_clase(con, cod, desde, hasta, desde_base, hasta_base, region)
            v = res.variacion_pct if res else None
        if v is not None:
            num += peso * v
            den += peso
    if not den:
        return None, 0.0
    peso_medible = sum(CANASTA[c].peso(region) * 100 for c in CLASES_CON_COBERTURA_SEPA)
    return num / den, den / peso_medible if peso_medible else 0.0


def indice_nacional(con, desde, hasta, desde_base, hasta_base):
    """Combina las regiones con datos, ponderando por su importancia
    nacional. Las regiones sin datos se excluyen y se renormaliza; se
    informa que fraccion del pais quedo representada.

    NO acepta overrides: la simulacion manual esta pensada para explorar una
    region especifica a la vez (que es como se usa en la pantalla), no para
    combinarse con el nacional. Si hace falta mas adelante, se agrega aca
    sin tocar el resto."""
    por_region: dict[str, float] = {}
    for region in PESO_REGION:
        v, _ = indice_region(con, desde, hasta, desde_base, hasta_base, region)
        if v is not None:
            por_region[region] = v
    if not por_region:
        return None, 0.0, {}
    den = sum(PESO_REGION[r] for r in por_region)
    nacional = sum(PESO_REGION[r] * v for r, v in por_region.items()) / den
    return nacional, den / sum(PESO_REGION.values()), por_region


def resumen_divisiones(con, desde, hasta, desde_base, hasta_base, region="GBA",
                       overrides: dict[str, float] | None = None):
    """Las 12 divisiones, con su variacion cuando hay datos. `overrides`
    aplica a cualquier clase de cualquier division, con la misma clave de
    codigo — se pasa tal cual a cada llamado de division_completa."""
    salida = []
    for div in divisiones():
        tiene = any(c.cobertura == Cobertura.MEDIDA_SEPA
                    for c in clases_de_division(div.codigo))
        if tiene:
            salida.append(division_completa(con, div.codigo, desde, hasta,
                                            desde_base, hasta_base, region, overrides))
        else:
            salida.append(ResultadoDivision(
                div.codigo, div.nombre, div.peso(region) * 100, None, 0.0, []))
    return salida
