#!/usr/bin/env python3
"""
Diagnóstico completo del estado local: qué días están cargados, cuáles
tienen respaldo, y en qué formato.

    python -m scripts.diagnosticar_estado

POR QUE ESTA HERRAMIENTA EXISTE: cuando algo "no aparece" en la app
publicada, hay tres lugares distintos donde puede haberse perdido el
rastro (la base local, el respaldo en historico/, o lo que efectivamente
llegó a GitHub) y sin verlos uno al lado del otro es dificil saber cual
es. Esto muestra los primeros dos; el tercero se confirma mirando el
repositorio en github.com o el log de "Manage app" en Streamlit Cloud.
"""

from __future__ import annotations

from pathlib import Path

from scripts.exportar_dia import VERSION_FORMATO, dias_en_base, version_del_respaldo
from storage.db import conectar

DB_PATH = Path("relevamiento_precios.db")
CARPETA = Path("historico")


def main() -> None:
    print(f"\n{'='*72}\n  DIAGNOSTICO DE ESTADO LOCAL\n{'='*72}\n")

    if not DB_PATH.exists():
        print(f"No existe {DB_PATH}. Corre primero scripts.correr_dia o scripts.reconstruir.")
        return

    con = conectar(DB_PATH)
    en_base = set(dias_en_base(con))
    con.close()

    en_historico: dict[str, int] = {}
    if CARPETA.exists():
        for archivo in sorted(CARPETA.glob("*.csv.gz")):
            # Path.stem solo saca UNA extension: "2026-08-09.csv.gz".stem
            # da "2026-08-09.csv", no "2026-08-09". Hay que sacar las dos.
            fecha = archivo.name.removesuffix(".csv.gz")
            en_historico[fecha] = version_del_respaldo(archivo)

    todas = sorted(en_base | set(en_historico))
    if not todas:
        print("No hay ningun dia ni en la base ni en historico/.")
        return

    print(f"{'fecha':<12} {'en base local':<15} {'en historico/':<15} {'formato'}")
    print(f"{'-'*12} {'-'*15} {'-'*15} {'-'*10}")
    problemas = []
    for fecha in todas:
        esta_en_base = "si" if fecha in en_base else "NO"
        if fecha in en_historico:
            v = en_historico[fecha]
            formato = "actual" if v >= VERSION_FORMATO else f"VIEJO (v{v}, sin nombres)"
            esta_en_hist = "si"
            if v < VERSION_FORMATO:
                problemas.append(f"{fecha}: respaldo en formato viejo")
        else:
            esta_en_hist, formato = "NO", "-"
            if fecha in en_base:
                problemas.append(f"{fecha}: esta en la base pero NO tiene respaldo")
        print(f"{fecha:<12} {esta_en_base:<15} {esta_en_hist:<15} {formato}")

    print(f"\nTotal: {len(en_base)} dias en la base, {len(en_historico)} respaldados.")

    if problemas:
        print(f"\n[!] {len(problemas)} cosa(s) para revisar:")
        for p in problemas:
            print(f"  - {p}")
        print("\nPara corregir: corre 'python -m scripts.correr_dia --carpeta datos_sepa/'")
        print("de nuevo (regenera respaldos viejos y faltantes automaticamente), y despues")
        print("subi lo nuevo con: git add historico/ && git commit -m \"datos\" && git push")
    else:
        print("\n[OK] Todo consistente: cada dia de la base tiene su respaldo, formato actual.")

    print(f"\n{'='*72}")
    print("Este diagnostico es SOLO LOCAL. Para confirmar que lo mismo llego a GitHub:")
    print("  1. Entra a tu repositorio en github.com, carpeta historico/")
    print("  2. Fijate si estas mismas fechas estan ahi")
    print("  3. Si falta alguna, seguramente no se hizo 'git push' despues de cargarla,")
    print("     o el push fallo -- revisa el mensaje de la terminal cuando lo corriste.")
    print(f"{'='*72}\n")


if __name__ == "__main__":
    main()
