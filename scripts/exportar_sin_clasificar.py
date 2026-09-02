#!/usr/bin/env python3
"""
Exporta TODAS las descripciones de producto que no matchean ninguna regla
de clasificación hoy — únicas, con cuántas veces aparecen, ordenadas de
más a menos frecuente. Pensado para revisar la lista completa (no solo
un resumen de palabras sueltas) y decidir, producto por producto, cuáles
deberían clasificarse y en qué categoría.

Acepta CUALQUIERA de las tres formas en que puede estar tu carpeta
datos_sepa/ — el mismo criterio que ya usa scripts/correr_dia.py, para
no obligarte a reacomodar nada:

    python -m scripts.exportar_sin_clasificar --archivo datos_sepa/sepa_lunes.zip
        # un ZIP diario sin descomprimir

    python -m scripts.exportar_sin_clasificar --carpeta datos_sepa/2026-08-10
        # una sola carpeta de fecha ya descomprimida (contiene los .zip
        # de cada comercio sueltos)

    python -m scripts.exportar_sin_clasificar --carpeta datos_sepa/
        # la carpeta MADRE con varios días adentro — detecta solos tanto
        # los .zip diarios como las carpetas de fecha ya descomprimidas
        # que haya, y los procesa todos juntos

Con --todo-el-pais se analizan las 6 regiones en vez de solo GBA (por
defecto), más lento pero exhaustivo.

Genera `sin_clasificar.csv`, abrible en Excel, con columnas:
Descripción | Veces vista | Comercios distintos | (columna vacía para
completar a mano con la subcategoría sugerida).

CÓMO USAR EL RESULTADO:
Abrí el CSV ordenado por "Veces vista" —ya viene así—, y completá la
última columna con la subcategoría que le corresponde a cada descripción.
Las primeras 100-200 líneas suelen explicar la gran mayoría del volumen.
Cuando tengas la lista, pasámela y agrego las reglas en
collectors/sepa/mapeo.py, verificando cada una contra datos reales.

Nada de lo que este script hace modifica la base de datos ni el mapeo —
es solo de lectura y exportación, para investigar antes de decidir.
"""

from __future__ import annotations

import argparse
import collections
import csv
import io
import re
import zipfile
from pathlib import Path

from collectors.sepa.ingesta import _sucursales_de_directorio
from collectors.sepa.mapeo import clasificar
from collectors.sepa.sucursales import leer_sucursales_de_zip

RAIZ = Path(__file__).resolve().parent.parent
RE_FECHA = re.compile(r"20\d{2}-\d{2}-\d{2}")


def _analizar_comercio(inner: zipfile.ZipFile, id_comercio: str, sucursales: dict,
                       solo_gba: bool, contador: collections.Counter,
                       comercios_por_desc: dict) -> tuple[int, int]:
    """Recorre el productos.csv de UN comercio (streaming, fila por fila)
    y acumula en `contador` cada descripción sin clasificar. Es el núcleo
    compartido tanto para el caso ZIP-diario como para el caso
    carpeta-de-fecha-ya-descomprimida: en los dos, un comercio es
    exactamente un ZIP con un productos.csv adentro."""
    objetivo = next((f for f in inner.namelist() if f.lower().endswith("productos.csv")), None)
    if not objetivo:
        return 0, 0

    total = sin_clasificar = 0
    with inner.open(objetivo) as fh:
        texto = io.TextIOWrapper(fh, encoding="utf-8-sig", errors="replace")
        lector = csv.DictReader(texto, delimiter="|")
        columnas = lector.fieldnames or []
        col_desc = next((c for c in columnas if "descripcion" in c.lower()), None)
        col_cad = next((c for c in columnas if c.lower() in ("id_bandera", "id_comercio")), None)
        col_suc = next((c for c in columnas if "sucursal" in c.lower()), None)
        if not col_desc:
            return 0, 0

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


def _procesar_zip_diario(path: Path, solo_gba: bool, contador: collections.Counter,
                         comercios_por_desc: dict) -> tuple[int, int]:
    """ZIP diario sin descomprimir: adentro hay una carpeta de fecha con
    un .zip por comercio."""
    sucursales = leer_sucursales_de_zip(path) if solo_gba else {}
    total = sin_clasificar = 0

    with zipfile.ZipFile(path) as z:
        internos = sorted(n for n in z.namelist() if n.lower().endswith(".zip"))
        for nombre in internos:
            try:
                inner = zipfile.ZipFile(io.BytesIO(z.read(nombre)))
            except (zipfile.BadZipFile, OSError):
                continue
            # Identificador de comercio: el nombre completo del archivo
            # interno. No se intenta "parsear" el patron real de SEPA
            # (sepa_1_comercio-sepa-12_..._.zip) partiendolo por "_" —
            # eso es fragil y en un intento anterior daba el mismo valor
            # "sepa" para todos los comercios (bug real, corregido).
            id_comercio = nombre.split("/")[-1]
            t, s = _analizar_comercio(inner, id_comercio, sucursales, solo_gba,
                                      contador, comercios_por_desc)
            total += t
            sin_clasificar += s

    return total, sin_clasificar


