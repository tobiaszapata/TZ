"""
Parser de un archivo diario de SEPA -> lista de ObservacionVariedad.

Este módulo no está probado contra un archivo real de SEPA por la misma
razón que schema.py: el sandbox donde escribo esto no tiene salida de red.
Lo que SÍ está probado (ver tests/test_parser_sepa.py) es la lógica de
normalización y mapeo contra un CSV sintético que respeta el esquema de
schema.py — así que el día que corras esto contra el primer archivo real,
si algo falla, va a fallar en `resolver_columnas` con un mensaje que te
dice exactamente qué alias de columna falta, no en un traceback críptico
en el medio del cálculo.
"""

from __future__ import annotations

import csv
from pathlib import Path

from collectors.sepa.mapeo import clasificar
from collectors.sepa.schema import resolver_columnas
from engine.index_elemental import ObservacionVariedad


def parsear_filas(filas: list[dict], columnas: list[str], fecha: str):
    """Nucleo del parseo, independiente de si las filas vienen de un CSV
    suelto o de adentro de un ZIP. Devuelve (observaciones, stats)."""
    alias = resolver_columnas(columnas)

    resultado: list[tuple[ObservacionVariedad, str]] = []
    n_filas = 0
    n_sin_mapear = 0
    n_precio_invalido = 0

    for fila in filas:
        n_filas += 1
        ean = (fila.get(alias["ean"]) or "").strip()
        nombre = (fila.get(alias["nombre_producto"]) or "").strip()
        cadena = (fila.get(alias["cadena"]) or "").strip()
        precio_raw = (fila.get(alias["precio"]) or "").strip()

        try:
            precio = float(precio_raw.replace(".", "").replace(",", ".")
                           if precio_raw.count(",") == 1 and precio_raw.count(".") > 1
                           else precio_raw.replace(",", "."))
            if precio <= 0:
                raise ValueError
        except ValueError:
            n_precio_invalido += 1
            continue

        clase = clasificar(nombre, ean=ean or None)
        if clase is None:
            n_sin_mapear += 1
            continue

        obs = ObservacionVariedad(
            fecha=fecha, ean_o_id=ean or nombre, comercio=cadena, precio=precio,
            nombre_producto=nombre,
        )
        resultado.append((obs, clase))

    stats = {
        "n_filas": n_filas,
        "n_mapeadas": len(resultado),
        "n_sin_mapear": n_sin_mapear,
        "n_precio_invalido": n_precio_invalido,
        "tasa_mapeo": len(resultado) / n_filas if n_filas else 0.0,
    }
    return resultado, stats


def parsear_zip(path: Path, fecha: str):
    """Lee un ZIP diario de SEPA tal cual se descarga y devuelve
    (observaciones, stats). Junta las filas de todos los CSV de precios que
    encuentre adentro — que en SEPA suele ser uno por comercio."""
    from collectors.sepa.zip_reader import leer_zip

    lectura = leer_zip(path)
    columnas = lectura.archivos[0].columnas
    obs, stats = parsear_filas(lectura.filas, columnas, fecha)
    stats["n_archivos_en_zip"] = len(lectura.archivos)
    return obs, stats


def parsear_csv(path: Path, fecha: str) -> tuple[list[tuple[ObservacionVariedad, str]], dict]:
    """Lee un CSV suelto ya normalizado. Se mantiene para archivos que no
    vienen del ZIP de SEPA (por ejemplo, un export manual)."""
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        columnas = reader.fieldnames or []
        filas = [fila for fila in reader]
    return parsear_filas(filas, columnas, fecha)
