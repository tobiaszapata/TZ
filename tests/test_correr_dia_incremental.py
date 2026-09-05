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


def test_forzar_rescata_un_producto_que_antes_no_clasificaba():
    """El caso real que motivo --forzar: se mejora una regla de
    mapeo.py, y hay dias YA CARGADOS donde un producto se habia
    descartado por completo (nunca llego a guardarse, no solo mal
    clasificado). scripts/reclasificar.py no puede rescatar esto porque
    el producto nunca existio en la base — hace falta releer el ZIP
    original de ese dia puntual, y --forzar es la forma de hacerlo sin
    tener que borrar TODA la base."""
    with tempfile.TemporaryDirectory() as t:
        proyecto = Path(t)
        _copiar_proyecto_a(proyecto)
        datos = proyecto / "datos_sepa"

        # Primera carga: un producto que SI clasifica (para que el dia
        # quede registrado en la base) y otro que NO matchea ninguna
        # regla todavia (simula "todavia no existe esa regla"). Con un
        # solo producto sin clasificar, el dia entero quedaria con 0
        # filas en precios_raw y el sistema no lo consideraria "cargado"
        # -- no reflejaria el caso real, donde la mayoria de los
        # productos de un dia SI clasifican y solo una minoria queda
        # afuera.
        carpeta_fecha = datos / "2026-08-09"
        carpeta_fecha.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(carpeta_fecha / "sepa_1_comercio-sepa-1_2026-08-09.zip", "w") as z:
            z.writestr(
                "productos.csv",
                "id_producto|productos_descripcion|productos_precio_lista|id_comercio\n"
                "EAN_BANANA|Banana x kg|100|1\n"
                "EAN_RARO|PRODUCTO SIN REGLA TODAVIA XYZ|200|1\n",
            )
        r1 = _correr(proyecto, ["--carpeta", str(datos)])
        assert "clasificadas                  1" in r1.stdout, r1.stdout

        # Agrego una regla nueva que SI clasifica ese producto (simula
        # una mejora real de mapeo.py hecha despues de la primera carga)
        mapeo_path = proyecto / "collectors" / "sepa" / "mapeo.py"
        contenido = mapeo_path.read_text()
        contenido = contenido.replace(
            "REGLAS: list[ReglaClase] = [",
            'REGLAS: list[ReglaClase] = [\n'
            '    ReglaClase("09.3.1", incluir=[r"producto sin regla todavia xyz"]),',
        )
        mapeo_path.write_text(contenido)

        # Sin --forzar: el dia se saltea, el producto sigue perdido
        r2 = _correr(proyecto, ["--carpeta", str(datos)])
        assert "Ya estaban en la base" in r2.stdout, r2.stdout + r2.stderr

        # Con --forzar: el dia se recarga entero, el producto se rescata
        # (ahora clasifican los 2: Banana, que ya clasificaba, y el
        # producto rescatado por la regla nueva)
        r3 = _correr(proyecto, ["--carpeta", str(datos), "--forzar"])
        assert "clasificadas                  2" in r3.stdout, r3.stdout + r3.stderr


def test_forzar_no_afecta_dias_que_no_estan_en_la_carpeta():
    """--forzar solo debe recargar los dias que efectivamente esten en
    la carpeta pasada — no debe tocar otros dias ya cargados que no
    aparezcan ahi."""
    with tempfile.TemporaryDirectory() as t:
        proyecto = Path(t)
        _copiar_proyecto_a(proyecto)
        datos = proyecto / "datos_sepa"

        _zip_de_prueba(datos / "2026-08-09", "2026-08-09", ean="EAN1", nombre="Banana x kg")
        _zip_de_prueba(datos / "2026-08-10", "2026-08-10", ean="EAN2", nombre="Manzana x kg")
        _correr(proyecto, ["--carpeta", str(datos)])

        # dejo SOLO el archivo del 09 en la carpeta, y fuerzo
        import shutil
        shutil.rmtree(datos / "2026-08-10")
        r = _correr(proyecto, ["--carpeta", str(datos), "--forzar"])

        # el 09 se reprocesa (aparece "cargados" > 0), el 10 sigue en la
        # base intacto porque no estaba en la carpeta para forzar
        assert "1 archivos cargados" in r.stdout, r.stdout + r.stderr
