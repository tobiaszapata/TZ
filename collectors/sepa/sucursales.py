"""
Lectura de sucursales.csv — filtro geografico y estrato de comercio.

POR QUE ESTE MODULO ES IMPORTANTE (mas que agregar productos):
Los ponderadores que usa el indice son los de la region GBA. Pero SEPA es
NACIONAL: sobre datos reales de agosto 2026 hay 2.752 sucursales, de las
cuales solo el 69% estan en CABA + Buenos Aires. El 31% restante (Cordoba,
Entre Rios, Mendoza, Neuquen, etc.) estaba entrando al calculo mezclado con
las de GBA, ponderado con pesos que no le corresponden.

Eso es un sesgo real y silencioso: un aumento de la nafta en Neuquen movia
un indice que dice medir el Gran Buenos Aires. Ninguna cantidad de
productos adicionales arregla eso; hay que filtrar por region.

SEGUNDO USO — ESTRATO DE COMERCIO:
sucursales.csv trae `sucursales_tipo` con los valores que define la
Resolucion: Hipermercado (mas de 15 cajas), Supermercado (4 a 15),
Autoservicio (1 a 3), Tradicional (mostrador) y Web. INDEC pondera los
estratos de comercio por separado (Metodologia N32, formula 8), asi que
tener este campo permite acercarse a esa metodologia en vez de promediar
todos los locales por igual.

FUENTE DE LOS CODIGOS DE PROVINCIA: norma ISO 3166-2, tal como exige la
especificacion tecnica de SEPA (Anexo II, campo sucursales_provincia).
"""

from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass
from pathlib import Path

# ISO 3166-2 -> nombre, segun el maestro publicado por SEPA
PROVINCIAS = {
    "AR-C": "CABA", "AR-B": "Buenos Aires", "AR-K": "Catamarca", "AR-H": "Chaco",
    "AR-U": "Chubut", "AR-X": "Cordoba", "AR-W": "Corrientes", "AR-E": "Entre Rios",
    "AR-P": "Formosa", "AR-Y": "Jujuy", "AR-L": "La Pampa", "AR-F": "La Rioja",
    "AR-M": "Mendoza", "AR-N": "Misiones", "AR-Q": "Neuquen", "AR-R": "Rio Negro",
    "AR-A": "Salta", "AR-J": "San Juan", "AR-D": "San Luis", "AR-Z": "Santa Cruz",
    "AR-S": "Santa Fe", "AR-G": "Santiago del Estero", "AR-V": "Tierra del Fuego",
    "AR-T": "Tucuman",
}

# Los 24 partidos del Gran Buenos Aires, segun la definicion que usa INDEC
# para el IPC-GBA (Metodologia N32, nota al pie 8). Se comparan normalizados
# (sin acentos, en minuscula) porque cada cadena escribe la localidad como
# quiere.
PARTIDOS_GBA = {
    "almirante brown", "avellaneda", "berazategui", "esteban echeverria",
    "ezeiza", "florencio varela", "general san martin", "hurlingham",
    "ituzaingo", "jose c. paz", "jose c paz", "la matanza", "lanus",
    "lomas de zamora", "malvinas argentinas", "merlo", "moreno", "moron",
    "quilmes", "san fernando", "san isidro", "san miguel", "tigre",
    "tres de febrero", "vicente lopez",
}

# --- Provincia -> REGION ESTADISTICA DE INDEC ---------------------------
# INDEC divide el pais en 6 regiones y publica ponderadores distintos para
# cada una. Buenos Aires es el caso especial: los 24 partidos del conurbano
# son GBA, y el resto de la provincia (Mar del Plata, Bahia Blanca, Tandil)
# es region Pampeana.
PROVINCIA_A_REGION = {
    "AR-C": "GBA",          # CABA entera
    "AR-B": None,           # depende de la localidad: GBA o Pampeana
    "AR-X": "Pampeana", "AR-E": "Pampeana", "AR-S": "Pampeana", "AR-L": "Pampeana",
    "AR-K": "Noroeste", "AR-Y": "Noroeste", "AR-F": "Noroeste",
    "AR-A": "Noroeste", "AR-G": "Noroeste", "AR-T": "Noroeste",
    "AR-W": "Noreste", "AR-H": "Noreste", "AR-P": "Noreste", "AR-N": "Noreste",
    "AR-M": "Cuyo", "AR-J": "Cuyo", "AR-D": "Cuyo",
    "AR-U": "Patagonia", "AR-Q": "Patagonia", "AR-R": "Patagonia",
    "AR-Z": "Patagonia", "AR-V": "Patagonia",
}

