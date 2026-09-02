#!/usr/bin/env python3
"""
Exporta TODAS las descripciones de producto que no matchean ninguna regla
de clasificación hoy — únicas, con cuántas veces aparecen, ordenadas de
más a menos frecuente. Pensado para revisar la lista completa (no solo
un resumen de palabras sueltas) y decidir, producto por producto, cuáles
deberían clasificarse y en qué categoría.

    python -m scripts.exportar_sin_clasificar --archivo datos_sepa/sepa_lunes.zip

Genera `sin_clasificar.csv`, abrible en Excel, con columnas:
Descripción | Veces vista | Comercios distintos donde aparece

    python -m scripts.exportar_sin_clasificar --carpeta datos_sepa/

Procesa TODOS los archivos de la carpeta juntos (varios días), acumulando
la frecuencia total — así un producto que aparece poco un día pero se
repite todos los días no queda subestimado.

    python -m scripts.exportar_sin_clasificar --archivo datos_sepa/sepa_lunes.zip --todo-el-pais

Por defecto se analiza solo GBA (más rápido, alcanza para tener una foto
representativa). Con esta opción se analizan las 6 regiones — tarda más
pero es exhaustivo.

CÓMO USAR EL RESULTADO:
Abrí el CSV en Excel, ordenado por "Veces vista" de mayor a menor —ya
viene así—, y andá marcando: para cada descripción, ¿a qué subcategoría
debería ir? Las primeras 100-200 líneas suelen explicar la gran mayoría
del volumen. Cuando tengas la lista de qué palabra va a qué categoría,
pasámela y agrego las reglas correspondientes en collectors/sepa/mapeo.py.

Nada de lo que este script hace modifica la base de datos ni el mapeo —
es solo de lectura y exportación, para investigar antes de decidir.
"""

from __future__ import annotations

import argparse
import collections
import csv
import io
import zipfile
from pathlib import Path

from collectors.sepa.mapeo import clasificar
from collectors.sepa.sucursales import leer_sucursales_de_zip

RAIZ = Path(__file__).resolve().parent.parent


def _procesar_un_zip(path: Path, solo_gba: bool, contador: collections.Counter,
                     comercios_por_desc: dict) -> tuple[int, int]:
    """Recorre un ZIP diario completo (todos los comercios, streaming fila
    por fila) y acumula en `contador` cada descripción sin clasificar.
    Devuelve (total_filas, total_sin_clasificar) de este archivo."""
    sucursales = leer_sucursales_de_zip(path) if solo_gba else {}
    total = sin_clasificar = 0

    with zipfile.ZipFile(path) as z:
        internos = sorted(n for n in z.namelist() if n.lower().endswith(".zip"))
        for nombre in internos:
            try:
                inner = zipfile.ZipFile(io.BytesIO(z.read(nombre)))
            except (zipfile.BadZipFile, OSError):
                continue
            objetivo = next((f for f in inner.namelist()
                             if f.lower().endswith("productos.csv")), None)
            if not objetivo:
                continue

            # Identificador de comercio: se usa el nombre completo del
            # archivo interno (no se intenta "parsear" el patron real de
            # SEPA, del tipo sepa_1_comercio-sepa-12_2026-08-10_09-05-10.zip,
            # porque partirlo por "_" es fragil y en un intento anterior
            # daba el mismo valor "sepa" para todos los comercios — un bug
            # real encontrado con un test que arma dos comercios distintos
            # y verifica que cuenten como 2, no como 1).
            id_comercio = nombre.split("/")[-1]

            with inner.open(objetivo) as fh:
                texto = io.TextIOWrapper(fh, encoding="utf-8-sig", errors="replace")
                lector = csv.DictReader(texto, delimiter="|")
                columnas = lector.fieldnames or []
                col_desc = next((c for c in columnas if "descripcion" in c.lower()), None)
                col_cad = next((c for c in columnas if c.lower() in ("id_bandera", "id_comercio")), None)
                col_suc = next((c for c in columnas if "sucursal" in c.lower()), None)
                if not col_desc:
                    continue

                for fila in lector:
                    total += 1

                    if solo_gba and sucursales and col_cad and col_suc:
                        clave = ((fila.get(col_cad) or "").strip(), (fila.get(col_suc) or "").strip())
                        suc = sucursales.get(clave)
                        if suc is None or suc.region != "GBA":
                            continue

                    desc = (fila.get(col_desc) or "").strip()
                    if not desc:
                        continue
                    if clasificar(desc) is not None:
                        continue

                    sin_clasificar += 1
                    desc_norm = desc.upper()
                    contador[desc_norm] += 1
                    comercios_por_desc.setdefault(desc_norm, set()).add(id_comercio)

    return total, sin_clasificar


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    grupo = ap.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--archivo", type=Path, help="un solo ZIP diario")
    grupo.add_argument("--carpeta", type=Path, help="carpeta con varios ZIP (todos los días juntos)")
    ap.add_argument("--todo-el-pais", action="store_true",
                    help="analizar las 6 regiones, no solo GBA (más lento, más exhaustivo)")
    ap.add_argument("--salida", default="sin_clasificar.csv")
    args = ap.parse_args()

    solo_gba = not args.todo_el_pais
    archivos = [args.archivo] if args.archivo else sorted(args.carpeta.glob("*.zip"))
    if not archivos:
        print(f"No encontré ningún .zip para procesar.")
        return

    contador: collections.Counter = collections.Counter()
    comercios_por_desc: dict = {}
    total_general = sin_clasificar_general = 0

    for archivo in archivos:
        print(f"Procesando {archivo.name}...")
        total, sin_clasif = _procesar_un_zip(archivo, solo_gba, contador, comercios_por_desc)
        total_general += total
        sin_clasificar_general += sin_clasif
        print(f"  {total:,} filas, {sin_clasif:,} sin clasificar")

    salida = RAIZ / args.salida
    with open(salida, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["Descripcion", "Veces vista", "Comercios distintos",
                   "-> Subcategoria sugerida (completar a mano)"])
        for desc, veces in contador.most_common():
            n_comercios = len(comercios_por_desc.get(desc, set()))
            w.writerow([desc, veces, n_comercios, ""])

    print(f"\n{'='*70}")
    print(f"Total analizado: {total_general:,} filas ({'solo GBA' if solo_gba else 'todo el país'})")
    print(f"Sin clasificar: {sin_clasificar_general:,}")
    print(f"Descripciones ÚNICAS sin clasificar: {len(contador):,}")
    print(f"\nExportado a: {salida}")
    print("Abrí en Excel (ya viene ordenado por frecuencia), y completá la última")
    print("columna con la subcategoría que le corresponde a cada una. Cuando la")
    print("tengas lista, pasámela y agrego las reglas correspondientes.")


if __name__ == "__main__":
    main()
