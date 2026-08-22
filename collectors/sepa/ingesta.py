"""
Ingesta en STREAMING de los ZIP de SEPA.

POR QUE NO SE PUEDE HACER "LEER TODO Y DESPUES PROCESAR":
Un dia de SEPA son ~14,5 MILLONES de filas repartidas en ~17 archivos, uno
por comercio, algunos de 130 MB comprimidos. Cargar eso en memoria mata el
proceso (se comprobo: el primer intento termino en "Killed"). Este modulo
procesa fila por fila y nunca retiene el archivo entero.

ADEMAS AGREGA AL VUELO. La misma botella de aceite aparece una vez por
SUCURSAL: miles de filas para un solo producto. Guardar todas seria inflar
la base sin ganar informacion, porque el indice trabaja con el precio
promedio del producto. Entonces se acumula en memoria un promedio por
(producto, comercio) y se guarda UNA fila por combinacion. De 14,5 millones
de filas crudas quedan decenas de miles.

QUE SE PIERDE CON ESA AGREGACION: el detalle por sucursal, que hoy no se
usa. Si en el futuro se quiere abrir por region, hay que guardar tambien
id_sucursal y cruzar con sucursales.csv — el lugar para hacerlo es aca.
"""

from __future__ import annotations

import csv
import io
import math
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from collectors.sepa.mapeo import clasificar
from collectors.sepa.schema import resolver_columnas
from collectors.sepa.sucursales import leer_sucursales_de_zip

RE_FECHA = re.compile(r"(20\d{2})-(\d{2})-(\d{2})")


@dataclass
class ResultadoIngesta:
    fecha: str | None = None
    n_filas: int = 0
    n_mapeadas: int = 0
    n_sin_mapear: int = 0
    n_precio_invalido: int = 0
    n_comercios: int = 0
    n_sin_region: int = 0
    n_sucursal_desconocida: int = 0
    comercios_con_error: list[str] = field(default_factory=list)
    # (ean, clase, comercio) -> [suma_logs, n, nombre]
    acumulado: dict = field(default_factory=dict)

    @property
    def tasa_mapeo(self) -> float:
        return self.n_mapeadas / self.n_filas if self.n_filas else 0.0


def fecha_desde_zip(z: zipfile.ZipFile) -> str | None:
    """SEPA nombra la carpeta interna con la fecha del relevamiento
    (`2026-08-10/...`). Eso permite deducirla aunque el archivo se llame
    'sepa_lunes.zip' — que es como lo publica el portal."""
    for nombre in z.namelist():
        m = RE_FECHA.search(nombre)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def procesar_directorio_fecha(carpeta: Path, fecha: str | None = None,
                              max_comercios: int | None = None,
                              regiones: set | None = None) -> ResultadoIngesta:
    """Procesa una CARPETA ya descomprimida que contiene los ZIP por
    comercio (la que adentro del ZIP diario se llama `2026-08-10/`).

    POR QUE EXISTE ESTA VARIANTE:
    Es comodo descomprimir el ZIP diario y quedarse con la carpeta de fecha,
    porque asi se ve de un vistazo que dias hay cargados. El sistema soporta
    las dos formas —ZIP sin tocar, o carpeta descomprimida— para no obligar
    a rehacer lo que ya este armado de una manera.

    La fecha se deduce del NOMBRE DE LA CARPETA (`2026-08-10`), que es como
    la nombra SEPA."""
    res = ResultadoIngesta()
    res.fecha = fecha or (RE_FECHA.search(carpeta.name).group(0)
                          if RE_FECHA.search(carpeta.name) else None)

    internos = sorted(carpeta.glob("*.zip"))
    if max_comercios:
        internos = internos[:max_comercios]

    # sucursales: se leen de los mismos zips internos
    sucursales = _sucursales_de_directorio(carpeta)

    for archivo in internos:
        try:
            inner = zipfile.ZipFile(archivo)
        except (zipfile.BadZipFile, OSError):
            res.comercios_con_error.append(archivo.name)
            continue
        objetivo = next((f for f in inner.namelist()
                         if f.lower().endswith("productos.csv")), None)
        if not objetivo:
            res.comercios_con_error.append(archivo.name + " (sin productos.csv)")
            continue
        with inner.open(objetivo) as fh:
            _procesar_stream(fh, res, sucursales, regiones)
        res.n_comercios += 1
        inner.close()

    return res


def _sucursales_de_directorio(carpeta: Path) -> dict:
    """Arma el mapa de sucursales leyendo los sucursales.csv de cada ZIP de
    comercio dentro de una carpeta de fecha descomprimida."""
    import csv as _csv
    from collectors.sepa.sucursales import Sucursal

    mapa: dict[tuple[str, str], Sucursal] = {}
    for archivo in sorted(carpeta.glob("*.zip")):
        try:
            inner = zipfile.ZipFile(archivo)
        except (zipfile.BadZipFile, OSError):
            continue
        objetivo = next((f for f in inner.namelist()
                         if f.lower().endswith("sucursales.csv")), None)
        if not objetivo:
            inner.close()
            continue
        raw = inner.read(objetivo).decode("utf-8-sig", errors="replace")
        for fila in _csv.DictReader(io.StringIO(raw), delimiter="|"):
            sid = (fila.get("id_sucursal") or "").strip()
            cid = (fila.get("id_comercio") or "").strip()
            if not sid or not cid:
                continue
            mapa[(cid, sid)] = Sucursal(
                id_comercio=cid, id_sucursal=sid,
                tipo=(fila.get("sucursales_tipo") or "").strip().capitalize(),
                localidad=(fila.get("sucursales_localidad") or "").strip(),
                provincia=(fila.get("sucursales_provincia") or "").strip(),
            )
        inner.close()
    return mapa


