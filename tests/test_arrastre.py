import math

from engine.arrastre import calcular_piso


def test_piso_con_precios_constantes_reproduce_ese_mismo_promedio():
    r = calcular_piso(
        valores_diarios_mes_actual=[100.0] * 10,
        dias_totales_mes=20,
        valor_promedio_mes_anterior=90.0,
    )
    assert math.isclose(r.promedio_proyectado_piso, 100.0)
    assert math.isclose(r.avance, 0.5)
    assert math.isclose(r.variacion_piso_pct, (100 / 90 - 1) * 100)


def test_piso_caso_resuelto_a_mano_con_precios_crecientes():
    # 5 de 20 días hábiles, precios 100,101,102,103,104
    # promedio_parcial = 510/5 = 102 ; ultimo = 104
    # promedio_piso = (5*102 + 15*104) / 20 = (510+1560)/20 = 103.5
    valores = [100.0, 101.0, 102.0, 103.0, 104.0]
    r = calcular_piso(
        valores_diarios_mes_actual=valores,
        dias_totales_mes=20,
        valor_promedio_mes_anterior=100.0,
    )
    assert math.isclose(r.avance, 0.25)
    assert math.isclose(r.promedio_parcial_observado, 102.0)
    assert math.isclose(r.promedio_proyectado_piso, 103.5)
    assert math.isclose(r.variacion_piso_pct, 3.5)


def test_piso_al_cierre_del_mes_coincide_con_el_promedio_observado():
    # cuando dias_transcurridos == dias_totales_mes, no queda nada por
    # proyectar: el piso tiene que ser exactamente el promedio observado.
    valores = [100.0, 102.0, 98.0, 104.0]
    r = calcular_piso(
        valores_diarios_mes_actual=valores,
        dias_totales_mes=4,
        valor_promedio_mes_anterior=90.0,
    )
    assert math.isclose(r.avance, 1.0)
    assert math.isclose(r.promedio_proyectado_piso, r.promedio_parcial_observado)
