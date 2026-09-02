"""
Tests de scripts/exportar_sin_clasificar.py — la herramienta que exporta
TODAS las descripciones de producto sin clasificar (únicas, con
frecuencia) para revisión manual completa.

Soporta las mismas tres formas de entrada que scripts/correr_dia.py:
ZIP diario sin descomprimir, una carpeta de fecha ya descomprimida, o la
carpeta madre con varios días adentro (mezclados o no). Esto se agregó
después de que se reportara un caso real: los datos estaban guardados
como carpetas de fecha ya descomprimidas, no como ZIP, y la primera
versión de la herramienta solo sabía leer ZIP.
"""

import collections
import csv
import zipfile
import io
import tempfile
from pathlib import Path

from scripts.exportar_sin_clasificar import (
    _procesar_carpeta_de_fecha, _procesar_zip_diario, main,
)


def _zip_de_prueba(carpeta: Path, filas: list[str]) -> Path:
    """Arma un ZIP diario minimo: una carpeta de fecha con un comercio
    adentro, con las filas de producto pasadas (ya en formato pipe)."""
    carpeta.mkdir(parents=True, exist_ok=True)
    zip_diario = carpeta / "sepa_test.zip"

    buf_comercio = io.BytesIO()
    with zipfile.ZipFile(buf_comercio, "w") as zc:
        contenido = "id_producto|productos_descripcion|productos_precio_lista|id_comercio\n"
        contenido += "\n".join(f"{i}|{desc}|100|9" for i, desc in enumerate(filas))
        zc.writestr("productos.csv", contenido)

    with zipfile.ZipFile(zip_diario, "w") as z:
        z.writestr("2026-08-20/sepa_1_comercio-sepa-9_2026-08-20_09-05-10.zip", buf_comercio.getvalue())
    return zip_diario


def _carpeta_de_fecha_de_prueba(carpeta_madre: Path, fecha: str, filas: list[str]) -> Path:
    """Arma una CARPETA DE FECHA ya descomprimida (el caso real reportado):
    una carpeta llamada como la fecha, con los .zip de comercio sueltos
    adentro — sin ningún ZIP diario contenedor."""
    carpeta_fecha = carpeta_madre / fecha
    carpeta_fecha.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(carpeta_fecha / "sepa_1_comercio-sepa-9_2026-08-20.zip", "w") as zc:
        contenido = "id_producto|productos_descripcion|productos_precio_lista|id_comercio\n"
        contenido += "\n".join(f"{i}|{desc}|100|9" for i, desc in enumerate(filas))
        zc.writestr("productos.csv", contenido)

    return carpeta_fecha


def test_zip_diario_solo_exporta_lo_que_no_clasifica():
    with tempfile.TemporaryDirectory() as t:
        zip_path = _zip_de_prueba(Path(t), [
            "BANANA X KG",              # esto SI clasifica (Frutas)
            "PRODUCTO INVENTADO XYZ",   # esto NO clasifica
            "PRODUCTO INVENTADO XYZ",   # repetido, para contar frecuencia
        ])
        contador = collections.Counter()
        comercios = {}
        total, sin_clasif = _procesar_zip_diario(zip_path, solo_gba=False,
                                                 contador=contador, comercios_por_desc=comercios)

        assert total == 3
        assert sin_clasif == 2
        assert "BANANA X KG" not in contador
        assert contador["PRODUCTO INVENTADO XYZ"] == 2


def test_zip_diario_cuenta_comercios_distintos_por_descripcion():
    with tempfile.TemporaryDirectory() as t:
        carpeta = Path(t)
        zip_diario = carpeta / "sepa_test.zip"

        def _sub_zip(desc, id_comercio):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zc:
                zc.writestr("productos.csv",
                           f"id_producto|productos_descripcion|productos_precio_lista|id_comercio\n"
                           f"1|{desc}|100|{id_comercio}")
            return buf.getvalue()

        with zipfile.ZipFile(zip_diario, "w") as z:
            z.writestr("2026-08-20/sepa_1_comercio-sepa-9_2026-08-20.zip",
                      _sub_zip("PRODUCTO RARO", "9"))
            z.writestr("2026-08-20/sepa_1_comercio-sepa-10_2026-08-20.zip",
                      _sub_zip("PRODUCTO RARO", "10"))

        contador = collections.Counter()
        comercios = {}
        _procesar_zip_diario(zip_diario, solo_gba=False, contador=contador, comercios_por_desc=comercios)

        assert contador["PRODUCTO RARO"] == 2
        assert len(comercios["PRODUCTO RARO"]) == 2


