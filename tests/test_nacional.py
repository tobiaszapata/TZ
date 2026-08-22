import math
from config.canasta import PESO_REGION_NACIONAL, peso
from engine.nacional import indice_de_region, indice_nacional


def test_region_usa_sus_propios_pesos_no_los_de_gba():
    # Frutas pesa distinto en GBA (1.27%) que en Noreste (1.46%). Si el
    # motor usara siempre GBA, los dos resultados serian identicos.
    clases = {"01.1.6": 10.0, "01.1.1": 0.0}
    gba = indice_de_region(clases, "GBA")
    nea = indice_de_region(clases, "Noreste")
    assert gba.variacion_pct != nea.variacion_pct


def test_una_sola_clase_devuelve_esa_variacion():
    r = indice_de_region({"01.1.6": 7.5}, "GBA")
    assert math.isclose(r.variacion_pct, 7.5)


def test_nacional_pondera_por_importancia_de_region():
    # Solo GBA y Pampeana con datos, ambas al 10% -> nacional 10%
    datos = {"GBA": {"01.1.6": 10.0}, "Pampeana": {"01.1.6": 10.0}}
    r = indice_nacional(datos)
    assert math.isclose(r.variacion_pct, 10.0, rel_tol=1e-9)
    # cobertura = suma de pesos de las dos regiones
    esperado = PESO_REGION_NACIONAL["GBA"] + PESO_REGION_NACIONAL["Pampeana"]
    assert math.isclose(r.cobertura_poblacional, esperado, rel_tol=1e-9)
    assert len(r.regiones_sin_datos) == 4


def test_regiones_sin_datos_no_se_asumen_en_cero():
    # Si una region con dato tiene 10% y las demas no tienen datos, el
    # nacional debe ser 10% (renormalizado), NO 10% * su peso.
    r = indice_nacional({"GBA": {"01.1.6": 10.0}})
    assert math.isclose(r.variacion_pct, 10.0, rel_tol=1e-9)
    assert math.isclose(r.cobertura_poblacional, PESO_REGION_NACIONAL["GBA"])


def test_nacional_es_promedio_ponderado_correcto():
    datos = {"GBA": {"01.1.6": 20.0}, "Patagonia": {"01.1.6": 0.0}}
    r = indice_nacional(datos)
    wg, wp = PESO_REGION_NACIONAL["GBA"], PESO_REGION_NACIONAL["Patagonia"]
    esperado = (wg * 20.0 + wp * 0.0) / (wg + wp)
    assert math.isclose(r.variacion_pct, esperado, rel_tol=1e-9)


def test_sin_ningun_dato_devuelve_none():
    r = indice_nacional({})
    assert r.variacion_pct is None
