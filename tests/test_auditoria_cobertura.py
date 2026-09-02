"""
Tests de config.canasta.cobertura_estructural_division — la función que
responde la pregunta real: "¿esta división está completa, o le falta
estructura además de datos?"

CASO REAL QUE MOTIVÓ ESTO: al mirar "Bebidas alcohólicas y tabaco" en la
interfaz, solo se ven 3 subcategorías (Licores, Vinos, Cerveza), las 3
medidas — pero "Tabaco" no aparece en ningún lado. La pregunta era: ¿la
división está completa (solo falta esa dentro de las medidas) o falta
directamente declararla? Este test confirma que es lo segundo: Tabaco
está declarado como GRUPO con su peso oficial, pero sin ninguna
subcategoría (clase) hija cargada — es un hueco estructural, no solo de
datos, y representa una fracción grande del peso de esa división.
"""

import math

from config.canasta import CANASTA, cobertura_estructural_division


def test_bebidas_alcoholicas_y_tabaco_tiene_un_hueco_estructural_real():
    """El caso real reportado: 'Tabaco' pesa ~57% de esta división y no
    tiene NINGUNA subcategoría cargada — ni medida, ni pendiente."""
    r = cobertura_estructural_division("02")
    assert r["sin_declarar"] > 0, (
        "se esperaba un hueco estructural real (el grupo Tabaco sin "
        "ninguna clase hija), pero el resultado dice que no hay ninguno"
    )
    fraccion_sin_declarar = r["sin_declarar"] / r["referencia"]
    # el hueco tiene que ser una fraccion GRANDE de la division (no un
    # residuo de redondeo chico) -- se espera bastante mas de la mitad,
    # ya que Tabaco pesa mas que las 3 subcategorias medidas juntas
    assert fraccion_sin_declarar > 0.5, (
        f"se esperaba un hueco mayor al 50% de la division, se obtuvo "
        f"{fraccion_sin_declarar:.1%}"
    )


def test_alimentos_no_tiene_ningun_hueco_estructural():
    """Contraste: Alimentos y bebidas no alcohólicas SÍ tiene sus 11
    subcategorías completas, todas medidas — no debería haber ningún
    hueco estructural ahí."""
    r = cobertura_estructural_division("01")
    assert math.isclose(r["sin_declarar"], 0.0, abs_tol=0.001)
    assert math.isclose(r["medido"], r["referencia"], abs_tol=0.001)


def test_educacion_es_hueco_estructural_completo():
    """Educación tiene sus GRUPOS declarados (con peso oficial) pero
    ninguna CLASE hija — es el caso más extremo: 100% sin declarar."""
    r = cobertura_estructural_division("10")
    assert math.isclose(r["medido"], 0.0, abs_tol=0.0001)
    assert math.isclose(r["declarado_sin_medir"], 0.0, abs_tol=0.0001)
    assert math.isclose(r["sin_declarar"], r["referencia"], abs_tol=0.001)


def test_las_tres_fracciones_suman_el_total_de_la_division():
    """Para cualquier división, medido + declarado_sin_medir + sin_declarar
    tiene que reproducir exactamente el peso de referencia — sin esto, la
    auditoría podría estar perdiendo o duplicando peso en algún lado."""
    from config.canasta import divisiones
    for d in divisiones():
        r = cobertura_estructural_division(d.codigo)
        suma = r["medido"] + r["declarado_sin_medir"] + r["sin_declarar"]
        assert math.isclose(suma, r["referencia"], abs_tol=0.001), (
            f"división {d.codigo}: las tres fracciones no suman el total "
            f"({suma} != {r['referencia']})"
        )


def test_suma_de_las_12_divisiones_da_aproximadamente_100_por_ciento():
    from config.canasta import divisiones
    total = sum(cobertura_estructural_division(d.codigo)["referencia"] for d in divisiones())
    assert math.isclose(total, 1.0, abs_tol=0.01)


def test_prendas_de_vestir_paso_de_0_a_medida():
    """Regresion del hallazgo real: Prendas de vestir y Zapatos (los dos
    grupos de mayor peso dentro de la division 03) ahora se clasifican
    con SEPA. Antes esta division daba 0% medido."""
    r = cobertura_estructural_division("03")
    assert r["medido"] / r["referencia"] > 0.8, (
        "se esperaba que Prendas de vestir quedara mayormente medida "
        "despues de declarar 03.1.2 y 03.2.1 como MEDIDA_SEPA"
    )


def test_bazar_y_textiles_del_hogar_ya_no_son_hueco_estructural():
    """Regresion del hallazgo real: los grupos 05.1 a 05.5 no tenian
    NINGUNA clase hija declarada, aunque ya existian reglas de
    clasificacion funcionando para bazar y textiles del hogar
    (mapeo.py) que nunca podian aplicarse. Ahora division 05 casi no
    tiene hueco estructural."""
    r = cobertura_estructural_division("05")
    assert r["sin_declarar"] / r["referencia"] < 0.05, (
        "todavia queda un hueco estructural grande en Equipamiento del hogar"
    )


def test_alimentos_no_alcoholicas_sigue_completa_tras_los_cambios():
    """Ningun cambio en otras divisiones deberia afectar a Alimentos."""
    r = cobertura_estructural_division("01")
    assert math.isclose(r["medido"], r["referencia"], abs_tol=0.001)


def test_tipo_de_bien_distingue_dentro_de_la_misma_division():
    """El caso real pedido: dentro de Salud, algunas PENDIENTE son bienes
    fisicos razonablemente scrapeables (artefactos terapeuticos) y otras
    son servicios sin precio de lista simple (consultas medicas) — la
    auditoria tiene que distinguirlos, no tratarlos igual solo por
    compartir el estado PENDIENTE."""
    from scripts.auditar_cobertura import _tipo_de_bien
    assert "físico" in _tipo_de_bien("06.1.3").lower()
    assert "físico" not in _tipo_de_bien("06.2.1").lower()
    assert "servicio" in _tipo_de_bien("06.2.1").lower()


def test_tipo_de_bien_identifica_tarifas_reguladas():
    from scripts.auditar_cobertura import _tipo_de_bien
    assert "regulada" in _tipo_de_bien("04.5.1").lower() or "combustible" in _tipo_de_bien("04.5.1").lower()
