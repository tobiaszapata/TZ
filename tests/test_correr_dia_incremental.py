"""
Tests de scripts/correr_dia.py — en particular, que `--carpeta` no vuelva
a procesar un dia que ya esta en la base.

POR QUE ESTO IMPORTA: procesar un dia real de SEPA son ~14,5 millones de
filas y tarda varios minutos. Sin el chequeo previo, correr
`--carpeta datos_sepa/` una segunda vez sobre una carpeta con dias viejos
repetia ese trabajo completo solo para insertar 0 filas nuevas al final
(la carga ya es idempotente) — el resultado final era correcto, pero el
tiempo perdido era real y crecia con cada dia acumulado en la carpeta.

Estos tests usan `subprocess` para invocar el script tal cual lo hace el
usuario desde la terminal, no importan sus funciones internas — es la
forma mas fiel de probar un script pensado para la linea de comandos.

CAMBIO IMPORTANTE (corrigiendo un bug real de produccion): los scripts
ahora anclan DB_PATH y CARPETA a la ubicacion del PROPIO ARCHIVO del
script (`Path(__file__).resolve().parent.parent`), no al directorio de
trabajo (`cwd`) del proceso que los ejecuta. Esto se hizo porque Streamlit
Cloud podia arrancar el proceso con un `cwd` distinto al de la raiz del
repositorio, y con la ruta relativa vieja eso hacia que la app buscara
`historico/` en el lugar equivocado — silenciosamente, sin ningun error,
mostrando "No hay datos todavia" pese a que los datos SI estaban bien
subidos a GitHub.

Como consecuencia, estos tests YA NO PUEDEN simplemente correr el script
con `cwd` apuntando a un directorio temporal y `PYTHONPATH` apuntando a la
raiz real — eso mezclaba "el codigo vive en un lado" con "los datos se
crean en otro", que es exactamente el acoplamiento fragil que causo el bug
real. Ahora cada test copia el proyecto ENTERO a una carpeta temporal
aislada, y corre el script ahi, tal cual lo haria una persona real."""

import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

_RAIZ_REAL = Path(__file__).resolve().parent.parent
_CARPETAS_A_COPIAR = ["scripts", "engine", "config", "collectors", "storage"]


def _copiar_proyecto_a(destino: Path) -> None:
    """Copia una version aislada y minima del proyecto (solo el codigo,
    sin datos ni base) a `destino`, para poder correr el script ahi como
    si fuera una instalacion real e independiente."""
    for carpeta in _CARPETAS_A_COPIAR:
        shutil.copytree(_RAIZ_REAL / carpeta, destino / carpeta)


def _zip_de_prueba(carpeta: Path, fecha: str, ean: str = "1", nombre: str = "Pan") -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    archivo = carpeta / f"sepa_1_comercio-sepa-1_{fecha}_09-05-10.zip"
    with zipfile.ZipFile(archivo, "w") as z:
        z.writestr(
            "productos.csv",
            f"id_producto|productos_descripcion|productos_precio_lista|id_comercio\n"
            f"{ean}|{nombre}|100|1",
        )
    return archivo


def _correr(proyecto: Path, args: list[str]):
    """Corre el script DENTRO de la copia aislada del proyecto, tal cual
    lo haria una persona parada en esa carpeta desde su terminal."""
    return subprocess.run(
        [sys.executable, "-m", "scripts.correr_dia"] + args,
        cwd=proyecto, capture_output=True, text=True, timeout=60,
    )


def test_carpeta_saltea_una_fecha_ya_cargada():
    with tempfile.TemporaryDirectory() as t:
        proyecto = Path(t)
        _copiar_proyecto_a(proyecto)
        datos = proyecto / "datos_sepa"
        _zip_de_prueba(datos / "2026-08-09", "2026-08-09")
        _zip_de_prueba(datos / "2026-08-10", "2026-08-10")

        r1 = _correr(proyecto, ["--carpeta", str(datos)])
        assert "2026-08-09" in r1.stdout and "2026-08-10" in r1.stdout, r1.stdout + r1.stderr

        # segunda corrida sobre la MISMA carpeta: las dos fechas ya estan
        r2 = _correr(proyecto, ["--carpeta", str(datos)])
        assert "Ya estaban en la base, no se re-procesaron" in r2.stdout, r2.stdout + r2.stderr
        assert "2026-08-09" in r2.stdout
        assert "2026-08-10" in r2.stdout
        assert "Listo: 0 archivos cargados." in r2.stdout


def test_carpeta_carga_solo_lo_nuevo_si_ya_habia_algo():
    with tempfile.TemporaryDirectory() as t:
        proyecto = Path(t)
        _copiar_proyecto_a(proyecto)
        datos = proyecto / "datos_sepa"
        _zip_de_prueba(datos / "2026-08-09", "2026-08-09")

        _correr(proyecto, ["--carpeta", str(datos)])

        # ahora aparece un dia nuevo al lado del viejo
        _zip_de_prueba(datos / "2026-08-10", "2026-08-10")
        r2 = _correr(proyecto, ["--carpeta", str(datos)])
        assert "Ya estaban en la base, no se re-procesaron: ['2026-08-09']" in r2.stdout, (
            r2.stdout + r2.stderr
        )
        assert "Listo: 1 archivos cargados." in r2.stdout
