#!/usr/bin/env python3
"""
Punto de entrada unico para CARGAR datos.

TRES FORMAS DE USARLO
---------------------------------------------------------------------------
1) INVENTARIO — mira que hay adentro de un ZIP de SEPA sin cargar nada.
   Esto es lo PRIMERO que conviene correr con un ZIP nuevo.

     python -m scripts.correr_dia --inventario sepa_2026-08-15.zip

2) UN DIA — carga un ZIP (o un CSV suelto) con su fecha.

     python -m scripts.correr_dia --archivo sepa_2026-08-15.zip --fecha 2026-08-15

3) UNA CARPETA ENTERA — carga de una vez todos los ZIP de una carpeta,
   deduciendo la fecha del nombre del archivo. Es lo que se usa la primera
   vez, para cargar un mes completo sin repetir el comando 20 veces.

     python -m scripts.correr_dia --carpeta datos_sepa/

   La fecha se saca del nombre: cualquier archivo que contenga una fecha
   tipo 2026-08-15 (o 20260815) la usa. Si un archivo no tiene fecha
   reconocible en el nombre, se informa y se saltea, no se adivina.
---------------------------------------------------------------------------

La carga es IDEMPOTENTE: correr el mismo archivo dos veces no duplica nada
(hay una restriccion de unicidad por fecha+producto+comercio). Por eso es
seguro re-ejecutar si algo se corto a la mitad.

Los datos se ACUMULAN: cada corrida agrega filas a la base, nunca pisa las
anteriores. Los calculos consultan la base entera por mes, no el ultimo
archivo cargado.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from collectors.sepa.ingesta import (
    observaciones, procesar_directorio_fecha, procesar_zip)
from collectors.sepa.parser import parsear_csv
from storage.db import conectar, insertar_observaciones, registrar_corrida

DB_PATH = Path("relevamiento_precios.db")

RE_FECHA_GUION = re.compile(r"(20\d{2})-(\d{2})-(\d{2})")
RE_FECHA_JUNTA = re.compile(r"(20\d{2})(\d{2})(\d{2})")


def _respaldar_automaticamente(con) -> None:
    """Guarda el respaldo comprimido de cualquier dia que todavia no lo
    tenga, apenas termina de cargar.

    POR QUE ESTO PASO A SER AUTOMATICO: antes habia que acordarse de correr
    `python -m scripts.exportar_dia` como paso aparte despues de cada carga.
    Si alguien se olvidaba, esos dias quedaban solo en la base local — y si
    la base se perdia o se reiniciaba sin haber respaldado, el dia se iba
    para siempre (SEPA no lo vuelve a tener disponible pasados 7 dias).
    Ahora es parte del mismo comando: cargar y respaldar son un solo paso,
    y no depende de la memoria de nadie.

    Reutiliza la logica de scripts/exportar_dia.py (no la duplica): esa es
    la fuente de verdad de "como se exporta un dia", esto solo la dispara."""
    from scripts.exportar_dia import CARPETA, dias_en_base, exportar_dia

    fechas = dias_en_base(con)
    CARPETA.mkdir(exist_ok=True)
    nuevos = 0
    for fecha in fechas:
        destino = CARPETA / f"{fecha}.csv.gz"
        if destino.exists():
            continue
        exportar_dia(con, fecha)
        nuevos += 1
    if nuevos:
        print(f"\nRespaldo automático: {nuevos} día(s) nuevo(s) guardados en {CARPETA}/")
        print("(para publicarlos: git add historico/ && git commit -m \"datos\" && git push)")


def fecha_desde_nombre(nombre: str) -> str | None:
    for rx in (RE_FECHA_GUION, RE_FECHA_JUNTA):
        m = rx.search(nombre)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def cargar_archivo(con, path: Path, fecha: str | None = None, verboso: bool = True) -> dict:
    """Carga un dia de SEPA. Acepta tres formas:
      - un ZIP diario sin tocar        (datos_sepa/sepa_lunes.zip)
      - una carpeta de fecha extraida  (datos_sepa/2026-08-10/)
      - un CSV suelto ya normalizado

    Las dos primeras usan la ingesta en streaming, que es la unica forma de
    procesar los ~14,5 millones de filas de un dia sin quedarse sin memoria.
    """
    if path.is_dir() or path.suffix.lower() == ".zip":
        res = (procesar_directorio_fecha(path, fecha) if path.is_dir()
               else procesar_zip(path, fecha))
        if not res.fecha:
            raise ValueError(
                f"No pude deducir la fecha de {path.name}. Pasala con --fecha."
            )
        fecha = res.fecha
        obs = observaciones(res)
        stats = {
            "n_filas": res.n_filas, "n_mapeadas": res.n_mapeadas,
            "n_sin_mapear": res.n_sin_mapear,
            "n_precio_invalido": res.n_precio_invalido,
            "tasa_mapeo": res.tasa_mapeo, "n_comercios": res.n_comercios,
            "n_productos": len(res.acumulado),
            "errores": res.comercios_con_error,
        }
    else:
        obs, stats = parsear_csv(path, fecha)

    n_nuevas = insertar_observaciones(con, obs)
    registrar_corrida(con, fecha, stats)

    if verboso:
        print(f"  {fecha}:")
        print(f"    filas leidas       {stats['n_filas']:>12,}"
              + (f"   ({stats['n_comercios']} comercios)" if "n_comercios" in stats else ""))
        print(f"    clasificadas       {stats['n_mapeadas']:>12,}   ({stats['tasa_mapeo']:.1%})")
        print(f"    sin clasificar     {stats['n_sin_mapear']:>12,}")
        if "n_productos" in stats:
            print(f"    productos unicos   {stats['n_productos']:>12,}   -> {n_nuevas:,} filas nuevas en la base")
        if stats.get("errores"):
            print(f"    comercios omitidos: {len(stats['errores'])} "
                  f"(archivo vacio o ilegible en el origen)")
        if stats["tasa_mapeo"] < 0.02 and stats["n_filas"] > 0:
            print("    AVISO: tasa de clasificacion muy baja. Revisar collectors/sepa/mapeo.py",
                  file=sys.stderr)
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inventario", type=Path, help="solo inspeccionar un ZIP, sin cargar")
    ap.add_argument("--archivo", type=Path, help="ZIP o CSV de un dia")
    ap.add_argument("--fecha", help="YYYY-MM-DD (obligatorio con --archivo)")
    ap.add_argument("--carpeta", type=Path, help="carpeta con varios ZIP a cargar de una vez")
    args = ap.parse_args()

    if args.inventario:
        from collectors.sepa.zip_reader import inventario
        print(inventario(args.inventario))
        print("\nSi las columnas de arriba no coinciden con las esperadas, agregá los")
        print("nombres correctos en ALIAS_COLUMNAS de collectors/sepa/schema.py")
        return

    if args.carpeta:
        # Se aceptan DOS estructuras adentro de la carpeta:
        #   (a) los ZIP diarios sin tocar     -> datos_sepa/sepa_lunes.zip
        #   (b) las carpetas de fecha ya      -> datos_sepa/2026-08-10/
        #       descomprimidas                             /2026-08-11/
        # Es comodo descomprimir para ver de un vistazo que dias hay, asi
        # que el sistema soporta las dos y no obliga a rehacer nada.
        zips = [p for p in args.carpeta.iterdir() if p.suffix.lower() in (".zip", ".csv")]
        carpetas_fecha = [p for p in args.carpeta.iterdir()
                          if p.is_dir() and fecha_desde_nombre(p.name)]
        archivos = sorted(zips + carpetas_fecha)
        if not archivos:
            print(f"No encontre nada para cargar en {args.carpeta}")
            print("Se esperan, adentro de esa carpeta, alguna de estas dos cosas:")
            print("  - los ZIP diarios de SEPA (ej. sepa_lunes.zip), o")
            print("  - las carpetas de fecha ya descomprimidas (ej. 2026-08-10/)")
            return
        if carpetas_fecha:
            print(f"  (detectadas {len(carpetas_fecha)} carpetas de fecha descomprimidas)")
        if zips:
            print(f"  (detectados {len(zips)} archivos ZIP)")
        print(f"== Carga por lote: {len(archivos)} archivos de {args.carpeta} ==\n")
        con = conectar(DB_PATH)
        cargados, salteados = 0, []
        for p in archivos:
            # la fecha sale del nombre; si no esta, procesar_zip la deduce
            # de la carpeta interna del ZIP (SEPA la incluye ahi)
            fecha = fecha_desde_nombre(p.name)
            try:
                cargar_archivo(con, p, fecha)
                cargados += 1
            except Exception as exc:
                print(f"  {p.name}: ERROR — {exc}", file=sys.stderr)
        print(f"\nListo: {cargados} archivos cargados.")
        if salteados:
            print(f"Salteados (sin fecha reconocible en el nombre): {salteados}")
            print("Renombralos incluyendo la fecha, o cargalos de a uno con --archivo/--fecha")

        if cargados:
            _respaldar_automaticamente(con)
        con.close()
        return

    if not args.archivo:
        ap.error("indica --inventario, o --archivo, o --carpeta")

    print("== Carga de un dia ==\n")
    con = conectar(DB_PATH)
    cargar_archivo(con, args.archivo, args.fecha)
    _respaldar_automaticamente(con)
    con.close()
    print("\nListo. Para ver resultados:")
    print("  python -m scripts.consultar resumen --mes YYYY-MM --contra YYYY-MM")


if __name__ == "__main__":
    main()
