#!/usr/bin/env python3
"""
Reinicio limpio — borra la base local para empezar de cero.

    python -m scripts.reiniciar

Pide confirmacion antes de borrar nada. Borra:
  - relevamiento_precios.db   (la base de calculo)
  - logs/actualizar.log       (el registro de corridas anteriores)

NO BORRA (a proposito):
  - historico/                los respaldos comprimidos por dia. Son el
                               archivo permanente: si ya subiste dias a
                               GitHub, siguen ahi aunque borres la base
                               local. Si de verdad queres borrar todo,
                               agrega --con-historico.
  - datos_sepa/                los ZIP que ya bajaste de SEPA. Sirven para
                               volver a cargar sin tener que bajarlos de
                               nuevo (SEPA los borra a los 7 dias).

POR QUE EXISTE ESTE COMANDO: "empezar de cero" a mano significa acordarse
de borrar el archivo correcto sin borrar el que no hay que borrar. Esto lo
hace explicito y pide confirmacion, para que no sea un accidente.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

# Ancladas al archivo, no al directorio de trabajo del proceso —
# ver la explicacion completa en scripts/reconstruir.py.
RAIZ = Path(__file__).resolve().parent.parent
DB_PATH = RAIZ / "relevamiento_precios.db"
LOG_PATH = Path("logs/actualizar.log")
HISTORICO = Path("historico")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--con-historico", action="store_true",
                    help="tambien borrar historico/ (los respaldos comprimidos). "
                         "Normalmente NO hace falta: son el archivo permanente.")
    ap.add_argument("--si", action="store_true", help="no pedir confirmacion")
    args = ap.parse_args()

    a_borrar = []
    if DB_PATH.exists():
        a_borrar.append(f"  {DB_PATH}  (base de calculo)")
    if LOG_PATH.exists():
        a_borrar.append(f"  {LOG_PATH}  (registro de corridas)")
    if args.con_historico and HISTORICO.exists():
        a_borrar.append(f"  {HISTORICO}/  (TODOS los respaldos diarios — esto SI es definitivo)")

    if not a_borrar:
        print("No hay nada para borrar. Ya está limpio.")
        return

    print("Se va a borrar:")
    print("\n".join(a_borrar))
    if HISTORICO.exists() and not args.con_historico:
        print(f"\n  {HISTORICO}/ NO se toca (los respaldos diarios quedan intactos).")

    if not args.si:
        resp = input("\n¿Confirmás? Escribí 'si' para continuar: ").strip().lower()
        if resp != "si":
            print("Cancelado. No se borró nada.")
            return

    if DB_PATH.exists():
        DB_PATH.unlink()
        print(f"Borrado: {DB_PATH}")
    if LOG_PATH.exists():
        LOG_PATH.unlink()
        print(f"Borrado: {LOG_PATH}")
    if args.con_historico and HISTORICO.exists():
        shutil.rmtree(HISTORICO)
        print(f"Borrado: {HISTORICO}/")

    print("\nListo. Para arrancar de nuevo:")
    print("  python -m tests._runner        (verificar que el motor sigue sano)")
    print("  python -m scripts.correr_dia --archivo datos_sepa\\<archivo del dia>.zip --fecha AAAA-MM-DD")


if __name__ == "__main__":
    main()
