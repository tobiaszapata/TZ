#!/usr/bin/env python3
"""
Exporta cada dia a un CSV comprimido, versionable en git.

    python -m scripts.exportar_dia            # exporta los dias que falten
    python -m scripts.exportar_dia --fecha 2026-08-10

POR QUE EXISTE ESTE SCRIPT (el problema que resuelve):
El historial de precios es el activo del proyecto y es IRRECUPERABLE: SEPA
solo mantiene una ventana de 7 dias, asi que un dia perdido no se recupera
nunca. Entonces hay que respaldarlo.

La idea original era versionar directamente `relevamiento_precios.db`, pero
esa base crece ~37 MB POR DIA. GitHub bloquea archivos de mas de 100 MB, o
sea que a los tres dias el repositorio dejaria de aceptar cambios. Ademas
git guarda una copia entera del archivo en cada commit (es binario, no
sabe hacer diferencias), asi que el historial explotaria.

La solucion es exportar UN ARCHIVO POR DIA, comprimido:
  historico/2026-08-10.csv.gz
  historico/2026-08-11.csv.gz

Ventajas frente a versionar la base:
  - cada archivo pesa unos pocos MB, muy lejos del limite;
  - un dia ya exportado NO SE VUELVE A TOCAR, asi que git solo agrega
    archivos nuevos en vez de reescribir uno gigante;
  - es texto plano: dentro de diez anios se puede leer sin este programa;
  - la base se puede borrar y reconstruir entera desde estos archivos
    (ver scripts/reconstruir.py).

La base `relevamiento_precios.db` pasa a ser un DERIVADO descartable, y por
eso queda excluida del repositorio.
"""

from __future__ import annotations

import argparse
import csv
import gzip
from pathlib import Path

from storage.db import conectar

DB_PATH = Path("relevamiento_precios.db")
CARPETA = Path("historico")

COLUMNAS = ["fecha", "ean_o_id", "clase_codigo", "comercio", "precio", "region"]


def dias_en_base(con) -> list[str]:
    return [r[0] for r in con.execute(
        "SELECT DISTINCT fecha FROM precios_raw ORDER BY fecha")]


def exportar_dia(con, fecha: str) -> Path:
    CARPETA.mkdir(exist_ok=True)
    destino = CARPETA / f"{fecha}.csv.gz"
    cur = con.execute(
        f"""SELECT {','.join(COLUMNAS)} FROM precios_raw
            WHERE fecha = ? ORDER BY clase_codigo, ean_o_id, comercio, region""",
        (fecha,),
    )
    n = 0
    with gzip.open(destino, "wt", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(COLUMNAS)
        for fila in cur:
            w.writerow(fila)
            n += 1
    return destino, n


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fecha", help="exportar solo este dia (YYYY-MM-DD)")
    ap.add_argument("--rehacer", action="store_true",
                    help="volver a exportar dias que ya tienen archivo")
    args = ap.parse_args()

    if not DB_PATH.exists():
        print(f"No encuentro {DB_PATH}. Corré primero: python -m scripts.actualizar")
        return

    con = conectar(DB_PATH)
    fechas = [args.fecha] if args.fecha else dias_en_base(con)
    if not fechas:
        print("La base no tiene dias cargados.")
        return

    CARPETA.mkdir(exist_ok=True)
    exportados = omitidos = 0
    for fecha in fechas:
        destino = CARPETA / f"{fecha}.csv.gz"
        if destino.exists() and not args.rehacer:
            omitidos += 1
            continue
        destino, n = exportar_dia(con, fecha)
        mb = destino.stat().st_size / 1024**2
        print(f"  {fecha}  {n:>8,} filas  ->  {destino.name}  ({mb:.1f} MB)")
        exportados += 1
    con.close()

    print(f"\nExportados: {exportados}   ya existian: {omitidos}")
    if exportados:
        print("\nEstos archivos SI van al repositorio (son el respaldo del historial).")
        print("Subilos con:  git add historico/ && git commit -m \"datos\" && git push")


if __name__ == "__main__":
    main()
