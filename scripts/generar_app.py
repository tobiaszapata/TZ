#!/usr/bin/env python3
"""
Genera la APLICACION HTML completa: un solo archivo con TODOS los datos
adentro, donde se elige el periodo, se navega por niveles y se simula.

    python -m scripts.generar_app

DIFERENCIA CON generar_html.py y generar_simulador.py:
Aquellos generan una foto para dos fechas fijas. Este exporta la serie
diaria completa y deja que el navegador haga cualquier corte temporal. Un
solo archivo responde todas las preguntas, sin volver a Python.

Los otros dos scripts se mantienen porque siguen siendo utiles para mandar
un reporte cerrado de un periodo puntual (mas liviano, sin controles).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from engine.exportador import exportar
from scripts._app_template import APP_HTML
from storage.db import conectar

DB_PATH = Path("relevamiento_precios.db")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", default="aplicacion.html")
    ap.add_argument("--meses", nargs="*", default=None,
                    help="limitar a ciertos meses (YYYY-MM). Por defecto, todos.")
    args = ap.parse_args()

    if not DB_PATH.exists():
        print(f"No encuentro la base {DB_PATH}. Corriste scripts.correr_dia al menos una vez?")
        return

    con = conectar(DB_PATH)
    datos = exportar(con, args.meses)
    con.close()

    if not datos["clases"]:
        print("No hay datos cargados todavia. Carga al menos un dia antes de generar la app.")
        return

    n_prod = sum(len(c["productos"]) for c in datos["clases"])
    n_val = sum(len(p["serie"]) for c in datos["clases"] for p in c["productos"])

    html = APP_HTML.replace("__DATOS__", json.dumps(datos, ensure_ascii=False))
    salida = Path(args.salida)
    salida.write_text(html, encoding="utf-8")

    print(f"Aplicacion generada: {salida.resolve()}")
    print(f"  subcategorias: {len(datos['clases'])}")
    print(f"  productos:     {n_prod}")
    print(f"  valores diarios exportados: {n_val}")
    print(f"  rango de fechas: {datos['fecha_min']} a {datos['fecha_max']}")
    print(f"  tamano del archivo: {salida.stat().st_size/1024:.0f} KB")
    print("\nAbrila con doble clic. Funciona sin internet y sin servidor.")


if __name__ == "__main__":
    main()
