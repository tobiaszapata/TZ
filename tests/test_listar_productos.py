"""
Tests de storage.db.productos_de_clase y scripts/listar_productos_por_categoria.py
— la herramienta de auditoría de clasificación pedida explícitamente: ver
todos los productos de cada subcategoría (nombre + código) para detectar
cuáles están mal clasificados y habría que reordenar.
"""

import csv
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from engine.index_elemental import ObservacionVariedad
from storage.db import conectar, insertar_observaciones, productos_de_clase

_RAIZ_REAL = Path(__file__).resolve().parent.parent
_CARPETAS_A_COPIAR = ["scripts", "engine", "config", "collectors", "storage"]


def _copiar_proyecto_a(destino: Path) -> None:
    """El script ancla DB_PATH a la ubicación de su propio archivo (ver
    scripts/listar_productos_por_categoria.py — mismo criterio que el
    resto de scripts/, adoptado tras el bug real de rutas relativas de
    Streamlit Cloud). Por eso el test no puede simplemente correr el
    script con PYTHONPATH apuntando a la raíz real y esperar que la base
    se cree en un directorio temporal aparte: hay que copiar el proyecto
    entero, para que el script opere sobre SU PROPIA raíz, como en un uso
    real."""
    for carpeta in _CARPETAS_A_COPIAR:
        shutil.copytree(_RAIZ_REAL / carpeta, destino / carpeta)


def test_productos_de_clase_devuelve_nombre_y_codigo():
    with tempfile.TemporaryDirectory() as t:
        con = conectar(Path(t) / "t.db")
        insertar_observaciones(con, [
            (ObservacionVariedad("2026-08-09", "EAN1", "C1", 100.0, "Banana x kg", region="GBA"),
             "01.1.6"),
        ])
        productos = productos_de_clase(con, "01.1.6")
        assert len(productos) == 1
        ean, nombre, n_obs = productos[0]
        assert ean == "EAN1"
        assert nombre == "Banana x kg"
        assert n_obs == 1
        con.close()


def test_productos_de_clase_ordena_por_frecuencia_descendente():
    """El mas observado (el que mas pesa en el calculo) tiene que salir
    primero — es el orden mas util para revisar clasificacion, ver el
    docstring de la funcion."""
    with tempfile.TemporaryDirectory() as t:
        con = conectar(Path(t) / "t.db")
        insertar_observaciones(con, [
            (ObservacionVariedad("2026-08-09", "POCO", "C1", 100.0, "Poco frecuente", region="GBA"),
             "01.1.6"),
            (ObservacionVariedad("2026-08-09", "MUCHO", "C1", 100.0, "Muy frecuente", region="GBA"),
             "01.1.6"),
            (ObservacionVariedad("2026-08-10", "MUCHO", "C2", 100.0, "Muy frecuente", region="GBA"),
             "01.1.6"),
            (ObservacionVariedad("2026-08-11", "MUCHO", "C1", 100.0, "Muy frecuente", region="GBA"),
             "01.1.6"),
        ])
        productos = productos_de_clase(con, "01.1.6")
        assert productos[0][0] == "MUCHO"
        assert productos[0][2] == 3
        assert productos[1][0] == "POCO"
        assert productos[1][2] == 1
        con.close()


def test_productos_de_clase_no_mezcla_otras_subcategorias():
    with tempfile.TemporaryDirectory() as t:
        con = conectar(Path(t) / "t.db")
        insertar_observaciones(con, [
            (ObservacionVariedad("2026-08-09", "FRUTA", "C1", 100.0, "Banana", region="GBA"),
             "01.1.6"),
            (ObservacionVariedad("2026-08-09", "CARNE", "C1", 300.0, "Bife", region="GBA"),
             "01.1.2"),
        ])
        solo_frutas = productos_de_clase(con, "01.1.6")
        assert len(solo_frutas) == 1
        assert solo_frutas[0][0] == "FRUTA"
        con.close()


def test_script_exporta_csv_con_las_columnas_esperadas():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        _copiar_proyecto_a(t)
        db_path = t / "relevamiento_precios.db"
        con = conectar(db_path)
        insertar_observaciones(con, [
            (ObservacionVariedad("2026-08-09", "EAN1", "C1", 100.0, "Banana x kg", region="GBA"),
             "01.1.6"),
            (ObservacionVariedad("2026-08-09", "EAN2", "C1", 300.0, "Bocaditos Pedigree", region="GBA"),
             "01.1.2"),
        ])
        con.close()

        r = subprocess.run(
            [sys.executable, "-m", "scripts.listar_productos_por_categoria"],
            cwd=t, capture_output=True, text=True, timeout=30,
        )

        salida = t / "productos_por_categoria.csv"
        assert salida.exists(), r.stdout + r.stderr
        with open(salida, encoding="utf-8-sig") as fh:
            filas = list(csv.reader(fh))
        assert filas[0] == ["Division", "Subcategoria (codigo)", "Subcategoria (nombre)",
                            "Codigo de producto", "Producto", "Observaciones"]
        codigos_exportados = {fila[3] for fila in filas[1:]}
        assert codigos_exportados == {"EAN1", "EAN2"}


def test_script_filtra_por_clase_especifica():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        _copiar_proyecto_a(t)
        db_path = t / "relevamiento_precios.db"
        con = conectar(db_path)
        insertar_observaciones(con, [
            (ObservacionVariedad("2026-08-09", "FRUTA1", "C1", 100.0, "Banana", region="GBA"),
             "01.1.6"),
            (ObservacionVariedad("2026-08-09", "CARNE1", "C1", 300.0, "Bife", region="GBA"),
             "01.1.2"),
        ])
        con.close()

        subprocess.run(
            [sys.executable, "-m", "scripts.listar_productos_por_categoria", "--clase", "01.1.6"],
            cwd=t, capture_output=True, text=True, timeout=30,
        )

        salida = t / "productos_por_categoria.csv"
        with open(salida, encoding="utf-8-sig") as fh:
            filas = list(csv.reader(fh))
        codigos_exportados = {fila[3] for fila in filas[1:]}
        assert codigos_exportados == {"FRUTA1"}, "el filtro --clase no funciono"
