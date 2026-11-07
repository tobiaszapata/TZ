"""Tests de la clase 06.4.1 (prepagas, cuadros tarifarios de SSSalud):
regiones, periodos, almacenamiento, calculo, integracion con el motor y descarga."""
import csv
import gzip
import math
import tempfile
from pathlib import Path

from collectors.prepagas.descargar import (
    DescargaIncompleta, bajar_entidad, bajar_periodo, escribir_mes, fila_csv,
    importar_csv_plano, pedir,
)
from config.canasta import CANASTA, CLASES_EXTERNAS, CLASES_MEDIDAS, PESO_REGION, REGIONES, es_medida
from config.regiones_prepagas import cargar_overrides, clasificar_region, regiones_indec
from engine.consultas import (
    resumen_divisiones_desde_valores, valores_medidos_nacional, variacion_clase,
    variaciones_de_region,
)
from engine.prepagas import (
    calcular_relativo, dias_por_mes, periodos_de_la_seleccion, unidades_de_la_ventana,
)
from storage.db import conectar
from storage.prepagas import (
    COLUMNAS, asegurar_periodos_cargados, filas_de_periodo, periodos_disponibles,
)


def _r(texto):
    return set(clasificar_region(texto).regiones)


# ----------------------------------------------------------------- regiones
def test_regiones_textos_reales_del_sitio():
    todas = set(REGIONES)
    assert _r("NACIONAL") == todas and _r("Todo el pais") == todas and _r("Rep. Arg.") == todas
    assert _r("CABA") == {"GBA"} and _r("AMBA") == {"GBA"}
    assert _r("Area Metropolitana de Buenos Aires (AMBA)") == {"GBA"}
    assert _r("PROVINCIA DE BUENOS AIRES") == {"GBA", "Pampeana"}
    assert _r("BsAs Interior - Santa Fe") == {"Pampeana"}
    assert _r("CABA, Provincia de Bs As y Ciudad de Viedma") == {"GBA", "Pampeana", "Patagonia"}
    assert _r("Pais excepto Patagonia, Bs As y CABA") == {"Pampeana", "Noreste", "Noroeste", "Cuyo"}
    assert _r("Pais excepto region Patagonia") == todas - {"Patagonia"}
    assert _r("Interior pais") == todas - {"GBA"}
    assert _r("SALTA, JUJUY, TUCUMAN, MISIONES, CHACO, FORMOSA") == {"Noroeste", "Noreste"}
    assert _r("RIO NEGRO, NEUQUEN, CHUBUT, SANTA CRUZ, TIERRA DEL FUEGO") == {"Patagonia"}
    assert _r("Cordoba") == {"Pampeana"} and _r("Mendoza") == {"Cuyo"}
    assert _r("MAR DEL PLATA") == {"Pampeana"}


def test_regiones_parentesis_de_excepcion_se_ignoran_y_la_pampa_patagonica_no_suma_pampeana():
    assert _r("Region Patagonia incluye Neuquen Chubut Santa Cruz Tierra del Fuego La Pampa "
              "Rio Negro (excepto Ciudad de Viedma)") == {"Patagonia"}
    assert _r("CORRIENTES, LA RIOJA, CATAMARCA, SGO DEL ESTERO Y CORDOBA (EXCLUYE DPTOS RIO "
              "CUARTO, MARCOS JUAREZ)") == {"Noreste", "Noroeste", "Pampeana"}
    # La Pampa fuera de una lista patagonica SI es Pampeana
    assert _r("LA PAMPA JUJUY") == {"Pampeana", "Noroeste"}


def test_regiones_gba_no_cuenta_dos_veces_como_provincia():
    # "GRAN BUENOS AIRES" es GBA, no tambien "Buenos Aires" provincia (Pampeana)
    assert _r("GRAN BUENOS AIRES") == {"GBA"}


