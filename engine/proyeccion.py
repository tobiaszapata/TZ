"""
Proyeccion de cierre de mes por CURVA DE REALIZACION INTRA-MENSUAL.

Esto es distinto —y mejor— que el "piso" de engine/arrastre.py. El piso
asume precio congelado el resto del mes (variacion futura = 0). Esta
proyeccion, en cambio, estima cuanto FALTA realizarse segun como se
comporta historicamente esa categoria dentro del mes.

--------------------------------------------------------------------------
POR QUE NO ES LINEAL (respondiendo la pregunta directa):
La inflacion no se reparte pareja a lo largo del mes. Algunas categorias
cargan aumentos a principio de mes (tarifas, regulados), otras a fin de mes
o en fechas puntuales. "Frutas al dia 15 ya realizo el 60% de su variacion
mensual tipica" es un hecho estimable, y NO implica ni linealidad ni
rendimientos crecientes/decrecientes: es simplemente el patron empirico de
esa categoria. Si al dia 15 llevas +4% y esa categoria suele tener el 60%
hecho a esa altura, el cierre proyectado es 4% / 0.60 = 6.7%.

  variacion_proyectada = variacion_observada_hasta_hoy / fraccion_realizada(dia)

donde `fraccion_realizada(dia)` es una CURVA por categoria, no una recta.
--------------------------------------------------------------------------
LOS DOS LIMITES, DECLARADOS (para no vender lo que no es):

1. NECESITA HISTORIA DIARIA PARA CALIBRARSE. La curva de realizacion se
   estima con meses ya cerrados, dia por dia. Hoy no tenemos ni un mes
   cargado. Por eso este modulo arranca con una curva GENERICA marcada como
   PRELIMINAR (un perfil suave, sin picos, que reparte la realizacion de
   forma monotona pero no lineal), y expone `estado_calibracion` para que
   ningun reporte muestre una proyeccion sin aclarar que la curva todavia
   no se estimo con datos propios. El dia que haya 3+ meses cargados, se
   reemplaza la curva generica por una estimada por categoria SIN tocar el
   resto del sistema.

2. LA PROYECCION ES UN RANGO, NO UN NUMERO. Un cierre proyectado sin banda
   de error miente sobre lo que se sabe. Se devuelve un intervalo cuyo piso
   es exactamente el "piso" de arrastre.py (si nada mas sube) y cuyo centro
   es la proyeccion por curva. El ancho de la banda se achica a medida que
   avanza el mes, porque queda menos por proyectar.
--------------------------------------------------------------------------
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class EstadoCalibracion(str, Enum):
    PRELIMINAR_GENERICA = "preliminar_generica"   # curva no estimada con datos propios todavia
    CALIBRADA_CATEGORIA = "calibrada_categoria"    # estimada con historia real de esta categoria


@dataclass
class Proyeccion:
    dia_habil_actual: int
    dias_habiles_mes: int
    fraccion_mes_transcurrida: float
    fraccion_realizada_estimada: float     # cuanto de la variacion mensual suele estar hecho a esta altura
    variacion_observada_pct: float          # lo efectivamente medido hasta hoy
    variacion_proyectada_pct: float         # cierre estimado (centro)
    piso_pct: float                          # cierre si nada mas cambia (limite inferior duro)
    banda_baja_pct: float
    banda_alta_pct: float
    estado_calibracion: EstadoCalibracion


def curva_realizacion_generica(dia_habil: int, dias_habiles_mes: int) -> float:
    """Fraccion de la variacion mensual que TIPICAMENTE ya esta realizada al
    `dia_habil` de un mes de `dias_habiles_mes` dias habiles.

    PRELIMINAR: no estimada con datos, es un perfil razonable por defecto.
    Propiedades que cumple a proposito:
      - monotona creciente (nunca "se desrealiza"),
      - fraccion(ultimo dia) = 1.0 (al cerrar el mes esta todo realizado),
      - NO lineal: usa una curva suave levemente adelantada (los aumentos
        tienden a concentrarse algo mas en la primera mitad en regimenes
        inflacionarios, por el efecto de arrastre de fin del mes anterior),
        pero sin picos ni saltos que serian invencion pura.

    La forma es t^0.85 con t = dia/dias_mes: da una curva concava suave
    (algo por encima de la diagonal), sin rendimientos constantes. El
    exponente 0.85 es un placeholder honesto — se reemplaza por la
    estimacion real cuando haya datos. Ver docstring del modulo.
    """
    if dias_habiles_mes <= 0:
        raise ValueError("dias_habiles_mes debe ser positivo")
    if dia_habil <= 0:
        return 0.0
    if dia_habil >= dias_habiles_mes:
        return 1.0
    t = dia_habil / dias_habiles_mes
    return t ** 0.85


def proyectar_cierre(
    variacion_observada_pct: float,
    piso_pct: float,
    dia_habil_actual: int,
    dias_habiles_mes: int,
    fraccion_realizada: float | None = None,
    estado: EstadoCalibracion = EstadoCalibracion.PRELIMINAR_GENERICA,
) -> Proyeccion:
    """Proyecta el cierre del mes para una categoria.

    `variacion_observada_pct`: variacion del promedio del mes-hasta-hoy vs
        el mes base (lo que ya devuelve la consulta normal).
    `piso_pct`: el piso de arrastre.py (cierre si nada mas cambia). Se usa
        como limite inferior duro de la banda.
    `fraccion_realizada`: si se pasa (porque hay curva calibrada), se usa;
        si es None, se calcula con la curva generica preliminar.
    """
    if fraccion_realizada is None:
        fraccion_realizada = curva_realizacion_generica(dia_habil_actual, dias_habiles_mes)

    # Al principio del mes no hay senal suficiente para proyectar: con muy
    # pocos dias, dividir la variacion observada por una fraccion chica
    # amplifica ruido y da cierres disparatados (0.2% observado / 0.08 =
    # 2.5% proyectado, que no significa nada). Umbral doble: hacen falta al
    # menos 3 dias habiles Y una fraccion realizada de al menos 20% para
    # arriesgar una proyeccion; si no, la mejor estimacion honesta es el
    # piso, con la banda bien ancha para reflejar la incertidumbre.
    proyeccion_confiable = dia_habil_actual >= 3 and fraccion_realizada >= 0.20
    if not proyeccion_confiable:
        centro = piso_pct
    else:
        centro = variacion_observada_pct / fraccion_realizada

    # La proyeccion nunca puede ser menor que el piso (el piso ya es un
    # minimo garantizado bajo precio-constante).
    centro = max(centro, piso_pct)

    # Banda: el piso es el limite inferior; el ancho hacia arriba es
    # proporcional a cuanto FALTA por realizarse (1 - fraccion). Cuanto mas
    # avanzado el mes, mas angosta.
    falta = 1.0 - fraccion_realizada
    semiancho = (centro - piso_pct) + abs(centro) * 0.15 * falta
    banda_baja = piso_pct
    banda_alta = centro + semiancho

    return Proyeccion(
        dia_habil_actual=dia_habil_actual,
        dias_habiles_mes=dias_habiles_mes,
        fraccion_mes_transcurrida=dia_habil_actual / dias_habiles_mes if dias_habiles_mes else 0.0,
        fraccion_realizada_estimada=fraccion_realizada,
        variacion_observada_pct=variacion_observada_pct,
        variacion_proyectada_pct=centro,
        piso_pct=piso_pct,
        banda_baja_pct=banda_baja,
        banda_alta_pct=banda_alta,
        estado_calibracion=estado,
    )
