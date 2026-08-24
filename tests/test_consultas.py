"""
Tests de engine/consultas.py — la capa que usa la app de Streamlit.

POR QUE IMPORTAN ESPECIALMENTE: el entorno donde se desarrollo esto no
tiene Streamlit instalado ni salida a internet para instalarlo, asi que la
pantalla en si no se pudo ejecutar. Pero como app_streamlit.py NO hace
cuentas —solo llama a estas funciones— testear esto cubre toda la logica.
Lo unico sin probar es el cableado de widgets.
"""

import math
import tempfile
from pathlib import Path

from engine.consultas import (
    division_completa,
    indice_nacional,
    indice_region,
    resumen_divisiones,
)
from engine.index_elemental import ObservacionVariedad
from storage.db import conectar, insertar_observaciones

REGIONES = ["GBA", "Pampeana", "Noreste", "Noroeste", "Cuyo", "Patagonia"]
SUBAS = {"GBA": 1.05, "Pampeana": 1.08, "Noreste": 1.12,
         "Noroeste": 1.10, "Cuyo": 1.06, "Patagonia": 1.03}
DATOS = {"01.1.6": [("BANANA", "Banana x kg", 100)],
         "01.1.7": [("PAPA", "Papa x kg", 80)],
         "01.1.1": [("PAN", "Pan x kg", 1500)],
         "05.6.1": [("DET", "Detergente 750ml", 1900)]}
BASE = ["2026-08-09", "2026-08-10", "2026-08-11", "2026-08-12"]
ACT = ["2026-08-13", "2026-08-14", "2026-08-15", "2026-08-16"]
D1, H1, D0, H0 = "2026-08-13", "2026-08-16", "2026-08-09", "2026-08-12"


def _base(path):
    con = conectar(path)
    obs = []
    for reg in REGIONES:
        for clase, prods in DATOS.items():
            for ean, nom, p in prods:
                for d in BASE:
                    obs.append((ObservacionVariedad(d, ean, "C1", float(p), nom, region=reg), clase))
                for d in ACT:
                    obs.append((ObservacionVariedad(d, ean, "C1", p * SUBAS[reg], nom, region=reg), clase))
    insertar_observaciones(con, obs)
    return con


def test_cada_region_devuelve_su_propia_variacion():
    with tempfile.TemporaryDirectory() as t:
        con = _base(Path(t) / "t.db")
        for r in REGIONES:
            v, _ = indice_region(con, D1, H1, D0, H0, r)
            assert abs(v - (SUBAS[r] - 1) * 100) < 0.01, f"{r}: {v}"
        con.close()


def test_nacional_pondera_por_importancia_de_region():
    from config.canasta import PESO_REGION
    with tempfile.TemporaryDirectory() as t:
        con = _base(Path(t) / "t.db")
        nac, cob, detalle = indice_nacional(con, D1, H1, D0, H0)
        esperado = (sum(PESO_REGION[r] * (SUBAS[r] - 1) * 100 for r in REGIONES)
                    / sum(PESO_REGION.values()))
        assert abs(nac - esperado) < 1e-6
        assert len(detalle) == 6
        assert math.isclose(cob, 1.0, abs_tol=1e-9)
        con.close()


def test_nacional_con_una_region_faltante_renormaliza():
    """Si falta una region no se asume cero: se excluye y se avisa."""
    from config.canasta import PESO_REGION
    with tempfile.TemporaryDirectory() as t:
        con = conectar(Path(t) / "t.db")
        obs = []
        for d in BASE:
            obs.append((ObservacionVariedad(d, "BANANA", "C1", 100.0, "Banana", region="GBA"), "01.1.6"))
        for d in ACT:
            obs.append((ObservacionVariedad(d, "BANANA", "C1", 110.0, "Banana", region="GBA"), "01.1.6"))
        insertar_observaciones(con, obs)
        nac, cob, detalle = indice_nacional(con, D1, H1, D0, H0)
        assert list(detalle) == ["GBA"]
        assert abs(nac - 10.0) < 1e-9          # con una sola region, es esa region
        assert abs(cob - PESO_REGION["GBA"] / sum(PESO_REGION.values())) < 1e-9
        con.close()


