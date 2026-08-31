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
  - un dia ya exportado, con el formato AL DIA, no se vuelve a tocar — asi
    que en el dia a dia git solo agrega archivos nuevos en vez de
    reescribir uno gigante. La unica excepcion es cuando el formato de
    exportacion mejora (ver VERSION_FORMATO mas abajo): ahi si conviene
    reescribir los viejos, una sola vez, para que se pongan al dia;
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

# Mismo motivo que en scripts/reconstruir.py: anclado al archivo, no al
# directorio de trabajo del proceso que lo ejecuta.
RAIZ = Path(__file__).resolve().parent.parent
DB_PATH = RAIZ / "relevamiento_precios.db"
CARPETA = RAIZ / "historico"

COLUMNAS = ["fecha", "ean_o_id", "clase_codigo", "comercio", "precio", "region", "nombre_producto"]

# Version del FORMATO de exportacion — no del contenido de un dia puntual.
# Sube cada vez que se agrega o cambia una columna. Sirve para que un
# respaldo viejo (generado con menos columnas) se detecte como "atrasado"
# y se regenere solo, en vez de quedar congelado para siempre con el
# formato anterior. Historial:
#   1 -> columnas originales, SIN nombre_producto (mostraba el codigo del
#        producto en los reportes en vez del nombre — este fue el bug real
#        reportado en produccion).
#   2 -> se agrego nombre_producto.
VERSION_FORMATO = 2


def version_del_respaldo(path: Path) -> int:
    """Detecta con que version de formato se genero un respaldo existente,
    mirando solo su encabezado (no hace falta leer el archivo entero). La
    version SE DEDUCE de las columnas presentes, no de un numero aparte
    guardado a mano — asi no hay dos fuentes de verdad que puedan
    desincronizarse entre si."""
    try:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            encabezado = fh.readline().strip().split(",")
    except (OSError, EOFError):
        return 0  # archivo corrupto o vacio: tratar como "hay que rehacerlo"
    return VERSION_FORMATO if "nombre_producto" in encabezado else 1


def dias_en_base(con) -> list[str]:
    return [r[0] for r in con.execute(
        "SELECT DISTINCT fecha FROM precios_raw ORDER BY fecha")]


def exportar_dia(con, fecha: str) -> Path:
    # LEFT JOIN con `productos` para incluir el nombre en el respaldo.
    #
    # POR QUE ESTO FALTABA Y QUE SE VEIA MAL POR ESO: el nombre del
    # producto vive en la tabla `productos` de la base local, NO en
    # `precios_raw`. El respaldo (esta funcion) solo exportaba
    # `precios_raw` — asi que cuando la app en Streamlit Cloud reconstruye
    # la base desde el respaldo (scripts/reconstruir.py), la tabla
    # `productos` quedaba vacia, y el desglose de productos mostraba el
    # codigo en vez de "Banana". Sumar el nombre aca es lo que permite que
    # `reconstruir.py` la repueble tambien.
    CARPETA.mkdir(exist_ok=True)
    destino = CARPETA / f"{fecha}.csv.gz"
    cur = con.execute(
        """SELECT p.fecha, p.ean_o_id, p.clase_codigo, p.comercio, p.precio, p.region,
                  COALESCE(pr.nombre_producto, '') AS nombre_producto
           FROM precios_raw p
           LEFT JOIN productos pr ON pr.ean_o_id = p.ean_o_id
           WHERE p.fecha = ?
           ORDER BY p.clase_codigo, p.ean_o_id, p.comercio, p.region""",
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
        if destino.exists() and not args.rehacer and version_del_respaldo(destino) >= VERSION_FORMATO:
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
