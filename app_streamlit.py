"""
Aplicacion Streamlit — interfaz de analisis del relevamiento.

    streamlit run app_streamlit.py

IMPORTANTE — ESTE ARCHIVO NO HACE CUENTAS. Todo el calculo vive en
engine/consultas.py, testeado sin necesidad de levantar Streamlit.

INCLUYE MODO SIMULACION en dos niveles:
  - Subcategoria (dentro de una division medida): pisa el dato de, por
    ejemplo, Frutas.
  - Division completa (para las que SEPA no mide nada, como Comunicacion,
    Transporte o Vivienda): permite poner el dato de otra consultora
    directamente, y ver como queda el NIVEL GENERAL combinando lo medido
    con lo manual, siempre con los ponderadores oficiales de INDEC.

Ninguno de los dos modos toca la base de datos — viven solo en la memoria
de esta sesion del navegador. Ver el docstring de engine/consultas.py y el
test que lo garantiza
(tests/test_consultas.py::test_override_no_modifica_la_base_de_datos).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import streamlit as st

from config.canasta import PESO_REGION
from engine.consultas import (
    indice_nacional,
    nivel_general,
    resumen_divisiones,
    variacion_clase,
)
from engine.fechas import acotar_rango, calcular_preset
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
if "overrides_clase" not in st.session_state:
    st.session_state.overrides_clase = {}      # {codigo_clase: valor_pct}
if "overrides_division" not in st.session_state:
    st.session_state.overrides_division = {}   # {codigo_division: valor_pct}

# ---------------------------------------------------------------- controles
with st.sidebar:
    st.header("Período")

    d_max = date.fromisoformat(fmax)
    d_min = date.fromisoformat(fmin)

    preset_sel = st.radio(
        "Comparación rápida",
        ["Última semana vs previa", "Mes actual vs anterior", "Personalizado"],
        index=0,
    )
    clave_preset = {"Última semana vs previa": "semana",
                    "Mes actual vs anterior": "mes",
                    "Personalizado": "personalizado"}[preset_sel]

    d1, h1, d0, h0 = calcular_preset(clave_preset, d_max)
    d1, h1, d0, h0 = acotar_rango(d1, h1, d0, h0, d_min, d_max)

    if d_min == d_max:
        st.info(
            "Con un solo día cargado todavía no hay nada para comparar. "
            "Cargá al menos un día más (lo ideal es una semana) para "
            "empezar a ver variaciones."
        )

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
    region_sel = st.selectbox(
        "Región", opciones, index=0,
        help="'Nacional' combina las 6 regiones según su importancia relativa en el país "
             "(sin modo simulación). Elegí una región específica para ver su nivel general "
             "y poder simular valores manuales.",
    )
    region_detalle = region_sel if region_sel != "Nacional (todas)" else (
        "GBA" if "GBA" in disponibles else (disponibles[0] if disponibles else "GBA")
    )

    st.divider()
    st.header("Modo simulación")
    modo_simulacion = st.toggle(
        "Activar edición manual",
        value=False,
        help="Permite pisar el valor de una subcategoría, o de una división "
             "entera (por ejemplo Comunicación, que SEPA no mide), con un "
             "número propio — el dato de otra consultora. No modifica ningún "
             "dato guardado.",
    )
    n_manuales = len(st.session_state.overrides_clase) + len(st.session_state.overrides_division)
    if n_manuales:
        st.caption(f"⚠️ {n_manuales} valor(es) editado(s) a mano")
        if st.button("Borrar todos los valores manuales"):
            st.session_state.overrides_clase = {}
            st.session_state.overrides_division = {}
            st.rerun()

D1, H1, D0, H0 = (x.isoformat() for x in (d1, h1, d0, h0))

if modo_simulacion:
    st.warning(
        "**Modo simulación activo.** Los valores marcados con ✏️ son manuales, no medidos. "
        "Es un ejercicio de \"¿qué pasaría si…?\" — la base de datos real no se toca. "
        "Desactivá el modo para ver únicamente los datos relevados."
    )

ov_clase = st.session_state.overrides_clase if modo_simulacion else {}
ov_division = st.session_state.overrides_division if modo_simulacion else {}

# La edicion manual solo tiene sentido eligiendo una region especifica: el
# nivel general se calcula por region (con SUS pesos), y "Nacional" es un
# eje distinto (combina regiones, no divisiones). Se corta aca, no solo en
# el texto de aviso, para que nunca aparezca un control de edicion que en
# realidad no se está aplicando a nada — eso confundiría mas que ayudar.
mostrar_edicion = modo_simulacion and region_sel != "Nacional (todas)"
if not mostrar_edicion:
    ov_clase, ov_division = {}, {}

if modo_simulacion and region_sel == "Nacional (todas)":
    st.caption(
        "La simulación no está disponible en la vista Nacional combinada — "
        f"elegí una región (por ejemplo {region_detalle}) en el panel izquierdo."
    )

# ---------------------------------------------------------------- resultado
if region_sel == "Nacional (todas)":
    st.header("Índice Nacional")
    st.caption(
        "Combina las 6 regiones de INDEC según su importancia relativa en el país "
        "(GBA 44,7% · Pampeana 34,2% · Noroeste 6,9% · Cuyo 5,2% · Patagonia 4,6% · "
        "Noreste 4,5%). No admite simulación — es agregado de regiones, no de divisiones."
    )
    nac, cob_pais, por_region = indice_nacional(_con(), D1, H1, D0, H0)
    c1, c2 = st.columns([1, 2])
    c1.metric("Índice nacional", _color(nac))
    c2.caption(f"Cobertura geográfica: {cob_pais:.0%} de la población de referencia del país.")
    if por_region:
        st.dataframe(
            [{"Región": r, "Peso nacional": f"{PESO_REGION[r]*100:.1f}%",
              "Variación": _color(v)} for r, v in sorted(por_region.items())],
            use_container_width=True, hide_index=True,
        )
    st.caption(f"El detalle por división de abajo se muestra para **{region_detalle}**.")

st.header("Nivel general" if region_sel != "Nacional (todas)" else f"Nivel general — {region_detalle}")
st.caption(
    f"Región: **{region_detalle}** · combina las 12 divisiones de INDEC con sus ponderadores "
    "oficiales. Las divisiones sin datos se excluyen y se renormaliza — nunca se asumen en cero."
)

r = nivel_general(_con(), D1, H1, D0, H0, region_detalle,
                  overrides_clase=ov_clase, overrides_division=ov_division)

c1, c2 = st.columns([1, 2])
c1.metric("Nivel general", _color(r.variacion_pct))
c2.caption(
    f"Cobertura: {r.cobertura:.0%} del peso total de la canasta en {region_detalle} "
    "quedó representado (sumando lo medido más lo que hayas puesto a mano)."
)

# ---------------------------------------------------------------- 12 divisiones
st.header("Las 12 divisiones de INDEC")
st.caption(
    "Las que SEPA no releva (Comunicación, Transporte, Vivienda, Prendas, Educación, "
    "Restaurantes) se pueden completar a mano en modo simulación para que participen del "
    "nivel general de arriba."
)

encabezado = st.columns([2.6, 0.9, 1.1, 1.6] if mostrar_edicion else [2.6, 0.9, 1.1, 1.8])
encabezado[0].markdown("**División**")
encabezado[1].markdown("**Peso**")
encabezado[2].markdown("**Variación**")
if mostrar_edicion:
    encabezado[3].markdown("**Poner valor manual**")
else:
    encabezado[3].markdown("**Estado**")

for f in r.divisiones:
    cols = st.columns([2.6, 0.9, 1.1, 1.6] if mostrar_edicion else [2.6, 0.9, 1.1, 1.8])
    cols[0].write(f"**{f.codigo}** {f.nombre}")
    cols[1].write(f"{f.peso:.2f}%")

    texto_var = _color(f.variacion_pct)
    if f.fuente == "manual":
        texto_var += " ✏️"
    elif f.fuente == "medida" and f.cobertura_interna is not None and f.cobertura_interna < 0.5:
        texto_var += " ⚠️"
    cols[2].write(texto_var)

    if not mostrar_edicion:
        etiqueta = {"medida": "Medida", "manual": "Manual",
                   "sin_dato": "Sin fuente"}[f.fuente]
        cols[3].write(etiqueta)
        continue

    actual = st.session_state.overrides_division.get(f.codigo)
    with cols[3]:
        sub = st.columns([2, 1])
        nuevo = sub[0].number_input(
            "valor %", value=actual if actual is not None else 0.0,
            step=0.1, format="%.2f", key=f"ovdiv_{f.codigo}_{region_detalle}",
            label_visibility="collapsed",
        )
        usar = sub[1].checkbox("usar", value=(actual is not None),
                               key=f"chkdiv_{f.codigo}_{region_detalle}")
    if usar:
        st.session_state.overrides_division[f.codigo] = nuevo
    elif f.codigo in st.session_state.overrides_division:
        del st.session_state.overrides_division[f.codigo]

    if f.fuente == "medida" and f.cobertura_interna is not None and f.cobertura_interna < 0.5:
        st.caption(
            f"　⚠️ Esta división se calculó con solo {f.cobertura_interna:.0%} de sus "
            "subcategorías — el número es real, pero se apoya en poca información."
        )

st.divider()

# ---------------------------------------------------------------- detalle por subcategoria
st.header("Detalle dentro de cada división medida")
st.caption("Cada división medida se abre para ver sus subcategorías, y cada subcategoría para "
           "ver los productos. La columna *aporte* suma la variación de la división.")

divs_detalle = resumen_divisiones(_con(), D1, H1, D0, H0, region_detalle, overrides=ov_clase)

for d in divs_detalle:
    if not d.clases:
        continue  # sin ninguna clase medida: ya esta arriba, en la tabla de 12 divisiones
    tiene = d.variacion_pct is not None
    marca_manual = " ✏️" if d.tiene_manuales else ""
    etiqueta = f"{d.codigo} · {d.nombre} — {_color(d.variacion_pct)}{marca_manual}"
    if not tiene:
        etiqueta += "  (sin datos en este período)"

    with st.expander(etiqueta, expanded=(d.codigo == "01" and tiene)):
        st.caption(f"Cobertura de la división: {d.cobertura:.0%} del peso medible por SEPA")

        cabecera = st.columns([3, 1, 1.2, 1, 2] if mostrar_edicion else [3, 1, 1.2, 1])
        cabecera[0].markdown("**Subcategoría**")
        cabecera[1].markdown("**Peso oficial**")
        cabecera[2].markdown("**Variación**")
        cabecera[3].markdown("**Aporte pp**")
        if mostrar_edicion:
            cabecera[4].markdown("**Poner valor manual**")

        for f in d.clases:
            cols = st.columns([3, 1, 1.2, 1, 2] if mostrar_edicion else [3, 1, 1.2, 1])
            cols[0].write(f"**{f.codigo}** {f.nombre}")
            cols[1].write(f"{f.peso:.2f}%")
            texto_var = _color(f.variacion_pct) + (" ✏️" if f.es_manual else "")
            cols[2].write(texto_var)
            cols[3].write(_color(f.aporte_pp) if f.aporte_pp is not None else "—")

            if mostrar_edicion:
                clave = f.codigo
                actual = st.session_state.overrides_clase.get(clave)
                with cols[4]:
                    sub = st.columns([2, 1])
                    nuevo = sub[0].number_input(
                        "valor %", value=actual if actual is not None else 0.0,
                        step=0.1, format="%.2f", key=f"ovcls_{clave}_{region_detalle}",
                        label_visibility="collapsed",
                    )
                    usar = sub[1].checkbox("usar", value=(actual is not None),
                                           key=f"chkcls_{clave}_{region_detalle}")
                if usar:
                    st.session_state.overrides_clase[clave] = nuevo
                elif clave in st.session_state.overrides_clase:
                    del st.session_state.overrides_clase[clave]

        st.markdown("")
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
    "**Los dos niveles de peso no son igual de sólidos.** División → nivel general usa el "
    "ponderador oficial de INDEC. Producto → subcategoría usa una aproximación propia. · Las "
    "categorías sin datos se excluyen y se renormaliza; nunca se asumen en cero. · ✏️ indica un "
    "valor editado a mano — nunca modifica los datos guardados. · ⚠️ indica que el número medido "
    "se apoya en menos de la mitad de las subcategorías de esa división."
)
