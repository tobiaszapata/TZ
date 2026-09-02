"""
Tests de scripts/exportar_sin_clasificar.py — la herramienta que exporta
TODAS las descripciones de producto sin clasificar (únicas, con
frecuencia) para revisión manual completa, pedida explícitamente para
poder decidir producto por producto dónde ubicar cada uno.
"""

import csv
import zipfile
import io
import tempfile
from pathlib import Path

from scripts.exportar_sin_clasificar import _procesar_un_zip


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


def test_solo_exporta_lo_que_no_clasifica():
    with tempfile.TemporaryDirectory() as t:
        zip_path = _zip_de_prueba(Path(t), [
            "BANANA X KG",              # esto SI clasifica (Frutas)
            "PRODUCTO INVENTADO XYZ",   # esto NO clasifica
            "PRODUCTO INVENTADO XYZ",   # repetido, para contar frecuencia
        ])
        import collections
        contador = collections.Counter()
        comercios = {}
        total, sin_clasif = _procesar_un_zip(zip_path, solo_gba=False,
                                             contador=contador, comercios_por_desc=comercios)

        assert total == 3
        assert sin_clasif == 2
        assert "BANANA X KG" not in contador
        assert contador["PRODUCTO INVENTADO XYZ"] == 2


def test_cuenta_comercios_distintos_por_descripcion():
    """El mismo producto sin clasificar visto en 2 comercios distintos
    tiene que contar 2 en la columna de comercios."""
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

        import collections
        contador = collections.Counter()
        comercios = {}
        _procesar_un_zip(zip_diario, solo_gba=False, contador=contador, comercios_por_desc=comercios)

        assert contador["PRODUCTO RARO"] == 2
        assert len(comercios["PRODUCTO RARO"]) == 2