def test_regiones_certeza_y_overrides():
    assert clasificar_region("GENERAL").certeza == "dudosa"
    assert clasificar_region("CABA").certeza == "clara"
    with tempfile.TemporaryDirectory() as d:
        ruta = Path(d) / "regiones.csv"
        ruta.write_text("region_texto;regiones\nGENERAL;GBA, Cuyo\n", encoding="utf-8")
        ov = cargar_overrides(ruta)
        cl = regiones_indec("general", ov)
        assert cl.certeza == "manual" and set(cl.regiones) == {"GBA", "Cuyo"}
        ruta.write_text("region_texto;regiones\nX;Marte\n", encoding="utf-8")
        try:
            cargar_overrides(ruta)
            assert False, "debia rechazar una region INDEC inexistente"
        except ValueError:
            pass
    assert cargar_overrides(None) == {} and cargar_overrides(Path("/no/existe.csv")) == {}


# ----------------------------------------------------------------- periodos
def test_dias_por_mes_y_periodos():
    assert dias_por_mes("2026-10-26", "2026-11-05") == {202610: 6, 202611: 5}
    assert dias_por_mes([("2026-10-01", "2026-10-02"), ("2026-11-03", "2026-11-03")], None) == {202610: 2, 202611: 1}
    assert periodos_de_la_seleccion("2026-11-01", "2026-11-30", "2026-10-01", "2026-10-31") == [202610, 202611]


# ----------------------------------------------------------------- datos de prueba
def _fila(per, rnemp, plan, cuota, cap, region, desde=0, hasta=99, nombre=None, tipo="I",
          com=1, copago=0, modal=1):
    return [per, rnemp, nombre or f"ENT{rnemp}", 1, plan, cuota, cap, desde, hasta, region, tipo,
            com, copago, 0.02, modal, "A"]


def _carpeta_con(meses: dict[int, list]) -> Path:
    d = Path(tempfile.mkdtemp())
    for per, filas in meses.items():
        escribir_mes(filas, d / f"{per}.csv.gz")
    return d


def _con_prepagas(meses: dict[int, list]):
    d = _carpeta_con(meses)
    con = conectar(Path(tempfile.mkdtemp()) / "t.db")
    asegurar_periodos_cargados(con, d, list(meses))
    return con


# ----------------------------------------------------------------- almacenamiento
def test_almacenamiento_carga_salta_y_recarga():
    d = _carpeta_con({202610: [_fila(202610, 1, "P", 100, 10, "NACIONAL")]})
    con = conectar(Path(tempfile.mkdtemp()) / "t.db")
    assert periodos_disponibles(d) == [202610]
    r1 = asegurar_periodos_cargados(con, d, [202610, 202609])
    assert r1["cargados"] == [202610] and r1["sin_archivo"] == [202609]
    r2 = asegurar_periodos_cargados(con, d, [202610])
    assert r2["ya_estaban"] == [202610] and not r2["cargados"]
    escribir_mes([_fila(202610, 1, "P", 100, 10, "NACIONAL"), _fila(202610, 2, "Q", 50, 5, "CABA")],
                 d / "202610.csv.gz")
    r3 = asegurar_periodos_cargados(con, d, [202610])
    assert r3["recargados"] == [202610]
    assert len(filas_de_periodo(con, 202610)) == 2   # no duplica filas al recargar


def test_archivo_mensual_tiene_las_columnas_esperadas():
    d = _carpeta_con({202610: [_fila(202610, 1, "P", 100.5, 10, "CABA")]})
    with gzip.open(d / "202610.csv.gz", "rt", encoding="utf-8") as f:
        filas = list(csv.reader(f))
    assert filas[0] == COLUMNAS and len(filas[1]) == len(COLUMNAS)


