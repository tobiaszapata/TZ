"""
Tests de engine.fechas.hace_falta_confirmar.

Corrige la molestia real reportada: la app calculaba resultados apenas
arrancaba, usando el preset "última semana" sin que nadie lo hubiera
elegido — daba la sensación de "por qué me tarda/me muestra algo que no
pedí". Ahora se pide confirmar las fechas antes de calcular nada.
"""

from datetime import date

from engine.fechas import hace_falta_confirmar


def test_primera_vez_sin_nada_confirmado_hace_falta_confirmar():
    combinacion = (date(2026, 8, 18), date(2026, 8, 24), date(2026, 8, 11), date(2026, 8, 17))
    assert hace_falta_confirmar(combinacion, None) is True


def test_misma_combinacion_ya_confirmada_no_hace_falta_de_nuevo():
    combinacion = (date(2026, 8, 18), date(2026, 8, 24), date(2026, 8, 11), date(2026, 8, 17))
    assert hace_falta_confirmar(combinacion, combinacion) is False


def test_cambiar_cualquier_fecha_vuelve_a_pedir_confirmacion():
    confirmada = (date(2026, 8, 18), date(2026, 8, 24), date(2026, 8, 11), date(2026, 8, 17))
    nueva = (date(2026, 8, 19), date(2026, 8, 24), date(2026, 8, 11), date(2026, 8, 17))
    assert hace_falta_confirmar(nueva, confirmada) is True


def test_cambiar_el_preset_y_volver_al_mismo_resultado_no_pide_confirmar_de_nuevo():
    """Si la persona cambia de preset y después vuelve a uno que da
    exactamente las mismas cuatro fechas ya confirmadas, no hace falta
    pedir confirmación de nuevo — importa la combinación resultante, no
    el camino para llegar a ella."""
    confirmada = (date(2026, 8, 18), date(2026, 8, 24), date(2026, 8, 11), date(2026, 8, 17))
    misma_de_nuevo = (date(2026, 8, 18), date(2026, 8, 24), date(2026, 8, 11), date(2026, 8, 17))
    assert hace_falta_confirmar(misma_de_nuevo, confirmada) is False
