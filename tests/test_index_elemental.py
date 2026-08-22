import math

from engine.index_elemental import (
    ObservacionVariedad,
    indice_elemental_encadenado,
    media_geometrica,
    precio_mensual_variedad,
    relativo,
)


def _series_iguales(a: list[float], b: list[float]) -> bool:
    return len(a) == len(b) and all(math.isclose(x, y, rel_tol=1e-9) for x, y in zip(a, b))


def test_media_geometrica_caso_resuelto_a_mano():
    # sqrt(100 * 121) = sqrt(12100) = 110 exacto — elegido para poder
    # verificar sin calculadora.
    assert math.isclose(media_geometrica([100, 121]), 110.0, rel_tol=1e-9)


def test_media_geometrica_tres_precios_iguales_da_ese_precio():
    assert math.isclose(media_geometrica([50, 50, 50]), 50.0)


def test_geometrica_de_relativos_es_simetrica_ante_baja_y_suba_proporcional():
    # Un producto que baja 50% y otro que sube 100% (dos "relativos": 0.5
    # y 2.0) se cancelan EXACTO en la media geométrica: 1.0, sin cambio.
    # La media aritmética de los mismos relativos da 1.25 — un +25% que no
    # existió. Esta es la propiedad real por la que se usa geométrica
    # (ver docstring de media_geometrica) y por la que no hace falta
    # winsorizar ofertas puntuales, no que "amortigüe outliers de nivel"
    # en un sentido genérico.
    relativos = [0.5, 2.0]
    geo = media_geometrica(relativos)
    aritm = sum(relativos) / len(relativos)
    assert math.isclose(geo, 1.0, rel_tol=1e-9)
    assert math.isclose(aritm, 1.25)
    assert geo < aritm  # la aritmética sobreestima frente a swings simétricos


def test_relativo_basico():
    assert math.isclose(relativo(110, 100), 1.10)


def test_indice_elemental_encadenado():
    serie = indice_elemental_encadenado([1.10, 1.05], base=100.0)
    # comparación con tolerancia, no con == : 110.0 * 1.05 no da 115.5
    # exacto en punto flotante (da 115.49999999999999) — comparar igualdad
    # estricta de floats es en sí mismo un error a evitar en este motor.
    assert _series_iguales(serie, [100.0, 110.0, 115.5])


def test_precio_mensual_variedad_filtra_por_mes_y_usa_geometrica():
    obs = [
        ObservacionVariedad("2026-07-01", "ean1", "comercioA", 100),
        ObservacionVariedad("2026-07-15", "ean1", "comercioA", 121),
        ObservacionVariedad("2026-06-30", "ean1", "comercioA", 999),  # mes distinto, no debe entrar
    ]
    resultado = precio_mensual_variedad(obs, "01.1.1", "2026-07")
    assert math.isclose(resultado.precio_promedio, 110.0, rel_tol=1e-9)
    assert resultado.n_observaciones == 2
