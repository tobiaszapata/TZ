"""
Cálculo de rangos de fecha para los presets de la interfaz (Streamlit).

POR QUE ESTO ESTA ACA Y NO ADENTRO DE app_streamlit.py:
app_streamlit.py necesita Streamlit instalado para poder importarse siquiera,
y este entorno de desarrollo no tiene forma de instalarlo. Sacar la lógica de
fechas a un módulo aparte, sin dependencias de Streamlit, permite testearla
de verdad (ver tests/test_fechas.py) en vez de "probarla a mano" en la nube y
enterarse del bug cuando ya está en manos de otra persona — que es
exactamente lo que pasó con el bug que corrige este módulo.

EL BUG QUE CORRIGE `acotar_rango`:
Los presets restan una cantidad fija de días (6, 7, 13...) para armar "la
semana pasada" o "el mes anterior". Si la base tiene pocos días cargados
—algo normal al empezar, o el primer día que alguien prueba la app— esa
resta da una fecha ANTERIOR al día más viejo disponible. Streamlit no
acepta que el valor por defecto de un `date_input` quede fuera de
[min_value, max_value]: en vez de mostrar un aviso, la aplicación entera
se cae con `StreamlitAPIException`. `acotar_rango` recorta las cuatro
fechas al rango real disponible antes de que lleguen al widget.
"""

from __future__ import annotations

from datetime import date, timedelta


def calcular_preset(preset: str, d_max: date) -> tuple[date, date, date, date]:
    """Devuelve (desde, hasta, desde_base, hasta_base) para un preset dado,
    SIN tener en cuenta todavía cuántos días hay realmente disponibles —
    eso lo resuelve `acotar_rango` a continuación. Separar los dos pasos
    permite testear cada uno por separado.

    "personalizado" arranca con las cuatro fechas en el último día
    disponible: la persona elige a mano tanto "período a analizar" como
    "comparado contra". Se probó que "período a analizar" arrancara
    cubriendo todo el rango cargado, pero no tenía sentido para el caso de
    uso real (comparar un mes puntual contra otro mes puntual, no "todo"
    contra un mes) — se volvió a esta versión más simple a pedido."""
    if preset == "semana":
        hasta, desde = d_max, d_max - timedelta(days=6)
        hasta_base, desde_base = desde - timedelta(days=1), desde - timedelta(days=7)
    elif preset == "mes":
        desde = d_max.replace(day=1)
        hasta = d_max
        hasta_base = desde - timedelta(days=1)
        desde_base = hasta_base.replace(day=1)
    else:  # "personalizado" o cualquier otro valor: sin ventana, todo en el último día
        desde = hasta = hasta_base = desde_base = d_max
    return desde, hasta, desde_base, hasta_base


def acotar_rango(
    desde: date, hasta: date, desde_base: date, hasta_base: date,
    d_min: date, d_max: date,
) -> tuple[date, date, date, date]:
    """Recorta las cuatro fechas para que ninguna quede fuera de
    [d_min, d_max]. Con datos suficientes, esto no cambia nada (todas las
    fechas ya caen dentro del rango). Con pocos días cargados, es lo que
    evita el crash: nunca deja pasar una fecha anterior a la más vieja
    disponible ni posterior a la más nueva."""
    def _acotar(d: date) -> date:
        return max(d_min, min(d_max, d))

    return _acotar(desde), _acotar(hasta), _acotar(desde_base), _acotar(hasta_base)


def hace_falta_confirmar(combinacion_actual: tuple, combinacion_confirmada: tuple | None) -> bool:
    """Logica PURA de cuándo la app tiene que pedir confirmación antes de
    calcular con un período nuevo, en vez de disparar el cálculo apenas
    arranca o apenas se toca cualquier fecha.

    Se separa de app_streamlit.py para poder testearla sin Streamlit
    instalado — ver tests/test_confirmacion_fechas.py.

    POR QUE ESTO EXISTE: antes, la app calculaba el resultado apenas
    arrancaba, usando el preset activo por defecto ("última semana").
    Alguien que abría el link y no quería ver justamente esa comparación
    tenía la sensación de "por qué me tarda/me muestra esto que no pedí"
    — no era un error de cálculo, pero sí una mala primera impresión.
    Ahora se piden las fechas y se muestra un resumen ANTES de calcular
    nada; recién con la confirmación explícita se dispara el cálculo."""
    return combinacion_confirmada != combinacion_actual
