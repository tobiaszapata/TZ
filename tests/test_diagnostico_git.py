"""
Tests de scripts/diagnosticar_estado.py::_estado_de_git.

POR QUE ESTO EXISTE: el diagnostico anterior solo miraba la base local y
la carpeta historico/ LOCAL, y decia "todo consistente" aunque esos
cambios nunca hubieran llegado a GitHub. Como Streamlit Cloud lee de
GitHub, no del disco de la persona, ese "todo consistente" local no
significaba nada sobre lo que realmente se iba a ver publicado — que fue
exactamente el problema reportado: se corrigieron los respaldos, el
diagnostico local decia que estaba todo bien, pero nada cambio en la app
publicada porque el paso de git nunca se completo.

Estos tests usan repositorios git REALES (creados en carpetas temporales),
no simulaciones — es la unica forma honesta de probar algo que depende
del comportamiento real de git."""

import subprocess
import tempfile
from pathlib import Path


def _git(args, cwd):
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=15)


def _repo_con_historico(tmp: Path) -> Path:
    _git(["init", "-q"], tmp)
    _git(["config", "user.email", "test@test.com"], tmp)
    _git(["config", "user.name", "Test"], tmp)
    (tmp / "historico").mkdir()
    (tmp / "historico" / "2026-08-09.csv.gz").write_text("contenido inicial")
    return tmp


def _importar_estado_de_git(cwd: Path) -> str:
    import sys
    import os
    raiz = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(raiz))
    os.chdir(cwd)
    # reimport limpio por si otro test ya lo importo con un cwd distinto
    import importlib
    import scripts.diagnosticar_estado as mod
    importlib.reload(mod)
    return mod._estado_de_git()


def test_detecta_archivo_sin_commitear():
    with tempfile.TemporaryDirectory() as t:
        repo = _repo_con_historico(Path(t))
        resultado = _importar_estado_de_git(repo)
        assert "SIN SUBIR A GITHUB" in resultado


def test_detecta_commit_sin_pushear():
    with tempfile.TemporaryDirectory() as t:
        repo = _repo_con_historico(Path(t))
        _git(["add", "historico/"], repo)
        _git(["commit", "-q", "-m", "primero"], repo)

        with tempfile.TemporaryDirectory() as remoto_dir:
            remoto = Path(remoto_dir) / "remoto.git"
            _git(["init", "-q", "--bare", str(remoto)], repo)
            _git(["remote", "add", "origin", str(remoto)], repo)
            _git(["branch", "-M", "main"], repo)
            _git(["push", "-u", "-q", "origin", "main"], repo)

            # modificar y commitear SIN pushear -- el escenario real reportado
            (repo / "historico" / "2026-08-09.csv.gz").write_text("contenido corregido")
            _git(["add", "historico/"], repo)
            _git(["commit", "-q", "-m", "arreglo respaldo"], repo)

            resultado = _importar_estado_de_git(repo)
            assert "commiteados" in resultado and "no se subieron" in resultado


def test_todo_commiteado_y_pusheado_da_ok():
    with tempfile.TemporaryDirectory() as t:
        repo = _repo_con_historico(Path(t))
        _git(["add", "historico/"], repo)
        _git(["commit", "-q", "-m", "primero"], repo)

        with tempfile.TemporaryDirectory() as remoto_dir:
            remoto = Path(remoto_dir) / "remoto.git"
            _git(["init", "-q", "--bare", str(remoto)], repo)
            _git(["remote", "add", "origin", str(remoto)], repo)
            _git(["branch", "-M", "main"], repo)
            _git(["push", "-u", "-q", "origin", "main"], repo)

            resultado = _importar_estado_de_git(repo)
            assert "commiteado y subido" in resultado


def test_sin_repositorio_de_git_no_rompe():
    with tempfile.TemporaryDirectory() as t:
        # ni siquiera 'git init' -- carpeta comun y corriente
        (Path(t) / "historico").mkdir()
        resultado = _importar_estado_de_git(Path(t))
        assert "no es un repositorio de git" in resultado
