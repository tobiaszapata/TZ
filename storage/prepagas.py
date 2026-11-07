"""
Almacenamiento de los cuadros tarifarios de prepagas (SSSalud) en SQLite.

FLUJO (igual idea que los dias de SEPA):
  1. scripts/descargar_prepagas.py baja cada mes del sitio de la
     Superintendencia y lo guarda en externos/prepagas/YYYYMM.csv.gz
     (eso es lo que se sube a GitHub).
  2. Cuando la app calcula, `asegurar_periodos_cargados` pasa a la base SOLO
     los meses que el calculo necesita (y que todavia no estan). Si un
     archivo cambio de tamano (se volvio a bajar), se recarga ese mes.

Un MES es la unidad natural: las prepagas declaran un cuadro por periodo
(AAAAMM) y los precios cambian de forma discreta, una vez por mes.
"""

from __future__ import annotations

import csv
import gzip
import re
import sqlite3
from pathlib import Path

_PATRON = re.compile(r"^(\d{6})\.csv\.gz$")

COLUMNAS = [
    "periodo", "rnemp", "nombre_comercial", "codigo_plan", "nombre_plan",
    "valor_capital", "cantidad_capitas", "rango_desde", "rango_hasta", "region",
    "tipo_plan", "comercializable", "permite_copago", "tasa_aumento_mensual",
    "modalidad_adhesion", "tipificacion",
]

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS prepagas_cuadros (
    periodo INTEGER NOT NULL,
    rnemp INTEGER NOT NULL,
    nombre_comercial TEXT,
    codigo_plan TEXT,
    nombre_plan TEXT NOT NULL,
    valor_capital REAL,
    cantidad_capitas REAL,
    rango_desde INTEGER,
    rango_hasta INTEGER,
    region TEXT,
    tipo_plan TEXT,
    comercializable INTEGER,
    permite_copago INTEGER,
    tasa_aumento_mensual REAL,
    modalidad_adhesion INTEGER,
    tipificacion TEXT
);
CREATE INDEX IF NOT EXISTS idx_prepagas_periodo ON prepagas_cuadros (periodo);
CREATE TABLE IF NOT EXISTS prepagas_cargados (
    periodo INTEGER PRIMARY KEY,
    tamano INTEGER NOT NULL
);
"""


def crear_tablas(con: sqlite3.Connection) -> None:
    con.executescript(_ESQUEMA)


def periodos_disponibles(carpeta: Path) -> list[int]:
    """Meses con archivo en `carpeta` (solo mira nombres), ordenados."""
    carpeta = Path(carpeta)
    if not carpeta.exists():
        return []
    return sorted(int(m.group(1)) for p in carpeta.iterdir() if (m := _PATRON.match(p.name)))


def _num(x, tipo=float):
    if x is None or str(x).strip() == "" or str(x).strip().lower() in ("none", "null", "nan"):
        return None
    try:
        return tipo(float(x))
    except ValueError:
        return None


def _bool(x) -> int | None:
    s = str(x).strip().lower()
    if s in ("1", "true", "t", "si", "sí", "yes"):
        return 1
    if s in ("0", "false", "f", "no"):
        return 0
    return None


def leer_archivo(archivo: Path) -> list[tuple]:
    """Filas de un archivo mensual, ya tipadas, en el orden de COLUMNAS."""
    filas = []
    with gzip.open(archivo, "rt", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            filas.append((
                _num(r["periodo"], int), _num(r["rnemp"], int), r.get("nombre_comercial") or None,
                r.get("codigo_plan") or None, r.get("nombre_plan") or "",
                _num(r["valor_capital"]), _num(r["cantidad_capitas"]),
                _num(r["rango_desde"], int), _num(r["rango_hasta"], int), r.get("region") or None,
                r.get("tipo_plan") or None, _bool(r.get("comercializable")),
                _bool(r.get("permite_copago")), _num(r.get("tasa_aumento_mensual")),
                _bool(r.get("modalidad_adhesion")), r.get("tipificacion") or None,
            ))
    return filas


def asegurar_periodos_cargados(con: sqlite3.Connection, carpeta: Path,
                               periodos: list[int]) -> dict:
    """Carga a la base los `periodos` que faltan (o cuyo archivo cambio).
    Devuelve {'cargados': [...], 'recargados': [...], 'ya_estaban': [...],
    'sin_archivo': [...]}. Un mes sin archivo NO es un error: el calculo de
    prepagas simplemente no tendra dato para ese mes."""
    crear_tablas(con)
    carpeta = Path(carpeta)
    res = {"cargados": [], "recargados": [], "ya_estaban": [], "sin_archivo": []}
    for p in sorted(set(periodos)):
        archivo = carpeta / f"{p}.csv.gz"
        if not archivo.exists():
            res["sin_archivo"].append(p)
            continue
        tam = archivo.stat().st_size
        fila = con.execute("SELECT tamano FROM prepagas_cargados WHERE periodo=?", (p,)).fetchone()
        if fila and fila[0] == tam:
            res["ya_estaban"].append(p)
            continue
        filas = leer_archivo(archivo)
        con.execute("DELETE FROM prepagas_cuadros WHERE periodo=?", (p,))
        con.executemany(
            f"INSERT INTO prepagas_cuadros ({','.join(COLUMNAS)}) VALUES ({','.join('?' * len(COLUMNAS))})",
            filas)
        con.execute("INSERT OR REPLACE INTO prepagas_cargados (periodo, tamano) VALUES (?, ?)", (p, tam))
        con.commit()
        (res["recargados"] if fila else res["cargados"]).append(p)
    return res


def filas_de_periodo(con: sqlite3.Connection, periodo: int) -> list[tuple]:
    """Filas de un mes: (rnemp, nombre_comercial, nombre_plan, valor_capital,
    cantidad_capitas, rango_desde, rango_hasta, region, tipo_plan,
    modalidad_adhesion, permite_copago). Lista vacia si el mes no esta."""
    crear_tablas(con)
    return con.execute(
        "SELECT rnemp, nombre_comercial, nombre_plan, valor_capital, cantidad_capitas, "
        "rango_desde, rango_hasta, region, tipo_plan, modalidad_adhesion, permite_copago "
        "FROM prepagas_cuadros WHERE periodo=?", (periodo,)).fetchall()
