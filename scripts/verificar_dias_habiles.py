#!/usr/bin/env python3
"""
Verifica, ANTES de cargar, si en datos_sepa/ (o la carpeta que se le pase)
hay algún archivo o carpeta de fecha correspondiente a sábado o domingo.

Pensado para el criterio metodológico ya decidido: la Metodología N°32 de
INDEC solo usa días hábiles, y la forma elegida de cumplir con eso es
simplemente no descargar los archivos de SEPA de fin de semana (no un
filtro automático en el código, que no reconocería feriados).

    python -m scripts.verificar_dias_habiles --carpeta datos_sepa/

Muestra cada fecha detectada, marcando cuáles son sábado o domingo, y al
final un resumen con la cantidad de días hábiles vs. no hábiles. No borra
ni mueve nada — es solo de diagnóstico, para revisar antes de correr
`scripts.correr_dia`.

NOTA sobre feriados: esta herramienta NO reconoce feriados nacionales,
porque no hay una fuente de feriados conectada al proyecto. Detecta
únicamente sábados y domingos por el día de la semana. Si un feriado cae
entre semana (lunes a viernes), hay que excluirlo a mano — no aparece
marcado acá.
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from scripts.correr_dia import fecha_desde_nombre

DIAS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--carpeta", type=Path, default=Path("datos_sepa"),
                    help="carpeta a revisar (default: datos_sepa/)")
    args = ap.parse_args()

    if not args.carpeta.exists():
        print(f"No encuentro la carpeta {args.carpeta}")
        return

    # Mismo criterio de deteccion que scripts.correr_dia: ZIP/CSV sueltos
    # o carpetas de fecha ya descomprimidas.
    zips = [p for p in args.carpeta.iterdir() if p.suffix.lower() in (".zip", ".csv")]
    carpetas_fecha = [p for p in args.carpeta.iterdir()
                      if p.is_dir() and fecha_desde_nombre(p.name)]
    archivos = sorted(zips + carpetas_fecha)

    if not archivos:
        print(f"No encontré ningún archivo ni carpeta de fecha en {args.carpeta}")
        return

    fines_de_semana = []
    habiles = []
    sin_fecha_detectable = []

    for archivo in archivos:
        fecha_str = fecha_desde_nombre(archivo.name)
        if not fecha_str:
            sin_fecha_detectable.append(archivo.name)
            continue
        anio, mes, dia = (int(x) for x in fecha_str.split("-"))
        d = date(anio, mes, dia)
        dia_semana = DIAS_ES[d.weekday()]
        if d.weekday() >= 5:
            fines_de_semana.append((fecha_str, dia_semana, archivo.name))
        else:
            habiles.append((fecha_str, dia_semana, archivo.name))

    print(f"Revisando {args.carpeta}...\n")

    if habiles:
        print(f"✅ Días hábiles detectados ({len(habiles)}):")
        for fecha_str, dia_semana, nombre in sorted(habiles):
            print(f"   {fecha_str}  ({dia_semana:<10}) — {nombre}")

    if fines_de_semana:
        print(f"\n⚠️  Fines de semana detectados ({len(fines_de_semana)}) — "
              "según el criterio metodológico, NO deberían cargarse:")
        for fecha_str, dia_semana, nombre in sorted(fines_de_semana):
            print(f"   {fecha_str}  ({dia_semana:<10}) — {nombre}")
        print("\n   Sacá estos archivos de la carpeta (o movelos a otro lado) antes de")
        print("   correr scripts.correr_dia, para que no entren a la base.")

    if sin_fecha_detectable:
        print(f"\n❓ No se pudo extraer una fecha de estos ({len(sin_fecha_detectable)}):")
        for nombre in sin_fecha_detectable:
            print(f"   {nombre}")

    print(f"\n{'='*60}")
    print(f"Total: {len(archivos)}   Hábiles: {len(habiles)}   "
          f"Fin de semana: {len(fines_de_semana)}")
    if fines_de_semana:
        print("\n⚠️  Encontré fin de semana en la carpeta — revisar antes de cargar.")
    else:
        print("\n✅ Todo lo que hay en la carpeta es día hábil (lunes a viernes).")
    print("\nRecordá: esto NO reconoce feriados nacionales — si algún día entre")
    print("semana fue feriado, hay que sacarlo a mano, no aparece marcado acá.")


if __name__ == "__main__":
    main()
