#!/usr/bin/env python3
"""
Reclasifica TODOS los productos ya cargados en la base, aplicando las
reglas de mapeo.py ACTUALES — sin volver a leer ni un solo archivo de
SEPA. Pensado para el problema real de "cada vez que mejoro una regla,
tengo que borrar todo y recargar los ~14,5 millones de filas por día
desde cero, lo que tarda horas".

    python -m scripts.reclasificar

POR QUE ESTO ES POSIBLE SIN VOLVER A LEER SEPA:
El nombre real de cada producto (la descripción tal como vino en el
archivo original) ya se guarda de forma permanente en la tabla
`productos` — nunca se descarta después de clasificar una vez. Reclasificar
consiste en volver a correr `clasificar()` sobre esos nombres YA
GUARDADOS (unos cientos de miles, uno por producto único), no sobre las
filas crudas (14,5 millones POR DÍA). Es, en la práctica, cientos de veces
más rápido que recargar todo desde los ZIP de SEPA.

QUÉ HACE, PASO A PASO:
  1. Lee cada producto único de la tabla `productos` (ean_o_id + nombre).
  2. Le vuelve a aplicar `clasificar()` con las reglas actuales de
     mapeo.py.
  3. Si el resultado es DISTINTO al que tenía guardado en `precios_raw`,
     actualiza esa fila. Si es igual, no toca nada (para no reescribir
     millones de filas sin necesidad).
  4. Si el resultado nuevo es `None` (ya no matchea ninguna regla —
     pasaría si se saca una palabra clave), esas filas se BORRAN de
     `precios_raw`: es lo correcto, no dejarlas con una clase vieja que
     ya no corresponde. Esto es raro en la práctica (normalmente las
     reglas se agregan, no se sacan), pero se maneja explícito.

Al final, muestra un resumen de cuántos productos cambiaron de
clasificación y hacia dónde, y recuerda regenerar el respaldo y subirlo.

    python -m scripts.reclasificar --simular

Muestra qué cambiaría, SIN escribir nada en la base — para revisar antes
de aplicar de verdad.
"""

from __future__ import annotations

import argparse
import collections
from pathlib import Path

from collectors.sepa.mapeo import clasificar
from storage.db import conectar

RAIZ = Path(__file__).resolve().parent.parent
DB_PATH = RAIZ / "relevamiento_precios.db"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--simular", action="store_true",
                    help="mostrar que cambiaria, sin escribir nada en la base")
    args = ap.parse_args()

    if not DB_PATH.exists():
        print(f"No encuentro la base {DB_PATH}. Cargá al menos un día primero.")
        return

    con = conectar(DB_PATH)

    print("Leyendo productos únicos ya guardados...")
    productos = con.execute("SELECT ean_o_id, nombre_producto FROM productos").fetchall()
    print(f"  {len(productos):,} productos únicos en la base\n")

    # Para cada EAN, cual es la clase que HOY tiene asignada en precios_raw.
    # Un mismo EAN puede, en teoria, tener quedado con distintas clases en
    # distintas filas si algo raro paso antes — se usa la mas frecuente
    # como "la actual" para decidir si conviene actualizar.
    print("Consultando la clase actual de cada producto en precios_raw...")
    filas_por_ean = collections.defaultdict(collections.Counter)
    for ean, clase in con.execute("SELECT ean_o_id, clase_codigo FROM precios_raw"):
        filas_por_ean[ean][clase] += 1

    cambios: dict[str, tuple[str | None, str | None]] = {}
    a_borrar: list[str] = []

    for ean, nombre in productos:
        clase_nueva = clasificar(nombre, ean=ean)
        clases_actuales = filas_por_ean.get(ean)
        if not clases_actuales:
            continue  # producto sin ninguna fila en precios_raw (no debería pasar)
        clase_actual = clases_actuales.most_common(1)[0][0]

        if clase_nueva == clase_actual:
            continue

        cambios[ean] = (clase_actual, clase_nueva)
        if clase_nueva is None:
            a_borrar.append(ean)

    if not cambios:
        print("\nNingún producto cambia de clasificación con las reglas actuales.")
        con.close()
        return

    print(f"\n{len(cambios):,} producto(s) cambiarían de clasificación:\n")
    resumen = collections.Counter()
    for ean, (actual, nueva) in cambios.items():
        resumen[(actual, nueva)] += 1
    for (actual, nueva), n in sorted(resumen.items(), key=lambda x: -x[1])[:30]:
        actual_str = actual or "(sin clasificar)"
        nueva_str = nueva or "(pasaría a sin clasificar → se borra)"
        print(f"  {n:>6,}  {actual_str} -> {nueva_str}")
    if len(resumen) > 30:
        print(f"  ... y {len(resumen) - 30} combinación(es) más")

    if args.simular:
        print(f"\n(Simulación: no se escribió nada. Corré sin --simular para aplicar.)")
        con.close()
        return

    print(f"\nAplicando {len(cambios):,} cambio(s)...")
    actualizados = 0
    for ean, (_actual, nueva) in cambios.items():
        if nueva is None:
            con.execute("DELETE FROM precios_raw WHERE ean_o_id = ?", (ean,))
        else:
            con.execute("UPDATE precios_raw SET clase_codigo = ? WHERE ean_o_id = ?", (nueva, ean))
        actualizados += 1
    con.commit()
    con.close()

    print(f"Listo: {actualizados:,} producto(s) actualizados en la base.")
    if a_borrar:
        print(f"({len(a_borrar)} quedaron sin clasificar y se borraron de precios_raw — "
              f"sus nombres siguen en la tabla 'productos' por si una regla futura los recupera)")
    print("\nPara que esto se refleje en el respaldo y en Streamlit:")
    print("  python -m scripts.exportar_dia --rehacer")
    print("  git add historico/ && git commit -m \"reclasificacion\" && git push")


if __name__ == "__main__":
    main()
