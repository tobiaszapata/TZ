#!/usr/bin/env python3
"""
Compara el calculo ANTERIOR contra el nuevo (Metodologia N°32) sobre TU base.

    python -m scripts.comparar_metodo --desde 2026-10-12 --hasta 2026-10-16 --desde-base 2026-10-05 --hasta-base 2026-10-09

No cambia nada: solo lee la base y muestra, para cada subcategoria medida,
la variacion nacional con el metodo anterior, con el nuevo, la diferencia en
puntos porcentuales y en cuantas regiones hizo falta imputar (apartado 7.1).
Al final, el resultado por division y el nivel general con cada metodo.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from config.canasta import CANASTA, CLASES_CON_COBERTURA_SEPA, PESO_REGION
from engine.consultas import (
    nivel_general_desde_divisiones, resumen_divisiones_desde_valores,
    valores_medidos_nacional, variaciones_de_region,
)
from storage.db import conectar

RAIZ = Path(__file__).resolve().parent.parent


def _fmt(v):
    return "   —  " if v is None else f"{v:+6.2f}%"


def comparar(con, d1, h1, d0, h0) -> dict:
    prev = valores_medidos_nacional(con, d1, h1, d0, h0, metodo="previo")
    nuevo = valores_medidos_nacional(con, d1, h1, d0, h0, metodo="indec")
    imputadas = {c: 0 for c in CLASES_CON_COBERTURA_SEPA}
    for region in PESO_REGION:
        for cod, r in variaciones_de_region(con, d1, h1, d0, h0, region).items():
            if r.metodo_imputacion is not None:
                imputadas[cod] += 1
    div_prev = resumen_divisiones_desde_valores(prev)
    div_nuevo = resumen_divisiones_desde_valores(nuevo)
    return {"previo": prev, "nuevo": nuevo, "imputadas": imputadas,
            "divisiones": (div_prev, div_nuevo),
            "general": (nivel_general_desde_divisiones(div_prev),
                        nivel_general_desde_divisiones(div_nuevo))}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--desde", required=True)
    ap.add_argument("--hasta", required=True)
    ap.add_argument("--desde-base", required=True)
    ap.add_argument("--hasta-base", required=True)
    ap.add_argument("--db", default=str(RAIZ / "relevamiento_precios.db"))
    a = ap.parse_args()

    con = conectar(Path(a.db))
    r = comparar(con, a.desde, a.hasta, a.desde_base, a.hasta_base)

    print(f"\nPeriodo {a.desde} a {a.hasta}  vs  {a.desde_base} a {a.hasta_base}\n")
    print(f"{'Subcategoria':46s} {'Anterior':>8s} {'Nuevo':>8s} {'Dif pp':>8s}  Regiones imputadas")
    for cod in CLASES_CON_COBERTURA_SEPA:
        p, n = r["previo"].get(cod), r["nuevo"].get(cod)
        dif = None if p is None or n is None else n - p
        print(f"{cod + ' ' + CANASTA[cod].nombre[:40]:46s} {_fmt(p):>8s} {_fmt(n):>8s} "
              f"{_fmt(dif):>8s}  {r['imputadas'][cod]} de {len(PESO_REGION)}")

    print("\nPor division:")
    for dp, dn in zip(*r["divisiones"]):
        if dp.variacion_pct is None and dn.variacion_pct is None:
            continue
        print(f"{dp.codigo + ' ' + dp.nombre[:40]:46s} {_fmt(dp.variacion_pct):>8s} "
              f"{_fmt(dn.variacion_pct):>8s}")
    gp, gn = r["general"]
    print(f"\nNivel general (solo lo medido)  anterior {_fmt(gp.variacion_pct)}   nuevo {_fmt(gn.variacion_pct)}")
    con.close()


if __name__ == "__main__":
    main()
