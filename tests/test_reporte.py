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


def test_productos_no_comunes_se_cuentan_y_los_faltantes_se_imputan():
    # "nuevo" solo está este mes: no se puede saber su precio anterior,
    # nunca puede tener variación -- queda fuera del calculo, pero se
    # cuenta para el reporte de rotacion.
    # "viejo" solo estaba el mes anterior: con la correccion de
    # imputacion (Metodologia N°32, seccion 7.1), este producto YA NO
    # se descarta en silencio -- como la cobertura queda en 50% (1 de 2
    # productos del mes anterior sigue estando), cae en el tramo de
    # imputacion parcial y se le asigna la variacion del agrupamiento
    # superior (acá, la propia clase, unica variacion disponible).
    mes_actual = {"comun": [110.0] * 4, "nuevo": [50.0] * 4}
    mes_anterior = {"comun": [100.0] * 4, "viejo": [80.0] * 4}
    resultado, drivers = calcular_clase_y_productos(mes_actual, mes_anterior)

    assert resultado.n_productos_comparados == 1
    assert resultado.n_productos_solo_mes_actual == 1
    assert resultado.n_productos_solo_mes_anterior == 1
    assert resultado.cobertura == 0.5
    assert resultado.metodo_imputacion == "grupo_superior_parcial"
    # "viejo" ahora SI aparece, marcado como imputado -- antes de la
    # correccion, simplemente desaparecia del reporte sin ningun aviso
    assert len(drivers) == 2
    ean_ids = {d.ean_o_id for d in drivers}
    assert ean_ids == {"comun", "viejo"}
    viejo = next(d for d in drivers if d.ean_o_id == "viejo")
    assert viejo.es_imputado is True
    comun = next(d for d in drivers if d.ean_o_id == "comun")
    assert comun.es_imputado is False


def test_sin_productos_en_comun_devuelve_none():
    resultado, drivers = calcular_clase_y_productos(
        {"a": [100.0]}, {"b": [100.0]}
    )
    assert resultado is None
    assert drivers == []


def test_peso_proxy_no_depende_de_cuantos_productos_se_muestren():
    """Responde una duda real: si la interfaz solo MUESTRA los primeros N
    productos (por legibilidad), el peso proxy de esos N no debe cambiar
    como si el universo fuera solo esos N — tiene que seguir calculado
    sobre el TOTAL de productos comunes entre los dos periodos."""
    precios_mes = {
        "A": [100.0] * 20, "B": [150.0] * 15, "C": [120.0] * 10,
        "D": [300.0] * 3, "E": [400.0] * 2,
    }
    precios_mes_ant = {k: [v[0] * 0.95] * len(v) for k, v in precios_mes.items()}

    resultado, drivers = calcular_clase_y_productos(precios_mes, precios_mes_ant)

    total_obs = sum(len(v) for v in precios_mes.values())
    por_ean = {d.ean_o_id: d for d in drivers}

    assert math.isclose(por_ean["A"].peso_proxy_pct, 20 / total_obs * 100)
    assert math.isclose(por_ean["B"].peso_proxy_pct, 15 / total_obs * 100)

    # simulando que la interfaz solo "muestra" los primeros 3 (como el
    # limite real de 30 en pantalla): el peso de esos 3 no se recalcula
    # como si el total fuera 3
    solo_los_primeros_3 = drivers[:3]
    suma_de_esos_3 = sum(d.peso_proxy_pct for d in solo_los_primeros_3)
    assert suma_de_esos_3 < 100.0, (
        "si diera 100%, significaria que se esta recalculando el peso "
        "sobre el subconjunto mostrado, no sobre el total"
    )


def test_cobertura_alta_no_imputa_nada_se_comporta_igual_que_antes():
    """Con cobertura > 50% (la mayoria de los productos del periodo
    anterior siguen presentes), el comportamiento tiene que seguir
    siendo exactamente el de antes de la correccion: no se imputa nada,
    los productos faltantes ni siquiera aparecen en drivers."""
    mes_actual = {"A": [110.0] * 4, "B": [210.0] * 4, "C": [55.0] * 4}
    mes_anterior = {"A": [100.0] * 4, "B": [200.0] * 4, "C": [50.0] * 4, "D": [80.0] * 4}
    # cobertura = 3/4 = 75% > 50% -> sin imputacion
    resultado, drivers = calcular_clase_y_productos(mes_actual, mes_anterior)

    assert resultado.metodo_imputacion is None
    assert resultado.cobertura == 0.75
    assert len(drivers) == 3  # "D" no aparece, igual que el comportamiento historico
    assert all(not d.es_imputado for d in drivers)


def test_cobertura_baja_descarta_propio_y_usa_variacion_superior():
    """Con cobertura < 20%, la Metodologia N°32 (seccion 7.1) dice que se
    descartan los pocos precios validos que hay y se usa la variacion
    del agrupamiento superior para TODA la clase — no solo para los
    faltantes."""
    mes_actual = {"unico": [105.0] * 4}
    mes_anterior = {
        "unico": [100.0] * 4, "b": [1] * 4, "c": [1] * 4, "d": [1] * 4,
        "e": [1] * 4, "f": [1] * 4,
    }
    # cobertura = 1/6 = 16.7% < 20%
    resultado, drivers = calcular_clase_y_productos(
        mes_actual, mes_anterior, variacion_grupo_superior=3.5)

    assert resultado.metodo_imputacion == "grupo_superior_total"
    assert resultado.variacion_pct == 3.5  # la del grupo superior, no la propia (que seria +5%)


def test_variacion_grupo_superior_explicita_se_usa_para_imputar():
    """Cuando se pasa variacion_grupo_superior explicitamente (el valor
    real del grupo, calculado aparte), se usa esa en vez de la
    aproximacion (variacion de la propia clase) para los productos que
    hace falta imputar."""
    mes_actual = {"comun": [110.0] * 4, "nuevo": [50.0] * 4}
    mes_anterior = {"comun": [100.0] * 4, "viejo": [80.0] * 4}
    resultado, drivers = calcular_clase_y_productos(
        mes_actual, mes_anterior, variacion_grupo_superior=2.0)

    viejo = next(d for d in drivers if d.ean_o_id == "viejo")
    assert viejo.variacion_pct == 2.0  # la del grupo superior pasada explicitamente
    assert resultado.variacion_pct == 2.0  # tramo 20-50%: toda la clase usa la del superior
