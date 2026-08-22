import math

from engine.proyeccion import (
    EstadoCalibracion,
    curva_realizacion_generica,
    proyectar_cierre,
)


def test_curva_no_es_lineal_pero_es_monotona():
    dias = 20
    valores = [curva_realizacion_generica(d, dias) for d in range(0, dias + 1)]
    # monotona creciente
    assert all(valores[i] <= valores[i + 1] for i in range(len(valores) - 1))
    # arranca en 0 y termina en 1
    assert math.isclose(valores[0], 0.0)
    assert math.isclose(valores[-1], 1.0)
    # NO lineal: en el punto medio, la fraccion realizada != 0.5
    medio = curva_realizacion_generica(10, 20)
    assert not math.isclose(medio, 0.5, abs_tol=0.02)
    assert medio > 0.5  # curva concava: adelanta la realizacion


def test_proyeccion_escala_por_fraccion_realizada():
    # Si al dia 10 de 20 se realizo el 55% y llevamos +4%, el centro
    # proyectado es 4/0.55 ~= 7.27%.
    p = proyectar_cierre(
        variacion_observada_pct=4.0,
        piso_pct=4.0,
        dia_habil_actual=10,
        dias_habiles_mes=20,
    )
    esperado = 4.0 / curva_realizacion_generica(10, 20)
    assert math.isclose(p.variacion_proyectada_pct, max(esperado, 4.0), rel_tol=1e-9)


def test_proyeccion_nunca_por_debajo_del_piso():
    # Aunque la formula diera menos, el piso manda como limite inferior.
    p = proyectar_cierre(
        variacion_observada_pct=1.0,
        piso_pct=5.0,   # piso alto (mucho arrastre)
        dia_habil_actual=10,
        dias_habiles_mes=20,
    )
    assert p.variacion_proyectada_pct >= 5.0
    assert p.banda_baja_pct == 5.0


def test_inicio_de_mes_no_divide_por_cero_y_cae_al_piso():
    p = proyectar_cierre(
        variacion_observada_pct=0.2,
        piso_pct=0.2,
        dia_habil_actual=1,
        dias_habiles_mes=20,
    )
    # fraccion realizada casi nula -> centro = piso, sin crash
    assert math.isclose(p.variacion_proyectada_pct, 0.2)


def test_banda_se_angosta_al_avanzar_el_mes():
    comun = dict(variacion_observada_pct=3.0, piso_pct=2.0, dias_habiles_mes=20)
    temprano = proyectar_cierre(dia_habil_actual=5, **comun)
    tardio = proyectar_cierre(dia_habil_actual=18, **comun)
    ancho_temprano = temprano.banda_alta_pct - temprano.banda_baja_pct
    ancho_tardio = tardio.banda_alta_pct - tardio.banda_baja_pct
    assert ancho_tardio < ancho_temprano


def test_estado_calibracion_default_es_preliminar():
    p = proyectar_cierre(3.0, 2.0, 10, 20)
    assert p.estado_calibracion == EstadoCalibracion.PRELIMINAR_GENERICA
