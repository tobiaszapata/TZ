"""
Índice elemental de una variedad: el nivel más bajo de la canasta.

Todo lo demás del sistema (agregación por clase, división, nivel general) es
una suma ponderada de estos índices. Si esto está mal, todo lo de arriba
está mal aunque las cuentas de más arriba sean perfectas — por eso es el
primer módulo que se escribe y el primero que se testea contra ejemplos
resueltos a mano (ver tests/test_index_elemental.py).

Implementa las fórmulas 6 a 10 de Metodología N°32, sección 5.1, con una
simplificación deliberada de fase 1 explicada abajo.

QUÉ DICE INDEC (resumen de la fórmula):
1. El precio promedio de una variedad en un mes es la MEDIA GEOMÉTRICA
   simple de los precios de los artículos que la integran (fórmula 7).
2. Cuando hay dos estratos de comercio (supermercados y negocios
   tradicionales), primero se calcula el promedio geométrico de cada
   estrato por separado, y luego se combinan con una proporción FIJA
   (no de mercado) que sale de la ENGHo — fórmula 8.
3. El relativo es el cociente entre el precio promedio de este mes y el
   del mes anterior (fórmula 9).
4. El índice elemental es la productoria (encadenamiento) de esos
   relativos desde el mes base (fórmula 10).

SIMPLIFICACIÓN DE FASE 1 — por qué y qué implica:
SEPA cubre cadenas de supermercados. No tenemos (todavía) un panel de
"negocios tradicionales" equivalente al que releva INDEC a mano en más de
16.000 comercios de barrio. Eso significa que en fase 1 estamos calculando
el estrato "supermercados" únicamente, SIN combinarlo con el estrato
tradicional de la fórmula 8. Esto no es un error de implementación: es un
límite real de cobertura que hay que declarar en cada reporte, no esconder
en el código. Ver docs/decisiones.md, "El sesgo de canal".
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


def media_geometrica(precios: list[float]) -> float:
    """Media geométrica simple. Fórmula 7 de Metodología 32.

    Se usa geométrica y no aritmética por una razón puntual, no por
    intuición: la media geométrica de RELATIVOS (precio_t / precio_t-1) es
    simétrica ante cambios proporcionales, y la aritmética no. Ejemplo: un
    producto que baja 50% y después vuelve a subir 100% termina exactamente
    donde empezó — proporcionalmente no cambió nada. La media geométrica de
    esos dos relativos (0.5 y 2.0) da exactamente 1.0 (sin cambio). La
    media aritmética de los mismos dos relativos da 1.25: un +25% que no
    existió. Esa sobreestimación de la media aritmética de relativos es
    conocida en la literatura de números índice (es el motivo por el que
    el manual de IPC de OIT/FMI/OCDE/ONU/BM — citado en la bibliografía de
    Metodología 32 — prefiere índices tipo Jevons/geométrico frente al
    índice de Carli). Por eso no hace falta censurar ofertas puntuales
    (que es lo que hacía la winsorización al 15% del proyecto anterior,
    y que Metodología 17 muestra que termina subestimando el nivel): el
    propio promedio geométrico ya absorbe una baja temporaria sin sesgo,
    siempre que se aplique sobre relativos y el precio se recupere.
    """
    if not precios:
        raise ValueError("no se puede promediar una lista vacía de precios")
    if any(p <= 0 for p in precios):
        raise ValueError("precio no positivo — revisar antes de promediar, no filtrar en silencio")
    log_sum = sum(math.log(p) for p in precios)
    return math.exp(log_sum / len(precios))


def relativo(precio_actual: float, precio_base: float) -> float:
    """Cociente entre precio promedio actual y el del período anterior.
    Fórmula 9. Un relativo de 1.03 significa +3% respecto al período base."""
    if precio_base <= 0:
        raise ValueError("precio_base debe ser positivo")
    return precio_actual / precio_base


def indice_elemental_encadenado(relativos: list[float], base: float = 100.0) -> list[float]:
    """Encadena una secuencia de relativos mes a mes para obtener el índice
    en cada punto, arrancando en `base`. Fórmula 10.

    Devuelve la serie completa (no solo el último valor) porque el índice
    encadenado ES la serie — cada punto depende de que todos los anteriores
    estén bien encadenados, y queremos poder auditar el camino, no solo el
    resultado final.
    """
    serie = [base]
    for r in relativos:
        serie.append(serie[-1] * r)
    return serie


@dataclass
class ObservacionVariedad:
    """Una fila cruda: un precio, un producto, un comercio, un día.
    Es el único dato que se guarda como verdad — todo lo demás se
    recalcula desde acá. Ver docs/decisiones.md, "Por qué no hay
    endpoints de edición".

    `nombre_producto` es opcional (default vacío) para no romper código
    existente que construye esta clase sin ese dato — pero conviene
    completarlo siempre que se pueda: es lo único que permite mostrar
    "Banana" en un reporte en vez de un código EAN ilegible. Se guarda
    aparte (storage/db.py, tabla `productos`), no en cada fila de precio,
    porque el nombre no cambia día a día y no tiene sentido repetirlo."""
    fecha: str          # ISO "YYYY-MM-DD"
    ean_o_id: str
    comercio: str
    precio: float
    nombre_producto: str = ""
    region: str = ""     # region estadistica INDEC (GBA, Pampeana, ...)
    region: str = "GBA"   # region estadistica INDEC de la sucursal
    # region estadistica de INDEC (GBA, Pampeana, Noroeste, Noreste, Cuyo,
    # Patagonia). Se guarda para poder ponderar cada region con sus propios
    # pesos y despues agregar a nacional.
    region: str | None = None


@dataclass
class PrecioMensualVariedad:
    clase_codigo: str
    mes: str             # "YYYY-MM"
    precio_promedio: float
    n_observaciones: int
    n_articulos_distintos: int
    metodo: str = "media_geometrica_supermercados_unico_estrato"


def precio_mensual_variedad(
    obs: list[ObservacionVariedad], clase_codigo: str, mes: str
) -> PrecioMensualVariedad:
    """Colapsa todas las observaciones diarias de una clase en un mes a un
    único precio promedio, vía media geométrica sobre TODAS las
    observaciones del mes (no solo dos visitas como en el relevamiento
    físico de INDEC — con SEPA tenemos una observación por día hábil por
    comercio, que es más densidad de información, no menos)."""
    precios = [o.precio for o in obs if o.fecha.startswith(mes)]
    if not precios:
        raise ValueError(f"sin observaciones para {clase_codigo} en {mes}")
    return PrecioMensualVariedad(
        clase_codigo=clase_codigo,
        mes=mes,
        precio_promedio=media_geometrica(precios),
        n_observaciones=len(precios),
        n_articulos_distintos=len({o.ean_o_id for o in obs if o.fecha.startswith(mes)}),
    )
