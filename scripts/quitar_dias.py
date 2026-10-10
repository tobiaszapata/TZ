#!/usr/bin/env python3
"""
Quita días ya cargados (feriados, sábados/domingos) SIN reiniciar todo.

    python -m scripts.quitar_dias --sabados-domingos --simular
    python -m scripts.quitar_dias --fechas 2026-08-17 2026-10-12 --simular
    python -m scripts.quitar_dias --sabados-domingos --fechas 2026-08-17

Sin --simular, pide confirmacion (o usa --si).

Que hace, por cada fecha a quitar:
  1. borra sus filas de `precios_raw` en la base local;
  2. MUEVE su respaldo historico/<fecha>.csv.gz a historico_quitados/
     (no lo borra: queda afuera de historico/, asi Streamlit no lo cuenta,
     pero lo podes recuperar si te arrepentis).

La tabla `productos` (nombres) no se toca: es compartida entre dias.

Por que alcanza con eso: Streamlit Cloud compara la cantidad de dias de
historico/ con la de la base y reconstruye si difieren. Al subir a GitHub
un historico/ con menos dias, la proxima carga en frio reconstruye solo
con los dias que dejaste.

NO tiene logica de feriados: los feriados los indicas vos con --fechas.
--sabados-domingos mira SOLO las fechas que YA estan cargadas.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DB_PATH = RAIZ / "relevamiento_precios.db"
HISTORICO = RAIZ / "historico"
DESTINO = RAIZ / "historico_quitados"


def _es_fin_de_semana(fecha: str) -> bool:
    return date.fromisoformat(fecha).weekday() >= 5


def fechas_cargadas(db_path: Path, historico: Path) -> set[str]:
    out = {p.name[:-len(".csv.gz")] for p in historico.glob("*.csv.gz")} if historico.exists() else set()
    if db_path.exists():
        con = sqlite3.connect(db_path)
        try:
            out |= {r[0] for r in con.execute("SELECT DISTINCT fecha FROM precios_raw")}
        finally:
            con.close()
    return out


def quitar(fechas: list[str], db_path: Path, historico: Path, destino: Path,
           simular: bool = False) -> dict:
    """Devuelve {'filas': {fecha: n}, 'respaldos_movidos': [...]}."""
    resumen = {"filas": {}, "respaldos_movidos": []}
    con = sqlite3.connect(db_path, timeout=30) if db_path.exists() else None
    try:
        for f in sorted(fechas):
            n = 0
            if con is not None:
                n = con.execute("SELECT COUNT(*) FROM precios_raw WHERE fecha = ?", (f,)).fetchone()[0]
                if not simular and n:
                    con.execute("DELETE FROM precios_raw WHERE fecha = ?", (f,))
            resumen["filas"][f] = n
            resp = historico / f"{f}.csv.gz"
            if resp.exists():
                resumen["respaldos_movidos"].append(resp.name)
                if not simular:
                    destino.mkdir(exist_ok=True)
                    shutil.move(str(resp), str(destino / resp.name))
        if con is not None and not simular:
            con.commit()
    finally:
        if con is not None:
            con.close()
    return resumen


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fechas", nargs="*", default=[], help="fechas YYYY-MM-DD a quitar")
    ap.add_argument("--sabados-domingos", action="store_true",
                    help="quitar todos los sabados y domingos que esten cargados")
    ap.add_argument("--simular", action="store_true", help="solo mostrar, no cambiar nada")
    ap.add_argument("--si", action="store_true", help="no pedir confirmacion")
    args = ap.parse_args()

    for f in args.fechas:
        try:
            date.fromisoformat(f)
        except ValueError:
            raise SystemExit(f"Fecha invalida: {f!r} (usa YYYY-MM-DD)")

    cargadas = fechas_cargadas(DB_PATH, HISTORICO)
    a_quitar = set(args.fechas)
    if args.sabados_domingos:
        a_quitar |= {f for f in cargadas if _es_fin_de_semana(f)}
    no_estan = sorted(a_quitar - cargadas)
    a_quitar &= cargadas
    if no_estan:
        print("Ignoradas (no estaban cargadas):", ", ".join(no_estan))
    if not a_quitar:
        print("No hay nada para quitar.")
        return

    resumen = quitar(sorted(a_quitar), DB_PATH, HISTORICO, DESTINO, simular=True)
    print(f"Dias a quitar ({len(a_quitar)}) — quedarian {len(cargadas) - len(a_quitar)} de {len(cargadas)}:")
    for f, n in resumen["filas"].items():
        print(f"  {f} ({'SAB/DOM' if _es_fin_de_semana(f) else 'dia de semana'})  {n:,} filas en la base")
    if args.simular:
        print("\n(--simular: no se cambio nada)")
        return
    if not args.si and input("\n¿Quitarlos? (s/n): ").strip().lower() not in ("s", "si", "sí"):
        print("Cancelado.")
        return
    quitar(sorted(a_quitar), DB_PATH, HISTORICO, DESTINO)
    print(f"Listo. Respaldos movidos a {DESTINO.name}/. Ahora subi el cambio a GitHub (ver pasos).")


if __name__ == "__main__":
    main()
