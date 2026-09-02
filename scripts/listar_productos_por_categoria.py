#!/usr/bin/env python3
"""
Exporta un CSV con TODOS los productos alguna vez cargados, agrupados por
subcategoría — pensado para auditar la clasificación: revisar cuáles están
bien puestos y cuáles habría que reclasificar.

    python -m scripts.listar_productos_por_categoria

Genera `productos_por_categoria.csv` en la carpeta del proyecto, abrible
directo en Excel. Columnas: División, Subcategoría, Código (EAN),
Producto, Observaciones (cuántas veces se vio — los más frecuentes son
los que más pesan en el cálculo, y los que más vale la pena revisar si
algo está mal clasificado).

    python -m scripts.listar_productos_por_categoria --clase 01.1.6

Filtra a una sola subcategoría, si solo querés revisar esa.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from config.canasta import Cobertura, clases_de_division, divisiones
from storage.db import conectar, productos_de_clase

RAIZ = Path(__file__).resolve().parent.parent
DB_PATH = RAIZ / "relevamiento_precios.db"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clase", help="exportar solo esta subcategoría (ej. 01.1.6)")
    ap.add_argument("--salida", default="productos_por_categoria.csv",
                    help="nombre del archivo CSV (default: productos_por_categoria.csv)")
    args = ap.parse_args()

    if not DB_PATH.exists():
        print(f"No encuentro la base {DB_PATH}. Cargá al menos un día primero.")
        return

    con = conectar(DB_PATH)
    salida = RAIZ / args.salida

    filas_escritas = 0
    with open(salida, "w", newline="", encoding="utf-8-sig") as fh:
        # utf-8-sig (con BOM): para que Excel en Windows abra los acentos
        # bien de entrada, sin pedir elegir el encoding a mano.
        w = csv.writer(fh)
        w.writerow(["Division", "Subcategoria (codigo)", "Subcategoria (nombre)",
                   "Codigo de producto", "Producto", "Observaciones"])

        for div in divisiones():
            for clase in clases_de_division(div.codigo):
                if clase.cobertura != Cobertura.MEDIDA_SEPA:
                    continue
                if args.clase and clase.codigo != args.clase:
                    continue

                productos = productos_de_clase(con, clase.codigo)
                for ean, nombre, n_obs in productos:
                    w.writerow([div.nombre, clase.codigo, clase.nombre, ean, nombre, n_obs])
                    filas_escritas += 1

    con.close()

    if filas_escritas == 0:
        print("No se encontró ningún producto para exportar. ¿La base tiene datos cargados?")
        if args.clase:
            print(f"(revisá que '{args.clase}' sea un código de subcategoría válido y medido)")
        return

    print(f"Listo: {filas_escritas:,} productos exportados a {salida}")
    print("Se puede abrir directo en Excel — ordená por 'Subcategoria (codigo)' para revisar")
    print("una categoría a la vez, o por 'Observaciones' para ver primero los productos")
    print("más frecuentes (los que más pesan en el cálculo).")


if __name__ == "__main__":
    main()
