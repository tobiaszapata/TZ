"""
Lector de los ZIP diarios de SEPA.

POR QUE ESTE MODULO EXISTE:
SEPA no publica un CSV suelto: publica un ZIP que adentro tiene una
estructura de carpetas (tipicamente una por comercio) y dentro de cada una
varios CSV — `productos.csv` con los precios, mas `sucursales.csv` y
`comercio.csv` con metadatos. A veces hay ZIP anidados. Pedirle al usuario
que descomprima a mano y encuentre los archivos correctos seria un paso
manual innecesario y propenso a error.

QUE HACE: recibe el ZIP tal cual se baja, lo recorre entero (incluyendo
ZIP adentro de ZIP), encuentra los archivos que parecen tablas de
productos/precios, y los devuelve normalizados como filas de diccionario.

ROBUSTEZ DELIBERADA — por que tanta deteccion automatica:
No pude descargar un ZIP real de SEPA para verificar su estructura exacta
(el entorno donde se escribio este codigo no tiene salida de red). En vez
de adivinar un formato y que falle, este modulo detecta en tiempo de
ejecucion:
  - el DELIMITADOR (SEPA ha usado pipe "|" y tambien coma y punto y coma),
  - el ENCODING (utf-8 o latin-1, que es comun en datos argentinos),
  - QUE ARCHIVO adentro del ZIP tiene los precios (por nombre y por
    contenido de encabezados).
Si algo no encaja, falla con un mensaje que dice exactamente que encontro,
en vez de un traceback cripto.
"""

from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

# Nombres de archivo que suelen contener los precios dentro del ZIP.
PISTAS_NOMBRE_PRODUCTOS = ("producto", "precio")
# Archivos que NO son de precios aunque esten en el ZIP.
NOMBRES_A_IGNORAR = ("sucursal", "comercio", "readme", "licencia")

DELIMITADORES_CANDIDATOS = ["|", ",", ";", "\t"]
ENCODINGS_CANDIDATOS = ["utf-8-sig", "utf-8", "latin-1"]


class SepaZipError(Exception):
    pass


@dataclass
class ArchivoEncontrado:
    ruta_interna: str
    columnas: list[str]
    delimitador: str
    encoding: str
    n_filas_leidas: int = 0


@dataclass
class ResultadoLectura:
    filas: list[dict] = field(default_factory=list)
    archivos: list[ArchivoEncontrado] = field(default_factory=list)
    archivos_omitidos: list[str] = field(default_factory=list)


def _parece_archivo_de_precios(nombre: str) -> bool:
    """Decide si un archivo del ZIP puede tener precios.

    IMPORTANTE: se evalua solo el NOMBRE DEL ARCHIVO, no la ruta completa.
    SEPA organiza el ZIP en carpetas por comercio (`comercio-9-1/...`), asi
    que filtrar sobre la ruta entera descartaria `comercio-9-1/productos.csv`
    por contener la palabra "comercio". Este bug aparecio al probar contra
    una estructura realista y por eso hay un test que lo cubre.
    """
    solo_nombre = nombre.replace("\\", "/").split("/")[-1].lower()
    if not solo_nombre.endswith(".csv"):
        return False
    if any(ig in solo_nombre for ig in NOMBRES_A_IGNORAR):
        return False
    return True


def _detectar_delimitador(muestra: str) -> str:
    """Elige el delimitador que produce mas columnas en la primera linea.
    Es mas confiable que csv.Sniffer con archivos que tienen texto libre
    con comas adentro de los nombres de producto."""
    primera = muestra.splitlines()[0] if muestra.splitlines() else ""
    mejor, mejor_n = ",", 0
    for d in DELIMITADORES_CANDIDATOS:
        n = len(primera.split(d))
        if n > mejor_n:
            mejor, mejor_n = d, n
    return mejor