# --- Mapeo provincia ISO -> region estadistica de INDEC --------------------
# Las seis regiones del IPC (Metodologia N32). Buenos Aires es el caso
# especial: los 24 partidos del conurbano son GBA, el resto de la provincia
# es Pampeana. Por eso no alcanza con mirar la provincia: hay que mirar la
# localidad tambien (ver Sucursal.region).
PROVINCIA_A_REGION = {
    "AR-C": "GBA",           # CABA
    "AR-B": "Pampeana",      # resto de Buenos Aires (el conurbano se separa aparte)
    "AR-X": "Pampeana",      # Cordoba
    "AR-E": "Pampeana",      # Entre Rios
    "AR-L": "Pampeana",      # La Pampa
    "AR-S": "Pampeana",      # Santa Fe
    "AR-W": "Noreste",       # Corrientes
    "AR-H": "Noreste",       # Chaco
    "AR-P": "Noreste",       # Formosa
    "AR-N": "Noreste",       # Misiones
    "AR-K": "Noroeste",      # Catamarca
    "AR-Y": "Noroeste",      # Jujuy
    "AR-F": "Noroeste",      # La Rioja
    "AR-A": "Noroeste",      # Salta
    "AR-G": "Noroeste",      # Santiago del Estero
    "AR-T": "Noroeste",      # Tucuman
    "AR-M": "Cuyo",          # Mendoza
    "AR-J": "Cuyo",          # San Juan
    "AR-D": "Cuyo",          # San Luis
    "AR-U": "Patagonia",     # Chubut
    "AR-Q": "Patagonia",     # Neuquen
    "AR-R": "Patagonia",     # Rio Negro
    "AR-Z": "Patagonia",     # Santa Cruz
    "AR-V": "Patagonia",     # Tierra del Fuego
}

# --- Provincia (ISO 3166-2) -> region estadistica de INDEC ---------------
# Las 6 regiones del IPC. Buenos Aires se parte en dos: los 24 partidos del
# conurbano son GBA, y el resto de la provincia es Pampeana.
PROVINCIA_A_REGION = {
    "AR-C": "GBA",                                    # CABA
    "AR-B": None,                                     # depende del partido
    "AR-X": "Pampeana", "AR-E": "Pampeana", "AR-S": "Pampeana", "AR-L": "Pampeana",
    "AR-K": "Noroeste", "AR-Y": "Noroeste", "AR-F": "Noroeste",
    "AR-A": "Noroeste", "AR-G": "Noroeste", "AR-T": "Noroeste",
    "AR-W": "Noreste", "AR-H": "Noreste", "AR-P": "Noreste", "AR-N": "Noreste",
    "AR-M": "Cuyo", "AR-J": "Cuyo", "AR-D": "Cuyo",
    "AR-U": "Patagonia", "AR-Q": "Patagonia", "AR-R": "Patagonia",
    "AR-Z": "Patagonia", "AR-V": "Patagonia",
}

# Estratos segun la Resolucion (campo sucursales_tipo)
ESTRATOS = ["Hipermercado", "Supermercado", "Autoservicio", "Tradicional", "Web"]


def _norm(t: str) -> str:
    t = (t or "").strip().lower()
    for a, b in {"á":"a","é":"e","í":"i","ó":"o","ú":"u","ü":"u","ñ":"n"}.items():
        t = t.replace(a, b)
    return t


