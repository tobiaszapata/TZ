import math

from engine.reporte import calcular_clase_y_productos


def test_desglose_identifica_el_producto_que_mueve_la_clase():
    # Banana sube fuerte y tiene muchas observaciones; manzana estable.
    # El driver principal tiene que ser la banana.
    mes_actual = {
        "banana": [200.0] * 8,   # subió
        "manzana": [150.0] * 8,  # estable
    }
    mes_anterior = {
        "banana": [100.0] * 8,
        "manzana": [150.0] * 8,
    }
    nombres = {"banana": "Banana", "manzana": "Manzana"}

    resultado, drivers = calcular_clase_y_productos(mes_actual, mes_anterior, nombres)

    assert resultado is not None
    assert drivers[0].nombre_producto == "Banana"
    assert abs(drivers[0].variacion_pct - 100.0) < 1e-9
    # Manzana quedó estable: su variación es 0 y no explica nada de la clase.
    # (isclose contra 0.0 exacto no sirve — se compara con abs, ver
    #  docs de math.isclose sobre el caso cero.)
    manzana = next(d for d in drivers if d.nombre_producto == "Manzana")
    assert abs(manzana.variacion_pct) < 1e-9
    assert abs(manzana.incidencia_aproximada_pp) < 1e-9


def test_suma_de_incidencias_aproximadas_reproduce_variacion_de_la_clase():
    # La identidad clave: la suma de las incidencias aproximadas de cada
    # producto tiene que dar exactamente la variación de la clase — es lo
    # que permite decir "de estos 3 puntos que subió la clase, 2 los
    # explica la banana".
    mes_actual = {
        "a": [110.0] * 5,
        "b": [100.0] * 3,
        "c": [130.0] * 2,
    }
    mes_anterior = {
        "a": [100.0] * 5,
        "b": [100.0] * 3,
        "c": [100.0] * 2,
    }
    resultado, drivers = calcular_clase_y_productos(mes_actual, mes_anterior)

    suma_incidencias = sum(d.incidencia_aproximada_pp for d in drivers)
    assert math.isclose(suma_incidencias, resultado.variacion_pct, rel_tol=1e-9)


def test_pesos_proxy_suman_100():
    mes_actual = {"a": [100.0] * 7, "b": [100.0] * 3}
    mes_anterior = {"a": [100.0] * 7, "b": [100.0] * 3}
    _resultado, drivers = calcular_clase_y_productos(mes_actual, mes_anterior)
    assert math.isclose(sum(d.peso_proxy_pct for d in drivers), 100.0, rel_tol=1e-9)


def test_productos_no_comunes_se_cuentan_pero_no_entran_al_calculo():
    # "nuevo" solo está este mes; "viejo" solo el anterior. Ninguno entra
    # al cálculo de variación, pero sí quedan contados para que el reporte
    # pueda avisar cuánta rotación de productos hubo.
    mes_actual = {"comun": [110.0] * 4, "nuevo": [50.0] * 4}
    mes_anterior = {"comun": [100.0] * 4, "viejo": [80.0] * 4}
    resultado, drivers = calcular_clase_y_productos(mes_actual, mes_anterior)

    assert resultado.n_productos_comparados == 1
    assert resultado.n_productos_solo_mes_actual == 1
    assert resultado.n_productos_solo_mes_anterior == 1
    assert len(drivers) == 1
    assert drivers[0].ean_o_id == "comun"


def test_sin_productos_en_comun_devuelve_none():
    resultado, drivers = calcular_clase_y_productos(
        {"a": [100.0]}, {"b": [100.0]}
    )
    assert resultado is None
    assert drivers == []
