#!/usr/bin/env python3
"""
Muestra el detalle región por región de cómo se combina una categoría a
nivel nacional — pensado para contrastar contra un cálculo hecho a mano.

    python -m scripts.verificar_ponderadores --clase 01.1.6 \
        --desde 2026-08-01 --hasta 2026-08-31 \
        --desde-base 2026-07-01 --hasta-base 2026-07-31

POR QUE ESTA HERRAMIENTA EXISTE:
Si tu cuenta manual (variación de cada región × peso de esa región sobre
el nacional) da un número distinto al que muestra la aplicación, lo más
fácil es que la diferencia esté en la RENORMALIZACIÓN: si una región no
tiene datos para esa categoría en ese período puntual, el sistema la
EXCLUYE y reparte el 100% del peso entre las regiones que sí aportaron
dato — no divide por el peso de las 6 regiones si falta alguna. Un
cálculo manual que sí divida siempre por el total de las 6 va a diferir,
aunque sea poco, de éste. Esta herramienta imprime exactamente los números
que usa el sistema para que se pueda comparar renglón por renglón.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from config.canasta import CANASTA, PESO_REGION
from engine.consultas import variacion_clase
from storage.db import conectar

DB_PATH = Path("relevamiento_precios.db")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clase", required=True, help="código de la subcategoría, ej. 01.1.6")
    ap.add_argument("--desde", required=True)
    ap.add_argument("--hasta", required=True)
    ap.add_argument("--desde-base", required=True, dest="desde_base")
    ap.add_argument("--hasta-base", required=True, dest="hasta_base")
    args = ap.parse_args()

    if not DB_PATH.exists():
        print(f"No encuentro la base {DB_PATH}.")
        return

    con = conectar(DB_PATH)
    nombre = CANASTA[args.clase].nombre if args.clase in CANASTA else args.clase

    print(f"\n{'='*72}\n  {args.clase}  {nombre}")
    print(f"  [{args.desde} .. {args.hasta}] contra [{args.desde_base} .. {args.hasta_base}]")
    print(f"{'='*72}\n")

    print(f"  {'región':<12} {'peso oficial':>13} {'variación':>12} {'¿tiene dato?':>13}")
    print(f"  {'-'*12} {'-'*13} {'-'*12} {'-'*13}")

    valores, pesos_usados = {}, {}
    for region in PESO_REGION:
        res, _ = variacion_clase(con, args.clase, args.desde, args.hasta,
                                 args.desde_base, args.hasta_base, region)
        peso = PESO_REGION[region] * 100
        if res is not None:
            valores[region] = res.variacion_pct
            pesos_usados[region] = PESO_REGION[region]
            print(f"  {region:<12} {peso:>12.2f}% {res.variacion_pct:>+11.2f}% {'sí':>13}")
        else:
            print(f"  {region:<12} {peso:>12.2f}% {'—':>12} {'NO (se excluye)':>13}")

    if not valores:
        print("\n  Ninguna región tiene datos para esta categoría en este período.")
        con.close()
        return

    peso_total_6 = sum(PESO_REGION.values()) * 100
    peso_cubierto = sum(pesos_usados.values()) * 100
    numerador = sum(PESO_REGION[r] * valores[r] for r in valores)

    print(f"\n  Peso de las 6 regiones (debería ser ~100%): {peso_total_6:.2f}%")
    print(f"  Peso cubierto por las regiones CON dato:     {peso_cubierto:.2f}%")

    resultado_del_sistema = numerador / sum(pesos_usados.values())
    resultado_dividiendo_por_las_6 = numerador / sum(PESO_REGION.values())

    print(f"\n  >>> Resultado del sistema (renormalizado sobre {peso_cubierto:.1f}% cubierto):")
    print(f"      {resultado_del_sistema:+.4f}%")

    if peso_cubierto < peso_total_6 - 0.01:
        print(f"\n  >>> Si en cambio dividís por el 100% de las 6 regiones (sin renormalizar):")
        print(f"      {resultado_dividiendo_por_las_6:+.4f}%")
        print(f"\n  Diferencia entre las dos formas: "
              f"{abs(resultado_del_sistema - resultado_dividiendo_por_las_6):.4f} puntos.")
        print("  Si tu cálculo manual da un número parecido a la segunda línea, esa es la causa:")
        print("  hay que excluir la región sin dato del denominador, no solo del numerador.")
    else:
        print("\n  Las 6 regiones tienen dato: las dos formas de calcular coinciden acá.")
        print("  Si igual ves una diferencia con tu cálculo manual, revisá que estés usando")
        print("  los mismos pesos (Metodología N°32, Cuadro 6): GBA 44,7% · Pampeana 34,2% ·")
        print("  Noroeste 6,9% · Cuyo 5,2% · Patagonia 4,6% · Noreste 4,5%.")

    con.close()


if __name__ == "__main__":
    main()
