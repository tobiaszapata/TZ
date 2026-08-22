import io
import zipfile
from pathlib import Path
import tempfile

from collectors.sepa.zip_reader import (
    _detectar_delimitador,
    _parece_archivo_de_precios,
    leer_zip,
)


def test_carpeta_llamada_comercio_no_descarta_el_productos_csv():
    """REGRESION: SEPA organiza el ZIP en carpetas `comercio-9-1/`. Filtrar
    sobre la ruta completa hacia que `comercio-9-1/productos.csv` se
    descartara por contener la palabra 'comercio'. Se filtra solo por el
    nombre del archivo."""
    assert _parece_archivo_de_precios("comercio-9-1/productos.csv") is True
    assert _parece_archivo_de_precios("comercio-9-1/comercio.csv") is False
    assert _parece_archivo_de_precios("comercio-9-1/sucursales.csv") is False


def test_detecta_delimitador_pipe():
    muestra = "id|nombre|precio\n1|Banana|100"
    assert _detectar_delimitador(muestra) == "|"


def test_detecta_delimitador_coma():
    muestra = "id,nombre,precio\n1,Banana,100"
    assert _detectar_delimitador(muestra) == ","


def test_detecta_delimitador_punto_y_coma():
    muestra = "id;nombre;precio\n1;Banana;100"
    assert _detectar_delimitador(muestra) == ";"


def _zip_de_prueba(path: Path, encoding: str = "latin-1", delim: str = "|"):
    hdr = delim.join(["id_producto", "nombre_producto", "precio", "cadena"])
    fila = delim.join(["7790001", "Banana x kg", "100.00", "Coto"])
    contenido = (hdr + "\n" + fila).encode(encoding)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("comercio-9-1/productos.csv", contenido)
        z.writestr("comercio-9-1/sucursales.csv", "id|n\n1|C".encode(encoding))


def test_lee_zip_con_estructura_de_carpetas_por_comercio():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "sepa.zip"
        _zip_de_prueba(p)
        res = leer_zip(p)
        assert len(res.archivos) == 1
        assert res.archivos[0].delimitador == "|"
        assert len(res.filas) == 1
        assert res.filas[0]["nombre_producto"] == "Banana x kg"
        # el sucursales.csv tiene que haber quedado omitido
        assert any("sucursales" in o for o in res.archivos_omitidos)


def test_lee_zip_con_encoding_latin1_sin_romper():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "sepa.zip"
        hdr = "id_producto|nombre_producto|precio|cadena"
        fila = "7790001|Limón x kg|100.00|Coto"
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("c-1/productos.csv", (hdr + "\n" + fila).encode("latin-1"))
        res = leer_zip(p)
        assert len(res.filas) == 1
        # el acento tiene que haberse decodificado a algo legible
        assert "n" in res.filas[0]["nombre_producto"]


def test_detecta_fecha_en_nombre_de_carpeta():
    """REGRESION: si el ZIP diario se descomprime, queda una carpeta
    `2026-08-10/` con los ZIP por comercio adentro. El sistema tiene que
    deducir la fecha de ese nombre, igual que la deduce de la carpeta
    interna cuando el ZIP esta sin tocar."""
    from collectors.sepa.ingesta import RE_FECHA
    assert RE_FECHA.search("2026-08-10").group(0) == "2026-08-10"
    assert RE_FECHA.search("datos_sepa/2026-08-11").group(0) == "2026-08-11"
    assert RE_FECHA.search("sepa_lunes") is None


def test_carpeta_de_fecha_vacia_no_rompe():
    """Una carpeta de fecha sin ZIP adentro devuelve un resultado vacio,
    no una excepcion: puede pasar si la extraccion quedo a medias."""
    import tempfile
    from pathlib import Path
    from collectors.sepa.ingesta import procesar_directorio_fecha
    with tempfile.TemporaryDirectory() as d:
        carpeta = Path(d) / "2026-08-10"
        carpeta.mkdir()
        res = procesar_directorio_fecha(carpeta)
        assert res.fecha == "2026-08-10"
        assert res.n_filas == 0
        assert res.n_comercios == 0
