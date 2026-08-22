"""
Tests de engine/fechas.py.

El primer test reproduce EXACTAMENTE el bug real reportado en producción
(Streamlit Cloud, con la base recién creada y un solo día cargado):
la app se caía con StreamlitAPIException porque el preset "última semana"
calculaba una fecha anterior a la única disponible. Este test existe para
que, si alguna vez alguien vuelve a tocar `calcular_preset` o `acotar_rango`,
sepa inmediatamente si reintrodujo el problema.
"""

from datetime import date

from engine.fechas import acotar_rango, calcular_preset


def test_bug_real_un_solo_dia_cargado_no_debe_salirse_del_rango():
    """Caso real reportado: base con un único día (2026-08-09). El preset
    de 'última semana' resta 6, 7 y 13 días — muy anterior al único día
    disponible. Antes del arreglo, esto generaba fechas fuera de
    [d_min, d_max] que Streamlit rechazaba con una excepción."""
    d_min = d_max = date(2026, 8, 9)

    desde, hasta, desde_base, hasta_base = calcular_preset("semana", d_max)
    desde, hasta, desde_base, hasta_base = acotar_rango(
        desde, hasta, desde_base, hasta_base, d_min, d_max
    )

    for fecha in (desde, hasta, desde_base, hasta_base):
        assert d_min <= fecha <= d_max, f"{fecha} quedó fuera de [{d_min}, {d_max}]"


def test_pocos_dias_cargados_tambien_queda_dentro_del_rango():
    """Un caso intermedio: 5 días cargados, todavía menos de una semana."""
    d_min, d_max = date(2026, 8, 9), date(2026, 8, 13)

    for preset in ("semana", "mes", "personalizado"):
        desde, hasta, desde_base, hasta_base = calcular_preset(preset, d_max)
        desde, hasta, desde_base, hasta_base = acotar_rango(
            desde, hasta, desde_base, hasta_base, d_min, d_max
        )
        for fecha in (desde, hasta, desde_base, hasta_base):
            assert d_min <= fecha <= d_max, (
                f"preset={preset!r}: {fecha} fuera de [{d_min}, {d_max}]"
            )


def test_con_datos_normales_el_acotado_no_cambia_nada():
    """Con mes y medio de historia (el caso habitual una vez que el
    proyecto lleva un tiempo andando), acotar_rango no debe alterar las
    fechas del preset — nunca deberían quedar fuera de rango en ese caso."""
    d_min, d_max = date(2026, 7, 1), date(2026, 8, 20)

    desde, hasta, desde_base, hasta_base = calcular_preset("semana", d_max)
    acotadas = acotar_rango(desde, hasta, desde_base, hasta_base, d_min, d_max)

    assert acotadas == (desde, hasta, desde_base, hasta_base)


def test_preset_semana_da_dos_ventanas_de_7_dias_consecutivas():
    d_max = date(2026, 8, 20)
    desde, hasta, desde_base, hasta_base = calcular_preset("semana", d_max)

    assert hasta == d_max
    assert (hasta - desde).days == 6          # ventana de 7 días inclusive
    assert (hasta_base - desde_base).days == 6
    assert hasta_base == desde - __import__("datetime").timedelta(days=1)


def test_preset_mes_usa_el_primero_y_el_ultimo_del_mes_anterior():
    d_max = date(2026, 8, 20)
    desde, hasta, desde_base, hasta_base = calcular_preset("mes", d_max)

    assert desde == date(2026, 8, 1)
    assert hasta == d_max
    assert desde_base == date(2026, 7, 1)
    assert hasta_base == date(2026, 7, 31)


def test_preset_desconocido_no_rompe_devuelve_un_solo_dia():
    d_max = date(2026, 8, 20)
    resultado = calcular_preset("personalizado", d_max)
    assert resultado == (d_max, d_max, d_max, d_max)
