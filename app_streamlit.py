"""
Aplicacion Streamlit — interfaz de analisis del relevamiento.

    streamlit run app_streamlit.py

IMPORTANTE — ESTE ARCHIVO NO HACE CUENTAS. Todo el calculo vive en
engine/consultas.py, testeado sin necesidad de levantar Streamlit.

SIEMPRE MUESTRA EL NIVEL NACIONAL. El sistema calcula por region por
dentro (porque los ponderadores de INDEC son regionales — ver
engine/consultas.py::peso_nacional_clase), pero la interfaz no expone esa
region: combina las 6 automaticamente y solo muestra el resultado pais.
Es una decision de producto, no una limitacion — a quien usa la app no le
interesa el desglose geografico, le interesa el numero nacional.

"NIVEL GENERAL" SOLO APARECE CUANDO HAY AL MENOS UN VALOR MANUAL CARGADO
para una division que SEPA no mide (Comunicacion, Transporte, Vivienda,
Prendas, Educacion, Restaurantes). Sin eso, no tiene sentido mostrar un
"nivel general" que en realidad seria solo el de las divisiones medidas
maquillado de "general" — mejor mostrar directamente el detalle por
categoria, que es lo que se puede afirmar con SEPA solo.

MODO SIMULACION: permite pisar el valor de una subcategoria o de una
division entera (tipicamente las que SEPA no mide) con un numero propio.
Esto NUNCA toca la base de datos — vive en `st.session_state`, que en
Streamlit es propio de CADA sesion de navegador. Dos personas abriendo el
mismo link tienen cada una su propio `st.session_state`: lo que uno edita
no lo ve ni le afecta al otro, y ninguno de los dos modifica el dato real
que ve un tercero que entre despues. Ver el test que lo garantiza:
tests/test_consultas.py::test_override_no_modifica_la_base_de_datos.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import streamlit as st

from engine.consultas import (
    nivel_general_nacional,
    resumen_divisiones_nacional,
    variacion_clase,
)
from engine.fechas import acotar_rango, calcular_preset
from storage.db import conectar

DB_PATH = Path("relevamiento_precios.db")

st.set_page_config(page_title="Relevamiento de Precios", layout="wide")


@st.cache_resource
def _con():
    # TODA la logica de "si no existe la base, reconstruirla desde el
    # historico" vive DENTRO de esta funcion cacheada, no afuera.
    #
    # POR QUE ESTO IMPORTA: Streamlit Cloud puede atender varias sesiones
    # (personas) al mismo tiempo. Si el chequeo "existe la base?" y la
    # reconstruccion estuvieran afuera de un cache, CADA sesion nueva lo
    # correria por su cuenta — y si dos entran justo en el momento en que
    # la base todavia no existe, las dos arrancan a escribirla a la vez:
    # eso fue exactamente "OperationalError: database is locked" en
    # produccion.
    #
    # `@st.cache_resource` resuelve esto de raiz: Streamlit garantiza que
    # el CUERPO de esta funcion se ejecuta como maximo una vez (incluso con
    # llamadas concurrentes desde sesiones distintas) y todas comparten el
    # mismo resultado.
    if not DB_PATH.exists():
        historico = Path("historico")
        respaldos = sorted(historico.glob("*.csv.gz")) if historico.exists() else []
        if respaldos:
            from scripts.reconstruir import reconstruir
            reconstruir()
    return conectar(DB_PATH)


@st.cache_data(ttl=300)
def _rango_disponible():
    if not DB_PATH.exists():
        return None, None, 0
    cur = _con().execute("SELECT MIN(fecha), MAX(fecha), COUNT(DISTINCT fecha) FROM precios_raw")
    return cur.fetchone()


def _color(v):
    if v is None:
        return "—"
    return f"{v:+.2f}%"


# ---------------------------------------------------------------- arranque
st.title("Relevamiento de Precios")
st.caption("Índice de precios al consumidor · nivel nacional · fuente SEPA · metodología INDEC N°32")

fmin, fmax, ndias = _rango_disponible()
if not fmin:
    st.error(
        "No hay datos todavía. Si estás en tu computadora, corré "
        "`python -m scripts.correr_dia --carpeta datos_sepa/`. Si esto es la app "
        "publicada, todavía no hay ningún día guardado en `historico/`."
    )
    st.stop()

st.info(f"Datos disponibles: **{fmin}** a **{fmax}** · {ndias} días cargados")

# --------------------------------------------------------- estado: overrides
# session_state es POR SESION DE NAVEGADOR — cada persona que abre el link
# tiene el suyo propio. Ver el docstring de arriba del archivo.
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
    st.header("Modo simulación")
    modo_simulacion = st.toggle(
        "Activar edición manual",
        value=False,
        help="Permite pisar el valor de una subcategoría, o de una división "
             "entera (por ejemplo Comunicación, que SEPA no mide), con un "
             "número propio — el dato de otra consultora. No modifica ningún "
             "dato guardado, y es privado de tu sesión: nadie más lo ve.",
    )
    n_manuales = len(st.session_state.overrides_clase) + len(st.session_state.overrides_division)
    if n_manuales:
        st.caption(f"⚠️ {n_manuales} valor(es) editado(s) a mano")
        if st.button("Borrar todos los valores manuales"):
            st.session_state.overrides_clase = {}
            st.session_state.overrides_division = {}
            st.rerun()

D1, H1, D0, H0 = (x.isoformat() for x in (d1, h1, d0, h0))
ov_clase = st.session_state.overrides_clase if modo_simulacion else {}
ov_division = st.session_state.overrides_division if modo_simulacion else {}

if modo_simulacion:
    st.warning(
        "**Modo simulación activo.** Los valores marcados con ✏️ son manuales, no medidos. "
        "Es un ejercicio de \"¿qué pasaría si…?\" — la base de datos real no se toca, y esto "
        "solo lo ves vos: cada persona que entra al link tiene su propia simulación, "
        "independiente de la de cualquier otra. Desactivá el modo para ver únicamente "
        "los datos relevados."
    )

# ---------------------------------------------------------------- nivel general
# Se calcula siempre (barato), pero SOLO SE MUESTRA si hay al menos un
# valor manual de division cargado — ver el docstring del archivo.
r = nivel_general_nacional(_con(), D1, H1, D0, H0,
                           overrides_clase=ov_clase, overrides_division=ov_division)

if ov_division:
    st.header("Nivel general")
    st.caption(
        "Combina las 12 divisiones de INDEC a nivel nacional. Incluye los valores manuales "
        "que cargaste para las divisiones que SEPA no releva."
    )
    c1, c2 = st.columns([1, 2])
    c1.metric("Nivel general", _color(r.variacion_pct))
    c2.caption(
        f"Cobertura: {r.cobertura:.0%} del peso total de la canasta nacional quedó "
        "representado (sumando lo medido más lo que pusiste a mano)."
    )
else:
    st.caption(
        "💡 El **nivel general** aparece acá arriba apenas cargues, en modo simulación, "
        "el dato de alguna división que SEPA no mide (por ejemplo Comunicación). "
        "Mientras tanto, mirá el detalle por categoría de abajo."
    )

# ---------------------------------------------------------------- 12 divisiones
st.header("Las 12 divisiones de INDEC")
st.caption(
    "Nivel nacional. Las que SEPA no releva (Comunicación, Transporte, Vivienda, Prendas, "
    "Educación, Restaurantes) se pueden completar a mano en modo simulación."
)

mostrar_edicion = modo_simulacion

encabezado = st.columns([2.6, 0.9, 1.1, 1.6] if mostrar_edicion else [2.6, 0.9, 1.1, 1.8])
encabezado[0].markdown("**División**")
encabezado[1].markdown("**Peso**")
encabezado[2].markdown("**Variación**")
encabezado[3].markdown("**Poner valor manual**" if mostrar_edicion else "**Estado**")

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
        etiqueta = {"medida": "Medida", "manual": "Manual", "sin_dato": "Sin fuente"}[f.fuente]
        cols[3].write(etiqueta)
        continue

    actual = st.session_state.overrides_division.get(f.codigo)
    with cols[3]:
        sub = st.columns([2, 1])
        nuevo = sub[0].number_input(
            "valor %", value=actual if actual is not None else 0.0,
            step=0.1, format="%.2f", key=f"ovdiv_{f.codigo}",
            label_visibility="collapsed",
        )
        usar = sub[1].checkbox("usar", value=(actual is not None), key=f"chkdiv_{f.codigo}")
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
st.caption("Cada división medida se abre para ver sus subcategorías (nivel nacional), y cada "
           "subcategoría para ver los productos. La columna *aporte* suma la variación de la "
           "división.")

divs_detalle = resumen_divisiones_nacional(_con(), D1, H1, D0, H0, overrides_clase=ov_clase)

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
                        step=0.1, format="%.2f", key=f"ovcls_{clave}",
                        label_visibility="collapsed",
                    )
                    usar = sub[1].checkbox("usar", value=(actual is not None), key=f"chkcls_{clave}")
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
                # Aca SI se pool-ea sin distinguir region (region=None): es
                # una vista exploratoria de "que producto mueve la
                # subcategoria", no el numero oficial de arriba (que ya
                # esta bien ponderado por region). Mismo criterio que el
                # "peso proxy" de siempre: sirve para explicar, no para
                # citar como oficial.
                res, drivers = variacion_clase(_con(), cod, D1, H1, D0, H0, region=None)
                if res:
                    st.dataframe(
                        [{"Producto": p.nombre_producto,
                          "Variación": f"{p.variacion_pct:+.1f}%",
                          "Peso*": f"{p.peso_proxy_pct:.1f}%",
                          "Aporte pp": f"{p.incidencia_aproximada_pp:+.2f}"}
                         for p in drivers[:30]],
                        width="stretch", hide_index=True,
                    )
                    st.caption(
                        "\\* El peso por producto es una **aproximación** (participación en las "
                        "observaciones, de todo el país sin distinguir región): INDEC no publica "
                        "ponderadores por debajo de la categoría. Sirve para ver qué producto "
                        "mueve qué, no como peso oficial."
                    )
                else:
                    st.caption("Sin productos comparables entre los dos períodos elegidos.")

st.divider()
st.caption(
    "**Los dos niveles de peso no son igual de sólidos.** División → nivel general usa el "
    "ponderador oficial de INDEC, combinado a nivel nacional. Producto → subcategoría usa una "
    "aproximación propia. · Las categorías sin datos se excluyen y se renormaliza; nunca se "
    "asumen en cero. · ✏️ indica un valor editado a mano — nunca modifica los datos guardados, "
    "y es privado de tu sesión. · ⚠️ indica que el número medido se apoya en menos de la mitad "
    "de las subcategorías de esa división."
)
