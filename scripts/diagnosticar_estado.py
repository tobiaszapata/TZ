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

import subprocess
from pathlib import Path

from scripts.exportar_dia import VERSION_FORMATO, dias_en_base, version_del_respaldo
from storage.db import conectar

# Ancladas al archivo, no al directorio de trabajo del proceso —
# ver la explicacion completa en scripts/reconstruir.py.
RAIZ = Path(__file__).resolve().parent.parent
DB_PATH = RAIZ / "relevamiento_precios.db"
CARPETA = RAIZ / "historico"


def _estado_de_git(carpeta: Path = CARPETA) -> str:
    """Revisa si `carpeta` tiene cambios sin subir a GitHub. Por defecto
    revisa `CARPETA` (historico/ de este proyecto), pero acepta un
    parametro para poder testear contra un repositorio de prueba aislado
    sin depender de la ubicacion real del proyecto.

    POR QUE ESTO SE AGREGO: la version anterior de este diagnostico solo
    miraba la base local y la carpeta historico/ LOCAL — nunca chequeaba si
    lo que hay ahi realmente llego a GitHub. Ese es exactamente el eslabon
    que se rompio en un caso real: el diagnostico local decia "todo
    consistente", pero Streamlit Cloud (que lee de GitHub, no del disco de
    la persona) seguia mostrando lo viejo porque el 'git push' nunca se
    habia hecho, o habia fallado sin que se notara. Ahora esto se chequea
    en el mismo lugar, para no tener que adivinar entre tres pantallas
    distintas (terminal, GitHub, Streamlit)."""
    try:
        r = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"],
                          capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return "no es un repositorio de git (¿corriste 'git init'?)"
    except FileNotFoundError:
        return "git no esta instalado en esta terminal"

    sin_commitear = subprocess.run(
        ["git", "status", "--porcelain", "--", str(carpeta)],
        capture_output=True, text=True, timeout=10,
    ).stdout.strip()

    if sin_commitear:
        n = len(sin_commitear.splitlines())
        return (f"HAY {n} ARCHIVO(S) EN historico/ SIN SUBIR A GITHUB.\n"
                f"    Faltó (o falló) el 'git add historico/ && git commit && git push'.\n"
                f"    Streamlit Cloud NO puede ver estos cambios hasta que se suban.")

    sin_pushear = subprocess.run(
        ["git", "log", "@{u}..HEAD", "--oneline", "--", str(carpeta)],
        capture_output=True, text=True, timeout=10,
    )
    if sin_pushear.returncode != 0:
        return ("no se pudo comparar contra GitHub (no hay rama remota configurada).\n"
                f"    Si nunca corriste 'git push -u origin main', hacelo una vez;\n"
                f"    después este chequeo va a poder confirmar si falta subir algo.")

    # IMPORTANTE: lo de arriba compara contra la referencia de la rama
    # remota GUARDADA LOCALMENTE (lo que Git recuerda del ultimo
    # fetch/push), NO contra GitHub en vivo. Si por algun motivo esa
    # referencia quedo desactualizada (por ejemplo, alguien tocó el
    # repositorio desde otro lado, o el ultimo push no actualizo bien la
    # referencia local pese a haber llegado al servidor), esto podria decir
    # "todo subido" sin serlo de verdad. `git fetch` actualiza esa
    # referencia consultando al servidor real antes de comparar.
    fetch = subprocess.run(["git", "fetch", "--quiet"], capture_output=True,
                          text=True, timeout=20)
    if fetch.returncode == 0:
        sin_pushear = subprocess.run(
            ["git", "log", "@{u}..HEAD", "--oneline", "--", str(carpeta)],
            capture_output=True, text=True, timeout=10,
        )
    else:
        return (f"no se pudo confirmar contra GitHub en vivo (git fetch falló: "
                f"{fetch.stderr.strip()[:200]}).\n"
                f"    Puede ser un problema de conexión o de credenciales. El resultado "
                f"de abajo es SOLO según lo que esta máquina recordaba del último contacto "
                f"con GitHub, no está confirmado en este momento.")

    if sin_pushear.stdout.strip():
        n = len(sin_pushear.stdout.strip().splitlines())
        return (f"Hay {n} commit(s) CON CAMBIOS EN historico/ que están commiteados\n"
                f"    pero todavía no se subieron con 'git push'.")

    return "todo lo de historico/ está commiteado y subido (según esta rama local)."


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
    print("  ESTADO EN GITHUB (esto es lo que realmente ve Streamlit Cloud)")
    print(f"{'='*72}\n")
    print(_estado_de_git())
    print(f"\n{'='*72}\n")


if __name__ == "__main__":
    main()
