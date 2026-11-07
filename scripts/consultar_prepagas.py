r"""
Variacion de prepagas (clase 06.4.1) entre dos MESES, con todo el detalle para
poder revisar el calculo antes de mirarlo en la app.

Uso (PowerShell, desde la carpeta del proyecto):
  python -m scripts.consultar_prepagas --mes 202610 --base 202609

Muestra: la variacion por region INDEC (con cobertura y cantidad de planes
comparados), el nacional (regiones combinadas con su importancia en el gasto,
Cuadro 6 de la Metodologia N°32), las entidades que mas explican la variacion y
cuantas capitas caen en regiones declaradas con texto ambiguo.
"""
from __future__ import annotations

import argparse
import calendar
import sys
import tempfile
from pathlib import Path

from config.canasta import PESO_REGION, REGIONES
from engine.consultas import _combinar_regiones
from engine.prepagas import cobertura_de_clasificacion, variacion_clase_prepagas
from storage.db import conectar
from storage.prepagas import asegurar_periodos_cargados

RAIZ = Path(__file__).resolve().parents[1]
CARPETA = RAIZ / "externos" / "prepagas"


def _rango(periodo: int) -> tuple[str, str]:
    a, m = divmod(periodo, 100)
    return f"{a}-{m:02d}-01", f"{a}-{m:02d}-{calendar.monthrange(a, m)[1]:02d}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mes", type=int, required=True, help="mes actual AAAAMM")
    ap.add_argument("--base", type=int, required=True, help="mes base AAAAMM")
    ap.add_argument("--carpeta", type=Path, default=CARPETA)
    a = ap.parse_args(argv)

    con = conectar(Path(tempfile.mkdtemp()) / "prepagas.db")
    carga = asegurar_periodos_cargados(con, a.carpeta, [a.mes, a.base])
    if carga["sin_archivo"]:
        print(f"ERROR: falta el archivo de {carga['sin_archivo']} en {a.carpeta}. "
              "Bajalo con: python -m scripts.descargar_prepagas --periodos " + " ".join(map(str, carga["sin_archivo"])))
        return 1
    d1, h1 = _rango(a.mes)
    d0, h0 = _rango(a.base)

    print(f"\nPrepagas {a.mes} vs {a.base}\n")
    print(f"{'Region':<10}{'Variacion':>11}{'Cobertura':>11}{'Planes comparados':>20}{'Nuevos':>9}{'Perdidos':>10}")
    por_region = {}
    for r in REGIONES:
        res, _ = variacion_clase_prepagas(con, "06.4.1", d1, h1, d0, h0, region=r)
        if res is None:
            print(f"{r:<10}{'sin dato':>11}")
            continue
        por_region[r] = res.variacion_pct
        print(f"{r:<10}{res.variacion_pct:>+10.2f}%{res.cobertura:>10.0%}{res.n_productos_comparados:>20}"
              f"{res.n_productos_solo_mes_actual:>9}{res.n_productos_solo_mes_anterior:>10}")
    nac, cob = _combinar_regiones(por_region, PESO_REGION)
    if nac is not None:
        print(f"\nNACIONAL (regiones ponderadas por su peso en el gasto): {nac:+.2f}%  "
              f"(regiones con dato: {cob:.0%} del peso nacional)")

    res, drivers = variacion_clase_prepagas(con, "06.4.1", d1, h1, d0, h0, region=None)
    if res is not None:
        print(f"\nEntidades que mas explican la variacion (todo el pais junto, {res.variacion_pct:+.2f}%):")
        print(f"  {'Entidad':<42}{'Var.':>8}{'Peso':>8}{'Aporte pp':>11}")
        for d in drivers[:10]:
            print(f"  {d.nombre_producto[:40]:<42}{d.variacion_pct:>+7.2f}%{d.peso_proxy_pct:>7.1f}%"
                  f"{d.incidencia_aproximada_pp:>+11.3f}")

    cl = cobertura_de_clasificacion(con, a.mes)
    tot = cl["capitas_total"] or 1
    print("\nEquivalencia de regiones (capitas del mes actual segun certeza de la clasificacion):")
    for k, v in sorted(cl["por_certeza"].items()):
        print(f"  {k:<15}{v / tot:>7.1%}")
    if cl["textos_dudosos"]:
        print("  Textos dudosos (corregibles en externos/prepagas/regiones.csv):")
        for t, v in list(cl["textos_dudosos"].items())[:8]:
            print(f"    {t[:60]:<62}{v / tot:>6.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
