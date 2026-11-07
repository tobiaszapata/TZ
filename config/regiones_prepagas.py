"""
Equivalencia entre la REGION que declaran las prepagas (texto libre) y las
6 regiones estadisticas del IPC de INDEC.

POR QUE EXISTE: el sitio de la Superintendencia de Servicios de Salud
(cuadrostarifarios.sssalud.gob.ar) no usa las regiones de INDEC. Cada entidad
escribe la region como quiere: "CABA", "AMBA", "PROVINCIA DE BUENOS AIRES",
"Pais excepto Patagonia, Bs As y CABA", "SALTA, JUJUY, TUCUMAN, MISIONES,
CHACO, FORMOSA", "Region Patagonia incluye Neuquen Chubut ... (excepto Ciudad
de Viedma)", etc. Se relevaron 137 textos distintos en octubre 2026.

REGIONES DE INDEC (Metodologia N°32, Cuadro 5; los aglomerados de cada una):
  GBA       Ciudad de Buenos Aires + 24 partidos del Gran Buenos Aires.
  Pampeana  Buenos Aires (resto), Cordoba, Entre Rios, Santa Fe, La Pampa
            (Santa Rosa), Gran La Plata, Mar del Plata, Bahia Blanca, etc.
  Noreste   Chaco, Corrientes, Formosa, Misiones.
  Noroeste  Catamarca, Jujuy, La Rioja, Salta, Santiago del Estero, Tucuman.
  Cuyo      Mendoza, San Juan, San Luis.
  Patagonia Chubut, Neuquen, Rio Negro, Santa Cruz, Tierra del Fuego.

COMO SE USA UN TEXTO QUE ABARCA VARIAS REGIONES: el precio de ese plan rige
en TODAS las regiones que abarca, asi que aporta a cada una de ellas (no se
reparte). Ejemplo: "NACIONAL" aporta a las 6; "CABA, Provincia de Bs As y
Ciudad de Viedma" aporta a GBA, Pampeana y Patagonia.

APROXIMACIONES (declaradas, no ocultas):
 * "Provincia de Buenos Aires" abarca GBA (los 24 partidos) y Pampeana (el
   interior de la provincia): aporta a las dos. Si el texto dice "interior",
   "centro" o "resto" aporta solo a Pampeana.
 * "Pais excepto ... Bs As ..." resta solo GBA (el resto de la provincia sigue
   siendo Pampeana por Cordoba, Santa Fe, Entre Rios y La Pampa).
 * Un "(excepto Ciudad de Viedma)" o "(excluye dptos. ...)" entre parentesis
   se ignora: son localidades sueltas, no regiones enteras.
 * Textos ambiguos ("GENERAL", "Resto", "Interior", "ZONA CENTRO",
   "NO IDENTIFICADA") se resuelven con una regla razonable pero quedan
   marcados `dudosa`: el script de calculo imprime cuantas cápitas caen ahi
   y se pueden corregir sin tocar codigo con externos/prepagas/regiones.csv.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

REGIONES_INDEC = ("GBA", "Pampeana", "Noreste", "Noroeste", "Cuyo", "Patagonia")
TODAS = frozenset(REGIONES_INDEC)


@dataclass(frozen=True)
class Clasificacion:
    regiones: frozenset
    certeza: str        # "clara" | "dudosa" | "sin_clasificar" | "manual"


def normalizar(texto: str | None) -> str:
    """Mayusculas, sin acentos, sin puntuacion, espacios simples."""
    if not texto:
        return ""
    t = unicodedata.normalize("NFKD", texto)
    t = "".join(c for c in t if not unicodedata.combining(c)).upper()
    t = re.sub(r"[^A-Z0-9]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# Cada tupla: (patron, regiones). Se aplican EN ORDEN y cada match se
# CONSUME del texto, para que "GRAN BUENOS AIRES" cuente como GBA y no
# tambien como "Buenos Aires" (provincia).
_GBA = (re.compile(r"\bCABA\b|CAPITAL FEDERAL|CIUDAD AUTONOMA|\bAMBA\b|\bGBA\b|GRAN BUENOS AIRES"
                   r"|AREA METROPOLITANA DE BUENOS AIRES|AREA METROPOLITANA|CONURBANO"), {"GBA"})
_PROV_BSAS = re.compile(r"\bPROVINCIA DE BUENOS AIRES\b|\bPCIA BS AS\b|\bPROV DE BS AS\b"
                        r"|\bBUENOS ?AIRES\b|\bBS ?AS\b|\bBSAS\b")
_OTROS = [
    (re.compile(r"\bCORDOBA\b|\bENTRE RIOS\b|\bSANTA ?FE\b|\bSTA FE\b|\bLA PAMPA\b|\bROSARIO\b"
                r"|\bSANTO TOME\b|\bRIO CUARTO\b|\bVILLA MARIA\b|\bLA PLATA\b|\bMAR DEL PLATA\b"
                r"|\bPUEYRREDON\b|\bBAHIA BLANCA\b|\bTANDIL\b|\bOLAVARRIA\b"), {"Pampeana"}),
    (re.compile(r"\bCHACO\b|\bCORRIENTES\b|\bFORMOSA\b|\bMISIONES\b"), {"Noreste"}),
    (re.compile(r"\bCATAMARCA\b|\bJUJUY\b|\bLA RIOJA\b|\bSALTA\b|\bSANTIAGO DEL ESTERO\b"
                r"|\bSGO DEL ESTERO\b|\bSGO ESTERO\b|\bTUCUMAN\b"), {"Noroeste"}),
    (re.compile(r"\bMENDOZA\b|\bSAN JUAN\b|\bSAN LUIS\b"), {"Cuyo"}),
    (re.compile(r"\bPATAGONIA\b|\bNEUQUEN\b|\bCHUBUT\b|\bRIO NEGRO\b|\bSANTA CRUZ\b"
                r"|\bTIERRA DEL FUEGO\b|\bVIEDMA\b|\bBARILOCHE\b"), {"Patagonia"}),
]
_NACIONAL = re.compile(r"\bNACIONAL\b|\bGENERAL\b|\bPAIS\b|\bREP ARG\b|\bREPUBLICA ARGENTINA\b"
                       r"|\bTODO EL PAIS\b|\bTOTAL PAIS\b")
_INTERIOR = re.compile(r"\bINTERIOR\b|\bRESTO\b|\bCENTRO\b")
_EXCEPTO = re.compile(r"\bEXCEPTO\b|\bEXCLUYE\b|\bEXCLUYENDO\b")

# Textos que no tienen ninguna provincia pero si una regla razonable.
_ZONAS_DUDOSAS = [
    (re.compile(r"^ZONA (NORTE|SUR|OESTE)$"), {"GBA"}),
]


def _regiones_de_tokens(norm: str, bsas_solo_gba: bool = False) -> set:
    """Regiones nombradas en `norm` (sin interpretar 'excepto')."""
    out: set = set()
    t = norm
    if re.search(r"\bPATAGONIA\b", t):
        # "Region Patagonia incluye ... La Pampa ...": la entidad mete La Pampa
        # en su lista PATAGONICA; para INDEC La Pampa es Pampeana, pero no se
        # le suma esa region (seria inflar Pampeana con una lista patagonica).
        t = re.sub(r"\bLA PAMPA\b", " ", t)
    m = _GBA[0].search(t)
    if m:
        out |= _GBA[1]
        t = _GBA[0].sub(" ", t)
    if _PROV_BSAS.search(t):
        if bsas_solo_gba:
            out.add("GBA")
        elif _INTERIOR.search(norm):
            out.add("Pampeana")
        else:
            out |= {"GBA", "Pampeana"}
        t = _PROV_BSAS.sub(" ", t)
    for patron, regs in _OTROS:
        if patron.search(t):
            out |= regs
    return out


def _clasificar(texto: str) -> Clasificacion:
    norm = normalizar(texto)
    if not norm or norm == "NO IDENTIFICADA":
        return Clasificacion(TODAS, "dudosa")

    # (excepto ...) / (excluye ...) entre parentesis: localidades sueltas.
    sin_par = re.sub(r"\((?:\s*(?:EXCEPTO|EXCLUYE|EXCLUYENDO)[^)]*)\)", " ", texto, flags=re.I)
    norm = normalizar(sin_par)

    for patron, regs in _ZONAS_DUDOSAS:
        if patron.match(norm):
            return Clasificacion(frozenset(regs), "dudosa")

    partes = _EXCEPTO.split(norm, maxsplit=1)
    cabeza = partes[0].strip()
    cola = partes[1].strip() if len(partes) > 1 else ""

    nombradas_cabeza = _regiones_de_tokens(cabeza)
    es_generico = bool(_NACIONAL.search(cabeza))

    if es_generico and not nombradas_cabeza:
        regs = set(TODAS)
        if _INTERIOR.search(cabeza):               # "Interior pais": todo menos el AMBA
            regs -= {"GBA"}
        if cola:
            regs -= _regiones_de_tokens(cola, bsas_solo_gba=True)
        certeza = "dudosa" if re.fullmatch(r"GENERAL", cabeza) else "clara"
        return Clasificacion(frozenset(regs), certeza)

    if nombradas_cabeza:
        regs = set(nombradas_cabeza)
        if cola:                                   # "X EXCEPTO LA PLATA Y": sigue la lista
            regs |= _regiones_de_tokens(cola)
        return Clasificacion(frozenset(regs), "clara")

    if _INTERIOR.search(cabeza):
        return Clasificacion(TODAS - {"GBA"}, "dudosa")
    return Clasificacion(TODAS, "sin_clasificar")


@lru_cache(maxsize=4096)
def clasificar_region(texto: str | None) -> Clasificacion:
    return _clasificar(texto or "")


def cargar_overrides(ruta: Path | None) -> dict[str, frozenset]:
    """Lee externos/prepagas/regiones.csv (columnas: region_texto;regiones, con
    las regiones separadas por coma). Sirve para corregir una clasificacion
    dudosa sin tocar codigo. Si no existe, devuelve {}."""
    if ruta is None or not Path(ruta).exists():
        return {}
    salida: dict[str, frozenset] = {}
    with open(ruta, newline="", encoding="utf-8") as f:
        for fila in csv.DictReader(f, delimiter=";"):
            clave = normalizar(fila.get("region_texto"))
            regs = {r.strip() for r in (fila.get("regiones") or "").split(",") if r.strip()}
            invalidas = regs - TODAS
            if invalidas:
                raise ValueError(f"regiones.csv: region INDEC desconocida {sorted(invalidas)} "
                                 f"en {fila.get('region_texto')!r}. Validas: {list(REGIONES_INDEC)}")
            if clave and regs:
                salida[clave] = frozenset(regs)
    return salida


def regiones_indec(texto: str | None, overrides: dict[str, frozenset] | None = None) -> Clasificacion:
    """Regiones INDEC que abarca el texto de region de una prepaga."""
    if overrides:
        manual = overrides.get(normalizar(texto))
        if manual:
            return Clasificacion(manual, "manual")
    return clasificar_region(texto)