def _procesar_carpeta_de_fecha(carpeta: Path, solo_gba: bool, contador: collections.Counter,
                               comercios_por_desc: dict) -> tuple[int, int]:
    """Carpeta YA DESCOMPRIMIDA con los .zip de cada comercio sueltos
    adentro — el mismo caso que ya soporta
    collectors.sepa.ingesta.procesar_directorio_fecha."""
    sucursales = _sucursales_de_directorio(carpeta) if solo_gba else {}
    total = sin_clasificar = 0

    for archivo in sorted(carpeta.glob("*.zip")):
        try:
            inner = zipfile.ZipFile(archivo)
        except (zipfile.BadZipFile, OSError):
            continue
        t, s = _analizar_comercio(inner, archivo.name, sucursales, solo_gba,
                                  contador, comercios_por_desc)
        total += t
        sin_clasificar += s
        inner.close()

    return total, sin_clasificar


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    grupo = ap.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--archivo", type=Path, help="un solo ZIP diario, sin descomprimir")
    grupo.add_argument("--carpeta", type=Path,
                       help="una carpeta de fecha ya descomprimida, o la carpeta madre "
                            "con varios días adentro (ZIP y/o carpetas de fecha, mezclados)")
    ap.add_argument("--todo-el-pais", action="store_true",
                    help="analizar las 6 regiones, no solo GBA (más lento, más exhaustivo)")
    ap.add_argument("--salida", default="sin_clasificar.csv")
    args = ap.parse_args()

    solo_gba = not args.todo_el_pais
    contador: collections.Counter = collections.Counter()
    comercios_por_desc: dict = {}
    total_general = sin_clasificar_general = 0

    if args.archivo:
        print(f"Procesando {args.archivo.name} (ZIP diario)...")
        total, sin_clasif = _procesar_zip_diario(args.archivo, solo_gba, contador, comercios_por_desc)
        total_general += total
        sin_clasificar_general += sin_clasif
        print(f"  {total:,} filas, {sin_clasif:,} sin clasificar")
    else:
        carpeta = args.carpeta
        # Si la carpeta pasada YA ES una carpeta de fecha (su propio
        # nombre es una fecha y tiene .zip de comercios sueltos adentro),
        # se procesa directo. Si no, se asume que es la carpeta MADRE y
        # se buscan adentro tanto .zip diarios como sub-carpetas de fecha.
        es_carpeta_de_fecha = bool(RE_FECHA.search(carpeta.name)) and list(carpeta.glob("*.zip"))

        if es_carpeta_de_fecha:
            print(f"Procesando {carpeta.name} (carpeta de fecha descomprimida)...")
            total, sin_clasif = _procesar_carpeta_de_fecha(carpeta, solo_gba, contador, comercios_por_desc)
            total_general += total
            sin_clasificar_general += sin_clasif
            print(f"  {total:,} filas, {sin_clasif:,} sin clasificar")
        else:
            zips_diarios = sorted(carpeta.glob("*.zip"))
            carpetas_fecha = sorted(p for p in carpeta.iterdir()
                                    if p.is_dir() and RE_FECHA.search(p.name))

            if not zips_diarios and not carpetas_fecha:
                print(f"No encontré ningún .zip ni carpeta de fecha dentro de {carpeta}.")
                return

            print(f"Detectados: {len(zips_diarios)} ZIP diarios, "
                  f"{len(carpetas_fecha)} carpetas de fecha descomprimidas.\n")

            for archivo in zips_diarios:
                print(f"Procesando {archivo.name} (ZIP diario)...")
                total, sin_clasif = _procesar_zip_diario(archivo, solo_gba, contador, comercios_por_desc)
                total_general += total
                sin_clasificar_general += sin_clasif
                print(f"  {total:,} filas, {sin_clasif:,} sin clasificar")

            for sub in carpetas_fecha:
                print(f"Procesando {sub.name} (carpeta de fecha)...")
                total, sin_clasif = _procesar_carpeta_de_fecha(sub, solo_gba, contador, comercios_por_desc)
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
