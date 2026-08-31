"""
Tests de regresion del bug real reportado en produccion: el desglose de
productos mostraba el codigo en la columna "Producto" para TODOS los
productos, no solo algunos.

LA CADENA COMPLETA DEL BUG (dos fallas encadenadas):
  1. `_respaldar_automaticamente` saltaba cualquier dia que YA tuviera un
     archivo en historico/, sin mirar si ese archivo era de un formato
     viejo (sin la columna nombre_producto, agregada despues). Resultado:
     los respaldos existentes quedaban congelados para siempre en el
     formato viejo.
  2. Ademas, esa funcion solo se llamaba si `cargados > 0` (hubo archivos
     NUEVOS). Si todo lo de la carpeta ya estaba cargado -que es el caso
     normal despues de la primera vez- la reparacion de respaldos viejos
     nunca se disparaba, ni siquiera para los dias que si lo necesitaban.

Como Streamlit Cloud reconstruye la base ENTERA desde historico/ en cada
despliegue (storage/db.py + scripts/reconstruir.py), un historico
congelado en el formato viejo significa que la tabla `productos` queda
vacia ahi, y CUALQUIER producto cae al codigo como nombre de respaldo
(ver storage/db.py::nombres_de_productos) — de ahi que se viera el mismo
valor en las dos columnas para todos los productos, no unos pocos.

NOTA (corrigiendo un bug de produccion distinto, encontrado despues): los
scripts anclan DB_PATH y CARPETA a la ubicacion del PROPIO ARCHIVO del
script, no al directorio de trabajo del proceso — porque Streamlit Cloud
podia arrancar con un cwd distinto al de la raiz del repositorio y la ruta
relativa vieja rompia todo en silencio. Por eso estos tests copian el
proyecto ENTERO a una carpeta temporal aislada en vez de correr el script
con PYTHONPATH apuntando a la raiz real y el cwd apuntando a otro lado —
ese acoplamiento ya no refleja como funciona el script de verdad.
"""

import gzip
import csv
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

_RAIZ_REAL = Path(__file__).resolve().parent.parent
_CARPETAS_A_COPIAR = ["scripts", "engine", "config", "collectors", "storage"]


def _copiar_proyecto_a(destino: Path) -> None:
    for carpeta in _CARPETAS_A_COPIAR:
        shutil.copytree(_RAIZ_REAL / carpeta, destino / carpeta)