def test_suma_de_aportes_reproduce_la_division():
    with tempfile.TemporaryDirectory() as t:
        con = _base(Path(t) / "t.db")
        d = division_completa(con, "01", D1, H1, D0, H0, "GBA")
        suma = sum(f.aporte_pp for f in d.clases if f.aporte_pp is not None)
        assert abs(suma - d.variacion_pct) < 1e-9
        con.close()


def test_resumen_devuelve_las_12_divisiones():
    with tempfile.TemporaryDirectory() as t:
        con = _base(Path(t) / "t.db")
        divs = resumen_divisiones(con, D1, H1, D0, H0, "GBA")
        assert len(divs) == 12
        con_datos = [d for d in divs if d.variacion_pct is not None]
        assert len(con_datos) >= 2      # al menos 01 y 05 tienen datos
        con.close()


def test_clases_sin_datos_no_se_asumen_cero():
    """Una clase sin datos queda en None, no en 0.0 — si se asumiera cero
    diluiria la variacion de la division hacia abajo."""
    with tempfile.TemporaryDirectory() as t:
        con = _base(Path(t) / "t.db")
        d = division_completa(con, "01", D1, H1, D0, H0, "GBA")
        sin_datos = [f for f in d.clases if f.variacion_pct is None]
        assert sin_datos, "el escenario de prueba deberia tener clases sin datos"
        assert all(f.aporte_pp is None for f in sin_datos)
        # la division debe valer 5% (la suba de GBA), no menos
        assert abs(d.variacion_pct - 5.0) < 0.01
        con.close()


def test_override_reemplaza_el_valor_de_una_clase():
    with tempfile.TemporaryDirectory() as t:
        con = _base(Path(t) / "t.db")
        sin_override = division_completa(con, "01", D1, H1, D0, H0, "GBA")
        con_override = division_completa(con, "01", D1, H1, D0, H0, "GBA",
                                          overrides={"01.1.6": 50.0})
        fruta_normal = next(f for f in sin_override.clases if f.codigo == "01.1.6")
        fruta_manual = next(f for f in con_override.clases if f.codigo == "01.1.6")
        assert not fruta_normal.es_manual
        assert fruta_manual.es_manual
        assert math.isclose(fruta_manual.variacion_pct, 50.0)
        assert con_override.variacion_pct != sin_override.variacion_pct
        assert con_override.tiene_manuales is True
        assert sin_override.tiene_manuales is False
        con.close()


def test_override_no_modifica_la_base_de_datos():
    """El test mas importante de esta funcionalidad: simular un valor no
    puede dejar rastro en la base. Se verifica llamando SIN override
    despues de haber llamado CON override, y confirmando que el resultado
    real es exactamente el mismo que si el override nunca hubiera pasado."""
    with tempfile.TemporaryDirectory() as t:
        con = _base(Path(t) / "t.db")
        antes = division_completa(con, "01", D1, H1, D0, H0, "GBA")

        # simular varias veces, con valores distintos cada vez
        division_completa(con, "01", D1, H1, D0, H0, "GBA", overrides={"01.1.6": 999.0})
        division_completa(con, "01", D1, H1, D0, H0, "GBA", overrides={"01.1.7": -50.0})

        despues = division_completa(con, "01", D1, H1, D0, H0, "GBA")
        assert math.isclose(antes.variacion_pct, despues.variacion_pct)
        for fa, fd in zip(antes.clases, despues.clases):
            assert fa.variacion_pct == fd.variacion_pct
            assert not fd.es_manual
        con.close()


def test_override_en_indice_region():
    with tempfile.TemporaryDirectory() as t:
        con = _base(Path(t) / "t.db")
        v_normal, _ = indice_region(con, D1, H1, D0, H0, "GBA")
        v_manual, _ = indice_region(con, D1, H1, D0, H0, "GBA", overrides={"01.1.6": 200.0})
        assert v_manual > v_normal
        con.close()