@dataclass(frozen=True)
class Sucursal:
    id_comercio: str
    id_sucursal: str
    tipo: str
    localidad: str
    provincia: str

    @property
    def region(self) -> str | None:
        """Region estadistica de INDEC a la que pertenece la sucursal.

        NO se descarta nada por region: cada sucursal se ETIQUETA, y despues
        el indice se calcula por region con los ponderadores de esa region,
        y recien ahi se agrega a nacional. Ese es el procedimiento de INDEC.

        Devuelve None solo si la provincia viene vacia o con un codigo que
        no esta en la norma ISO — esos casos se reportan, no se asumen."""
        if self.provincia == "AR-B":
            # el conurbano es GBA; el resto de la provincia es Pampeana
            return "GBA" if _norm(self.localidad) in PARTIDOS_GBA else "Pampeana"
        return PROVINCIA_A_REGION.get(self.provincia)

    @property
    def region(self) -> str | None:
        """Region estadistica de INDEC a la que pertenece la sucursal.

        El unico caso que necesita mirar la localidad es Buenos Aires: los
        24 partidos del conurbano son GBA y el resto de la provincia
        (Mar del Plata, Bahia Blanca, Tandil...) es Pampeana."""
        if self.provincia == "AR-B":
            return "GBA" if _norm(self.localidad) in PARTIDOS_GBA else "Pampeana"
        return PROVINCIA_A_REGION.get(self.provincia)

    @property
    def region(self) -> str | None:
        """Region estadistica de INDEC a la que pertenece la sucursal.

        Devuelve None si la provincia no se reconoce (dato faltante o mal
        cargado en el origen) — esas filas se descartan y se cuentan, en
        vez de asignarlas a una region por defecto."""
        if self.provincia == "AR-B":
            return "GBA" if _norm(self.localidad) in PARTIDOS_GBA else "Pampeana"
        return PROVINCIA_A_REGION.get(self.provincia)

    @property
    def es_gba(self) -> bool:
        """Compatibilidad: True si la sucursal cae en la region GBA."""
        return self.region == "GBA"


def leer_sucursales_de_zip(path: Path) -> dict[tuple[str, str], Sucursal]:
    """Recorre el ZIP diario y devuelve {(id_comercio, id_sucursal): Sucursal}.
    Los sucursales.csv son chicos (unos pocos KB), asi que leerlos todos es
    barato aunque el ZIP pese cientos de MB."""
    mapa: dict[tuple[str, str], Sucursal] = {}
    with zipfile.ZipFile(path) as z:
        for nombre in sorted(n for n in z.namelist() if n.lower().endswith(".zip")):
            try:
                inner = zipfile.ZipFile(io.BytesIO(z.read(nombre)))
            except (zipfile.BadZipFile, OSError):
                continue
            objetivo = next((f for f in inner.namelist()
                             if f.lower().endswith("sucursales.csv")), None)
            if not objetivo:
                continue
            raw = inner.read(objetivo).decode("utf-8-sig", errors="replace")
            for fila in csv.DictReader(io.StringIO(raw), delimiter="|"):
                sid = (fila.get("id_sucursal") or "").strip()
                cid = (fila.get("id_comercio") or "").strip()
                if not sid or not cid:
                    continue
                mapa[(cid, sid)] = Sucursal(
                    id_comercio=cid, id_sucursal=sid,
                    # normalizado: en datos reales aparecen "Supermercado" y
                    # "supermercado" mezclados en el mismo campo
                    tipo=(fila.get("sucursales_tipo") or "").strip().capitalize(),
                    localidad=(fila.get("sucursales_localidad") or "").strip(),
                    provincia=(fila.get("sucursales_provincia") or "").strip(),
                )
    return mapa


def resumen(mapa: dict[tuple[str, str], Sucursal]) -> str:
    import collections
    reg = collections.Counter(s.region or "(sin region)" for s in mapa.values())
    tipo = collections.Counter(s.tipo for s in mapa.values())
    total = len(mapa)
    lineas = [f"Sucursales: {total:,}", "", "Por REGION de INDEC:"]
    for r, k in reg.most_common():
        lineas.append(f"  {r:22s} {k:>6,}  ({k/total:.1%})")
    lineas.append("\nPor estrato de comercio:")
    for t, k in tipo.most_common():
        lineas.append(f"  {t or '(vacio)':22s} {k:>6,}")
    return "\n".join(lineas)
