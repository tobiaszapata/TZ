#!/usr/bin/env python3
"""
Diagnostico de cobertura del mapeo: que productos NO se estan clasificando.

    python -m scripts.diagnosticar_mapeo --archivo datos_sepa/sepa_lunes.zip

POR QUE ESTA HERRAMIENTA EXISTE:
"Trackear la mayor cantidad de productos" no se resuelve escribiendo reglas
a ciegas: se resuelve MIDIENDO que quedo afuera y atacando lo que mas pesa.
Este script recorre un dia real, junta los productos sin clasificar,
y los ordena por cuantas veces aparecen. Las primeras 50 lineas de esa
lista suelen explicar una porcion enorme del faltante.

El flujo de mejora es: correr esto -> mirar el top -> agregar reglas para
lo que corresponda -> volver a correr y ver como sube la cobertura.

IMPORTANTE — NO TODO LO SIN CLASIFICAR DEBE CLASIFICARSE. SEPA incluye
categorias que NO forman parte del IPC o que corresponden a divisiones que
no medimos (ferreteria, electro, jardineria, alimento para mascotas — este
ultimo excluido a pedido). Una cobertura del 100% seria una senal de que
estamos metiendo cosas donde no van, no de que esta bien.
"""

from __future__ import annotations

import argparse
import collections
import csv
import io
import re
import zipfile
from pathlib import Path

from collectors.sepa.mapeo import clasificar, normalizar
from collectors.sepa.sucursales import leer_sucursales_de_zip

# palabras sin valor informativo para el ranking de terminos
VACIAS = {"de","del","la","el","con","sin","por","para","und","uni","gr","grm","ml",
          "kg","cc","lt","paq","bot","lat","cja","pack","x","d","sob","est","pou",
          "fwp","doy","gat","fra","bli","bde","ttb","sch","aer","pet","un","kgm"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--archivo", type=Path, required=True)
    ap.add_argument("--comercios", type=int, default=4,
                    help="cuantos comercios analizar (default 4, para que sea rapido)")
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--todo-el-pais", action="store_true",
                    help="no filtrar por GBA (por defecto solo GBA)")
    args = ap.parse_args()

    solo_gba = not args.todo_el_pais
    sucursales = leer_sucursales_de_zip(args.archivo) if solo_gba else {}

    sin_clasificar = collections.Counter()
    terminos = collections.Counter()
    total = mapeadas = fuera = 0

    with zipfile.ZipFile(args.archivo) as z:
        internos = sorted(n for n in z.namelist() if n.lower().endswith(".zip"))
        for nombre in internos[: args.comercios]:
            try:
                inner = zipfile.ZipFile(io.BytesIO(z.read(nombre)))
            except Exception:
                continue
            obj = next((f for f in inner.namelist()
                        if f.lower().endswith("productos.csv")), None)
            if not obj:
                continue
            with inner.open(obj) as fh:
                rd = csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8-sig",
                                                     errors="replace"), delimiter="|")
                for fila in rd:
                    total += 1
                    if solo_gba:
                        suc = sucursales.get(((fila.get("id_comercio") or "").strip(),
                                              (fila.get("id_sucursal") or "").strip()))
                        if suc is None or not suc.es_gba:
                            fuera += 1
                            continue
                    desc = (fila.get("productos_descripcion") or "").strip()
                    if clasificar(desc):
                        mapeadas += 1
                    else:
                        sin_clasificar[desc[:60]] += 1
                        for w in re.findall(r"[a-z]+", normalizar(desc)):
                            if len(w) > 3 and w not in VACIAS:
                                terminos[w] += 1
            del inner

    analizadas = total - fuera
    print(f"\n{'='*70}\nDIAGNOSTICO DE MAPEO — {args.archivo.name}")
    print(f"{'='*70}")
    print(f"filas totales          {total:>12,}")
    if solo_gba:
        print(f"descartadas (no GBA)   {fuera:>12,}")
    print(f"analizadas             {analizadas:>12,}")
    print(f"clasificadas           {mapeadas:>12,}   ({mapeadas/analizadas:.1%})")
    print(f"sin clasificar         {analizadas-mapeadas:>12,}   ({1-mapeadas/analizadas:.1%})")

    print(f"\n--- TERMINOS MAS FRECUENTES entre lo NO clasificado (top {args.top}) ---")
    print("    (cada uno es una regla potencial; ignorar los que no sean del IPC)")
    for palabra, n in terminos.most_common(args.top):
        print(f"  {n:>9,}  {palabra}")

    print(f"\n--- DESCRIPCIONES sin clasificar mas repetidas (top 25) ---")
    for desc, n in sin_clasificar.most_common(25):
        print(f"  {n:>7,}  {desc}")


if __name__ == "__main__":
    main()
