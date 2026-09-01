#!/usr/bin/env python3
"""
Valida que cada respaldo en historico/ se pueda descomprimir y leer sin
error — detecta archivos corruptos antes de que rompan una reconstrucción.

    python -m scripts.validar_historico

POR QUE ESTA HERRAMIENTA EXISTE:
Streamlit Cloud reconstruye la base leyendo, uno por uno, todos los
archivos de historico/. Si UNO SOLO está corrupto o vacío (por ejemplo,
por un problema de Git en Windows normalizando finales de línea en un
archivo que debería tratarse como binario — ver .gitattributes), la
reconstrucción entera puede fallar, y el síntoma visible es engañoso:
"No hay datos todavía", que suena a que nunca se cargó nada, cuando en
realidad SÍ hay archivos pero uno de ellos no se puede leer.

Este script recorre cada archivo y confirma, de forma explícita, cuál
es el problema y en qué archivo — en vez de dejar que la reconstrucción
se caiga en un lugar indefinido.

QUÉ ESTA HERRAMIENTA NO PUEDE DETECTAR (aclarado tras un caso real):
si el error que aparece en Streamlit es "OperationalError: database is
locked", este script NO va a encontrar nada mal — y con razón: ese error
no tiene que ver con el contenido de los archivos, sino con que otro
proceso tenía la base de datos abierta en el instante exacto de conectar
(típicamente Streamlit Cloud reiniciando el servidor). Para ese caso
puntual, la solución es simplemente esperar unos segundos y reintentar
("🔄 Actualizar datos" en la app) — no tiene sentido correr esta
herramienta para ese error específico.
"""

from __future__ import annotations

import csv
import gzip
import io
from pathlib import Path

# Ancladas al archivo, no al directorio de trabajo del proceso —
# ver la explicacion completa en scripts/reconstruir.py.
RAIZ = Path(__file__).resolve().parent.parent
CARPETA = RAIZ / "historico"

COLUMNAS_ESPERADAS = {"fecha", "ean_o_id", "clase_codigo", "comercio", "precio", "region"}


def main() -> None:
    if not CARPETA.exists():
        print(f"No existe la carpeta {CARPETA}/.")
        return

    archivos = sorted(CARPETA.glob("*.csv.gz"))
    if not archivos:
        print(f"No hay archivos .csv.gz en {CARPETA}/.")
        return

    print(f"Validando {len(archivos)} archivo(s)...\n")
    con_problema = []

    for archivo in archivos:
        try:
            with gzip.open(archivo, "rt", encoding="utf-8") as fh:
                contenido_crudo = fh.read()
            if not contenido_crudo.strip():
                con_problema.append((archivo.name, "el archivo está vacío (0 bytes de contenido)"))
                print(f"  ✗ {archivo.name}  ->  VACÍO (sin contenido)")
                continue

            lector = csv.DictReader(io.StringIO(contenido_crudo))
            columnas = set(lector.fieldnames or [])
            if not COLUMNAS_ESPERADAS.issubset(columnas):
                faltan = COLUMNAS_ESPERADAS - columnas
                con_problema.append((archivo.name, f"faltan columnas: {faltan}"))
                print(f"  ✗ {archivo.name}  ->  FALTAN COLUMNAS: {faltan}")
                continue

            n_filas = 0
            n_precio_invalido = 0
            for fila in lector:
                n_filas += 1
                try:
                    float(fila["precio"])
                except (ValueError, KeyError):
                    n_precio_invalido += 1

            if n_filas == 0:
                con_problema.append((archivo.name, "el archivo tiene encabezado pero 0 filas de datos"))
                print(f"  ✗ {archivo.name}  ->  SIN FILAS (solo encabezado)")
            elif n_precio_invalido > 0:
                con_problema.append((archivo.name, f"{n_precio_invalido} precios inválidos"))
                print(f"  ⚠ {archivo.name}  ->  {n_filas:,} filas, "
                      f"{n_precio_invalido} con precio inválido")
            else:
                print(f"  ✓ {archivo.name}  ->  {n_filas:,} filas, OK")

        except (gzip.BadGzipFile, OSError, UnicodeDecodeError) as exc:
            con_problema.append((archivo.name, f"{type(exc).__name__}: {exc}"))
            print(f"  ✗ {archivo.name}  ->  CORRUPTO: {type(exc).__name__}: {exc}")

    print()
    if con_problema:
        print(f"⚠ {len(con_problema)} archivo(s) con problemas:")
        for nombre, motivo in con_problema:
            print(f"  - {nombre}: {motivo}")
        print("\nQUÉ HACER:")
        print("  Si un archivo está corrupto, lo más seguro es regenerarlo desde la base")
        print("  local (que sí tiene el dato correcto, si nunca se borró):")
        print(f"    python -m scripts.exportar_dia --rehacer")
        print("  Después subir de nuevo: git add historico/ && git commit -m \"arreglo\" && git push")
    else:
        print("✓ Todos los archivos son válidos y se pueden leer sin error.")


if __name__ == "__main__":
    main()