# ----------------------------------------------------------------- calculo
def test_relativo_de_region_es_geometrica_ponderada_por_gasto_base():
    # Dos planes solo en CABA (GBA): A sube 10% con gasto base 100*1000, B sube 0% con gasto 100*1000/... 
    con = _con_prepagas({
        202609: [_fila(202609, 1, "A", 1000, 100, "CABA"), _fila(202609, 2, "B", 500, 400, "CABA")],
        202610: [_fila(202610, 1, "A", 1100, 100, "CABA"), _fila(202610, 2, "B", 500, 400, "CABA")],
    })
    res, drivers = variacion_clase(con, "06.4.1", "2026-10-01", "2026-10-31",
                                   "2026-09-01", "2026-09-30", region="GBA")
    wa, wb = 1000 * 100, 500 * 400
    esperado = (math.exp((wa * math.log(1.1)) / (wa + wb)) - 1) * 100
    assert math.isclose(res.variacion_pct, esperado, rel_tol=1e-12)
    assert res.cobertura == 1.0 and res.n_productos_comparados == 2
    # incidencias por entidad suman exactamente la variacion
    assert math.isclose(sum(d.incidencia_aproximada_pp for d in drivers), res.variacion_pct, rel_tol=1e-9)
    assert {d.ean_o_id for d in drivers} == {"1", "2"}
    # otra region sin planes -> no hay dato
    assert variacion_clase(con, "06.4.1", "2026-10-01", "2026-10-31", "2026-09-01", "2026-09-30",
                           region="Cuyo")[0] is None


def test_plan_nacional_aporta_a_todas_las_regiones_y_el_regional_solo_a_la_suya():
    con = _con_prepagas({
        202609: [_fila(202609, 1, "N", 100, 10, "NACIONAL"), _fila(202609, 2, "C", 100, 10, "Cordoba")],
        202610: [_fila(202610, 1, "N", 110, 10, "NACIONAL"), _fila(202610, 2, "C", 130, 10, "Cordoba")],
    })
    args = ("2026-10-01", "2026-10-31", "2026-09-01", "2026-09-30")
    gba = variacion_clase(con, "06.4.1", *args, region="GBA")[0].variacion_pct
    pamp = variacion_clase(con, "06.4.1", *args, region="Pampeana")[0].variacion_pct
    assert math.isclose(gba, 10.0, rel_tol=1e-9)                    # solo el nacional rige en GBA
    assert math.isclose(pamp, (math.sqrt(1.1 * 1.3) - 1) * 100, rel_tol=1e-9)
    # pool sin region: los dos
    assert math.isclose(variacion_clase(con, "06.4.1", *args, region=None)[0].variacion_pct, pamp, rel_tol=1e-9)


def test_periodo_que_cruza_dos_meses_pondera_por_dias():
    # Cuota 100 en septiembre y 110 en octubre. Periodo actual: 10 dias de sep + 20 de oct.
    con = _con_prepagas({
        202608: [_fila(202608, 1, "A", 100, 10, "CABA")],
        202609: [_fila(202609, 1, "A", 100, 10, "CABA")],
        202610: [_fila(202610, 1, "A", 110, 10, "CABA")],
    })
    res, _ = variacion_clase(con, "06.4.1", "2026-09-21", "2026-10-20", "2026-08-01", "2026-08-31",
                             region="GBA")
    # dias: sep 21..30 = 10 ; oct 1..20 = 20 -> cuota media (10*100+20*110)/30
    assert math.isclose(res.variacion_pct, ((10 * 100 + 20 * 110) / 30 / 100 - 1) * 100, rel_tol=1e-12)


def test_unidades_que_solo_estan_en_un_periodo_se_ignoran_y_se_cuentan():
    con = _con_prepagas({
        202609: [_fila(202609, 1, "A", 100, 10, "CABA"), _fila(202609, 1, "VIEJO", 100, 10, "CABA")],
        202610: [_fila(202610, 1, "A", 105, 10, "CABA"), _fila(202610, 1, "NUEVO", 999, 10, "CABA")],
    })
    res, _ = variacion_clase(con, "06.4.1", "2026-10-01", "2026-10-31", "2026-09-01", "2026-09-30",
                             region="GBA")
    assert math.isclose(res.variacion_pct, 5.0, rel_tol=1e-9)       # NUEVO (999) no contamina
    assert res.n_productos_solo_mes_actual == 1 and res.n_productos_solo_mes_anterior == 1
    assert math.isclose(res.cobertura, 0.5, rel_tol=1e-9)          # 1 de 2 de igual gasto base


