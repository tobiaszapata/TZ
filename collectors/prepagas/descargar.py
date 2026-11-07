"""
Descarga de los cuadros tarifarios de prepagas desde el sitio de la
Superintendencia de Servicios de Salud (https://cuadrostarifarios.sssalud.gob.ar).

El sitio es una pagina que consulta una API publica (la misma que usa la
tabla que se ve en pantalla):
  GET /api/getPeriodo            -> periodos disponibles (AAAAMM)
  GET /api/getPrepagas           -> entidades (rnemp, nombre_comercial, descripcion)
  GET /api/getCuadrosTarifarios?page=N&per_page=50&periodo=AAAAMM&rnemp=XXXXXX
                                 -> filas del cuadro, con "paginacion"

IMPORTANTE (verificado): el servidor responde "Gateway Timeout" si se piden
paginas grandes (200 o 5000 filas); con 50 por pagina responde bien. Por eso
se baja de a 50, por entidad, con reintentos.

INTEGRIDAD: para cada entidad se compara la cantidad de filas bajadas con el
"total" que informa la paginacion. Si no coincide, el mes se considera
INCOMPLETO y NO se escribe el archivo (mejor no tener el mes que tenerlo
con huecos que cambian el resultado sin avisar).
"""

from __future__ import annotations

import csv
import gzip
import json
import os
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from storage.prepagas import COLUMNAS

BASE = "https://cuadrostarifarios.sssalud.gob.ar/api"
USER_AGENT = "relevamiento-ipc/1.0"
POR_PAGINA = 50
# Primer mes que interesa bajar por defecto: el mes ANTERIOR al primer dia de
# SEPA cargado (agosto 2026), porque es la base para comparar agosto. Los
# meses anteriores (el sitio tiene desde 202507) no se usan y solo ocuparian
# lugar. Se cambia con --desde.
PERIODO_PISO = 202607


class DescargaIncompleta(Exception):
    pass


def abrir_http(url: str, timeout: int = 60) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def pedir(url: str, abrir=abrir_http, intentos: int = 6, espera: float = 1.5) -> dict:
    """GET con reintentos y espera creciente. Un JSON sin la clave "data" (por
    ejemplo {"code":504,"message":"Gateway Timeout"}) cuenta como fallo."""
    ultimo = None
    for i in range(intentos):
        try:
            j = abrir(url)
            if isinstance(j, dict) and "data" in j:
                return j
            ultimo = RuntimeError(f"respuesta sin 'data': {str(j)[:120]}")
        except Exception as exc:  # red, timeout, JSON invalido
            ultimo = exc
        if i < intentos - 1:
            time.sleep(espera * (i + 1))
    raise DescargaIncompleta(f"no se pudo leer {url}: {ultimo}")


def listar_periodos(abrir=abrir_http, **kw) -> list[int]:
    return sorted(int(p) for p in pedir(f"{BASE}/getPeriodo", abrir, **kw)["data"])


def listar_entidades(abrir=abrir_http, **kw) -> list[int]:
    return sorted({int(e["rnemp"]) for e in pedir(f"{BASE}/getPrepagas", abrir, **kw)["data"]})


def fila_csv(x: dict) -> list:
    def b(v):
        return "" if v is None else int(bool(v))
    return [x["periodo"], x["rnemp"], x.get("nombre_comercial") or "", x.get("codigo_plan", ""),
            x.get("nombre_plan") or "", x.get("valor_capital", ""), x.get("cantidad_capitas", ""),
            x.get("rango_etario_desde", ""), x.get("rango_etario_hasta", ""), x.get("region") or "",
            x.get("tipo_plan") or "", b(x.get("comercializable")), b(x.get("permite_copago")),
            x.get("tasa_aumento_mensual", ""), b(x.get("modalidad_adhesion")),
            x.get("tipificacion") or ""]


