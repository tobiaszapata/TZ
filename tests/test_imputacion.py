import math

from engine.imputacion import MetodoImputacion, resolver_relativo


def test_cobertura_mayor_50_usa_relativo_propio():
    r = resolver_relativo(
        n_precios_validos=6, n_precios_exigidos=10,
        relativo_propio=1.05, relativo_grupo_superior=1.02,
    )
    assert r.metodo == MetodoImputacion.PROPIO
    assert math.isclose(r.relativo_a_usar, 1.05)
    assert math.isclose(r.cobertura, 0.6)


def test_cobertura_entre_20_y_50_usa_grupo_superior():
    r = resolver_relativo(
        n_precios_validos=3, n_precios_exigidos=10,
        relativo_propio=1.05, relativo_grupo_superior=1.02,
    )
    assert r.metodo == MetodoImputacion.GRUPO_SUPERIOR_PARCIAL
    assert math.isclose(r.relativo_a_usar, 1.02)


def test_cobertura_exactamente_50_no_es_mayor_a_50_cae_a_parcial():
    # el corte es "cobertura > 50%", así que 50% exacto NO usa el propio.
    r = resolver_relativo(
        n_precios_validos=5, n_precios_exigidos=10,
        relativo_propio=1.05, relativo_grupo_superior=1.02,
    )
    assert r.metodo == MetodoImputacion.GRUPO_SUPERIOR_PARCIAL


def test_cobertura_menor_20_descarta_y_usa_grupo_superior():
    r = resolver_relativo(
        n_precios_validos=1, n_precios_exigidos=10,
        relativo_propio=1.05, relativo_grupo_superior=1.02,
    )
    assert r.metodo == MetodoImputacion.GRUPO_SUPERIOR_TOTAL
    assert math.isclose(r.relativo_a_usar, 1.02)


def test_cobertura_cero_no_rompe():
    r = resolver_relativo(
        n_precios_validos=0, n_precios_exigidos=10,
        relativo_propio=None, relativo_grupo_superior=1.02,
    )
    assert r.metodo == MetodoImputacion.GRUPO_SUPERIOR_TOTAL
    assert math.isclose(r.relativo_a_usar, 1.02)