def test_relativos_atipicos_se_descartan():
    con = _con_prepagas({
        202609: [_fila(202609, 1, "A", 100, 10, "CABA"), _fila(202609, 1, "ERROR", 100, 10, "CABA")],
        202610: [_fila(202610, 1, "A", 102, 10, "CABA"), _fila(202610, 1, "ERROR", 5000, 10, "CABA")],
    })
    res, _ = variacion_clase(con, "06.4.1", "2026-10-01", "2026-10-31", "2026-09-01", "2026-09-30",
                             region="GBA")
    assert math.isclose(res.variacion_pct, 2.0, rel_tol=1e-9)


def test_duplicados_de_clave_se_fusionan_y_sin_capitas_pesos_iguales():
    # mismo plan declarado dos veces (comercializable y no): una sola unidad
    con = _con_prepagas({
        202609: [_fila(202609, 1, "A", 100, 10, "CABA", com=1), _fila(202609, 1, "A", 100, 30, "CABA", com=0),
                 _fila(202609, 2, "B", 100, 0, "CABA")],
        202610: [_fila(202610, 1, "A", 120, 40, "CABA"), _fila(202610, 2, "B", 100, 0, "CABA")],
    })
    u = unidades_de_la_ventana(con, "2026-09-01", "2026-09-30")
    assert len(u) == 2
    assert sorted(v[1] for v in u.values()) == [0.0, 40.0]       # 10+30 capitas fusionadas
    res, _ = variacion_clase(con, "06.4.1", "2026-10-01", "2026-10-31", "2026-09-01", "2026-09-30",
                             region="GBA")
    assert math.isclose(res.variacion_pct, 20.0, rel_tol=1e-9)   # B pesa 0 (sin capitas), A manda


def test_todas_sin_capitas_usa_pesos_iguales():
    from engine.prepagas import DetalleCalculo
    base = {("1", "A", 0, 99, "CABA", "I", 1, 0): (100.0, 0.0, "X"),
            ("2", "B", 0, 99, "CABA", "I", 1, 0): (100.0, 0.0, "Y")}
    act = {("1", "A", 0, 99, "CABA", "I", 1, 0): (110.0, 0.0, "X"),
           ("2", "B", 0, 99, "CABA", "I", 1, 0): (100.0, 0.0, "Y")}
    det = DetalleCalculo()
    res, _ = calcular_relativo(act, base, "GBA", detalle=det)
    assert det.pesos_iguales and math.isclose(res.variacion_pct, (math.sqrt(1.1) - 1) * 100, rel_tol=1e-9)


def test_cobertura_baja_usa_la_imputacion_del_apartado_7_1():
    # Cobertura 10% (< 20%): usa TOTALMENTE la variacion del grupo superior
    con = _con_prepagas({
        202609: [_fila(202609, 1, "A", 100, 10, "CABA"), _fila(202609, 2, "B", 100, 90, "CABA")],
        202610: [_fila(202610, 1, "A", 150, 10, "CABA")],
    })
    args = ("2026-10-01", "2026-10-31", "2026-09-01", "2026-09-30")
    propia, _ = variacion_clase(con, "06.4.1", *args, region="GBA")
    assert math.isclose(propia.cobertura, 0.1, rel_tol=1e-9) and math.isclose(propia.variacion_pct, 50.0)
    imput, drivers = variacion_clase(con, "06.4.1", *args, region="GBA", variacion_grupo_superior=3.0)
    assert math.isclose(imput.variacion_pct, 3.0, rel_tol=1e-9)
    assert imput.metodo_imputacion == "grupo_superior_total"
    assert math.isclose(sum(d.incidencia_aproximada_pp for d in drivers), 0.0, abs_tol=1e-12)
    # cobertura 30% -> mezcla
    con2 = _con_prepagas({
        202609: [_fila(202609, 1, "A", 100, 30, "CABA"), _fila(202609, 2, "B", 100, 70, "CABA")],
        202610: [_fila(202610, 1, "A", 150, 30, "CABA")],
    })
    mix, _ = variacion_clase(con2, "06.4.1", *args, region="GBA", variacion_grupo_superior=3.0)
    c = 0.3
    assert math.isclose(mix.variacion_pct, (math.exp(c * math.log(1.5) + (1 - c) * math.log(1.03)) - 1) * 100,
                        rel_tol=1e-9)


