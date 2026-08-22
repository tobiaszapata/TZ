import math

from engine.escenarios import (
    escenario_congela_desde,
    escenario_congelamiento,
    escenario_continuidad,
    escenario_patron_intramensual,
    tasa_diaria_geometrica,
)


def test_tasa_geometrica_serie_constante_da_cero():
    assert abs(tasa_diaria_geometrica([100.0] * 5)) < 1e-12


def test_tasa_geometrica_recupera_una_tasa_conocida():
    # serie generada con exactamente +2% diario
    valores = [100.0 * (1.02 ** i) for i in range(6)]
    g = tasa_diaria_geometrica(valores)
    assert math.isclose(g, 0.02, rel_tol=1e-9)


def test_tasa_geometrica_serie_de_un_punto_no_rompe():
    assert tasa_diaria_geometrica([100.0]) == 0.0


def test_congelamiento_promedia_el_mes_no_toma_el_ultimo_dia():
    # 2 dias observados a 100 y 200, mes de 4 dias -> se congela en 200.
    # promedio del mes = (100+200+200+200)/4 = 175, NO 200.
    e = escenario_congelamiento([100.0, 200.0], dias_totales=4, nivel_base=100.0)
    assert math.isclose(e.promedio_mes_proyectado, 175.0)
    assert math.isclose(e.variacion_pct, 75.0)
    assert e.es_dato_duro is True


def test_continuidad_proyecta_mas_alto_que_congelamiento_si_sube():
    valores = [100.0, 102.0, 104.04]  # +2% diario
    cong = escenario_congelamiento(valores, 10, 100.0)
    cont = escenario_continuidad(valores, 10, 100.0)
    assert cont.variacion_pct > cong.variacion_pct


def test_continuidad_iguala_congelamiento_si_la_serie_es_plana():
    valores = [100.0, 100.0, 100.0]
    cong = escenario_congelamiento(valores, 10, 100.0)
    cont = escenario_continuidad(valores, 10, 100.0)
    assert math.isclose(cont.variacion_pct, cong.variacion_pct, abs_tol=1e-9)


def test_congela_desde_queda_entre_congelamiento_y_continuidad():
    valores = [100.0, 102.0, 104.04]
    cong = escenario_congelamiento(valores, 20, 100.0)
    cont = escenario_continuidad(valores, 20, 100.0)
    medio = escenario_congela_desde(valores, 20, 100.0, dia_congelamiento=10)
    assert cong.variacion_pct <= medio.variacion_pct <= cont.variacion_pct


def test_patron_intramensual_temprano_devuelve_el_piso():
    e = escenario_patron_intramensual(
        variacion_observada_pct=1.0, fraccion_realizada=0.10,
        piso_pct=2.0, nivel_base=100.0, promedio_congelamiento=102.0,
    )
    assert math.isclose(e.variacion_pct, 2.0)


def test_patron_intramensual_escala_por_la_fraccion():
    e = escenario_patron_intramensual(
        variacion_observada_pct=3.0, fraccion_realizada=0.60,
        piso_pct=1.0, nivel_base=100.0, promedio_congelamiento=101.0,
    )
    assert math.isclose(e.variacion_pct, 5.0)  # 3 / 0.60