def procesar_zip(path: Path, fecha: str | None = None,
                 max_comercios: int | None = None) -> ResultadoIngesta:
    """Recorre el ZIP diario completo y devuelve los precios promedio por
    (producto, comercio), listos para insertar.

    NO SE DESCARTA NINGUNA REGION. Cada precio se etiqueta con la region
    estadistica de INDEC a la que pertenece su sucursal (GBA, Pampeana,
    Noroeste, Noreste, Cuyo, Patagonia). Despues el indice se calcula por
    region con los ponderadores de esa region, y recien ahi se agrega a
    nacional. Ese es el procedimiento de INDEC, y es lo correcto: Alimentos
    pesa 23,4% en GBA y 35,3% en el Noreste, asi que un solo juego de pesos
    para todo el pais seria un error grande."""
    res = ResultadoIngesta()

    sucursales = leer_sucursales_de_zip(path)

    with zipfile.ZipFile(path) as z:
        res.fecha = fecha or fecha_desde_zip(z)
        internos = sorted(n for n in z.namelist() if n.lower().endswith(".zip"))

        # Si el ZIP no tiene ZIPs adentro, quizas es un unico CSV suelto
        if not internos:
            internos = [n for n in z.namelist() if n.lower().endswith(".csv")]
            for nombre in internos:
                _procesar_csv_bytes(z.read(nombre), res, nombre)
            res.n_comercios = len(internos)
            return res

        if max_comercios:
            internos = internos[:max_comercios]

        for nombre in internos:
            try:
                datos = z.read(nombre)
                inner = zipfile.ZipFile(io.BytesIO(datos))
            except (zipfile.BadZipFile, OSError):
                # SEPA a veces publica un comercio con el archivo vacio
                res.comercios_con_error.append(nombre.split("/")[-1])
                continue

            objetivo = next((f for f in inner.namelist()
                             if f.lower().endswith("productos.csv")), None)
            if not objetivo:
                res.comercios_con_error.append(nombre.split("/")[-1] + " (sin productos.csv)")
                continue

            with inner.open(objetivo) as fh:
                _procesar_stream(fh, res, sucursales)
            res.n_comercios += 1
            del datos, inner

    return res


def _procesar_csv_bytes(datos: bytes, res: ResultadoIngesta, nombre: str) -> None:
    _procesar_stream(io.BytesIO(datos), res)


def _procesar_stream(fh, res: ResultadoIngesta, sucursales=None, solo_gba=False) -> None:
    texto = io.TextIOWrapper(fh, encoding="utf-8-sig", errors="replace")
    lector = csv.DictReader(texto, delimiter="|")
    columnas = lector.fieldnames or []
    if not columnas:
        return
    alias = resolver_columnas(columnas)
    c_ean, c_desc = alias["ean"], alias["nombre_producto"]
    c_precio, c_cad = alias["precio"], alias["cadena"]
    c_suc = alias.get("sucursal_id")

    for fila in lector:
        res.n_filas += 1

        # Etiquetado de region (no filtrado): cada fila queda asignada a su
        # region de INDEC para poder ponderarla con los pesos correctos.
        region = None
        if sucursales is not None and c_suc:
            clave_suc = ((fila.get(c_cad) or "").strip(), (fila.get(c_suc) or "").strip())
            suc = sucursales.get(clave_suc)
            if suc is None:
                res.n_sucursal_desconocida += 1
                continue
            region = suc.region
            if region is None:
                # provincia vacia o codigo fuera de norma: se descarta, pero
                # se cuenta para que quede visible en el reporte
                res.n_sin_region += 1
                continue

        descripcion = fila.get(c_desc) or ""
        clase = clasificar(descripcion)
        if clase is None:
            res.n_sin_mapear += 1
            continue

        crudo = (fila.get(c_precio) or "").strip().replace(",", ".")
        try:
            precio = float(crudo)
        except ValueError:
            res.n_precio_invalido += 1
            continue
        if precio <= 0:
            res.n_precio_invalido += 1
            continue

        ean = (fila.get(c_ean) or "").strip()
        comercio = (fila.get(c_cad) or "").strip()
        if not ean:
            res.n_sin_mapear += 1
            continue

        clave = (ean, clase, comercio, region)
        acc = res.acumulado.get(clave)
        if acc is None:
            # [suma de logs, cantidad, nombre]  -> media geometrica al cerrar
            res.acumulado[clave] = [math.log(precio), 1, descripcion.strip()]
        else:
            acc[0] += math.log(precio)
            acc[1] += 1
        res.n_mapeadas += 1


def observaciones(res: ResultadoIngesta):
    """Convierte lo acumulado en observaciones listas para la base: una por
    (producto, comercio), con el precio promedio geometrico de todas sus
    sucursales."""
    from engine.index_elemental import ObservacionVariedad

    salida = []
    for (ean, clase, comercio, region), (suma_log, n, nombre) in res.acumulado.items():
        precio = math.exp(suma_log / n)
        salida.append((
            ObservacionVariedad(fecha=res.fecha, ean_o_id=ean, comercio=comercio,
                                precio=precio, nombre_producto=nombre, region=region),
            clase,
        ))
    return salida