def test_excluir_una_entidad_cambia_el_resultado():
    con = _con_prepagas({
        202609: [_fila(202609, 1, "A", 100, 10, "CABA"), _fila(202609, 2, "B", 100, 10, "CABA")],
        202610: [_fila(202610, 1, "A", 130, 10, "CABA"), _fila(202610, 2, "B", 100, 10, "CABA")],
    })
    args = ("2026-10-01", "2026-10-31", "2026-09-01", "2026-09-30")
    todo = variacion_clase(con, "06.4.1", *args, region="GBA")[0].variacion_pct
    sin = variacion_clase(con, "06.4.1", *args, region="GBA", excluir_eans={"1"})[0].variacion_pct
    assert todo > 10 and math.isclose(sin, 0.0, abs_tol=1e-12)


def test_sin_datos_del_mes_devuelve_none():
    con = _con_prepagas({202609: [_fila(202609, 1, "A", 100, 10, "CABA")]})
    assert variacion_clase(con, "06.4.1", "2026-10-01", "2026-10-31", "2026-09-01", "2026-09-30",
                           region="GBA") == (None, [])
    con_vacia = conectar(Path(tempfile.mkdtemp()) / "v.db")
    assert variacion_clase(con_vacia, "06.4.1", "2026-10-01", "2026-10-31", "2026-09-01",
                           "2026-09-30", region="GBA") == (None, [])


# ----------------------------------------------------------------- integracion con el motor
def test_canasta_clase_espejo_del_grupo_06_4():
    assert CLASES_EXTERNAS == ["06.4.1"] and "06.4.1" in CLASES_MEDIDAS
    assert es_medida(CANASTA["06.4.1"]) and not es_medida(CANASTA["06.4"])
    for r in PESO_REGION:
        assert CANASTA["06.4.1"].peso(r) == CANASTA["06.4"].peso(r)


def test_nacional_combina_regiones_con_los_pesos_de_indec():
    # Planes por region con distinta variacion: el nacional debe ser el promedio
    # ponderado por PESO_REGION (solo las regiones con dato, renormalizado).
    regs = {"GBA": ("CABA", 10.0), "Pampeana": ("Cordoba", 20.0)}
    f9, f10 = [], []
    for i, (reg, (txt, var)) in enumerate(regs.items(), 1):
        f9.append(_fila(202609, i, "P", 100, 10, txt))
        f10.append(_fila(202610, i, "P", 100 * (1 + var / 100), 10, txt))
    con = _con_prepagas({202609: f9, 202610: f10})
    v = valores_medidos_nacional(con, "2026-10-01", "2026-10-31", "2026-09-01", "2026-09-30")
    w = PESO_REGION["GBA"], PESO_REGION["Pampeana"]
    esperado = (w[0] * 10.0 + w[1] * 20.0) / (w[0] + w[1])
    assert "06.4.1" in v and math.isclose(v["06.4.1"], esperado, rel_tol=1e-9)