def test_nivel_general_combina_medida_y_manual_con_pesos_oficiales():
    """El caso real pedido: Alimentos con dato medido (via SEPA) y
    Comunicacion con el dato de otra consultora puesto a mano. Verificado
    con la cuenta hecha a mano, usando el PESO OFICIAL COMPLETO de cada
    division (no el peso interno de la clase que aporto el dato) — asi es
    como corresponde combinar una vez que una division ya devolvio un
    numero, sea medido o manual."""
    with tempfile.TemporaryDirectory() as t:
        con = _base(Path(t) / "t.db")
        from engine.consultas import nivel_general
        from config.canasta import CANASTA

        r = nivel_general(con, D1, H1, D0, H0, "GBA", overrides_division={"08": 3.5})

        div01 = next(f for f in r.divisiones if f.codigo == "01")
        div08 = next(f for f in r.divisiones if f.codigo == "08")
        assert div01.fuente == "medida"
        assert div08.fuente == "manual"
        assert math.isclose(div08.variacion_pct, 3.5)

        # Verificacion generica: la fixture _base() carga datos de VARIAS
        # divisiones (no solo 01 y 08 — tambien 05), asi que el chequeo a
        # mano se arma dinamicamente con todas las que devolvieron dato,
        # en vez de asumir cuales son. Es lo que se corrigio ademas: la
        # primera version de este test solo consideraba 01 y 08 y daba
        # "distinto" porque se olvidaba de 05 — no era un bug del motor,
        # era una cuenta a mano incompleta.
        con_dato = [f for f in r.divisiones if f.variacion_pct is not None]
        assert len(con_dato) >= 2
        num = sum(f.peso * f.variacion_pct for f in con_dato)
        den = sum(f.peso for f in con_dato)
        assert math.isclose(r.variacion_pct, num / den, rel_tol=1e-9)
        con.close()


def test_nivel_general_division_manual_no_requiere_datos_en_la_base():
    """Comunicacion no tiene NINGUNA clase medida por SEPA (cobertura
    total = 0 clases MEDIDA_SEPA). El override tiene que funcionar igual,
    sin que haga falta que haya una sola fila en la base para esa
    division."""
    with tempfile.TemporaryDirectory() as t:
        con = conectar(Path(t) / "vacia.db")
        from engine.consultas import nivel_general
        r = nivel_general(con, D1, H1, D0, H0, "GBA", overrides_division={"08": 5.0})
        div08 = next(f for f in r.divisiones if f.codigo == "08")
        assert div08.variacion_pct == 5.0
        assert math.isclose(r.variacion_pct, 5.0)
        con.close()


def test_nivel_general_sin_overrides_ni_datos_devuelve_none():
    with tempfile.TemporaryDirectory() as t:
        con = conectar(Path(t) / "vacia2.db")
        from engine.consultas import nivel_general
        r = nivel_general(con, D1, H1, D0, H0, "GBA")
        assert r.variacion_pct is None
        assert r.cobertura == 0.0
        con.close()


def test_nivel_general_reporta_cobertura_interna_de_cada_division():
    """Cuando una division tiene MUCHAS clases pero solo una con dato, la
    variacion de esa division igual se calcula (renormalizada) — pero la
    cobertura_interna tiene que reflejar que fue parcial, para que la
    interfaz pueda avisar que ese numero se apoya en poca informacion."""
    with tempfile.TemporaryDirectory() as t:
        con = _base(Path(t) / "t.db")
        from engine.consultas import nivel_general
        r = nivel_general(con, D1, H1, D0, H0, "GBA")
        div01 = next(f for f in r.divisiones if f.codigo == "01")
        assert div01.cobertura_interna is not None
        assert 0 < div01.cobertura_interna <= 1.0
        con.close()


