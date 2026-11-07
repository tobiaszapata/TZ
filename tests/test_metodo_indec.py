"""Tests del calculo segun Metodologia N°32 (apartados 5.1 y 7.1):
engine.reporte.calcular_clase_y_productos_indec y su conexion en consultas."""
import math
import tempfile
from pathlib import Path

from engine.consultas import (
    valores_medidos_nacional, variacion_clase, variacion_superior, variaciones_de_region,
)
from engine.reporte import calcular_clase_y_productos, calcular_clase_y_productos_indec
from storage.db import (
    conectar, precios_por_negocio_en_multiples_rangos, precios_por_negocio_en_rango,
)


def _pan(**datos):
    """{ean: {(cadena, 'GBA'): [precios]}} a partir de ean=dict(cadena=[...])."""
    return {e: {(c, "GBA"): p for c, p in n.items()} for e, n in datos.items()}


def test_media_aritmetica_dentro_del_negocio_y_geometrica_entre_negocios():
    # Negocio X: base [10,20] -> AM 15 ; actual [18,22] -> AM 20  => relativo 4/3
    # Negocio Y: base [30]    -> 30   ; actual [33]     -> 33     => relativo 1.1
    base = _pan(A=dict(X=[10, 20], Y=[30]))
    act = _pan(A=dict(X=[18, 22], Y=[33]))
    res, drivers = calcular_clase_y_productos_indec(act, base)
    esperado = (math.sqrt((20 / 15) * 1.1) - 1) * 100
    assert math.isclose(res.variacion_pct, esperado, rel_tol=1e-12)
    assert math.isclose(drivers[0].variacion_pct, esperado, rel_tol=1e-12)


def test_entre_productos_es_media_geometrica_con_el_peso_proxy():
    # A: 3 observaciones actuales, relativo 1.2 ; B: 1 observacion, relativo 1.0
    base = _pan(A=dict(X=[100]), B=dict(X=[100]))
    act = _pan(A=dict(X=[120, 120, 120]), B=dict(X=[100]))
    res, _ = calcular_clase_y_productos_indec(act, base)
    assert math.isclose(res.variacion_pct, (1.2 ** 0.75 - 1) * 100, rel_tol=1e-12)
    # la media aritmetica ponderada daria 15%: el metodo nuevo da menos
    assert res.variacion_pct < 15.0


def test_nunca_supera_al_metodo_anterior_con_los_mismos_datos():
    base = _pan(A=dict(X=[100]), B=dict(X=[50]), C=dict(X=[10]))
    act = _pan(A=dict(X=[160]), B=dict(X=[45]), C=dict(X=[12]))
    nuevo, _ = calcular_clase_y_productos_indec(act, base)
    viejo, _ = calcular_clase_y_productos(
        {e: [p for l in n.values() for p in l] for e, n in act.items()},
        {e: [p for l in n.values() for p in l] for e, n in base.items()})
    assert nuevo.variacion_pct <= viejo.variacion_pct + 1e-9


def test_negocio_que_solo_aparece_en_un_periodo_no_distorsiona():
    base = _pan(A=dict(X=[100]))
    act = _pan(A=dict(X=[110], Z=[500]))          # Z aparece recien ahora
    res, _ = calcular_clase_y_productos_indec(act, base)
    assert math.isclose(res.variacion_pct, 10.0, rel_tol=1e-12)


def test_sin_articulo_negocio_en_comun_devuelve_none():
    assert calcular_clase_y_productos_indec(_pan(A=dict(X=[1])), _pan(B=dict(X=[1]))) == (None, [])


def _panel_con_cobertura(n_base, n_actual, rel):
    base = {f"E{i}": {("X", "GBA"): [100.0]} for i in range(n_base)}
    act = {f"E{i}": {("X", "GBA"): [100.0 * rel]} for i in range(n_actual)}
    return act, base


def test_imputacion_tramo_mayor_50_usa_variacion_propia():
    act, base = _panel_con_cobertura(10, 6, 1.10)
    res, _ = calcular_clase_y_productos_indec(act, base, variacion_grupo_superior=2.0)
    assert res.metodo_imputacion is None
    assert math.isclose(res.variacion_pct, 10.0, rel_tol=1e-9)


