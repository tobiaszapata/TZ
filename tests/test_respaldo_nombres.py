"""
Tests de que el respaldo (historico/*.csv.gz) preserva el nombre del
producto, y que reconstruir() es compatible con respaldos viejos que no
lo tenian.

POR QUE ESTE TEST EXISTE:
Bug real: el desglose de productos mostraba el codigo (ej "BANANA123") en
vez del nombre ("Banana x kg") en la app publicada. La causa era que
exportar_dia() solo copiaba `precios_raw` al respaldo, sin el nombre (que
vive en la tabla `productos`) — asi que al reconstruir en Streamlit Cloud,
esa tabla quedaba vacia. Este test cubre las dos puntas: que el respaldo
nuevo incluye el nombre, y que uno viejo (sin esa columna) no rompe nada.
"""

import gzip
import csv
import tempfile
from pathlib import Path

from engine.index_elemental import ObservacionVariedad
from storage.db import conectar, insertar_observaciones, nombres_de_productos


def test_exportar_dia_incluye_el_nombre_del_producto():
    import scripts.exportar_dia as ed

    with tempfile.TemporaryDirectory() as d:
        db = Path(d) / "t.db"
        con = conectar(db)
        insertar_observaciones(con, [
            (ObservacionVariedad("2026-08-10", "BANANA123", "5", 100.0,
                                 "Banana x kg", region="GBA"), "01.1.6"),
        ])

        carpeta_vieja = ed.CARPETA
        ed.CARPETA = Path(d) / "historico"
        try:
            destino, n = ed.exportar_dia(con, "2026-08-10")
            with gzip.open(destino, "rt") as fh:
                filas = list(csv.DictReader(fh))
            assert n == 1
            assert filas[0]["nombre_producto"] == "Banana x kg"
        finally:
            ed.CARPETA = carpeta_vieja
        con.close()


def test_reconstruir_es_compatible_con_respaldos_viejos_sin_nombre():
    import scripts.reconstruir as rec

    with tempfile.TemporaryDirectory() as d:
        historico = Path(d) / "historico"
        historico.mkdir()

        # respaldo VIEJO: 6 columnas, sin nombre_producto
        with gzip.open(historico / "2026-08-09.csv.gz", "wt", newline="") as f:
            w = csv.writer(f)
            w.writerow(["fecha", "ean_o_id", "clase_codigo", "comercio", "precio", "region"])
            w.writerow(["2026-08-09", "BANANA123", "01.1.6", "5", "100.0", "GBA"])

        # respaldo NUEVO: 7 columnas, con nombre
        with gzip.open(historico / "2026-08-10.csv.gz", "wt", newline="") as f:
            w = csv.writer(f)
            w.writerow(["fecha", "ean_o_id", "clase_codigo", "comercio", "precio",
                       "region", "nombre_producto"])
            w.writerow(["2026-08-10", "BANANA123", "01.1.6", "5", "102.0", "GBA", "Banana x kg"])

        db_vieja, carpeta_vieja = rec.DB_PATH, rec.CARPETA
        rec.DB_PATH = Path(d) / "reconstruida.db"
        rec.CARPETA = historico
        try:
            total = rec.reconstruir(verboso=False)
            assert total == 2  # las dos filas de precio, del archivo viejo y del nuevo

            con = conectar(rec.DB_PATH)
            nombres = nombres_de_productos(con, ["BANANA123"])
            # el nombre viene del archivo NUEVO — el viejo no lo tenia, pero
            # no rompe nada y el nombre igual queda disponible
            assert nombres["BANANA123"] == "Banana x kg"
            con.close()
        finally:
            rec.DB_PATH, rec.CARPETA = db_vieja, carpeta_vieja