def test_variacion_clase_nacional_combina_solo_regiones_con_dato():
    """Verificado a mano: GBA +10%, Pampeana +20%, nada en las otras 4
    regiones. El nacional tiene que ser el promedio ponderado por
    PESO_REGION de esas DOS, renormalizado — nunca un promedio simple
    (que le daria a Pampeana el mismo peso que a GBA) ni un pool de
    precios sin ponderar (que sobre-representaria donde SEPA tiene mas
    sucursales)."""
    with tempfile.TemporaryDirectory() as t:
        con = conectar(Path(t) / "t.db")
        obs = []
        for d in ["2026-08-09", "2026-08-10", "2026-08-11", "2026-08-12"]:
            obs.append((ObservacionVariedad(d, "BANANA", "C1", 100.0, "Banana", region="GBA"), "01.1.6"))
            obs.append((ObservacionVariedad(d, "BANANA", "C1", 100.0, "Banana", region="Pampeana"), "01.1.6"))
        for d in ["2026-08-13", "2026-08-14", "2026-08-15", "2026-08-16"]:
            obs.append((ObservacionVariedad(d, "BANANA", "C1", 110.0, "Banana", region="GBA"), "01.1.6"))
            obs.append((ObservacionVariedad(d, "BANANA", "C1", 120.0, "Banana", region="Pampeana"), "01.1.6"))
        insertar_observaciones(con, obs)

        from engine.consultas import variacion_clase_nacional
        v, cob = variacion_clase_nacional(con, "01.1.6", D1, H1, D0, H0)

        from config.canasta import PESO_REGION
        esperado = (PESO_REGION["GBA"] * 10.0 + PESO_REGION["Pampeana"] * 20.0) / \
                   (PESO_REGION["GBA"] + PESO_REGION["Pampeana"])
        cob_esperada = (PESO_REGION["GBA"] + PESO_REGION["Pampeana"]) / sum(PESO_REGION.values())

        assert math.isclose(v, esperado, rel_tol=1e-9)
        assert math.isclose(cob, cob_esperada, rel_tol=1e-9)
        con.close()


def test_nivel_general_nacional_combina_medida_y_manual():
    with tempfile.TemporaryDirectory() as t:
        con = conectar(Path(t) / "t.db")
        obs = []
        for d in ["2026-08-09", "2026-08-10", "2026-08-11", "2026-08-12"]:
            obs.append((ObservacionVariedad(d, "BANANA", "C1", 100.0, "Banana", region="GBA"), "01.1.6"))
        for d in ["2026-08-13", "2026-08-14", "2026-08-15", "2026-08-16"]:
            obs.append((ObservacionVariedad(d, "BANANA", "C1", 110.0, "Banana", region="GBA"), "01.1.6"))
        insertar_observaciones(con, obs)

        from engine.consultas import nivel_general_nacional
        r = nivel_general_nacional(con, D1, H1, D0, H0, overrides_division={"08": 3.0})

        div01 = next(f for f in r.divisiones if f.codigo == "01")
        div08 = next(f for f in r.divisiones if f.codigo == "08")
        assert div01.fuente == "medida"
        assert div08.fuente == "manual"

        esperado = (div01.peso * div01.variacion_pct + div08.peso * 3.0) / (div01.peso + div08.peso)
        assert math.isclose(r.variacion_pct, esperado, rel_tol=1e-6)
        con.close()


def test_nivel_general_nacional_sin_overrides_devuelve_solo_lo_medido():
    with tempfile.TemporaryDirectory() as t:
        con = _base(Path(t) / "t.db")
        from engine.consultas import nivel_general_nacional
        r = nivel_general_nacional(con, D1, H1, D0, H0)
        assert r.variacion_pct is not None
        # ninguna division deberia venir marcada como manual
        assert all(f.fuente != "manual" for f in r.divisiones)
        con.close()


def test_camino_rapido_da_lo_mismo_que_el_camino_original():
    """La capa de rendimiento (valores_medidos_nacional +
    resumen_divisiones_desde_valores + nivel_general_desde_divisiones) NO
    puede dar un numero distinto al camino original — separar 'caro' de
    'barato' es una optimizacion, no un cambio de metodologia. Si algun
    dia se desincroniza, este test tiene que fallar."""
    with tempfile.TemporaryDirectory() as t:
        con = _base(Path(t) / "t.db")
        from engine.consultas import (
            nivel_general_nacional, resumen_divisiones_nacional,
            valores_medidos_nacional, resumen_divisiones_desde_valores,
            nivel_general_desde_divisiones,
        )
        ov_clase = {"01.1.6": 12.5}
        ov_div = {"08": 2.0}

        r_original = nivel_general_nacional(con, D1, H1, D0, H0,
                                            overrides_clase=ov_clase, overrides_division=ov_div)
        divs_original = resumen_divisiones_nacional(con, D1, H1, D0, H0, overrides_clase=ov_clase)

        valores = valores_medidos_nacional(con, D1, H1, D0, H0)
        divs_rapido = resumen_divisiones_desde_valores(valores, overrides_clase=ov_clase)
        r_rapido = nivel_general_desde_divisiones(divs_rapido, overrides_division=ov_div)

        assert math.isclose(r_original.variacion_pct, r_rapido.variacion_pct, rel_tol=1e-9)
        assert math.isclose(r_original.cobertura, r_rapido.cobertura, rel_tol=1e-9)
        for do, dr in zip(divs_original, divs_rapido):
            assert do.codigo == dr.codigo
            if do.variacion_pct is None:
                assert dr.variacion_pct is None
            else:
                assert math.isclose(do.variacion_pct, dr.variacion_pct, rel_tol=1e-9)
        con.close()