def test_varias_regiones_en_variaciones_de_region_e_imputacion_con_la_division():
    con = _con_prepagas({
        202609: [_fila(202609, 1, "A", 100, 10, "CABA"), _fila(202609, 2, "B", 100, 90, "CABA")],
        202610: [_fila(202610, 1, "A", 150, 10, "CABA")],
    })
    out = variaciones_de_region(con, "2026-10-01", "2026-10-31", "2026-09-01", "2026-09-30", "GBA")
    assert "06.4.1" in out and out["06.4.1"].cobertura <= 0.2   # no hay otras clases de 06: sin superior
    assert out["06.4.1"].imputacion_con_superior is False


def test_la_clase_aparece_en_la_division_salud_con_su_peso_nacional():
    divs = resumen_divisiones_desde_valores({"06.4.1": 2.0})
    salud = next(d for d in divs if d.codigo == "06")
    fila = next(f for f in salud.clases if f.codigo == "06.4.1")
    assert fila.variacion_pct == 2.0 and fila.peso > 0
    assert math.isclose(salud.variacion_pct, 2.0)


# ----------------------------------------------------------------- descarga
def _api_falsa(datos: dict, fallos: dict | None = None):
    """datos = {rnemp: [dict de fila API]}; paginacion real de 50 por pagina."""
    import urllib.parse as up
    llamadas = {"n": 0}
    fallos = fallos or {}

    def abrir(url):
        llamadas["n"] += 1
        path, _, qs = url.partition("?")
        if path.endswith("/getPeriodo"):
            return {"data": [202609, 202610]}
        if path.endswith("/getPrepagas"):
            return {"data": [{"rnemp": e, "nombre_comercial": f"E{e}"} for e in datos]}
        q = {k: v[0] for k, v in up.parse_qs(qs).items()}
        e, p, pp = int(q["rnemp"]), int(q["page"]), int(q["per_page"])
        if fallos.get(("timeout", e), 0) > 0:
            fallos[("timeout", e)] -= 1
            return {"code": 504, "message": "Gateway Timeout"}
        filas = datos[e]
        trozo = filas[(p - 1) * pp: p * pp]
        total = fallos.get(("total_mentido", e), len(filas))
        return {"data": trozo, "paginacion": {"total": total, "por_pagina": pp, "pagina_actual": p,
                                              "ultima_pagina": max(1, math.ceil(len(filas) / pp))}}
    abrir.llamadas = llamadas
    return abrir


def _x(per, rnemp, i):
    return {"periodo": per, "rnemp": rnemp, "codigo_plan": i, "nombre_plan": f"PLAN {i}",
            "valor_capital": 1000 + i, "cantidad_capitas": 10, "rango_etario_desde": 0,
            "rango_etario_hasta": 99, "region": "CABA", "tipo_plan": "I", "comercializable": True,
            "permite_copago": False, "tasa_aumento_mensual": 0.02, "modalidad_adhesion": True,
            "nombre_comercial": f"E{rnemp}", "tipificacion": "A"}


def test_descarga_pagina_de_a_50_y_junta_todo():
    datos = {1: [_x(202610, 1, i) for i in range(120)], 2: [_x(202610, 2, i) for i in range(3)], 3: []}
    abrir = _api_falsa(datos)
    filas = bajar_periodo(202610, [1, 2, 3], abrir=abrir, hilos=2, espera=0)
    assert len(filas) == 123
    assert len(fila_csv(datos[1][0])) == len(COLUMNAS)


def test_descarga_reintenta_los_timeouts():
    datos = {1: [_x(202610, 1, i) for i in range(5)]}
    abrir = _api_falsa(datos, {("timeout", 1): 2})
    assert len(bajar_entidad(202610, 1, abrir, espera=0)) == 5


def test_descarga_incompleta_no_se_escribe():
    datos = {1: [_x(202610, 1, i) for i in range(5)]}
    abrir = _api_falsa(datos, {("total_mentido", 1): 9})      # el sitio dice 9 y solo hay 5
    try:
        bajar_periodo(202610, [1], abrir=abrir, hilos=1, espera=0)
        assert False, "debia avisar que el mes esta incompleto"
    except DescargaIncompleta as exc:
        assert "INCOMPLETO" in str(exc)
    # si nunca responde bien, tambien falla
    mala = lambda url: {"code": 504}
    try:
        pedir("http://x/api", mala, intentos=2, espera=0)
        assert False
    except DescargaIncompleta:
        pass


