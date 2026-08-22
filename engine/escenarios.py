"""
Escenarios de cierre de mes — varias respuestas a "como cierra el mes",
cada una con un supuesto DISTINTO y EXPLICITO.

POR QUE VARIOS ESCENARIOS Y NO UNO:
Un solo numero de proyeccion esconde el supuesto que lo genero. Mostrar
cuatro escenarios lado a lado convierte el supuesto en la informacion
principal: el lector ve que el rango de cierre va de X a Y segun que se
asuma, y puede elegir cual creer. Es mas honesto y, para un informe, mas
util: "si los precios se congelan hoy cierra en 7,3%; si sigue el ritmo de
lo que va del mes, 12,1%" dice mucho mas que un numero solo.

--------------------------------------------------------------------------
PUNTO METODOLOGICO CENTRAL — TODOS LOS ESCENARIOS PROYECTAN EL PROMEDIO
DEL MES, NO EL PRECIO DEL ULTIMO DIA.

INDEC compara el promedio del mes contra el promedio del mes anterior (ver
docs/metodologia.md). Entonces proyectar "a cuanto llega el precio el dia
31" seria responder otra pregunta. Lo que hay que proyectar es:

    promedio_mes = (suma de los D valores diarios) / D

de los cuales conocemos los primeros k. Cada escenario es una forma
distinta de completar los dias k+1..D, y despues se promedia TODO el mes.
Por eso un aumento fuerte el dia 28 mueve poco el promedio de ese mes (y
mucho el del siguiente): el efecto arrastre sale solo de esta cuenta.
--------------------------------------------------------------------------

LOS CUATRO ESCENARIOS:

1. CONGELAMIENTO — los precios quedan como el ultimo dia observado.
   Supuesto: variacion futura = 0. Es el "piso": aritmetica pura, sin
   modelo. Solo puede quedar corto si los precios siguen subiendo.

2. CONTINUIDAD DE RITMO — el ritmo diario de lo que va del mes se mantiene
   hasta fin de mes. Se estima una tasa diaria geometrica por ajuste
   log-lineal sobre los dias observados (no lineal: es crecimiento
   compuesto). Responde "que pasa si sigue mostrando este comportamiento".

3. PATRON INTRA-MENSUAL — usa la curva de realizacion de
   engine/proyeccion.py: cuanto de la variacion mensual suele estar hecho a
   esta altura del mes. No asume que el ritmo sigue igual; asume que la
   categoria se comporta como suele comportarse dentro del mes.

4. CONGELA DESPUES DE UNA FECHA — hibrido: sigue el ritmo observado hasta
   un dia elegido, y de ahi en adelante se congela. Sirve para preguntas
   del tipo "si el aumento de tarifas frena la suba a partir del dia 20".

Ninguno es "el correcto". Son cuatro lentes sobre la misma informacion.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class Escenario:
    nombre: str
    supuesto: str                 # explicacion en una linea, para mostrar en reportes
    promedio_mes_proyectado: float
    variacion_pct: float
    es_dato_duro: bool = False    # True solo para congelamiento (sin modelo)


def _variacion(promedio_proyectado: float, nivel_base: float) -> float:
    return (promedio_proyectado / nivel_base - 1) * 100


def tasa_diaria_geometrica(valores: list[float]) -> float:
    """Estima la tasa de crecimiento diaria compuesta de una serie, por
    ajuste log-lineal (minimos cuadrados sobre log(valor) vs. dia).

    Se usa log-lineal y no "ultimo sobre primero" porque el primero
    promedia todos los puntos (mas robusto a un dia raro) y porque el
    crecimiento de precios es multiplicativo, no aditivo: una tasa diaria
    del 0,5% compuesta 20 dias no da 10%, da 10,5%.

    Devuelve la tasa como fraccion (0.005 = +0,5% por dia).
    """
    n = len(valores)
    if n < 2:
        return 0.0
    if any(v <= 0 for v in valores):
        raise ValueError("valores deben ser positivos para ajuste log-lineal")

    xs = list(range(n))
    ys = [math.log(v) for v in valores]
    x_prom = sum(xs) / n
    y_prom = sum(ys) / n
    denom = sum((x - x_prom) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    pendiente = sum((x - x_prom) * (y - y_prom) for x, y in zip(xs, ys)) / denom
    return math.exp(pendiente) - 1


def _promedio_mes(observados: list[float], futuros: list[float]) -> float:
    todos = observados + futuros
    return sum(todos) / len(todos)


def escenario_congelamiento(
    valores_observados: list[float], dias_totales: int, nivel_base: float
) -> Escenario:
    k = len(valores_observados)
    ultimo = valores_observados[-1]
    futuros = [ultimo] * (dias_totales - k)
    prom = _promedio_mes(valores_observados, futuros)
    return Escenario(
        nombre="Congelamiento",
        supuesto="Los precios quedan como el ultimo dia relevado.",
        promedio_mes_proyectado=prom,
        variacion_pct=_variacion(prom, nivel_base),
        es_dato_duro=True,
    )


def escenario_continuidad(
    valores_observados: list[float], dias_totales: int, nivel_base: float
) -> Escenario:
    k = len(valores_observados)
    g = tasa_diaria_geometrica(valores_observados)
    ultimo = valores_observados[-1]
    futuros = [ultimo * ((1 + g) ** (i + 1)) for i in range(dias_totales - k)]
    prom = _promedio_mes(valores_observados, futuros)
    return Escenario(
        nombre="Continuidad de ritmo",
        supuesto=f"Sigue el ritmo de lo que va del mes ({g*100:+.2f}% por dia habil).",
        promedio_mes_proyectado=prom,
        variacion_pct=_variacion(prom, nivel_base),
    )


def escenario_congela_desde(
    valores_observados: list[float],
    dias_totales: int,
    nivel_base: float,
    dia_congelamiento: int,
) -> Escenario:
    """Sigue el ritmo observado hasta `dia_congelamiento` (dia habil del
    mes) y de ahi en adelante se congela."""
    k = len(valores_observados)
    g = tasa_diaria_geometrica(valores_observados)
    ultimo = valores_observados[-1]

    futuros: list[float] = []
    valor = ultimo
    for dia in range(k + 1, dias_totales + 1):
        if dia <= dia_congelamiento:
            valor = valor * (1 + g)
        futuros.append(valor)

    prom = _promedio_mes(valores_observados, futuros)
    return Escenario(
        nombre=f"Congela desde dia habil {dia_congelamiento}",
        supuesto=f"Sigue el ritmo hasta el dia habil {dia_congelamiento}, despues se congela.",
        promedio_mes_proyectado=prom,
        variacion_pct=_variacion(prom, nivel_base),
    )


def escenario_patron_intramensual(
    variacion_observada_pct: float,
    fraccion_realizada: float,
    piso_pct: float,
    nivel_base: float,
    promedio_congelamiento: float,
) -> Escenario:
    """Usa la curva de realizacion intra-mensual (engine/proyeccion.py).
    A diferencia de los otros tres, este escenario razona sobre la
    VARIACION directamente, no completando dias — por eso recibe la
    fraccion ya calculada y devuelve el promedio implicito."""
    if fraccion_realizada < 0.20:
        # muy temprano: sin senal, se reporta el piso
        return Escenario(
            nombre="Patron intra-mensual",
            supuesto="Muy temprano en el mes para aplicar el patron; se reporta el piso.",
            promedio_mes_proyectado=promedio_congelamiento,
            variacion_pct=piso_pct,
        )
    var = max(variacion_observada_pct / fraccion_realizada, piso_pct)
    prom_implicito = nivel_base * (1 + var / 100)
    return Escenario(
        nombre="Patron intra-mensual",
        supuesto=(f"La categoria completa el mes como suele hacerlo "
                  f"({fraccion_realizada:.0%} de la variacion ya realizada a esta altura)."),
        promedio_mes_proyectado=prom_implicito,
        variacion_pct=var,
    )