def bajar_entidad(periodo: int, rnemp: int, abrir=abrir_http, por_pagina: int = POR_PAGINA,
                  **kw) -> list[list]:
    filas: list[list] = []
    pagina, ultima, total = 1, 1, 0
    while pagina <= ultima:
        q = urllib.parse.urlencode({"page": pagina, "per_page": por_pagina,
                                    "periodo": periodo, "rnemp": rnemp})
        j = pedir(f"{BASE}/getCuadrosTarifarios?{q}", abrir, **kw)
        pag = j.get("paginacion") or {}
        ultima = int(pag.get("ultima_pagina") or 1)
        total = int(pag.get("total") or len(j["data"]))
        filas += [fila_csv(x) for x in j["data"]]
        pagina += 1
    if len(filas) != total:
        raise DescargaIncompleta(
            f"entidad {rnemp}, periodo {periodo}: se bajaron {len(filas)} filas y el sitio "
            f"informa {total}")
    return filas


def bajar_periodo(periodo: int, entidades: list[int], abrir=abrir_http, hilos: int = 4,
                  progreso=None, **kw) -> list[list]:
    """Todas las filas de un mes. Levanta DescargaIncompleta si alguna entidad
    no se pudo bajar completa."""
    filas: list[list] = []
    errores: list[str] = []

    def una(e):
        try:
            return e, bajar_entidad(periodo, e, abrir, **kw), None
        except Exception as exc:
            return e, [], str(exc)

    with ThreadPoolExecutor(max_workers=hilos) as ex:
        for n, (e, f, err) in enumerate(ex.map(una, entidades), 1):
            if err:
                errores.append(err)
            filas += f
            if progreso:
                progreso(n, len(entidades), e, len(f))
    if errores:
        raise DescargaIncompleta(
            f"mes {periodo} INCOMPLETO ({len(errores)} entidades con error), no se escribe:\n  "
            + "\n  ".join(errores[:10]))
    filas.sort(key=lambda r: (r[1], str(r[4]), str(r[9]), str(r[7]), str(r[8])))
    return filas


def escribir_mes(filas: list[list], ruta: Path) -> None:
    """Escribe el CSV comprimido de forma atomica (archivo temporal + rename)."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_name(ruta.name + ".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLUMNAS)
        w.writerows(filas)
    os.replace(tmp, ruta)


def importar_csv_plano(origen: Path, carpeta: Path) -> Path:
    """Toma un CSV (el que genera scripts/prepagas_navegador.js) y lo guarda
    comprimido como externos/prepagas/AAAAMM.csv.gz. El periodo se toma de la
    primera fila y se verifica que TODAS las filas sean del mismo mes."""
    with open(origen, newline="", encoding="utf-8") as f:
        lector = csv.reader(f)
        cab = next(lector)
        if cab != COLUMNAS:
            raise ValueError(f"cabecera inesperada en {origen}: {cab}")
        filas = list(lector)
    if not filas:
        raise ValueError(f"{origen} no tiene filas")
    periodos = {r[0] for r in filas}
    if len(periodos) != 1:
        raise ValueError(f"{origen} mezcla periodos: {sorted(periodos)}")
    destino = Path(carpeta) / f"{periodos.pop()}.csv.gz"
    escribir_mes(filas, destino)
    return destino


def total_del_periodo(periodo: int, abrir=abrir_http, **kw) -> int:
    """Cantidad total de filas que el sitio tiene hoy para un mes (una sola
    consulta, de 1 fila): sirve para saber si un mes ya bajado cambio."""
    j = pedir(f"{BASE}/getCuadrosTarifarios?page=1&per_page=1&periodo={periodo}", abrir, **kw)
    return int((j.get("paginacion") or {}).get("total", 0))


def contar_filas_archivo(ruta: Path) -> int:
    """Filas de datos (sin la cabecera) de un archivo mensual bajado."""
    with gzip.open(ruta, "rt", encoding="utf-8", newline="") as f:
        return max(0, sum(1 for _ in csv.reader(f)) - 1)