def test_descarga_escribe_archivo_que_la_base_lee_y_importa_csv_plano():
    datos = {1: [_x(202610, 1, i) for i in range(3)]}
    filas = bajar_periodo(202610, [1], abrir=_api_falsa(datos), hilos=1, espera=0)
    d = Path(tempfile.mkdtemp())
    escribir_mes(filas, d / "202610.csv.gz")
    assert not list(d.glob("*.tmp"))
    con = conectar(Path(tempfile.mkdtemp()) / "t.db")
    asegurar_periodos_cargados(con, d, [202610])
    assert len(filas_de_periodo(con, 202610)) == 3
    # CSV plano (plan B con el navegador)
    plano = d / "bajado.csv"
    with open(plano, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(COLUMNAS); w.writerows(filas)
    destino = importar_csv_plano(plano, Path(tempfile.mkdtemp()))
    assert destino.name == "202610.csv.gz"
    plano.write_text("periodo,x\n1,2\n", encoding="utf-8")
    try:
        importar_csv_plano(plano, d)
        assert False
    except ValueError:
        pass


# ----------------------------------------------------------------- "solo cuando lo pido"
def test_sin_incluir_externas_prepagas_no_se_calcula_ni_afecta_salud():
    con = _con_prepagas({
        202609: [_fila(202609, 1, "A", 100, 10, "CABA")],
        202610: [_fila(202610, 1, "A", 110, 10, "CABA")],
    })
    args = ("2026-10-01", "2026-10-31", "2026-09-01", "2026-09-30")
    con_pre = valores_medidos_nacional(con, *args)
    sin_pre = valores_medidos_nacional(con, *args, incluir_externas=False)
    assert "06.4.1" in con_pre and "06.4.1" not in sin_pre
    divs = resumen_divisiones_desde_valores(sin_pre, incluir_externas=False)
    salud = next(d for d in divs if d.codigo == "06")
    assert all(f.codigo != "06.4.1" for f in salud.clases)
    # con SEPA de Salud presente, prepagas apagado no mueve el resultado de Salud
    base = {"06.1.1": 5.0}
    s_off = next(d for d in resumen_divisiones_desde_valores(base, incluir_externas=False) if d.codigo == "06")
    s_on = next(d for d in resumen_divisiones_desde_valores({**base, "06.4.1": 1.0}) if d.codigo == "06")
    assert math.isclose(s_off.variacion_pct, 5.0)
    assert s_on.variacion_pct < 5.0        # prepagas encendida y mas baja: baja la division


def test_semana_dentro_de_un_mes_da_cero_y_cruzando_el_mes_entra_todo():
    con = _con_prepagas({
        202610: [_fila(202610, 1, "A", 100, 10, "CABA")],
        202611: [_fila(202611, 1, "A", 110, 10, "CABA")],
    })
    misma = variacion_clase(con, "06.4.1", "2026-10-19", "2026-10-25", "2026-10-12", "2026-10-18",
                            region="GBA")[0]
    cruza = variacion_clase(con, "06.4.1", "2026-11-02", "2026-11-08", "2026-10-26", "2026-11-01",
                            region="GBA")[0]
    assert math.isclose(misma.variacion_pct, 0.0, abs_tol=1e-12)
    assert cruza.variacion_pct > 0           # la ventana base mezcla 6 dias de oct y 1 de nov


# ----------------------------------------------------------------- sincronizacion semanal
def _sitio_falso(meses: dict[int, int], caido=False):
    """meses = {periodo: cantidad de filas}; 1 entidad. Soporta total por periodo."""
    import urllib.parse as up
    estado = {"meses": dict(meses), "bajadas": []}

    def abrir(url):
        if caido:
            raise OSError("sin red")
        path, _, qs = url.partition("?")
        if path.endswith("/getPeriodo"):
            return {"data": sorted(estado["meses"])}
        if path.endswith("/getPrepagas"):
            return {"data": [{"rnemp": 1, "nombre_comercial": "E1"}]}
        q = {k: v[0] for k, v in up.parse_qs(qs).items()}
        per, p, pp = int(q["periodo"]), int(q["page"]), int(q["per_page"])
        n = estado["meses"][per]
        if "rnemp" in q and p == 1:
            estado["bajadas"].append(per)
        filas = [_x(per, 1, i) for i in range(n)]
        return {"data": filas[(p - 1) * pp: p * pp],
                "paginacion": {"total": n, "por_pagina": pp, "pagina_actual": p,
                               "ultima_pagina": max(1, math.ceil(n / pp))}}
    abrir.estado = estado
    return abrir


def test_sincronizar_baja_lo_nuevo_respeta_el_piso_y_detecta_cambios():
    from scripts.actualizar_prepagas import sincronizar
    d = Path(tempfile.mkdtemp())
    sitio = _sitio_falso({202506: 3, 202607: 4, 202608: 5})
    logs = []
    r1 = sincronizar(d, desde=202607, abrir=sitio, hilos=1, espera=0, log=logs.append)
    assert r1["bajados"] == [202607, 202608] and not r1["errores"]
    assert periodos_disponibles(d) == [202607, 202608]                 # 202506 quedo afuera (piso)
    # sin cambios: no baja nada
    sitio.estado["bajadas"].clear()
    r2 = sincronizar(d, desde=202607, abrir=sitio, hilos=1, espera=0, log=logs.append)
    assert r2["sin_cambios"] == [202607, 202608] and not sitio.estado["bajadas"]
    # el mes en curso se llena: el sitio ahora tiene mas filas -> se vuelve a bajar SOLO ese
    sitio.estado["meses"][202608] = 9
    r3 = sincronizar(d, desde=202607, abrir=sitio, hilos=1, espera=0, log=logs.append)
    assert r3["actualizados"] == [202608] and sitio.estado["bajadas"] == [202608]
    from collectors.prepagas.descargar import contar_filas_archivo
    assert contar_filas_archivo(d / "202608.csv.gz") == 9
    # aparece un mes nuevo
    sitio.estado["meses"][202609] = 2
    r4 = sincronizar(d, desde=202607, abrir=sitio, hilos=1, espera=0, log=logs.append)
    assert r4["bajados"] == [202609]


def test_sincronizar_con_el_sitio_caido_no_levanta_excepcion():
    from scripts.actualizar_prepagas import sincronizar
    d = Path(tempfile.mkdtemp())
    r = sincronizar(d, abrir=_sitio_falso({202607: 1}, caido=True), espera=0, intentos=2, log=lambda *_: None)
    assert r["errores"] and not r["bajados"] and periodos_disponibles(d) == []


def test_mes_recargado_con_datos_distintos_no_usa_el_cache_viejo():
    d = _carpeta_con({202609: [_fila(202609, 1, "A", 100, 10, "CABA")],
                      202610: [_fila(202610, 1, "A", 110, 10, "CABA")]})
    con = conectar(Path(tempfile.mkdtemp()) / "t.db")
    asegurar_periodos_cargados(con, d, [202609, 202610])
    args = ("2026-10-01", "2026-10-31", "2026-09-01", "2026-09-30")
    assert math.isclose(variacion_clase(con, "06.4.1", *args, region="GBA")[0].variacion_pct, 10.0)
    # el mes se vuelve a bajar y las entidades corrigieron la cuota (misma cantidad de filas)
    escribir_mes([_fila(202610, 1, "A", 150, 10, "CABA")], d / "202610.csv.gz")
    asegurar_periodos_cargados(con, d, [202610])
    assert math.isclose(variacion_clase(con, "06.4.1", *args, region="GBA")[0].variacion_pct, 50.0)
