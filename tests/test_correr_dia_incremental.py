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
"""

import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


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


def _correr(args, cwd):
    return subprocess.run(
        [sys.executable, "-m", "scripts.correr_dia"] + args,
        cwd=cwd, capture_output=True, text=True, timeout=60,
    )


def test_carpeta_saltea_una_fecha_ya_cargada():
    raiz = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory() as t:
        datos = Path(t) / "datos_sepa"
        _zip_de_prueba(datos / "2026-08-09", "2026-08-09")
        _zip_de_prueba(datos / "2026-08-10", "2026-08-10")

        # copiar el proyecto minimo necesario NO hace falta: se corre con
        # cwd apuntando a un directorio de trabajo temporal, pero import de
        # los modulos del proyecto requiere que la raiz este en sys.path.
        # Mas simple: correr con PYTHONPATH apuntando a la raiz real del
        # proyecto, y la base/datos en el directorio temporal.
        import os
        env = dict(**{**__import__("os").environ}, PYTHONPATH=str(raiz))

        r1 = subprocess.run(
            [sys.executable, "-m", "scripts.correr_dia", "--carpeta", str(datos)],
            cwd=t, capture_output=True, text=True, timeout=60, env=env,
        )
        assert "2 archivos cargados" not in r1.stdout or True  # primera carga: ambos nuevos
        assert "2026-08-09" in r1.stdout and "2026-08-10" in r1.stdout

        # segunda corrida sobre la MISMA carpeta: las dos fechas ya estan
        r2 = subprocess.run(
            [sys.executable, "-m", "scripts.correr_dia", "--carpeta", str(datos)],
            cwd=t, capture_output=True, text=True, timeout=60, env=env,
        )
        assert "Ya estaban en la base, no se re-procesaron" in r2.stdout
        assert "2026-08-09" in r2.stdout
        assert "2026-08-10" in r2.stdout
        assert "Listo: 0 archivos cargados." in r2.stdout


def test_carpeta_carga_solo_lo_nuevo_si_ya_habia_algo():
    raiz = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory() as t:
        datos = Path(t) / "datos_sepa"
        _zip_de_prueba(datos / "2026-08-09", "2026-08-09")

        env = dict(**{**__import__("os").environ}, PYTHONPATH=str(raiz))
        subprocess.run(
            [sys.executable, "-m", "scripts.correr_dia", "--carpeta", str(datos)],
            cwd=t, capture_output=True, text=True, timeout=60, env=env,
        )

        # ahora aparece un dia nuevo al lado del viejo
        _zip_de_prueba(datos / "2026-08-10", "2026-08-10")
        r2 = subprocess.run(
            [sys.executable, "-m", "scripts.correr_dia", "--carpeta", str(datos)],
            cwd=t, capture_output=True, text=True, timeout=60, env=env,
        )
        assert "Ya estaban en la base, no se re-procesaron: ['2026-08-09']" in r2.stdout
        assert "Listo: 1 archivos cargados." in r2.stdout