def _respaldo_viejo(path: Path, fecha: str, ean: str = "7790001") -> None:
    """Escribe un respaldo en el formato ANTERIOR (sin nombre_producto),
    tal como quedaron los que ya existian antes de este arreglo."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["fecha", "ean_o_id", "clase_codigo", "comercio", "precio", "region"])
        w.writerow([fecha, ean, "01.1.6", "C1", "100.0", "GBA"])


def _zip_de_prueba(carpeta: Path, fecha: str, ean: str = "7790001", nombre: str = "Banana x kg") -> None:
    carpeta.mkdir(parents=True, exist_ok=True)
    archivo = carpeta / f"sepa_1_comercio-sepa-1_{fecha}_09-05-10.zip"
    with zipfile.ZipFile(archivo, "w") as z:
        z.writestr(
            "productos.csv",
            f"id_producto|productos_descripcion|productos_precio_lista|id_comercio\n"
            f"{ean}|{nombre}|100|1",
        )


def _correr(proyecto: Path, args: list[str]):
    return subprocess.run(
        [sys.executable, "-m", "scripts.correr_dia"] + args,
        cwd=proyecto, capture_output=True, text=True, timeout=60,
    )


def test_version_del_respaldo_detecta_formato_viejo():
    from scripts.exportar_dia import VERSION_FORMATO, version_del_respaldo
    with tempfile.TemporaryDirectory() as t:
        viejo = Path(t) / "2026-08-09.csv.gz"
        _respaldo_viejo(viejo, "2026-08-09")
        assert version_del_respaldo(viejo) == 1
        assert version_del_respaldo(viejo) < VERSION_FORMATO


def test_correr_dia_regenera_respaldo_viejo_aunque_no_haya_archivos_nuevos():
    """El escenario real reportado: la carpeta datos_sepa/ tiene un dia que
    YA esta cargado (0 archivos nuevos), y ese dia tiene un respaldo en
    formato viejo. correr_dia --carpeta tiene que:
      (a) informar '0 archivos cargados' (correcto: no habia nada nuevo),
      (b) IGUAL regenerar el respaldo viejo, para que incluya el nombre.
    """
    from scripts.exportar_dia import VERSION_FORMATO, version_del_respaldo
    with tempfile.TemporaryDirectory() as t:
        proyecto = Path(t)
        _copiar_proyecto_a(proyecto)
        datos = proyecto / "datos_sepa"
        historico = proyecto / "historico"
        _zip_de_prueba(datos / "2026-08-09", "2026-08-09")
        _respaldo_viejo(historico / "2026-08-09.csv.gz", "2026-08-09")

        assert version_del_respaldo(historico / "2026-08-09.csv.gz") == 1

        # primera corrida: carga el dia (todavia no esta en la base)
        _correr(proyecto, ["--carpeta", str(datos)])

        # segunda corrida: el dia YA esta cargado (0 nuevos), pero forzamos
        # el respaldo de vuelta a formato viejo, simulando que quedo de una
        # version anterior del programa:
        _respaldo_viejo(historico / "2026-08-09.csv.gz", "2026-08-09")
        assert version_del_respaldo(historico / "2026-08-09.csv.gz") == 1

        r2 = _correr(proyecto, ["--carpeta", str(datos)])

        assert "Listo: 0 archivos cargados." in r2.stdout, r2.stdout + r2.stderr
        assert version_del_respaldo(historico / "2026-08-09.csv.gz") == VERSION_FORMATO, (
            "el respaldo viejo NO se regenero aunque no hubo archivos nuevos que cargar"
        )

        with gzip.open(historico / "2026-08-09.csv.gz", "rt") as fh:
            contenido = fh.read()
        assert "Banana x kg" in contenido


def test_repara_respaldos_viejos_aunque_la_carpeta_de_sepa_este_vacia():
    """Antes, si datos_sepa/ no tenia nada para cargar, el comando se iba
    ANTES de llegar a la reparacion de respaldos viejos -- aunque esa
    reparacion no necesita los ZIP de SEPA para nada, trabaja sobre la
    base local ya cargada. Reproduce exactamente ese escenario: una base
    con un dia cargado y su respaldo en formato viejo, y una carpeta de
    SEPA completamente vacia."""
    from scripts.exportar_dia import VERSION_FORMATO, version_del_respaldo
    with tempfile.TemporaryDirectory() as t:
        proyecto = Path(t)
        _copiar_proyecto_a(proyecto)
        (proyecto / "datos_sepa").mkdir()  # vacia a proposito
        historico = proyecto / "historico"
        _respaldo_viejo(historico / "2026-08-09.csv.gz", "2026-08-09")

        # armar una base local con ese mismo dia cargado, DENTRO de la
        # copia aislada del proyecto (para que quede en su misma raiz)
        script = (
            "from pathlib import Path\n"
            "from engine.index_elemental import ObservacionVariedad\n"
            "from storage.db import conectar, insertar_observaciones\n"
            "con = conectar(Path('relevamiento_precios.db'))\n"
            "insertar_observaciones(con, [(ObservacionVariedad("
            "'2026-08-09','7790001','C1',100.0,'Banana x kg',region='GBA'),'01.1.6')])\n"
            "con.close()\n"
        )
        subprocess.run([sys.executable, "-c", script], cwd=proyecto, timeout=30)

        assert version_del_respaldo(historico / "2026-08-09.csv.gz") == 1

        r = _correr(proyecto, ["--carpeta", str(proyecto / "datos_sepa")])

        assert version_del_respaldo(historico / "2026-08-09.csv.gz") == VERSION_FORMATO, (
            "el respaldo viejo no se reparo aunque datos_sepa/ estuviera vacia:\n" + r.stdout
        )
        with gzip.open(historico / "2026-08-09.csv.gz", "rt") as fh:
            assert "Banana x kg" in fh.read()
