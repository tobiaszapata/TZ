r"""
Mantiene al dia los cuadros tarifarios de prepagas (se corre una vez por semana,
junto con SEPA, o cuando quieras).

    python -m scripts.actualizar_prepagas

QUE HACE (y es seguro repetirlo, no duplica nada):
  1. Consulta que meses publico el sitio de la Superintendencia (desde el mes
     piso, por defecto 202607).
  2. BAJA los meses que te faltan.
  3. REVISA los dos ultimos meses ya bajados: compara la cantidad de filas que
     tenes con la que el sitio tiene hoy (una consulta de 1 fila). Si cambio,
     vuelve a bajar ese mes. Esto importa porque las entidades cargan sus
     cuadros durante el mes: un mes recien empezado esta INCOMPLETO y se va
     llenando (el 7/11/2026, noviembre tenia 7.748 filas y octubre 11.801).
  4. Con --subir, hace git add/commit/push de externos/.

NUNCA frena otras tareas: si el sitio no responde, avisa y sale con codigo 0
(salvo que uses --estricto), para que no corte la carga de SEPA.

Opciones:
  --desde AAAAMM   primer mes a considerar (por defecto 202607; 0 = todos)
  --subir          sube a GitHub lo que se haya bajado
  --estricto       terminar con error si algo falla
  --hilos N        pedidos en paralelo (por defecto 4)
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path

from collectors.prepagas.descargar import (
    PERIODO_PISO, DescargaIncompleta, abrir_http, bajar_periodo, contar_filas_archivo,
    escribir_mes, listar_entidades, listar_periodos, total_del_periodo,
)
from storage.prepagas import periodos_disponibles

RAIZ = Path(__file__).resolve().parents[1]
CARPETA = RAIZ / "externos" / "prepagas"


def sincronizar(carpeta: Path = CARPETA, desde: int = PERIODO_PISO, abrir=abrir_http,
                hilos: int = 4, log=print, revisar_ultimos: int = 2, **kw) -> dict:
    """Devuelve {'bajados': [...], 'actualizados': [...], 'sin_cambios': [...],
    'errores': [...]}. No levanta excepciones por problemas de red: los
    informa en 'errores'."""
    res = {"bajados": [], "actualizados": [], "sin_cambios": [], "errores": []}
    try:
        sitio = [p for p in listar_periodos(abrir, **kw) if p >= desde]
    except DescargaIncompleta as exc:
        res["errores"].append(f"no se pudo consultar el sitio: {exc}")
        return res
    tengo = set(periodos_disponibles(carpeta))
    faltan = [p for p in sitio if p not in tengo]
    ya_estan = [p for p in sitio if p in tengo]
    revisar = ya_estan[-revisar_ultimos:] if revisar_ultimos else []

    a_bajar: list[tuple[int, str]] = [(p, "nuevo") for p in faltan]
    for p in revisar:
        try:
            en_sitio = total_del_periodo(p, abrir, **kw)
            local = contar_filas_archivo(carpeta / f"{p}.csv.gz")
        except Exception as exc:
            res["errores"].append(f"{p}: no se pudo comparar con el sitio ({exc})")
            continue
        if en_sitio != local:
            log(f"  {p}: el sitio tiene {en_sitio} filas y vos {local}: se vuelve a bajar.")
            a_bajar.append((p, "cambio"))
        else:
            res["sin_cambios"].append(p)
            log(f"  {p}: sin cambios ({local} filas).")
    if not a_bajar:
        return res

    try:
        entidades = listar_entidades(abrir, **kw)
    except DescargaIncompleta as exc:
        res["errores"].append(f"no se pudo leer la lista de entidades: {exc}")
        return res
    for p, motivo in a_bajar:
        try:
            filas = bajar_periodo(
                p, entidades, abrir=abrir, hilos=hilos, **kw,
                progreso=lambda n, tot, e, nf, p=p: print(f"\r  {p}: {n}/{tot} entidades", end="", flush=True))
            print()
            escribir_mes(filas, carpeta / f"{p}.csv.gz")
            (res["bajados"] if motivo == "nuevo" else res["actualizados"]).append(p)
            log(f"  {p}: {len(filas)} filas guardadas.")
        except DescargaIncompleta as exc:
            res["errores"].append(f"{p}: {exc}")
    return res


def _subir(carpeta: Path) -> None:
    es_repo = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True)
    if es_repo.returncode != 0:
        print("  Esta carpeta no es un repositorio git: se omite la subida.")
        return
    subprocess.run(["git", "add", "externos/"])
    if subprocess.run(["git", "diff", "--staged", "--quiet"]).returncode == 0:
        print("  No hay cambios de prepagas para subir.")
        return
    subprocess.run(["git", "commit", "-m", f"prepagas: actualizacion {date.today().isoformat()}"])
    if subprocess.run(["git", "push"]).returncode == 0:
        print("  Subido a GitHub.")
    else:
        print("  No se pudo subir (ver el error de arriba). Podes hacerlo despues con: git push")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--desde", type=int, default=PERIODO_PISO)
    ap.add_argument("--subir", action="store_true")
    ap.add_argument("--estricto", action="store_true")
    ap.add_argument("--hilos", type=int, default=4)
    a = ap.parse_args(argv)

    print("Prepagas (SSSalud): buscando meses nuevos o cambiados...")
    res = sincronizar(CARPETA, a.desde, hilos=a.hilos)
    hubo = res["bajados"] or res["actualizados"]
    print(f"  Bajados: {res['bajados'] or '-'} | Actualizados: {res['actualizados'] or '-'} | "
          f"Sin cambios: {res['sin_cambios'] or '-'}")
    for e in res["errores"]:
        print(f"  AVISO: {e}")
    if res["errores"]:
        print("  (No es bloqueante. Podes reintentar mas tarde con el mismo comando, o usar el")
        print("   plan B con el navegador: scripts/prepagas_navegador.js.)")
    if a.subir and hubo:
        _subir(CARPETA)
    return 1 if (a.estricto and res["errores"]) else 0


if __name__ == "__main__":
    sys.exit(main())
