r"""
Baja los cuadros tarifarios de prepagas (SSSalud) a externos/prepagas/.

Uso (desde la carpeta del proyecto, en PowerShell):
  python -m scripts.descargar_prepagas --listar
  python -m scripts.descargar_prepagas --periodos 202610
  python -m scripts.descargar_prepagas --todos
  python -m scripts.descargar_prepagas --faltantes
  python -m scripts.descargar_prepagas --desde-csv C:\ruta\202610.csv

  --listar      muestra los meses del sitio y cuales ya tenes bajados.
  --periodos    uno o mas meses AAAAMM (separados por espacio).
  --todos       todos los meses del sitio desde el piso (pisa los que ya tenes).
  --faltantes   solo los meses (desde el piso) que todavia no tenes.
  --desde AAAAMM  piso: no se consideran meses anteriores (por defecto 202607;
                0 = todos los del sitio, desde 202507).
  --desde-csv   importa un CSV generado con scripts/prepagas_navegador.js
                (plan B si tu red bloquea a Python pero no al navegador).
  --hilos N     pedidos en paralelo (por defecto 4; bajalo si hay errores).
Cada mes tarda unos minutos (son ~200 entidades, de a 50 filas por pedido).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from collectors.prepagas.descargar import (
    PERIODO_PISO, DescargaIncompleta, bajar_periodo, escribir_mes, importar_csv_plano,
    listar_entidades, listar_periodos,
)
from storage.prepagas import periodos_disponibles

RAIZ = Path(__file__).resolve().parents[1]
CARPETA = RAIZ / "externos" / "prepagas"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--listar", action="store_true")
    ap.add_argument("--periodos", nargs="+", type=int)
    ap.add_argument("--todos", action="store_true")
    ap.add_argument("--faltantes", action="store_true")
    ap.add_argument("--desde-csv", type=Path)
    ap.add_argument("--hilos", type=int, default=4)
    ap.add_argument("--desde", type=int, default=PERIODO_PISO)
    a = ap.parse_args(argv)

    if a.desde_csv:
        destino = importar_csv_plano(a.desde_csv, CARPETA)
        print(f"OK: {destino}")
        return 0

    tengo = set(periodos_disponibles(CARPETA))
    sitio = [p for p in listar_periodos() if p >= a.desde]
    if a.listar or not (a.periodos or a.todos or a.faltantes):
        print("Meses en el sitio:", ", ".join(str(p) + ("" if p in tengo else "  (te falta)") for p in sitio))
        return 0
    if a.periodos:
        pedidos = a.periodos
    elif a.todos:
        pedidos = sitio
    else:
        pedidos = [p for p in sitio if p not in tengo]
    fuera = [p for p in pedidos if p not in sitio]
    if fuera:
        print(f"ERROR: el sitio no tiene estos meses: {fuera}")
        return 1
    if not pedidos:
        print("No falta ningun mes.")
        return 0

    entidades = listar_entidades()
    print(f"{len(entidades)} entidades en el sitio. Meses a bajar: {pedidos}")
    for p in pedidos:
        t0 = time.time()
        try:
            filas = bajar_periodo(
                p, entidades, hilos=a.hilos,
                progreso=lambda n, tot, e, nf: (print(f"\r  {p}: {n}/{tot} entidades", end="", flush=True)))
        except DescargaIncompleta as exc:
            print(f"\n  {exc}\n  Reintenta ese mes (python -m scripts.descargar_prepagas --periodos {p}).")
            return 2
        escribir_mes(filas, CARPETA / f"{p}.csv.gz")
        print(f"\n  {p}: {len(filas)} filas guardadas en {time.time() - t0:.0f}s")
    print("Listo. Subi la carpeta externos/prepagas/ a GitHub (git add externos).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
