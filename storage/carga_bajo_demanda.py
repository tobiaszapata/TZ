"""
Carga de dias desde historico/ BAJO DEMANDA (solo los que hacen falta).

POR QUE EXISTE: antes, cuando Streamlit Cloud arrancaba de cero (la app se
durmio o se hizo "Reboot app"), reconstruia la base con TODOS los dias de
historico/ antes de mostrar nada, aunque despues solo se quisiera comparar
dos semanas. Ese tiempo crece con cada dia acumulado.

Ahora:
  1. La lista de dias disponibles sale de los NOMBRES de archivo de
     historico/ (no se abre ninguno): es instantanea.
  2. Recien cuando se confirman las fechas a calcular, se cargan a la base
     SOLO los dias que esas fechas necesitan y que todavia no estan.

QUE PASA SI UN DIA SE REESCRIBE (ej. despues de `reclasificar` + `exportar_dia
--rehacer`, el archivo conserva el nombre pero cambia el contenido): la tabla
`dias_cargados` guarda el TAMANO del archivo con el que se cargo cada dia. Si
el tamano cambio, ese dia se borra y se vuelve a cargar.

BASE LOCAL: si la base ya tiene filas de un dia pero no hay registro en
`dias_cargados` (por ejemplo, la base armada con correr_dia en tu
computadora), se confia en ella y NO se recarga: solo se anota el dia.
"""

from __future__ import annotations

import csv
import gzip
import re
import sqlite3
from pathlib import Path

_PATRON = re.compile(r"^(\d{4}-\d{2}-\d{2})\.csv\.gz$")

_TABLA = """
CREATE TABLE IF NOT EXISTS dias_cargados (
    fecha TEXT PRIMARY KEY,
    tamano INTEGER NOT NULL
)
"""


def dias_disponibles(carpeta: Path) -> list[str]:
    """Fechas con respaldo en `carpeta`, ordenadas. Solo mira nombres."""
    if not carpeta.exists():
        return []
    return sorted(m.group(1) for p in carpeta.iterdir() if (m := _PATRON.match(p.name)))


def rango_disponible(carpeta: Path) -> tuple[str | None, str | None, int]:
    dias = dias_disponibles(carpeta)
    if not dias:
        return None, None, 0
    return dias[0], dias[-1], len(dias)


def fechas_necesarias(disponibles: list[str], rangos: list[tuple[str, str]]) -> list[str]:
    """Dias disponibles que caen dentro de alguno de los rangos (inclusive)."""
    return sorted({d for d in disponibles for (desde, hasta) in rangos if desde <= d <= hasta})


def rangos_de_la_seleccion(D1, H1, D0, H0) -> list[tuple[str, str]]:
    """Convierte lo que usa la app (strings, o tuplas de tramos) en una lista
    de (desde, hasta)."""
    rangos: list[tuple[str, str]] = []
    for D, H in ((D1, H1), (D0, H0)):
        if isinstance(D, str):
            rangos.append((D, H))
        else:
            rangos.extend((a, b) for a, b in D)
    return rangos


def cargar_archivo_historico(con: sqlite3.Connection, archivo: Path) -> tuple[int, int, bool]:
    """Inserta un respaldo diario. Devuelve (filas, nombres, tiene_nombre).
    No hace commit."""
    with gzip.open(archivo, "rt", encoding="utf-8") as fh:
        lector = csv.DictReader(fh)
        # Respaldos viejos no traen "nombre_producto": se detecta por encabezado.
        tiene_nombre = bool(lector.fieldnames and "nombre_producto" in lector.fieldnames)
        filas: list[tuple] = []
        nombres: list[tuple] = []
        for r in lector:
            filas.append((r["fecha"], r["ean_o_id"], r["clase_codigo"],
                          r["comercio"], float(r["precio"]), r["region"]))
            if tiene_nombre and r.get("nombre_producto"):
                nombres.append((r["ean_o_id"], r["nombre_producto"]))

    con.executemany(
        """INSERT OR IGNORE INTO precios_raw
           (fecha, ean_o_id, clase_codigo, comercio, precio, region)
           VALUES (?, ?, ?, ?, ?, ?)""", filas)
    if nombres:
        con.executemany(
            """INSERT INTO productos (ean_o_id, nombre_producto, actualizado_en)
               VALUES (?, ?, datetime('now'))
               ON CONFLICT(ean_o_id) DO UPDATE SET
                   nombre_producto = excluded.nombre_producto,
                   actualizado_en = excluded.actualizado_en""", nombres)
    return len(filas), len(nombres), tiene_nombre


def asegurar_dias_cargados(con: sqlite3.Connection, carpeta: Path,
                           fechas: list[str]) -> dict:
    """Garantiza que `fechas` esten cargadas con la version actual de su
    archivo. Devuelve {'cargados': [...], 'recargados': [...], 'ya_estaban': [...],
    'sin_respaldo': [...]}."""
    con.execute(_TABLA)
    registrados = dict(con.execute("SELECT fecha, tamano FROM dias_cargados"))
    resumen = {"cargados": [], "recargados": [], "ya_estaban": [], "sin_respaldo": []}

    for fecha in sorted(set(fechas)):
        archivo = carpeta / f"{fecha}.csv.gz"
        if not archivo.exists():
            resumen["sin_respaldo"].append(fecha)
            continue
        tamano = archivo.stat().st_size

        if fecha in registrados:
            if registrados[fecha] == tamano:
                resumen["ya_estaban"].append(fecha)
                continue
            con.execute("DELETE FROM precios_raw WHERE fecha = ?", (fecha,))
            etiqueta = "recargados"
        else:
            hay_filas = con.execute(
                "SELECT 1 FROM precios_raw WHERE fecha = ? LIMIT 1", (fecha,)).fetchone()
            if hay_filas:
                # Base local ya poblada por otro camino: se confia, solo se anota.
                con.execute("INSERT OR REPLACE INTO dias_cargados VALUES (?, ?)", (fecha, tamano))
                con.commit()
                resumen["ya_estaban"].append(fecha)
                continue
            etiqueta = "cargados"

        cargar_archivo_historico(con, archivo)
        con.execute("INSERT OR REPLACE INTO dias_cargados VALUES (?, ?)", (fecha, tamano))
        con.commit()
        resumen[etiqueta].append(fecha)
    return resumen
