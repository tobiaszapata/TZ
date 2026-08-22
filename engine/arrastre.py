"""
Piso mensual bajo precios constantes — extensión propia sobre el "efecto
arrastre" que describe Metodología N°32, sección 6, y Notas al Pie N°2.

AVISO DE HONESTIDAD METODOLÓGICA:
Lo que sigue NO es una fórmula que INDEC publique. INDEC describe el
mecanismo cualitativamente (si el precio sube al final del mes, pesa poco
ese mes y pesa todo el mes siguiente) pero no publica una fórmula de "piso
proyectado" en tiempo real, porque ellos publican una sola vez al mes,
cerrado el mes. Nosotros tenemos precios diarios, así que podemos ir más
lejos: formalizar esa idea en una fórmula que se pueda correr CUALQUIER día
del mes con los datos que hay hasta ese día. Esto es nuestro, hay que
presentarlo como tal.

LA IDEA:
INDEC compara el promedio de precios del mes t contra el promedio del mes
t-1 (no punta contra punta — ver docs/decisiones.md, "El sesgo de
comparación punta a punta", que es el error de diseño más grande del
proyecto anterior). Si el mes tiene D días hábiles y hoy es el día k <= D,
el promedio del mes se puede partir en dos pedazos:

    promedio_mes = (k/D) * promedio(días 1..k)  +  (D-k)/D * promedio(días k+1..D)

El primer término ya está determinado — son precios que ya observamos. El
segundo término es el futuro, que no conocemos. Bajo el supuesto de que el
último precio observado se mantiene sin cambios hasta que cierre el mes
(el supuesto más simple posible, no una predicción), el segundo término se
estima como el último precio observado. Eso da un "piso": el promedio que
va a dar el mes SI NO PASA NADA MÁS.

QUÉ NO ES este número: no es una garantía de que la inflación no puede ser
menor. Si en lo que queda del mes los precios bajan, el cierre real puede
quedar por debajo del piso. Lo que sí es: un número que solo puede quedar
desactualizado por sorpresas de acá al cierre, nunca por el pasado — y que
se vuelve más preciso (el término `avance` crece) cada día que pasa.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PisoMensual:
    dias_transcurridos: int
    dias_totales_mes: int
    avance: float                    # 0 a 1: qué fracción del mes ya está determinada
    promedio_parcial_observado: float  # promedio de los días ya transcurridos
    ultimo_valor_observado: float
    promedio_proyectado_piso: float    # bajo supuesto de precio constante el resto del mes
    variacion_piso_pct: float          # promedio_proyectado_piso vs. mes anterior, en %


def calcular_piso(
    valores_diarios_mes_actual: list[float],
    dias_totales_mes: int,
    valor_promedio_mes_anterior: float,
) -> PisoMensual:
    """`valores_diarios_mes_actual` es la serie de valores (precio o índice,
    funciona igual en cualquier nivel de agregación) para cada día hábil ya
    transcurrido del mes en curso, en orden. No hace falta que tenga los
    `dias_totales_mes` completos — de hecho la gracia es correrlo con lo
    que haya hasta hoy.
    """
    if not valores_diarios_mes_actual:
        raise ValueError("necesito al menos un día observado del mes en curso")
    if dias_totales_mes <= 0:
        raise ValueError("dias_totales_mes debe ser positivo")
    k = len(valores_diarios_mes_actual)
    if k > dias_totales_mes:
        raise ValueError("hay más observaciones que días en el mes")

    avance = k / dias_totales_mes
    promedio_parcial = sum(valores_diarios_mes_actual) / k
    ultimo = valores_diarios_mes_actual[-1]

    dias_restantes = dias_totales_mes - k
    promedio_piso = (
        k * promedio_parcial + dias_restantes * ultimo
    ) / dias_totales_mes

    variacion_piso = (promedio_piso / valor_promedio_mes_anterior - 1) * 100

    return PisoMensual(
        dias_transcurridos=k,
        dias_totales_mes=dias_totales_mes,
        avance=avance,
        promedio_parcial_observado=promedio_parcial,
        ultimo_valor_observado=ultimo,
        promedio_proyectado_piso=promedio_piso,
        variacion_piso_pct=variacion_piso,
    )