def test_carpeta_de_fecha_ya_descomprimida_funciona_igual():
    """El caso real reportado: los datos estan guardados como una carpeta
    de fecha ya descomprimida (con los .zip de comercio sueltos adentro),
    no como un ZIP diario contenedor. Tiene que dar el mismo resultado
    que si fuera un ZIP diario con el mismo contenido."""
    with tempfile.TemporaryDirectory() as t:
        carpeta_fecha = _carpeta_de_fecha_de_prueba(Path(t), "2026-08-20", [
            "BANANA X KG",
            "PRODUCTO INVENTADO XYZ",
            "PRODUCTO INVENTADO XYZ",
        ])
        contador = collections.Counter()
        comercios = {}
        total, sin_clasif = _procesar_carpeta_de_fecha(carpeta_fecha, solo_gba=False,
                                                        contador=contador, comercios_por_desc=comercios)

        assert total == 3
        assert sin_clasif == 2
        assert "BANANA X KG" not in contador
        assert contador["PRODUCTO INVENTADO XYZ"] == 2


def test_main_detecta_carpeta_de_fecha_pasada_directamente():
    """python -m scripts.exportar_sin_clasificar --carpeta datos_sepa/2026-08-20
    (apuntando DIRECTO a la carpeta de una fecha) tiene que reconocerla
    como tal, no como la carpeta madre."""
    import sys
    import scripts.exportar_sin_clasificar as mod

    with tempfile.TemporaryDirectory() as t:
        carpeta_fecha = _carpeta_de_fecha_de_prueba(Path(t), "2026-08-20", ["PRODUCTO INVENTADO"])

        raiz_original = mod.RAIZ
        argv_original = sys.argv
        try:
            mod.RAIZ = Path(t)
            sys.argv = ["exportar_sin_clasificar", "--carpeta", str(carpeta_fecha),
                       "--salida", "salida.csv"]
            main()
        finally:
            mod.RAIZ = raiz_original
            sys.argv = argv_original

        salida = Path(t) / "salida.csv"
        assert salida.exists()
        with open(salida, encoding="utf-8-sig") as fh:
            filas = list(csv.reader(fh))
        assert any("PRODUCTO INVENTADO" in fila[0] for fila in filas[1:])


def test_main_detecta_carpeta_madre_con_una_carpeta_de_fecha_adentro():
    """python -m scripts.exportar_sin_clasificar --carpeta datos_sepa/
    (la carpeta MADRE, con carpetas de fecha adentro) tiene que
    encontrarlas solo y procesarlas todas."""
    import sys
    import scripts.exportar_sin_clasificar as mod

    with tempfile.TemporaryDirectory() as t:
        carpeta_madre = Path(t) / "datos_sepa"
        carpeta_madre.mkdir()
        _carpeta_de_fecha_de_prueba(carpeta_madre, "2026-08-20", ["PRODUCTO INVENTADO"])
        _carpeta_de_fecha_de_prueba(carpeta_madre, "2026-08-21", ["OTRO PRODUCTO INVENTADO"])

        raiz_original = mod.RAIZ
        argv_original = sys.argv
        try:
            mod.RAIZ = Path(t)
            sys.argv = ["exportar_sin_clasificar", "--carpeta", str(carpeta_madre),
                       "--salida", "salida.csv"]
            main()
        finally:
            mod.RAIZ = raiz_original
            sys.argv = argv_original

        salida = Path(t) / "salida.csv"
        with open(salida, encoding="utf-8-sig") as fh:
            contenido = fh.read()
        assert "PRODUCTO INVENTADO" in contenido
        assert "OTRO PRODUCTO INVENTADO" in contenido
