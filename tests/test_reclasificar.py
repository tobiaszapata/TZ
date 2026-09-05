"""
Tests de scripts/reclasificar.py — la herramienta que reaplica las reglas
de clasificación ACTUALES sobre productos ya cargados, sin volver a leer
ningún archivo de SEPA.

POR QUE ESTO EXISTE: cada vez que se mejora una regla de mapeo.py (por
ejemplo, corrigiendo que "CHIZITOS QUESO" caía mal en Lácteos), la única
forma de que ese arreglo se reflejara en datos YA CARGADOS era borrar la
base entera y recargar los ZIP de SEPA desde cero — un proceso de horas
para varios días acumulados. Como el nombre real de cada producto ya
queda guardado de forma permanente en la tabla `productos`, reclasificar
solo necesita releer esos nombres (unos cientos de miles) y volver a
aplicarles `clasificar()`, sin tocar los archivos originales de SEPA en
absoluto — mucho más rápido.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

from engine.index_elemental import ObservacionVariedad
from storage.db import conectar, insertar_observaciones


def test_detecta_un_producto_que_cambiaria_de_clase():
    """El caso real que motivo esto: un producto quedo guardado con una
    clase VIEJA (de antes de una correccion de mapeo.py), y reclasificar
    tiene que detectar que ahora deberia ir a otra clase."""
    with tempfile.TemporaryDirectory() as t:
        db_path = Path(t) / "test.db"
        con = conectar(db_path)
        insertar_observaciones(con, [
            (ObservacionVariedad("2026-08-09", "EAN1", "C1", 300.0, "CHIZITOS QUESO", region="GBA"),
             "01.1.4"),  # clase vieja, incorrecta segun las reglas actuales
        ])
        con.close()

        import scripts.reclasificar as mod
        viejo_db = mod.DB_PATH
        mod.DB_PATH = db_path
        try:
            import sys as sys_mod
            viejo_argv = sys_mod.argv
            sys_mod.argv = ["reclasificar"]
            mod.main()
            sys_mod.argv = viejo_argv
        finally:
            mod.DB_PATH = viejo_db

        con2 = conectar(db_path)
        resultado = con2.execute("SELECT clase_codigo FROM precios_raw WHERE ean_o_id='EAN1'").fetchone()
        assert resultado[0] == "01.1.1", "no reclasifico al valor correcto segun las reglas actuales"
        con2.close()


def test_producto_ya_bien_clasificado_no_se_toca():
    with tempfile.TemporaryDirectory() as t:
        db_path = Path(t) / "test.db"
        con = conectar(db_path)
        insertar_observaciones(con, [
            (ObservacionVariedad("2026-08-09", "EAN1", "C1", 100.0, "Banana x kg", region="GBA"),
             "01.1.6"),  # ya correcto
        ])
        con.close()

        import scripts.reclasificar as mod
        viejo_db = mod.DB_PATH
        mod.DB_PATH = db_path
        try:
            import sys as sys_mod
            viejo_argv = sys_mod.argv
            sys_mod.argv = ["reclasificar"]
            mod.main()
            sys_mod.argv = viejo_argv
        finally:
            mod.DB_PATH = viejo_db

        con2 = conectar(db_path)
        resultado = con2.execute("SELECT clase_codigo FROM precios_raw WHERE ean_o_id='EAN1'").fetchone()
        assert resultado[0] == "01.1.6"
        con2.close()


def test_simular_no_escribe_nada():
    with tempfile.TemporaryDirectory() as t:
        db_path = Path(t) / "test.db"
        con = conectar(db_path)
        insertar_observaciones(con, [
            (ObservacionVariedad("2026-08-09", "EAN1", "C1", 300.0, "CHIZITOS QUESO", region="GBA"),
             "01.1.4"),
        ])
        con.close()

        import scripts.reclasificar as mod
        viejo_db = mod.DB_PATH
        mod.DB_PATH = db_path
        try:
            import sys as sys_mod
            viejo_argv = sys_mod.argv
            sys_mod.argv = ["reclasificar", "--simular"]
            mod.main()
            sys_mod.argv = viejo_argv
        finally:
            mod.DB_PATH = viejo_db

        con2 = conectar(db_path)
        resultado = con2.execute("SELECT clase_codigo FROM precios_raw WHERE ean_o_id='EAN1'").fetchone()
        assert resultado[0] == "01.1.4", "el modo --simular no debe escribir nada"
        con2.close()


def test_producto_que_ya_no_matchea_ninguna_regla_se_borra():
    """Si una regla se saca (raro, pero se maneja explicito): el producto
    que dependia de ella queda sin clasificar, y hay que borrarlo de
    precios_raw en vez de dejarlo con una clase que ya no corresponde."""
    with tempfile.TemporaryDirectory() as t:
        db_path = Path(t) / "test.db"
        con = conectar(db_path)
        insertar_observaciones(con, [
            (ObservacionVariedad("2026-08-09", "EAN_INVENTADO", "C1", 100.0,
                                 "PRODUCTO QUE NO EXISTE EN NINGUNA REGLA XYZ123", region="GBA"),
             "01.1.6"),  # clase que ya no le corresponderia (simulando que antes matcheaba algo)
        ])
        con.close()

        import scripts.reclasificar as mod
        viejo_db = mod.DB_PATH
        mod.DB_PATH = db_path
        try:
            import sys as sys_mod
            viejo_argv = sys_mod.argv
            sys_mod.argv = ["reclasificar"]
            mod.main()
            sys_mod.argv = viejo_argv
        finally:
            mod.DB_PATH = viejo_db

        con2 = conectar(db_path)
        resultado = con2.execute(
            "SELECT * FROM precios_raw WHERE ean_o_id='EAN_INVENTADO'").fetchall()
        assert resultado == [], "deberia haberse borrado de precios_raw"
        # pero el nombre sigue en productos, por si una regla futura lo recupera
        nombre = con2.execute(
            "SELECT nombre_producto FROM productos WHERE ean_o_id='EAN_INVENTADO'").fetchone()
        assert nombre is not None
        con2.close()


def test_no_reprocesa_archivos_de_sepa():
    """Verificacion de la premisa central: reclasificar funciona con SOLO
    la base de datos, sin necesitar (ni tocar) ningun ZIP de SEPA."""
    with tempfile.TemporaryDirectory() as t:
        db_path = Path(t) / "test.db"
        con = conectar(db_path)
        insertar_observaciones(con, [
            (ObservacionVariedad("2026-08-09", "EAN1", "C1", 300.0, "CHIZITOS QUESO", region="GBA"),
             "01.1.4"),
        ])
        con.close()

        # NO se crea ninguna carpeta datos_sepa/ ni historico/ — si
        # reclasificar necesitara esos archivos, esto fallaria.
        import scripts.reclasificar as mod
        viejo_db = mod.DB_PATH
        mod.DB_PATH = db_path
        try:
            import sys as sys_mod
            viejo_argv = sys_mod.argv
            sys_mod.argv = ["reclasificar"]
            mod.main()  # no debe tirar ninguna excepcion por falta de datos_sepa/
            sys_mod.argv = viejo_argv
        finally:
            mod.DB_PATH = viejo_db
