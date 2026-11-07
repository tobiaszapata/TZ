"""
Calculo de la clase 06.4.1 "Prepagas y obras sociales" a partir de los
cuadros tarifarios que las entidades declaran a la Superintendencia de
Servicios de Salud (cuadrostarifarios.sssalud.gob.ar, Res. 645/2025).

QUE ES CADA COSA
  * UNIDAD = un plan de una entidad, para una region declarada, un rango
    etario y una modalidad: (RNEMP, nombre del plan, rango etario desde y
    hasta, region, tipo de plan, modalidad de adhesion, copago). Es la misma
    clave de unicidad que define el manual de la Res. 645/2025 (sin el
    periodo). Una unidad tiene un VALOR DE CAPITA (la cuota) por mes y una
    CANTIDAD DE CAPITAS (afiliados) por mes.
  * PRECIO DE LA UNIDAD EN UN PERIODO = promedio de sus cuotas mensuales,
    ponderado por la cantidad de dias del periodo que cae en cada mes. Como
    la cuota cambia de forma DISCRETA (una vez por mes), esto equivale a
    tratarla como un escalon que rige hasta el proximo cambio: un periodo que
    cruza dos meses mezcla las dos cuotas en proporcion a los dias.

COMO SE CALCULA LA VARIACION (misma estructura que las clases de SEPA,
Metodologia N°32 apartados 5.1 y 7.1):
  1. Solo se comparan unidades presentes en AMBOS periodos (mismo plan,
     misma region, mismo rango etario): se compara lo comparable.
  2. Relativo de la unidad = precio actual / precio base.
  3. Relativo de la region = MEDIA GEOMETRICA ponderada de los relativos de
     las unidades que rigen en esa region de INDEC. El ponderador es el GASTO
     del periodo base de la unidad: capitas x cuota (tipo Laspeyres: pesos
     del periodo base, como hace INDEC con sus ponderadores). Ver
     config/regiones_prepagas.py para como se decide en que regiones rige una
     unidad.
  4. COBERTURA = gasto base de lo comparado / gasto base total de la region.
     Si es > 50% se usa el relativo propio; entre 20% y 50% se mezcla con la
     variacion de las demas clases de la division; si es < 20% se usa la de
     las demas clases (apartado 7.1; lo hace engine.consultas con
     `variacion_grupo_superior`).
  5. El NACIONAL lo arma engine.consultas como con cualquier clase: combina
     las 6 regiones con la importancia de cada una en el gasto nacional
     (Cuadro 6 de la Metodologia, config.canasta.PESO_REGION).

CONTROL DE CALIDAD: un relativo fuera de [0.5, 2.0] en una unidad (la cuota se
duplico o se redujo a la mitad entre periodos) se considera un error de carga
y se descarta (se cuenta en `descartadas_por_atipicas`). Las unidades sin
cantidad de capitas pesan 0; si NINGUNA unidad de la region tiene capitas, se
usan pesos iguales (queda marcado en el resultado).

LO QUE ESTE CALCULO NO HACE (y conviene saberlo): los valores son los
DECLARADOS a la Superintendencia, no necesariamente lo facturado (las entidades
pueden bonificar); no distingue planes nuevos de planes renombrados (un plan
que cambia de nombre sale de la comparacion ese mes); y el rango etario se
toma tal cual lo declara cada entidad (no hay una grilla unica).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

from config.regiones_prepagas import REGIONES_INDEC, cargar_overrides, regiones_indec
from engine.imputacion import MetodoImputacion, relativo_de_variedad
from engine.reporte import ProductoDriver, VariacionClase
from storage.prepagas import filas_de_periodo

RELATIVO_MIN = 0.5
RELATIVO_MAX = 2.0

RUTA_REGIONES_CSV = Path(__file__).resolve().parents[1] / "externos" / "prepagas" / "regiones.csv"


# ------------------------------------------------------------------ periodos

def _es_multibloque(x) -> bool:
    return isinstance(x, (list, tuple)) and bool(x) and isinstance(x[0], (list, tuple))


def dias_por_mes(desde, hasta) -> dict[int, int]:
    """{AAAAMM: cantidad de dias del rango que caen en ese mes}. `desde`
    puede ser una lista de tramos [(desde, hasta), ...] (varios bloques)."""
    bloques = list(desde) if _es_multibloque(desde) else [(desde, hasta)]
    out: dict[int, int] = {}
    for d, h in bloques:
        a, b = date.fromisoformat(str(d)[:10]), date.fromisoformat(str(h)[:10])
        dia = a
        while dia <= b:
            clave = dia.year * 100 + dia.month
            out[clave] = out.get(clave, 0) + 1
            dia += timedelta(days=1)
    return out


def periodos_de_la_seleccion(d1, h1, d0, h0) -> list[int]:
    """Meses (AAAAMM) que tocan las dos ventanas del calculo."""
    return sorted(set(dias_por_mes(d1, h1)) | set(dias_por_mes(d0, h0)))


# ------------------------------------------------------------------ unidades

def _clave_unidad(f) -> tuple:
    # f = (rnemp, nombre_comercial, nombre_plan, valor, capitas, desde, hasta,
    #      region, tipo_plan, modalidad, copago)
    return (f[0], f[2], f[5], f[6], f[7], f[8], f[9], f[10])


# Cache por CONEXION (no global): dos bases distintas nunca comparten entradas.
# Se guarda la propia conexion junto a sus entradas para que su id() no se
# pueda reutilizar mientras la entrada exista. La clave incluye
# `con.total_changes`, que sube cada vez que esa conexion carga o recarga un
# mes: un mes recargado con datos nuevos nunca se lee de una entrada vieja.
_CACHE_POR_CON: dict = {}


def _unidades_del_mes(con, periodo: int) -> dict[tuple, tuple[float, float, str | None]]:
    """{clave_unidad: (cuota, capitas, nombre de la entidad)} de un mes.
    Filas repetidas con la misma clave (p. ej. un plan comercializable y el
    mismo no comercializable) se fusionan: cuota ponderada por capitas y
    capitas sumadas."""
    if id(con) not in _CACHE_POR_CON:
        if len(_CACHE_POR_CON) >= 16:
            _CACHE_POR_CON.clear()
        _CACHE_POR_CON[id(con)] = (con, {})
    cache = _CACHE_POR_CON[id(con)][1]
    clave_cache = (periodo, con.total_changes)
    if clave_cache in cache:
        return cache[clave_cache]

    acum: dict[tuple, list] = {}
    for f in filas_de_periodo(con, periodo):
        cuota, cap = f[3], f[4]
        if cuota is None or cuota <= 0:
            continue
        cap = cap if (cap is not None and cap > 0) else 0.0
        a = acum.setdefault(_clave_unidad(f), [0.0, 0.0, 0.0, 0, f[1]])
        a[0] += cuota * cap          # suma cuota*capitas
        a[1] += cap                  # suma capitas
        a[2] += cuota                # suma simple (para filas sin capitas)
        a[3] += 1
    salida = {}
    for k, (cc, cap, suma, n, nom) in acum.items():
        salida[k] = ((cc / cap) if cap > 0 else suma / n, cap, nom)
    if len(cache) > 32:
        cache.clear()
    cache[clave_cache] = salida
    return salida


def _tabla_existe(con, nombre: str) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                       (nombre,)).fetchone() is not None


def _firma(con, periodo: int) -> tuple:
    """(filas, suma de cuotas, suma de capitas) del mes: identifica el CONTENIDO
    cargado, asi el cache se invalida si el mes se vuelve a cargar con datos
    distintos (aunque el archivo pese lo mismo)."""
    if not _tabla_existe(con, "prepagas_cuadros"):
        return (0, 0.0, 0.0)
    return tuple(con.execute(
        "SELECT COUNT(*), TOTAL(valor_capital), TOTAL(cantidad_capitas) "
        "FROM prepagas_cuadros WHERE periodo=?", (periodo,)).fetchone())


def _contar(con, periodo: int) -> int:
    return int(_firma(con, periodo)[0])


def unidades_de_la_ventana(con, desde, hasta) -> dict[tuple, tuple[float, float, str | None]]:
    """{unidad: (cuota promedio del periodo, capitas promedio, entidad)}.
    Cuota y capitas = promedio ponderado por dias de cada mes del periodo,
    sobre los meses en que la unidad existe."""
    meses = dias_por_mes(desde, hasta)
    acum: dict[tuple, list] = {}
    for mes, dias in meses.items():
        for k, (cuota, cap, nom) in _unidades_del_mes(con, mes).items():
            a = acum.setdefault(k, [0.0, 0.0, 0, nom])
            a[0] += dias * cuota
            a[1] += dias * cap
            a[2] += dias
    return {k: (a[0] / a[2], a[1] / a[2], a[3]) for k, a in acum.items()}


# ------------------------------------------------------------------ calculo

@lru_cache(maxsize=1)
def _overrides_cacheados(mtime: float) -> dict:
    return cargar_overrides(RUTA_REGIONES_CSV)


def _overrides() -> dict:
    try:
        mt = RUTA_REGIONES_CSV.stat().st_mtime
    except OSError:
        mt = 0.0
    return _overrides_cacheados(mt)


@dataclass
class DetalleCalculo:
    descartadas_por_atipicas: int = 0
    pesos_iguales: bool = False


def calcular_relativo(unid_t: dict, unid_0: dict, region: str | None,
                      excluir=frozenset(), variacion_grupo_superior: float | None = None,
                      overrides: dict | None = None, detalle: DetalleCalculo | None = None):
    """Devuelve (VariacionClase, [ProductoDriver por entidad]) o (None, [])."""
    detalle = detalle if detalle is not None else DetalleCalculo()
    excluir = {str(e) for e in (excluir or ())}
    overrides = overrides if overrides is not None else {}

    def rige(k) -> bool:
        if str(k[0]) in excluir:
            return False
        if region is None:
            return True
        return region in regiones_indec(k[4], overrides).regiones

    base = {k: v for k, v in unid_0.items() if rige(k)}
    if not base:
        return None, []
    gasto0 = {k: v[0] * v[1] for k, v in base.items()}
    if sum(gasto0.values()) <= 0:
        peso = {k: 1.0 for k in base}
        detalle.pesos_iguales = True
    else:
        peso = gasto0

    comparables: dict[tuple, float] = {}
    for k in base:
        if k in unid_t and rige(k):
            rel = unid_t[k][0] / base[k][0]
            if RELATIVO_MIN <= rel <= RELATIVO_MAX:
                comparables[k] = rel
            else:
                detalle.descartadas_por_atipicas += 1
    comparables = {k: r for k, r in comparables.items() if peso[k] > 0}
    if not comparables:
        return None, []

    w_total = sum(peso[k] for k in comparables)
    w_base = sum(peso.values())
    S = sum(peso[k] * math.log(r) for k, r in comparables.items()) / w_total
    relativo_propio = math.exp(S)

    sup = (1 + variacion_grupo_superior / 100) if variacion_grupo_superior is not None else None
    res = relativo_de_variedad(w_total, w_base, relativo_propio, sup)
    c = res.cobertura
    T = math.log(res.relativo)
    variacion_final = (res.relativo - 1) * 100

    if res.metodo == MetodoImputacion.PROPIO or not res.uso_superior:
        peso_propio_en_T = 1.0
    elif res.metodo == MetodoImputacion.GRUPO_SUPERIOR_PARCIAL:
        peso_propio_en_T = c
    else:
        peso_propio_en_T = 0.0
    factor = (math.exp(T) - 1) / T if abs(T) > 1e-12 else 1.0

    # Detalle por ENTIDAD (lo que la pantalla muestra como "productos").
    por_entidad: dict[int, dict] = {}
    for k, r in comparables.items():
        e = por_entidad.setdefault(k[0], {"w": 0.0, "lw": 0.0, "cap": 0.0, "pt": 0.0,
                                          "p0": 0.0, "nom": base[k][2]})
        w = peso[k]
        e["w"] += w
        e["lw"] += w * math.log(r)
        e["cap"] += unid_t[k][1]
        e["pt"] += w * unid_t[k][0]
        e["p0"] += w * base[k][0]
    drivers = []
    for rnemp, e in por_entidad.items():
        ln_e = e["lw"] / e["w"]
        share = e["w"] / w_total
        drivers.append(ProductoDriver(
            ean_o_id=str(rnemp),
            nombre_producto=e["nom"] or f"RNEMP {rnemp}",
            n_observaciones_mes=int(round(e["cap"])),
            precio_mes=e["pt"] / e["w"],
            precio_mes_anterior=e["p0"] / e["w"],
            variacion_pct=(math.exp(ln_e) - 1) * 100,
            peso_proxy_pct=share * 100,
            incidencia_aproximada_pp=100 * factor * peso_propio_en_T * share * ln_e,
            es_imputado=False,
        ))
    drivers.sort(key=lambda d: abs(d.incidencia_aproximada_pp), reverse=True)

    nuevas = sum(1 for k in unid_t if k not in unid_0 and rige(k))
    perdidas = sum(1 for k in base if k not in unid_t)
    resultado = VariacionClase(
        clase_codigo="", mes="", mes_anterior="",
        variacion_pct=variacion_final,
        n_productos_comparados=len(comparables),
        n_productos_solo_mes_actual=nuevas,
        n_productos_solo_mes_anterior=perdidas,
        cobertura=c,
        metodo_imputacion=(res.metodo.value if res.metodo != MetodoImputacion.PROPIO else None),
        imputacion_con_superior=res.uso_superior,
    )
    return resultado, drivers


def variacion_clase_prepagas(con, clase, desde, hasta, desde_base, hasta_base, region=None,
                             variacion_grupo_superior=None, excluir_eans=None):
    """Interfaz identica a la parte final de engine.consultas.variacion_clase
    (mismos argumentos, mismo resultado), para que la clase de prepagas se
    comporte como cualquier otra en todo el motor y en la pantalla.
    `excluir_eans` = RNEMP (como texto) de entidades a dejar afuera."""
    unid_t = unidades_de_la_ventana(con, desde, hasta)
    unid_0 = unidades_de_la_ventana(con, desde_base, hasta_base)
    if not unid_t or not unid_0:
        return None, []
    res, drivers = calcular_relativo(unid_t, unid_0, region, excluir_eans or (),
                                     variacion_grupo_superior, _overrides())
    if res is not None:
        res.clase_codigo = clase
    return res, drivers


def hay_datos(con, desde, hasta) -> bool:
    """True si hay cuadros cargados para algun mes de la ventana."""
    return any(_contar(con, m) > 0 for m in dias_por_mes(desde, hasta))


def cobertura_de_clasificacion(con, periodo: int) -> dict:
    """Diagnostico de un mes: que parte de las capitas cae en cada nivel de
    certeza de la equivalencia region texto -> region INDEC."""
    ov = _overrides()
    por_certeza: dict[str, float] = {}
    textos_dudosos: dict[str, float] = {}
    total = 0.0
    for k, (cuota, cap, _nom) in _unidades_del_mes(con, periodo).items():
        cl = regiones_indec(k[4], ov)
        por_certeza[cl.certeza] = por_certeza.get(cl.certeza, 0.0) + cap
        total += cap
        if cl.certeza in ("dudosa", "sin_clasificar"):
            textos_dudosos[k[4]] = textos_dudosos.get(k[4], 0.0) + cap
    return {"capitas_total": total, "por_certeza": por_certeza,
            "textos_dudosos": dict(sorted(textos_dudosos.items(), key=lambda x: -x[1]))}