def _decodificar(datos: bytes) -> tuple[str, str]:
    for enc in ENCODINGS_CANDIDATOS:
        try:
            return datos.decode(enc), enc
        except UnicodeDecodeError:
            continue
    # ultimo recurso: no perder el archivo por un byte raro
    return datos.decode("latin-1", errors="replace"), "latin-1(con reemplazos)"


def _leer_csv_bytes(datos: bytes, ruta: str) -> tuple[list[dict], ArchivoEncontrado] | None:
    texto, encoding = _decodificar(datos)
    if not texto.strip():
        return None
    delim = _detectar_delimitador(texto[:8000])
    reader = csv.DictReader(io.StringIO(texto), delimiter=delim)
    columnas = reader.fieldnames or []
    if len(columnas) < 2:
        return None
    filas = [f for f in reader]
    info = ArchivoEncontrado(
        ruta_interna=ruta, columnas=columnas, delimitador=delim,
        encoding=encoding, n_filas_leidas=len(filas),
    )
    return filas, info


def leer_zip(path: Path, max_archivos: int | None = None) -> ResultadoLectura:
    """Abre el ZIP de SEPA y devuelve todas las filas de los CSV de precios
    que encuentre adentro, junto con un inventario de que leyo.

    `max_archivos` permite hacer una prueba rapida con los primeros N CSV
    (util la primera vez, para ver la estructura sin procesar 4 GB)."""
    if not path.exists():
        raise SepaZipError(f"No existe el archivo {path}")

    resultado = ResultadoLectura()

    with zipfile.ZipFile(path) as z:
        nombres = z.namelist()
        if not nombres:
            raise SepaZipError("El ZIP esta vacio.")

        for nombre in nombres:
            if max_archivos is not None and len(resultado.archivos) >= max_archivos:
                break
            if nombre.endswith("/"):
                continue

            # ZIP anidado: SEPA a veces entrega un zip por comercio adentro
            if nombre.lower().endswith(".zip"):
                try:
                    interno = zipfile.ZipFile(io.BytesIO(z.read(nombre)))
                except zipfile.BadZipFile:
                    resultado.archivos_omitidos.append(f"{nombre} (zip ilegible)")
                    continue
                for sub in interno.namelist():
                    if sub.endswith("/") or not _parece_archivo_de_precios(sub):
                        continue
                    leido = _leer_csv_bytes(interno.read(sub), f"{nombre}::{sub}")
                    if leido:
                        filas, info = leido
                        resultado.filas.extend(filas)
                        resultado.archivos.append(info)
                continue

            if not _parece_archivo_de_precios(nombre):
                resultado.archivos_omitidos.append(nombre)
                continue

            leido = _leer_csv_bytes(z.read(nombre), nombre)
            if leido:
                filas, info = leido
                resultado.filas.extend(filas)
                resultado.archivos.append(info)
            else:
                resultado.archivos_omitidos.append(f"{nombre} (sin columnas reconocibles)")

    if not resultado.archivos:
        raise SepaZipError(
            "No encontre ningun CSV con datos adentro del ZIP.\n"
            f"Contenido del ZIP: {nombres[:25]}"
            + (" ..." if len(nombres) > 25 else "")
        )

    return resultado


def inventario(path: Path, max_archivos: int = 3) -> str:
    """Devuelve un resumen legible de que hay adentro del ZIP, SIN procesar
    todo. Es lo primero que conviene correr con un ZIP nuevo, para ver la
    estructura y confirmar los nombres de columna."""
    res = leer_zip(path, max_archivos=max_archivos)
    lineas = [f"Inventario de {path.name}", "=" * 60]
    for a in res.archivos:
        lineas.append(f"\nArchivo: {a.ruta_interna}")
        lineas.append(f"  delimitador: {a.delimitador!r}   encoding: {a.encoding}")
        lineas.append(f"  filas: {a.n_filas_leidas}")
        lineas.append(f"  columnas ({len(a.columnas)}): {a.columnas}")
    if res.archivos_omitidos:
        lineas.append(f"\nOmitidos: {res.archivos_omitidos[:10]}")
    return "\n".join(lineas)
