#!/usr/bin/env python3
"""
Audita, división por división Y subcategoría por subcategoría, tres
niveles de cobertura que NO son lo mismo — pensado para responder con
precisión preguntas del tipo "¿esta categoría está completa?", y para
identificar qué subcategorías puntuales (dentro de una división que ya
tiene cosas medidas) serían candidatas a complementar con web scraping
más adelante.

  1. MEDIDO: subcategorías con dato real de SEPA.
  2. DECLARADO SIN MEDIR: subcategorías que el sistema conoce (con su peso
     oficial) pero sin ninguna fuente de datos todavía. Se marcan además
     con un tipo de bien orientativo (ver _tipo_de_bien), porque no todas
     son igual de viables por scraping: un producto físico con precio de
     lista en un sitio de venta es mucho más simple que un servicio o una
     tarifa regulada.
  3. NI SIQUIERA DECLARADO: parte del peso oficial de la división para la
     que no hay NINGUNA subcategoría cargada en config/canasta.py — un
     hueco estructural, no solo de datos.

    python -m scripts.auditar_cobertura

Exporta además `auditoria_cobertura.csv` (una fila por subcategoría, todas
las divisiones) para trabajar el detalle en Excel.

    python -m scripts.auditar_cobertura --division 06

Limita el detalle impreso a una sola división (el CSV exportado sigue
siendo completo, con todas).
"""

from __future__ import annotations

import argparse
import csv as csv_module
from pathlib import Path

from config.canasta import CANASTA, Cobertura, cobertura_estructural_division, clases_de_division, divisiones

RAIZ = Path(__file__).resolve().parent.parent

# Clasificación orientativa de qué tan viable es, en principio, sumar una
# subcategoría PENDIENTE por web scraping — no es una promesa de que sea
# fácil, es una primera señal para priorizar. Basada en si el "bien" tiene
# un precio de lista simple y público (una heladera en una web de venta)
# frente a algo que no lo tiene (un alquiler, una consulta médica).
_BIEN_TANGIBLE_SCRAPEABLE = {
    "03.1.1", "03.1.3", "05.1.1", "05.3.1", "05.5.1", "06.1.3",
    "07.1.1", "07.1.2", "07.1.3", "08.2.1", "08.2.2",
    "09.1.1", "09.1.2", "09.1.3", "09.1.4", "09.3.2", "09.5.1", "09.5.2", "09.5.4",
}
_TARIFA_REGULADA_O_COMBUSTIBLE = {
    "04.5.1", "04.5.2", "07.2.2", "08.3.1", "08.3.2", "08.3.3",
}
_SERVICIO_O_ALQUILER_DIFICIL = {
    "03.1.4", "03.2.2", "04.1.1", "04.1.3", "04.3.1", "04.3.2",
    "06.2.1", "06.2.2", "06.2.3", "07.2.1", "07.2.3", "07.2.4",
    "07.3.2", "07.3.3", "07.3.6", "09.4.1", "09.4.2", "12.1.1",
}


def _tipo_de_bien(codigo: str) -> str:
    if codigo in _BIEN_TANGIBLE_SCRAPEABLE:
        return "Bien físico — scraping en principio viable"
    if codigo in _TARIFA_REGULADA_O_COMBUSTIBLE:
        return "Tarifa regulada / combustible — mejor cargar calendario oficial que scrapear"
    if codigo in _SERVICIO_O_ALQUILER_DIFICIL:
        return "Servicio o alquiler — sin precio de lista simple, scraping poco viable"
    return "—"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--division", help="limitar el detalle impreso a una sola división (ej. 06)")
    ap.add_argument("--salida", default="auditoria_cobertura.csv")
    args = ap.parse_args()

    print(f"\n{'='*110}")
    print("  AUDITORÍA DE COBERTURA — nivel nacional (pesos de GBA, usados como referencia)")
    print(f"{'='*110}\n")

    total_medido = total_declarado_sin_medir = total_sin_declarar = total_division = 0.0
    filas_csv = []

    for d in divisiones():
        r = cobertura_estructural_division(d.codigo)
        referencia = r["referencia"]

        total_medido += r["medido"]
        total_declarado_sin_medir += r["declarado_sin_medir"]
        total_sin_declarar += r["sin_declarar"]
        total_division += referencia

        pct_medido = r["medido"] / referencia * 100 if referencia else 0
        pct_declarado = r["declarado_sin_medir"] / referencia * 100 if referencia else 0
        pct_sin_declarar = r["sin_declarar"] / referencia * 100 if referencia else 0

        mostrar = not args.division or args.division == d.codigo
        if mostrar:
            print(f"{d.codigo}  {d.nombre}  (peso oficial: {referencia*100:.2f}% de la canasta)")
            print(f"      Medido con SEPA:................ {pct_medido:5.1f}%")
            print(f"      Declarado pero sin medir:........ {pct_declarado:5.1f}%")
            if r["sin_declarar"] > 0.0001:
                print(f"      ⚠ SIN NINGUNA SUBCATEGORÍA CARGADA: {pct_sin_declarar:5.1f}%  "
                      f"<-- hueco estructural, no solo de datos")

        clases = clases_de_division(d.codigo)
        for c in clases:
            peso_gba = c.peso("GBA")
            pct_de_su_division = peso_gba / referencia * 100 if referencia else 0
            marca = ("MEDIDA" if c.cobertura == Cobertura.MEDIDA_SEPA
                    else c.cobertura.value.upper())
            tipo_bien = _tipo_de_bien(c.codigo) if c.cobertura == Cobertura.PENDIENTE else "—"

            if mostrar:
                linea = (f"        {c.codigo}  {c.nombre:<48} "
                        f"{peso_gba*100:5.2f}% del país  ({pct_de_su_division:4.1f}% de la división)  [{marca}]")
                print(linea)
                if tipo_bien != "—":
                    print(f"              → {tipo_bien}")

            filas_csv.append([
                d.codigo, d.nombre, c.codigo, c.nombre,
                f"{peso_gba*100:.4f}", f"{pct_de_su_division:.1f}", marca, tipo_bien,
            ])
        if mostrar:
            print()

    if not args.division:
        print(f"{'='*110}")
        print("  RESUMEN NACIONAL (suma de las 12 divisiones)")
        print(f"{'='*110}")
        print(f"  Medido con SEPA:......................... {total_medido*100:6.2f}%  "
              f"({total_medido/total_division*100:.1f}% de la canasta total)")
        print(f"  Declarado, con peso conocido, sin medir:.. {total_declarado_sin_medir*100:6.2f}%")
        print(f"  Sin ninguna subcategoría cargada:......... {total_sin_declarar*100:6.2f}%")
        print(f"  {'-'*60}")
        print(f"  Total (debería ≈100%):.................... {total_division*100:6.2f}%")

    salida = RAIZ / args.salida
    with open(salida, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv_module.writer(fh)
        w.writerow(["Division (codigo)", "Division (nombre)", "Subcategoria (codigo)",
                   "Subcategoria (nombre)", "Peso % del pais", "% de su division",
                   "Estado", "Tipo de bien (si es PENDIENTE)"])
        w.writerows(filas_csv)
    print(f"\nDetalle completo exportado a {salida} (abrible en Excel).")


if __name__ == "__main__":
    main()
