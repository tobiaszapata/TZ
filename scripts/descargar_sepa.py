#!/usr/bin/env python3
"""
Descarga el archivo diario de SEPA.

CONTEXTO CRITICO — POR QUE ESTE SCRIPT EXISTE Y POR QUE HAY QUE CORRERLO
TODOS LOS DIAS SIN FALTA:

SEPA no publica un archivo por fecha. Publica SIETE recursos, nombrados por
dia de la semana ("Lunes", "Martes", ... "Domingo"), y cada uno se
SOBRESCRIBE cada semana. El "Lunes" de hoy pisa al "Lunes" de la semana
pasada. Es una ventana movil de 7 dias.

Consecuencia: LOS DATOS SON PERECEDEROS. Un dia que no se descarga se
pierde para siempre — no hay archivo historico al que volver. Toda la
serie que este proyecto necesita (comparacion mes contra mes, calibracion
de la curva de proyeccion, backtest contra INDEC) solo se puede construir
acumulando de a un dia por vez, sin saltearse ninguno.

Por eso la recomendacion es automatizar ESTA parte desde el dia uno
(ver .github/workflows/recolectar.yml), aunque el analisis siga siendo
manual hasta validarlo.

--------------------------------------------------------------------------
USO

  # ver que recursos hay publicados hoy y con que nombre
  python -m scripts.descargar_sepa --listar

  # bajar el de hoy a la carpeta datos_sepa/
  python -m scripts.descargar_sepa --hoy --destino datos_sepa

  # bajar el de un dia de la semana puntual (si todavia esta en la ventana)
  python -m scripts.descargar_sepa --dia lunes --destino datos_sepa

El archivo se guarda como `sepa_AAAA-MM-DD.zip` — con la fecha en el
nombre, que es lo que despues usa `scripts/correr_dia.py --carpeta` para
saber a que dia corresponde cada archivo.
--------------------------------------------------------------------------

AVISO SOBRE PRUEBAS: el entorno donde se escribio este codigo no tiene
salida a datos.produccion.gob.ar, asi que la descarga real no pudo
probarse de punta a punta. Lo que si esta hecho: el script no hardcodea
ninguna URL — consulta la API del portal (CKAN, `package_show`) y resuelve
el recurso por su nombre. Si el portal cambia la estructura, `--listar`
muestra exactamente que devolvio la API para poder ajustar.
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
import urllib.request
from datetime import date, timedelta
from pathlib import Path

API_PACKAGE = "https://datos.produccion.gob.ar/api/3/action/package_show?id=sepa-precios"

DIAS_ES = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]

# Encabezados que imita un navegador real.
#
# POR QUE: el portal de datos abiertos devuelve 403 Forbidden a los pedidos
# que "se declaran" automaticos. Es una proteccion antibot habitual. Mandar
# los mismos encabezados que manda Chrome suele destrabarlo. No es un truco
# ilegitimo: se accede al mismo dato publico que cualquiera puede bajar
# desde el navegador, a la misma velocidad.
#
# Si aun asi devuelve 403 (por ejemplo desde un servidor de GitHub, cuyas
# direcciones IP estan bloqueadas por rango), no hay nada mas que hacer del
# lado del codigo: hay que descargar desde una computadora comun.
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
}


def _normalizar(texto: str) -> str:
    """Saca acentos y pasa a minusculas, para poder matchear 'Miércoles'
    contra 'miercoles' sin depender de como venga escrito."""
    sin_acentos = unicodedata.normalize("NFKD", texto)
    sin_acentos = "".join(c for c in sin_acentos if not unicodedata.combining(c))
    return sin_acentos.strip().lower()


def obtener_recursos() -> list[dict]:
    """Consulta la API del portal y devuelve la lista de recursos del
    dataset. No hardcodea URLs de archivo: las trae de la API."""
    req = urllib.request.Request(API_PACKAGE, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read().decode("utf-8"))
    if not data.get("success"):
        raise RuntimeError(f"La API respondio sin exito: {data}")
    return data["result"]["resources"]


def buscar_recurso_por_dia(recursos: list[dict], dia: str) -> dict | None:
    objetivo = _normalizar(dia)
    for r in recursos:
        if _normalizar(r.get("name", "")) == objetivo:
            return r
    # fallback: que el nombre del dia aparezca adentro del nombre del recurso
    for r in recursos:
        if objetivo in _normalizar(r.get("name", "")):
            return r
    return None


def fecha_del_dia_semana(dia: str, hoy: date | None = None) -> date:
    """Devuelve la fecha mas reciente (hoy o hacia atras) que cae en ese dia
    de la semana. Sirve para nombrar el archivo con la fecha real a la que
    corresponde el recurso."""
    hoy = hoy or date.today()
    objetivo = DIAS_ES.index(_normalizar(dia))
    delta = (hoy.weekday() - objetivo) % 7
    return hoy - timedelta(days=delta)


def descargar(url: str, destino: Path) -> int:
    destino.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers=HEADERS)
    total = 0
    with urllib.request.urlopen(req, timeout=1800) as r, open(destino, "wb") as f:
        while True:
            chunk = r.read(1024 * 512)
            if not chunk:
                break
            f.write(chunk)
            total += len(chunk)
    return total


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--listar", action="store_true", help="mostrar los recursos publicados")
    ap.add_argument("--hoy", action="store_true", help="bajar el recurso del dia de hoy")
    ap.add_argument("--dia", help="bajar el de un dia puntual (lunes, martes, ...)")
    ap.add_argument("--destino", type=Path, default=Path("datos_sepa"))
    args = ap.parse_args()

    try:
        recursos = obtener_recursos()
    except Exception as exc:
        print(f"ERROR consultando la API de SEPA: {exc}", file=sys.stderr)
        print("", file=sys.stderr)
        print("QUE SIGNIFICA", file=sys.stderr)
        print("  No se pudo leer el listado de archivos del portal. Causas comunes:", file=sys.stderr)
        print("    - el portal esta caido o en mantenimiento;", file=sys.stderr)
        print("    - el portal BLOQUEA pedidos automaticos desde servidores. Es", file=sys.stderr)
        print("      habitual que permita tu navegador pero no una nube como", file=sys.stderr)
        print("      GitHub Actions (error 403 Forbidden);", file=sys.stderr)
        print("    - cambio la direccion de la API.", file=sys.stderr)
        print("", file=sys.stderr)
        print("QUE HACER", file=sys.stderr)
        print("  1. Abri en el navegador:", file=sys.stderr)
        print("     https://datos.produccion.gob.ar/dataset/sepa-precios", file=sys.stderr)
        print("     Si carga bien, el portal esta en linea y esto es un bloqueo.", file=sys.stderr)
        print("  2. En tu computadora: baja el ZIP a mano y ponelo en datos_sepa/.", file=sys.stderr)
        print("     TODO EL RESTO DEL SISTEMA FUNCIONA IGUAL.", file=sys.stderr)
        print("  3. Si esto corre en GitHub Actions y falla siempre, la descarga", file=sys.stderr)
        print("     automatica en la nube no es viable con este portal: usar el", file=sys.stderr)
        print("     Programador de tareas de Windows (manual, seccion 8.2).", file=sys.stderr)
        return 1

    if args.listar:
        print(f"Recursos publicados en el dataset ({len(recursos)}):\n")
        for r in recursos:
            print(f"  nombre: {r.get('name')!r}")
            print(f"    formato: {r.get('format')}   actualizado: {r.get('last_modified')}")
            print(f"    url: {r.get('url')}\n")
        return 0

    if not (args.hoy or args.dia):
        ap.error("indica --listar, --hoy o --dia <dia de la semana>")

    dia = DIAS_ES[date.today().weekday()] if args.hoy else args.dia
    recurso = buscar_recurso_por_dia(recursos, dia)
    if recurso is None:
        print(f"No encontre un recurso llamado {dia!r}.", file=sys.stderr)
        print("Nombres disponibles:", [r.get("name") for r in recursos], file=sys.stderr)
        return 1

    fecha = fecha_del_dia_semana(dia)
    salida = args.destino / f"sepa_{fecha.isoformat()}.zip"

    if salida.exists():
        print(f"Ya existe {salida} — no se vuelve a descargar.")
        return 0

    print(f"Descargando recurso {recurso.get('name')!r} -> {salida}")
    try:
        n = descargar(recurso["url"], salida)
    except Exception as exc:
        print(f"ERROR descargando: {exc}", file=sys.stderr)
        if salida.exists():
            salida.unlink()
        return 1

    print(f"Listo: {n/1_048_576:.1f} MB en {salida}")
    print("\nPara cargarlo:")
    print(f"  python -m scripts.correr_dia --archivo {salida} --fecha {fecha.isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
