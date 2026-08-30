"""
Tests de scripts/validar_historico.py.

Existe para tener una forma directa de confirmar (o descartar) que un
archivo de historico/ esta corrupto, en vez de depender de que la
reconstruccion de Streamlit falle de forma indefinida y solo muestre
"No hay datos todavia" -- un mensaje que sugiere "nunca se cargo nada"
cuando en realidad el problema puede ser que un archivo puntual no se
puede leer.
"""

import gzip
import importlib
import sys
import tempfile
from pathlib import Path
from io import StringIO


def _correr_validador(carpeta: Path):
    """Corre validar_historico.main() apuntando a `carpeta`, capturando
    la salida impresa para poder revisarla en el test."""
    raiz = Path(__file__).resolve().parent.parent
    if str(raiz) not in sys.path:
        sys.path.insert(0, str(raiz))

    import scripts.validar_historico as mod
    importlib.reload(mod)
    mod.CARPETA = carpeta / "historico"

    salida = StringIO()
    viejo_stdout = sys.stdout
    sys.stdout = salida
    try:
        mod.main()
    finally:
        sys.stdout = viejo_stdout
    return salida.getvalue()


def test_archivo_bueno_no_reporta_problemas():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        (t / "historico").mkdir()
        with gzip.open(t / "historico" / "2026-08-09.csv.gz", "wt") as fh:
            fh.write("fecha,ean_o_id,clase_codigo,comercio,precio,region\n"
                     "2026-08-09,EAN1,01.1.1,C1,100.0,GBA\n")

        salida = _correr_validador(t)
        assert "✓ 2026-08-09.csv.gz" in salida
        assert "Todos los archivos son válidos" in salida


def test_archivo_corrupto_se_detecta_con_su_nombre():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        (t / "historico").mkdir()
        (t / "historico" / "corrupto.csv.gz").write_bytes(b"esto no es gzip valido")

        salida = _correr_validador(t)
        assert "corrupto.csv.gz" in salida
        assert "CORRUPTO" in salida


def test_archivo_vacio_se_distingue_de_corrupto():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        (t / "historico").mkdir()
        (t / "historico" / "vacio.csv.gz").touch()

        salida = _correr_validador(t)
        assert "VACÍO" in salida


def test_columnas_faltantes_se_reportan_explicitamente():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        (t / "historico").mkdir()
        with gzip.open(t / "historico" / "incompleto.csv.gz", "wt") as fh:
            fh.write("fecha,ean_o_id\n2026-08-09,EAN1\n")  # faltan columnas

        salida = _correr_validador(t)
        assert "FALTAN COLUMNAS" in salida


def test_un_archivo_malo_no_impide_reportar_los_buenos():
    """Si hay varios archivos y solo uno esta roto, el reporte tiene que
    mostrar el estado de TODOS, no cortarse en el primer problema."""
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        (t / "historico").mkdir()
        with gzip.open(t / "historico" / "2026-08-09.csv.gz", "wt") as fh:
            fh.write("fecha,ean_o_id,clase_codigo,comercio,precio,region\n"
                     "2026-08-09,EAN1,01.1.1,C1,100.0,GBA\n")
        (t / "historico" / "2026-08-10.csv.gz").write_bytes(b"corrupto")

        salida = _correr_validador(t)
        assert "✓ 2026-08-09.csv.gz" in salida
        assert "✗ 2026-08-10.csv.gz" in salida or "CORRUPTO" in salida