def test_imputacion_tramo_20_a_50_mezcla_geometrica_propio_y_superior():
    act, base = _panel_con_cobertura(10, 3, 1.10)             # cobertura 30%
    res, _ = calcular_clase_y_productos_indec(act, base, variacion_grupo_superior=2.0)
    esperado = (1.10 ** 0.3 * 1.02 ** 0.7 - 1) * 100
    assert res.metodo_imputacion == "grupo_superior_parcial"
    assert math.isclose(res.variacion_pct, esperado, rel_tol=1e-9)


def test_imputacion_tramo_menor_20_usa_solo_el_superior():
    act, base = _panel_con_cobertura(10, 1, 1.10)             # cobertura 10%
    res, drivers = calcular_clase_y_productos_indec(act, base, variacion_grupo_superior=2.0)
    assert res.metodo_imputacion == "grupo_superior_total"
    assert math.isclose(res.variacion_pct, 2.0, rel_tol=1e-9)
    assert all(d.incidencia_aproximada_pp == 0.0 for d in drivers if not d.es_imputado)


def test_cobertura_baja_sin_superior_usa_la_propia_y_lo_declara():
    act, base = _panel_con_cobertura(10, 3, 1.10)
    res, _ = calcular_clase_y_productos_indec(act, base, variacion_grupo_superior=None)
    assert res.metodo_imputacion == "grupo_superior_parcial"
    assert res.imputacion_con_superior is False
    assert math.isclose(res.variacion_pct, 10.0, rel_tol=1e-9)


def test_la_suma_de_incidencias_reproduce_exactamente_la_variacion():
    base = _pan(A=dict(X=[100]), B=dict(X=[50]), C=dict(X=[10, 12]))
    act = _pan(A=dict(X=[160]), B=dict(X=[45]), C=dict(X=[12, 13, 14]))
    res, drivers = calcular_clase_y_productos_indec(act, base)
    assert math.isclose(sum(d.incidencia_aproximada_pp for d in drivers), res.variacion_pct, rel_tol=1e-9)


def test_variacion_superior_excluye_la_propia_clase_y_pondera_por_region():
    v = {"01.1.1": 10.0, "01.1.2": 2.0, "01.1.4": 4.0}
    sup = variacion_superior("01.1.1", v, "GBA")
    from config.canasta import CANASTA
    w2, w4 = CANASTA["01.1.2"].peso("GBA"), CANASTA["01.1.4"].peso("GBA")
    assert math.isclose(sup, (w2 * 2.0 + w4 * 4.0) / (w2 + w4), rel_tol=1e-12)
    assert variacion_superior("01.1.1", {"01.1.1": 10.0}, "GBA") is None


def _insertar(con, filas):
    con.executemany(
        "INSERT INTO precios_raw (fecha, ean_o_id, clase_codigo, comercio, precio, region) VALUES (?,?,?,?,?,?)",
        filas)
    con.commit()


def test_db_conserva_el_negocio_y_junta_tramos():
    with tempfile.TemporaryDirectory() as t:
        con = conectar(Path(t) / "x.db")
        _insertar(con, [("2026-10-01", "A", "01.1.1", "X", 10.0, "GBA"),
                        ("2026-10-02", "A", "01.1.1", "X", 12.0, "GBA"),
                        ("2026-10-05", "A", "01.1.1", "Y", 20.0, "GBA")])
        r = precios_por_negocio_en_rango(con, "01.1.1", "2026-10-01", "2026-10-05")
        assert r == {"A": {("X", "GBA"): [10.0, 12.0], ("Y", "GBA"): [20.0]}}
        m = precios_por_negocio_en_multiples_rangos(
            con, "01.1.1", [("2026-10-01", "2026-10-01"), ("2026-10-05", "2026-10-05")])
        assert m == {"A": {("X", "GBA"): [10.0], ("Y", "GBA"): [20.0]}}
        con.close()


