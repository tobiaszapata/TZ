"""
Tests de scripts/reiniciar.py.

CONTEXTO DEL BUG REAL: en Windows, con el proyecto guardado dentro de una
carpeta sincronizada con OneDrive (la ruta típica del usuario real es
"...\\OneDrive\\Desktop\\..."), `python -m scripts.reiniciar --con-historico`
fallaba con:

    PermissionError: [WinError 5] Acceso denegado: 'historico'

La causa: OneDrive a veces marca archivos como "solo lectura" mientras
sincroniza, y `shutil.rmtree` sin ningún manejador de errores no puede
borrar un archivo así — aunque el archivo sea perfectamente borrable una
vez que se le saca ese atributo. Se corrigió agregando un manejador
(`onexc`) que quita el atributo de solo lectura y reintenta, en vez de
fallar directamente.
"""

import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


_RAIZ_REAL = Path(__file__).resolve().parent.parent
_CARPETAS_A_COPIAR = ["scripts", "engine", "config", "collectors", "storage"]


def _copiar_proyecto_a(destino: Path) -> None:
    for carpeta in _CARPETAS_A_COPIAR:
        import shutil
        shutil.copytree(_RAIZ_REAL / carpeta, destino / carpeta)


def test_reiniciar_borra_historico_con_archivo_de_solo_lectura():
    """Reproduce el bug real de Windows/OneDrive: un archivo de solo
    lectura dentro de historico/ no debe impedir el borrado."""
    with tempfile.TemporaryDirectory() as t:
        proyecto = Path(t)
        _copiar_proyecto_a(proyecto)

        historico = proyecto / "historico"
        historico.mkdir()
        archivo_solo_lectura = historico / "2026-08-09.csv.gz"
        archivo_solo_lectura.write_text("contenido de prueba")
        os.chmod(archivo_solo_lectura, stat.S_IREAD)

        resultado = subprocess.run(
            [sys.executable, "-m", "scripts.reiniciar", "--con-historico", "--si"],
            cwd=proyecto, capture_output=True, text=True, timeout=30,
        )

        assert resultado.returncode == 0, (
            f"reiniciar.py fallo con codigo {resultado.returncode}\n"
            f"stdout: {resultado.stdout}\nstderr: {resultado.stderr}"
        )
        assert not historico.exists(), "historico/ deberia haberse borrado por completo"


def test_reiniciar_sin_con_historico_no_toca_historico():
    """Sin --con-historico, historico/ queda intacto (comportamiento
    normal, no relacionado al bug de Windows)."""
    with tempfile.TemporaryDirectory() as t:
        proyecto = Path(t)
        _copiar_proyecto_a(proyecto)

        historico = proyecto / "historico"
        historico.mkdir()
        (historico / "2026-08-09.csv.gz").write_text("contenido")

        resultado = subprocess.run(
            [sys.executable, "-m", "scripts.reiniciar", "--si"],
            cwd=proyecto, capture_output=True, text=True, timeout=30,
        )

        assert resultado.returncode == 0
        assert historico.exists()
        assert (historico / "2026-08-09.csv.gz").exists()