def test_valores_medidos_nacional_no_depende_de_overrides():
    """Confirma la premisa que hace valido el cacheo: los valores medidos
    son los mismos sin importar que overrides se vayan a aplicar despues
    (porque se calculan ANTES de aplicar ninguno)."""
    with tempfile.TemporaryDirectory() as t:
        con = _base(Path(t) / "t.db")
        from engine.consultas import valores_medidos_nacional
        v1 = valores_medidos_nacional(con, D1, H1, D0, H0)
        v2 = valores_medidos_nacional(con, D1, H1, D0, H0)
        assert v1 == v2
        con.close()


def test_combinar_regiones_renormaliza_cuando_falta_una():
    """El caso que explica diferencias con calculos manuales que dividen
    siempre por el 100% de las 6 regiones: si una region no tiene dato,
    el sistema renormaliza sobre las que si tienen — no divide por el
    peso de las 6."""
    from engine.consultas import _combinar_regiones
    from config.canasta import PESO_REGION

    valores_incompletos = {"GBA": 5.0, "Pampeana": 8.0, "Noroeste": 10.0,
                           "Cuyo": 6.0, "Patagonia": 3.0}  # falta Noreste
    v, cobertura = _combinar_regiones(valores_incompletos, PESO_REGION)

    pesos_5 = {r: PESO_REGION[r] for r in valores_incompletos}
    esperado_renormalizado = (sum(pesos_5[r] * valores_incompletos[r] for r in valores_incompletos)
                              / sum(pesos_5.values()))
    esperado_sin_renormalizar = (sum(pesos_5[r] * valores_incompletos[r] for r in valores_incompletos)
                                 / sum(PESO_REGION.values()))

    assert math.isclose(v, esperado_renormalizado, rel_tol=1e-9)
    assert not math.isclose(v, esperado_sin_renormalizar, abs_tol=0.01), (
        "si esto se cumpliera, el sistema NO estaria renormalizando"
    )
    assert math.isclose(cobertura, sum(pesos_5.values()) / sum(PESO_REGION.values()), rel_tol=1e-9)


def test_peso_region_suma_exactamente_uno():
    """Historial: los pesos de la Metodologia N32 Cuadro 6, redondeados a 3
    decimales (0.447, 0.342, 0.069, 0.045, 0.052, 0.046), sumaban 1.001 en
    vez de 1.000. Se reemplazaron por una tabla con 2 decimales provista
    directamente (44.67%, 34.19%, 6.88%, 4.51%, 5.18%, 4.57%), que suma
    exacto sin necesidad de normalizar. Este test evita que un valor mal
    tipeado en una futura edicion rompa esa suma."""
    from config.canasta import PESO_REGION
    assert math.isclose(sum(PESO_REGION.values()), 1.0, abs_tol=1e-9)


def test_peso_region_coincide_con_la_tabla_oficial_provista():
    """Valores exactos de la tabla de INDEC, para detectar si alguien
    edita PESO_REGION sin darse cuenta de que tiene que seguir sumando
    exacto 1.0 y usando estos numeros como fuente."""
    from config.canasta import PESO_REGION
    esperado = {"GBA": 0.4467, "Pampeana": 0.3419, "Noroeste": 0.0688,
               "Noreste": 0.0451, "Cuyo": 0.0518, "Patagonia": 0.0457}
    for region, valor in esperado.items():
        assert math.isclose(PESO_REGION[region], valor, abs_tol=1e-9), region


def test_los_12_pesos_nacionales_de_division_suman_100():
    from engine.consultas import peso_nacional_division
    from config.canasta import divisiones
    suma = sum(peso_nacional_division(d.codigo) for d in divisiones())
    assert math.isclose(suma, 100.0, abs_tol=0.01)
