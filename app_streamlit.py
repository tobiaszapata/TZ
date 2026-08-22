"""
Aplicacion Streamlit — interfaz de analisis del relevamiento.

    streamlit run app_streamlit.py

IMPORTANTE — ESTE ARCHIVO NO HACE CUENTAS. Todo el calculo vive en
engine/consultas.py, testeado sin necesidad de levantar Streamlit.

INCLUYE MODO SIMULACION: se puede pisar el valor de cualquier subcategoria
con un numero manual (por ejemplo, el dato que publica otra consultora) y
ver como se propaga hacia la division. Esto NUNCA toca la base de datos —
vive solo en la memoria de esta sesion del navegador. Ver el docstring de
engine/consultas.py para el detalle y el test que lo garantiza
(tests/test_consultas.py::test_override_no_modifica_la_base_de_datos).
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import streamlit as st

from config.canasta import PESO_REGION
from engine.consultas import (
    division_completa,
    indice_nacional,
    indice_region,
    resumen_divisiones,
    variacion_clase,
)
from storage.db import conectar, regiones_disponibles

DB_PATH = Path("relevamiento_precios.db")

st.set_page_config(page_title="Relevamiento de Precios", layout="wide")


@st.cache_resource
def _con():
    return conectar(DB_PATH)


@st.cache_data(ttl=300)
def _rango_disponible():
    cur = _con().execute("SELECT MIN(fecha), MAX(fecha), COUNT(DISTINCT fecha) FROM precios_raw")
    return cur.fetchone()


def _color(v):
    if v is None:
        return "—"
    return f"{v:+.2f}%"


# ---------------------------------------------------------------- arranque
st.title("Relevamiento de Precios")
st.caption("Índice de precios por región y categoría · fuente SEPA · metodología INDEC N°32")

if not DB_PATH.exists():
    historico = Path("historico")
    respaldos = sorted(historico.glob("*.csv.gz")) if historico.exists() else []
    if respaldos:
        with st.spinner(f"Primera carga: reconstruyendo la base desde {len(respaldos)} "
                        f"días de respaldo. Pasa una sola vez..."):
            from scripts.reconstruir import reconstruir
            reconstruir()
        st.success("Base reconstruida desde el histórico.")
    else:
        st.error(
            "No hay datos todavía. Si estás en tu computadora, corré "
            "`python -m scripts.correr_dia --carpeta datos_sepa/`. Si esto es la app "
            "publicada, todavía no hay ningún día guardado en `historico/`."
        )
        st.stop()

fmin, fmax, ndias = _rango_disponible()
if not fmin:
    st.warning("La base está vacía. Cargá al menos un día para empezar.")
    st.stop()

st.info(f"Datos disponibles: **{fmin}** a **{fmax}** · {ndias} días cargados")

# --------------------------------------------------------- estado: overrides
if "overrides" not in st.session_state:
    st.session_state.overrides = {}   # {codigo_clase: valor_pct}

# ---------------------------------------------------------------- controles
with st.sidebar:
    st.header("Período")

    d_max = date.fromisoformat(fmax)
    d_min = date.fromisoformat(fmin)

    preset = st.radio(
        "Comparación rápida",
        ["Última semana vs previa", "Mes actual vs anterior", "Personalizado"],
        index=0,
    )

    if preset == "Última semana vs previa":
        h1, d1 = d_max, d_max - timedelta(days=6)
        h0, d0 = d1 - timedelta(days=1), d1 - timedelta(days=7)
    elif preset == "Mes actual vs anterior":
        d1 = d_max.replace(day=1)
        h1 = d_max
        h0 = d1 - timedelta(days=1)
        d0 = h0.replace(day=1)
    else:
        d1 = h1 = h0 = d0 = d_max

    st.markdown("**Período a analizar**")
    d1 = st.date_input("desde", d1, min_value=d_min, max_value=d_max, key="d1")
    h1 = st.date_input("hasta", h1, min_value=d_min, max_value=d_max, key="h1")
    st.markdown("**Comparado contra**")
    d0 = st.date_input("desde ", d0, min_value=d_min, max_value=d_max, key="d0")
    h0 = st.date_input("hasta ", h0, min_value=d_min, max_value=d_max, key="h0")

    st.divider()
    st.header("Región")
    disponibles = regiones_disponibles(_con())
    opciones = ["Nacional (todas)"] + disponibles
    region_sel = st.selectbox("Región", opciones, index=0)

    st.divider()
    st.header("Modo simulación")
    modo_simulacion = st.toggle(
        "Activar edición manual",
        value=False,
        help="Permite pisar el valor de una subcategoría con un número propio "
             "(por ejemplo, el dato de otra consultora) para ver cómo cambiaría "
             "la categoría. No modifica ningún dato guardado.",
    )
    if st.session_state.overrides:
        st.caption(f"⚠️ {len(st.session_state.overrides)} valor(es) editado(s) a mano")
        if st.button("Borrar todos los valores manuales"):
            st.session_state.overrides = {}
            st.rerun()

D1, H1, D0, H0 = (x.isoformat() for x in (d1, h1, d0, h0))

if modo_simulacion:
    st.warning(
        "**Modo simulación activo.** Los valores marcados con ✏️ son manuales, no medidos. "
        "Esto es un ejercicio de \"¿qué pasaría si…?\" — la base de datos real no se toca. "
        "Desactivá el modo para volver a ver únicamente los datos relevados."
    )

# ---------------------------------------------------------------- resultado
st.header("Resultado")

if region_sel == "Nacional (todas)":
    nac, cob_pais, por_region = indice_nacional(_con(), D1, H1, D0, H0)
    c1, c2 = st.columns([1, 2])
    c1.metric("Índice nacional", _color(nac))
    c2.caption(
        f"Cobertura geográfica: {cob_pais:.0%} de la población de referencia del país. "
        "Las regiones sin datos se excluyen y se renormaliza — no se asumen en cero."
    )
    if por_region:
        st.subheader("Por región")
        st.dataframe(
            [{"Región": r,
              "Peso nacional": f"{PESO_REGION[r]*100:.1f}%",
              "Variación": _color(v)} for r, v in sorted(por_region.items())],
            use_container_width=True, hide_index=True,
        )
    region_detalle = "GBA" if "GBA" in disponibles else (disponibles[0] if disponibles else "GBA")
    st.caption(f"El detalle por categoría de abajo se muestra para **{region_detalle}**. "
               "Elegí una región en el panel izquierdo para ver otra, o para simular.")
    if modo_simulacion:
        st.caption("La simulación no está disponible en la vista Nacional combinada — "
                   f"elegí una región (por ejemplo {region_detalle}) en el panel izquierdo.")
else:
    region_detalle = region_sel
    overrides_activos = st.session_state.overrides if modo_simulacion else {}
    v, cob = indice_region(_con(), D1, H1, D0, H0, region_detalle, overrides=overrides_activos)
    c1, c2 = st.columns([1, 2])
    c1.metric(f"Índice {region_detalle}", _color(v))
    c2.caption(f"Cobertura: {cob:.0%} de las categorías que el sistema puede medir en esta región. "
               f"Ponderadores oficiales de INDEC para {region_detalle}.")

# ---------------------------------------------------------------- detalle
st.header("Detalle por categoría")
st.caption("Cada división se abre para ver sus subcategorías, y cada subcategoría para ver los "
           "productos. La columna *aporte* suma exactamente la variación de la división.")

overrides_activos = st.session_state.overrides if (modo_simulacion and region_sel != "Nacional (todas)") else {}
divs = resumen_divisiones(_con(), D1, H1, D0, H0, region_detalle, overrides=overrides_activos)

for d in divs:
    tiene = d.variacion_pct is not None
    marca_manual = " ✏️" if d.tiene_manuales else ""
    etiqueta = f"{d.codigo} · {d.nombre} — {_color(d.variacion_pct)}{marca_manual}"
    if not tiene:
        etiqueta += "  (sin datos)"
    with st.expander(etiqueta, expanded=(d.codigo == "01" and tiene)):
        if not d.clases:
            st.caption("Esta división todavía no tiene ninguna categoría medida por SEPA.")
            continue
        st.caption(f"Cobertura de la división: {d.cobertura:.0%} del peso medible")

        for f in d.clases:
            if modo_simulacion:
                cols = st.columns([2.6, 0.9, 1.1, 0.9, 1.3, 1.3])
            else:
                cols = st.columns([3, 1, 1.2, 1])
            cols[0].write(f"**{f.codigo}** {f.nombre}")
            cols[1].write(f"{f.peso:.2f}%")
            texto_var = _color(f.variacion_pct) + (" ✏️" if f.es_manual else "")
            cols[2].write(texto_var)
            cols[3].write(_color(f.aporte_pp) if f.aporte_pp is not None else "—")

            if modo_simulacion:
                clave = f.codigo
                actual = st.session_state.overrides.get(clave)
                nuevo = cols[4].number_input(
                    "valor manual %", value=actual if actual is not None else 0.0,
                    step=0.1, format="%.2f", key=f"ov_{clave}_{region_detalle}",
                    label_visibility="collapsed",
                )
                usar = cols[5].checkbox("usar", value=(actual is not None),
                                        key=f"chk_{clave}_{region_detalle}")
                if usar:
                    st.session_state.overrides[clave] = nuevo
                elif clave in st.session_state.overrides:
                    del st.session_state.overrides[clave]

        st.divider()
        medidas = [f for f in d.clases if f.variacion_pct is not None]
        if medidas:
            elegida = st.selectbox(
                "Ver productos de una subcategoría",
                ["(ninguna)"] + [f"{f.codigo} {f.nombre}" for f in medidas],
                key=f"sel_{d.codigo}",
            )
            if elegida != "(ninguna)":
                cod = elegida.split()[0]
                res, drivers = variacion_clase(_con(), cod, D1, H1, D0, H0, region_detalle)
                if res:
                    st.dataframe(
                        [{"Producto": p.nombre_producto,
                          "Variación": f"{p.variacion_pct:+.1f}%",
                          "Peso*": f"{p.peso_proxy_pct:.1f}%",
                          "Aporte pp": f"{p.incidencia_aproximada_pp:+.2f}"}
                         for p in drivers[:30]],
                        use_container_width=True, hide_index=True,
                    )
                    st.caption(
                        "\\* El peso por producto es una **aproximación** (participación en las "
                        "observaciones): INDEC no publica ponderadores por debajo de la "
                        "categoría. Sirve para ver qué producto mueve qué, no como peso oficial."
                    )
                else:
                    st.caption("Sin productos comparables entre los dos períodos elegidos.")

st.divider()
st.caption(
    "**Los dos niveles de peso no son igual de sólidos.** Subcategoría → división usa el "
    "ponderador oficial de INDEC de la región elegida. Producto → subcategoría usa una "
    "aproximación propia. · Las categorías sin datos se excluyen y se renormaliza; nunca "
    "se asumen en cero. · ✏️ indica un valor editado a mano en modo simulación — nunca "
    "modifica los datos guardados."
)
