#!/usr/bin/env python3
"""
Reconstruye la base de datos desde los CSV del historial.

    python -m scripts.reconstruir

Sirve para: empezar de cero en otra maquina, recuperarse de una base
corrupta, o volver a armar todo despues de cambiar el codigo de calculo.

La base es un DERIVADO descartable: la verdad son los archivos de
historico/. Este script materializa una desde la otra."""

from __future__ import annotations

import argparse
import csv
import gzip
from pathlib import Path

from storage.db import conectar

DB_PATH = Path("relevamiento_precios.db")
CARPETA = Path("historico")


def reconstruir(borrar: bool = False, verboso: bool = True) -> int:
    """Reconstruye la base desde los respaldos de historico/.

    Es una funcion aparte de main() a proposito: la app de Streamlit la
    llama directamente cuando arranca sin base (que es lo que pasa en
    Streamlit Cloud, porque la base no viaja en el repositorio). Devuelve
    la cantidad de filas reconstruidas.
    """
    if not CARPETA.exists() or not list(CARPETA.glob("*.csv.gz")):
        if verboso:
            print(f"No hay archivos en {CARPETA}/. Nada que reconstruir.")
        return 0

    if borrar and DB_PATH.exists():
        DB_PATH.unlink()
        if verboso:
            print("Base anterior borrada.")

    con = conectar(DB_PATH)
    total = 0
    for archivo in sorted(CARPETA.glob("*.csv.gz")):
        with gzip.open(archivo, "rt", encoding="utf-8") as fh:
            lector = csv.DictReader(fh)
            filas = [(r["fecha"], r["ean_o_id"], r["clase_codigo"],
                      r["comercio"], float(r["precio"]), r["region"])
                     for r in lector]
        con.executemany(
            """INSERT OR IGNORE INTO precios_raw
               (fecha, ean_o_id, clase_codigo, comercio, precio, region)
               VALUES (?, ?, ?, ?, ?, ?)""", filas)
        con.commit()
        total += len(filas)
        if verboso:
            print(f"  {archivo.name}  {len(filas):>8,} filas")
    con.close()
    if verboso:
        print(f"\nListo: {total:,} filas reconstruidas en {DB_PATH}")
    return total


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--borrar", action="store_true",
                    help="borrar la base actual antes de reconstruir")
    args = ap.parse_args()
    reconstruir(borrar=args.borrar)


if __name__ == "__main__":
    main()