def test_integracion_clase_con_cobertura_baja_usa_las_demas_clases_del_grupo():
    with tempfile.TemporaryDirectory() as t:
        con = conectar(Path(t) / "x.db")
        filas = []
        # 01.1.2: cobertura 100%, +5%
        for i in range(4):
            filas += [("2026-09-01", f"M{i}", "01.1.2", "X", 100.0, "GBA"),
                      ("2026-10-01", f"M{i}", "01.1.2", "X", 105.0, "GBA")]
        # 01.1.1: 10 productos en la base, solo 1 en el actual (10%) con +20%
        for i in range(10):
            filas.append(("2026-09-01", f"P{i}", "01.1.1", "X", 100.0, "GBA"))
        filas.append(("2026-10-01", "P0", "01.1.1", "X", 120.0, "GBA"))
        _insertar(con, filas)
        args = ("2026-10-01", "2026-10-01", "2026-09-01", "2026-09-01")
        r = variaciones_de_region(con, *args, "GBA")
        assert r["01.1.2"].variacion_pct > 4.99
        assert r["01.1.1"].metodo_imputacion == "grupo_superior_total"
        assert math.isclose(r["01.1.1"].variacion_pct, r["01.1.2"].variacion_pct, rel_tol=1e-9)
        # el metodo previo no imputa nada: la clase de baja cobertura se queda con su +20%
        p = variaciones_de_region(con, *args, "GBA", metodo="previo")
        assert math.isclose(p["01.1.1"].variacion_pct, 20.0, rel_tol=1e-9)
        # y el nacional corre con ambos metodos
        assert "01.1.2" in valores_medidos_nacional(con, *args)
        assert "01.1.2" in valores_medidos_nacional(con, *args, metodo="previo")
        con.close()


def test_script_comparar_metodo_corre_de_punta_a_punta():
    import scripts.comparar_metodo as cm
    with tempfile.TemporaryDirectory() as t:
        con = conectar(Path(t) / "x.db")
        filas = []
        for i in range(6):
            filas += [("2026-10-05", f"E{i}", "01.1.1", "X", 100.0, "GBA"),
                      ("2026-10-12", f"E{i}", "01.1.1", "X", 110.0, "GBA")]
        _insertar(con, filas)
        r = cm.comparar(con, "2026-10-12", "2026-10-12", "2026-10-05", "2026-10-05")
        assert math.isclose(r["previo"]["01.1.1"], 10.0, rel_tol=1e-9)
        assert math.isclose(r["nuevo"]["01.1.1"], 10.0, rel_tol=1e-9)
        assert r["imputadas"]["01.1.1"] == 0
        con.close()


def test_excluir_productos_recalcula_la_clase_sin_ellos():
    from engine.consultas import variacion_clase_nacional_sin_productos
    with tempfile.TemporaryDirectory() as t:
        con = conectar(Path(t) / "x.db")
        filas = []
        for i, rel in enumerate([1.02, 1.04, 2.00]):          # el tercero es un salto extremo
            filas += [("2026-09-01", f"P{i}", "01.1.1", "X", 100.0, "GBA"),
                      ("2026-10-01", f"P{i}", "01.1.1", "X", 100.0 * rel, "GBA")]
        _insertar(con, filas)
        a = ("2026-10-01", "2026-10-01", "2026-09-01", "2026-09-01")
        todos, _ = variacion_clase(con, "01.1.1", *a, "GBA")
        sin, drv = variacion_clase(con, "01.1.1", *a, "GBA", excluir_eans={"P2"})
        assert math.isclose(sin.variacion_pct, (math.sqrt(1.02 * 1.04) - 1) * 100, rel_tol=1e-12)
        assert sin.variacion_pct < todos.variacion_pct
        assert all(d.ean_o_id != "P2" for d in drv)
        # nacional: solo GBA tiene datos, asi que coincide con el de GBA
        nac = variacion_clase_nacional_sin_productos(con, "01.1.1", *a, ["P2"])
        assert math.isclose(nac, sin.variacion_pct, rel_tol=1e-12)
        # excluir todo no deja nada
        assert variacion_clase(con, "01.1.1", *a, "GBA", excluir_eans={"P0", "P1", "P2"}) == (None, [])
        assert variacion_clase_nacional_sin_productos(con, "01.1.1", *a, ["P0", "P1", "P2"]) is None
        # tambien con el metodo previo
        p, _ = variacion_clase(con, "01.1.1", *a, "GBA", metodo="previo", excluir_eans={"P2"})
        assert math.isclose(p.variacion_pct, 3.0, rel_tol=1e-9)
        con.close()
