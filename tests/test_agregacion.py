import math

from engine.agregacion import incidencia, laspeyres


def test_laspeyres_cobertura_completa():
    r = laspeyres(
        variaciones_pct={"a": 10.0, "b": 0.0},
        pesos={"a": 0.6, "b": 0.4},
    )
    assert math.isclose(r.variacion_pct, 6.0)
    assert math.isclose(r.cobertura, 1.0)


def test_laspeyres_cobertura_parcial_se_renormaliza_y_lo_declara():
    # si "b" no tiene variación todavía, no se asume 0: se excluye del
    # cálculo, y la cobertura queda registrada en 0.6 para que no se lea
    # el resultado como si fuera la canasta completa.
    r = laspeyres(
        variaciones_pct={"a": 10.0},
        pesos={"a": 0.6, "b": 0.4},
    )
    assert math.isclose(r.variacion_pct, 10.0)
    assert math.isclose(r.cobertura, 0.6)
    assert math.isclose(r.peso_cubierto, 0.6)


def test_incidencia_caso_resuelto_a_mano():
    # (110-100)/105 * 0.2 * 100 = 1.904761...
    val = incidencia(
        indice_agrupacion_t=110, indice_agrupacion_t_1=100,
        indice_general_t_1=105, peso_agrupacion=0.2,
    )
    assert math.isclose(val, 1.9047619047619, rel_tol=1e-9)


def test_identidad_suma_de_incidencias_igual_variacion_del_agregado():
    # Construcción: nivel general definido como Laspeyres de "a" (peso .6)
    # y "b" (peso .4). Si a t-1 ambos valen 100 y a t valen 110 y 100
    # respectivamente, el agregado pasa de 100 a 106 (variación 6%).
    # La suma de incidencias de a y b tiene que dar exactamente 6.0.
    peso_a, peso_b = 0.6, 0.4
    indice_a_t, indice_a_t_1 = 110.0, 100.0
    indice_b_t, indice_b_t_1 = 100.0, 100.0
    indice_general_t_1 = peso_a * indice_a_t_1 + peso_b * indice_b_t_1  # = 100

    inc_a = incidencia(indice_a_t, indice_a_t_1, indice_general_t_1, peso_a)
    inc_b = incidencia(indice_b_t, indice_b_t_1, indice_general_t_1, peso_b)

    variacion_general_esperada = 6.0  # calculado a mano arriba en el docstring del módulo
    assert math.isclose(inc_a + inc_b, variacion_general_esperada, rel_tol=1e-9)
