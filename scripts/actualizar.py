#!/usr/bin/env python3
"""
COMANDO UNICO — hace todo el ciclo diario de una sola vez.

    python -m scripts.actualizar

Eso es todo. No hay que pasar fechas, ni nombres de archivo, ni acordarse
del orden de los pasos. El script:

  1. DESCARGA el archivo de SEPA del dia (si todavia no esta bajado).
  2. CARGA en la base todos los ZIP de datos_sepa/ que aun no esten
     cargados — incluye los que hayas bajado a mano.
  3. REGENERA la aplicacion HTML con todos los datos actualizados.

Es IDEMPOTENTE y seguro de repetir: si ya descargo el archivo de hoy no lo
vuelve a bajar, y si un dia ya esta en la base no lo duplica. Se puede
correr varias veces sin consecuencias.

PARA QUE CORRA SOLO TODOS LOS DIAS, sin que tengas que acordarte:
  - Windows: Programador de tareas -> tarea diaria -> programa "python",
    argumentos "-m scripts.actualizar", iniciar en la carpeta del proyecto.
  - Mac/Linux: crontab -e  y agregar
        0 9 * * *  cd /ruta/al/proyecto && python3 -m scripts.actualizar
  - GitHub Actions: ya esta el workflow en .github/workflows/

QUE NO HACE SOLO, A PROPOSITO: no publica ni manda nada. Genera el archivo
y lo deja ahi. Revisar la salida antes de mandarla sigue siendo tarea
humana mientras el mapeo se este afinando.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path

from storage.db import conectar

DB_PATH = Path("relevamiento_precios.db")
CARPETA = Path("datos_sepa")


def _paso(titulo: str) -> None:
    print(f"\n{'='*66}\n  {titulo}\n{'='*66}")


def dias_ya_cargados() -> set[str]:
    if not DB_PATH.exists():
        return set()
    con = conectar(DB_PATH)
    try:
        cur = con.execute("SELECT DISTINCT fecha FROM precios_raw")
        return {r[0] for r in cur.fetchall()}
    finally:
        con.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sin-descarga", action="store_true",
                    help="no intentar bajar de SEPA; solo procesar lo que ya esta en datos_sepa/")
    ap.add_argument("--sin-app", action="store_true", help="no regenerar el HTML")
    ap.add_argument("--sin-github", action="store_true",
                    help="no subir el respaldo a GitHub")
    args = ap.parse_args()

    CARPETA.mkdir(exist_ok=True)
    hoy = date.today().isoformat()

    # ---------- 1. descarga ----------
    if not args.sin_descarga:
        _paso("1/4  Descargar el archivo de SEPA de hoy")
        ya = list(CARPETA.glob(f"*{hoy}*.zip"))
        if ya:
            print(f"  Ya esta descargado: {ya[0].name}")
        else:
            r = subprocess.run([sys.executable, "-m", "scripts.descargar_sepa",
                                "--hoy", "--destino", str(CARPETA)])
            if r.returncode != 0:
                print("\n  La descarga automatica fallo. No es bloqueante:")
                print("  baja el ZIP a mano del portal, dejalo en datos_sepa/ y volve")
                print("  a correr este mismo comando.")
    else:
        _paso("1/4  Descarga omitida (--sin-descarga)")

    # ---------- 2. carga ----------
    _paso("2/4  Cargar en la base los dias que falten")
    antes = dias_ya_cargados()
    print(f"  Dias ya en la base: {len(antes)}")
    archivos = sorted(CARPETA.glob("*.zip"))
    if not archivos:
        print(f"  No hay ZIP en {CARPETA}/ — nada que cargar.")
    else:
        print(f"  Archivos en {CARPETA}/: {len(archivos)}")
        r = subprocess.run([sys.executable, "-m", "scripts.correr_dia",
                            "--carpeta", str(CARPETA)])
        if r.returncode != 0:
            print("  Hubo errores en la carga (ver arriba).", file=sys.stderr)
    despues = dias_ya_cargados()
    nuevos = sorted(despues - antes)
    print(f"\n  Dias nuevos incorporados: {len(nuevos)}" + (f" -> {nuevos}" if nuevos else ""))
    print(f"  Total de dias en la base: {len(despues)}")

    # ---------- 3. respaldo + subida a GitHub ----------
    _paso("3/4  Guardar respaldo y subir a GitHub")
    if not despues:
        print("  Sin datos: nada que respaldar.")
    else:
        subprocess.run([sys.executable, "-m", "scripts.exportar_dia"])

        if args.sin_github:
            print("  Subida a GitHub omitida (--sin-github).")
        else:
            # Solo se sube si la carpeta ya es un repositorio git configurado.
            # Si no lo es, no pasa nada: el respaldo queda igual en historico/
            # y se puede subir despues a mano. No se rompe la corrida.
            es_repo = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"],
                                     capture_output=True, text=True)
            if es_repo.returncode != 0:
                print("  Esta carpeta no es un repositorio git: se omite la subida.")
                print("  (El respaldo quedo guardado en historico/ igual.)")
            else:
                subprocess.run(["git", "add", "historico/"])
                sin_cambios = subprocess.run(["git", "diff", "--staged", "--quiet"])
                if sin_cambios.returncode == 0:
                    print("  No hay dias nuevos para subir.")
                else:
                    subprocess.run(["git", "commit", "-m", f"datos: actualizacion {hoy}"])
                    r = subprocess.run(["git", "push"])
                    if r.returncode == 0:
                        print("  Subido a GitHub. Streamlit Cloud se actualiza solo.")
                    else:
                        print("  No se pudo subir (ver el error de arriba).")
                        print("  El respaldo esta guardado localmente; podes subirlo")
                        print("  mas tarde con:  git push")

    # ---------- 4. app ----------
    if not args.sin_app:
        _paso("4/4  Regenerar la aplicacion HTML")
        if not despues:
            print("  Sin datos cargados todavia: no se genera la app.")
        else:
            subprocess.run([sys.executable, "-m", "scripts.generar_app"])
    else:
        _paso("4/4  Generacion de la app omitida (--sin-app)")

    print(f"\n{'='*66}\n  LISTO\n{'='*66}")
    if despues:
        print("  Para ver los resultados:  streamlit run app_streamlit.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
