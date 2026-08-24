"""
Aplicacion Streamlit — interfaz de analisis del relevamiento.

    streamlit run app_streamlit.py

IMPORTANTE — ESTE ARCHIVO NO HACE CUENTAS. Todo el calculo vive en
engine/consultas.py, testeado sin necesidad de levantar Streamlit.

SIEMPRE MUESTRA EL NIVEL NACIONAL. El sistema calcula por region por
dentro (los ponderadores de INDEC son regionales), pero la interfaz no
expone la region: combina las 6 automaticamente y solo muestra el pais.

"NIVEL GENERAL" SOLO APARECE CUANDO HAY AL MENOS UN VALOR MANUAL DE
DIVISION cargado (para las que SEPA no mide: Comunicacion, Transporte,
Vivienda, Prendas, Educacion, Restaurantes). Sin eso, se muestra
directamente el detalle por categoria/subcategoria/producto.

RENDIMIENTO: la parte cara (leer la base y calcular la variacion de cada
subcategoria medida) se cachea por rango de fechas con `@st.cache_data` y
NO depende de los overrides — asi que tildar una casilla o escribir un
valor en modo simulacion no vuelve a golpear la base, solo hace la
combinacion (instantanea). Ver engine/consultas.py, seccion "CAPA DE
RENDIMIENTO", y el test que garantiza que da lo mismo que el camino
directo: tests/test_consultas.py::test_camino_rapido_da_lo_mismo_que_el_camino_original.

MODO SIMULACION: session_state es POR SESION DE NAVEGADOR — cada persona
que abre el link tiene el suyo, aislado del de cualquier otra. Nunca toca
la base de datos. Ver tests/test_consultas.py::test_override_no_modifica_la_base_de_datos.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import streamlit as st

from engine.consultas import (
    actualizar_override,
    hace_falta_reconstruir,
    nivel_general_desde_divisiones,
    resumen_divisiones_desde_valores,
    valores_medidos_nacional,
    variacion_clase,
)
from engine.fechas import acotar_rango, calcular_preset
from storage.db import conectar

DB_PATH = Path("relevamiento_precios.db")

st.set_page_config(page_title="Relevamiento de Precios", layout="wide")


@st.cache_resource
def _con():
    # `@st.cache_resource` garantiza que el CUERPO de esta funcion se
    # ejecuta como maximo una vez por proceso, incluso con sesiones
    # concurrentes — asi la reconstruccion desde historico/ nunca corre
    # dos veces en paralelo (lo que causaba "database is locked").
    #
    # PERO ESO TIENE UNA CONSECUENCIA IMPORTANTE, que causo un bug real:
    # el chequeo `if not DB_PATH.exists()` solo reconstruye la PRIMERA vez
    # que el proceso arranca. Streamlit Cloud NO reinicia el proceso en
    # cada `git push` — el codigo se actualiza, pero si el proceso de
    # Python ya estaba corriendo, la base vieja sigue en el disco del
    # servidor y esta funcion nunca vuelve a mirar `historico/` de nuevo,
    # sin importar cuantos dias nuevos se hayan subido. Por eso un
    # deploy actualizaba el codigo pero los datos nuevos "no aparecian"
    # hasta que, por casualidad, Streamlit reiniciaba el proceso solo.
    #
    # LA CORRECCION: comparar cuantos dias hay en la base contra cuantos
    # archivos hay en historico/ (ver hace_falta_reconstruir). Si
    # historico/ tiene MAS dias que la base, quiere decir que se subieron
    # datos nuevos despues de que este proceso arranco.
    historico = Path("historico")
    respaldos = sorted(historico.glob("*.csv.gz")) if historico.exists() else []

    dias_en_base = 0
    if DB_PATH.exists():
        con_provisoria = conectar(DB_PATH)
        dias_en_base = con_provisoria.execute(
            "SELECT COUNT(DISTINCT fecha) FROM precios_raw").fetchone()[0]
        con_provisoria.close()

    if hace_falta_reconstruir(DB_PATH.exists(), dias_en_base, len(respaldos)):
        from scripts.reconstruir import reconstruir
        reconstruir()

    return conectar(DB_PATH)


@st.cache_data(ttl=300)
def _rango_disponible():
    if not DB_PATH.exists():
        return None, None, 0
    cur = _con().execute("SELECT MIN(fecha), MAX(fecha), COUNT(DISTINCT fecha) FROM precios_raw")
    return cur.fetchone()


@st.cache_data(ttl=600)
def _valores_medidos_cacheado(_con_obj, D1, H1, D0, H0):
    # El prefijo "_" en `_con_obj` le dice a Streamlit que NO incluya este
    # argumento en la clave de cache (no se puede "hashear" una conexion
    # de base de datos, y tampoco hace falta: si el rango de fechas es el
    # mismo, el resultado es el mismo sin importar la conexion).
    #
    # Esta es la parte CARA (golpea la base, ~19 subcategorias x 6
    # regiones). Como los overrides NO son parametros de esta funcion, se
    # sigue usando el mismo resultado cacheado sin importar cuantas veces
    # se edite un valor manual en modo simulacion.
    return valores_medidos_nacional(_con_obj, D1, H1, D0, H0)


@st.cache_data(ttl=600)
def _productos_de_clase_cacheado(_con_obj, cod, D1, H1, D0, H0):
    return variacion_clase(_con_obj, cod, D1, H1, D0, H0, region=None)


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
if "overrides_clase" not in st.session_state:
    st.session_state.overrides_clase = {}      # {codigo_clase: valor_pct}
if "overrides_division" not in st.session_state:
    st.session_state.overrides_division = {}   # {codigo_division: valor_pct}


def _aplicar_override_division(codigo: str, valor_medido: float | None) -> None:
    """Callback de los widgets de edicion a nivel division (checkbox 'usar'
    + number_input). Se ejecuta ANTES de que Streamlit vuelva a correr el
    script desde el principio — a diferencia de leer el valor del widget y
    guardarlo mas abajo en el mismo bucle donde se renderiza, que quedaba
    grabado DESPUES de que el nivel general ya se habia calculado mas
    arriba en ese mismo pase del script. Ver el comentario junto a donde
    se usa esto, mas abajo, y tests/test_callbacks_edicion.py.

    `valor_medido`: al tildar "usar" por primera vez, el number_input
    TODAVIA NO EXISTE en session_state (este callback corre antes de que
    se dibuje) — sin este parametro, el valor caeria a 0.0 en vez de
    precargar el dato ya medido, que es justo lo que se pidio: que la
    persona tenga que TOCAR el numero solo si de verdad quiere cambiarlo,
    no que arranque siempre en cero."""
    default = valor_medido if valor_medido is not None else 0.0
    actualizar_override(
        st.session_state.overrides_division, codigo,
        st.session_state.get(f"chkdiv_{codigo}", False),
        st.session_state.get(f"ovdiv_{codigo}", default),
    )


def _aplicar_override_clase(codigo: str, valor_medido: float | None) -> None:
    """Igual que `_aplicar_override_division`, para las subcategorias."""
    default = valor_medido if valor_medido is not None else 0.0
    actualizar_override(
        st.session_state.overrides_clase, codigo,
        st.session_state.get(f"chkcls_{codigo}", False),
        st.session_state.get(f"ovcls_{codigo}", default),
    )


# ---------------------------------------------------------------- controles
with st.sidebar:
    if st.button("🔄 Actualizar datos", help="Forzá esto si acabás de subir días nuevos a "
                                             "GitHub y no los ves reflejados abajo."):
        st.cache_resource.clear()
        st.cache_data.clear()
        st.rerun()

    st.header("Período")

    d_max = date.fromisoformat(fmax)
    d_min = date.fromisoformat(fmin)

    preset_sel = st.radio(
        "Comparación rápida",
        ["Última semana vs previa", "Mes actual vs anterior", "Personalizado (ver todo lo cargado)"],
        index=0,
    )
    clave_preset = {"Última semana vs previa": "semana",
                    "Mes actual vs anterior": "mes",
                    "Personalizado (ver todo lo cargado)": "personalizado"}[preset_sel]

    # "personalizado" recibe d_min para arrancar mostrando TODO el período
    # cargado en "período a analizar" — la persona ajusta despues
    # "comparado contra" a lo que le interese.
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
        "**Modo simulación activo.** Tildá \"usar valor manual\" en la fila que quieras editar "
        "para que aparezca el casillero — mientras no la tildes, se sigue mostrando el dato "
        "medido. Los valores con ✏️ son manuales, no medidos: es un ejercicio de "
        "\"¿qué pasaría si…?\", la base de datos real no se toca, y esto solo lo ves vos — "
        "cada persona que entra al link tiene su propia simulación, independiente de la de "
        "cualquier otra."
    )

# ---------------------------------------------------------------- calculo (rapido)
valores = _valores_medidos_cacheado(_con(), D1, H1, D0, H0)
divs_detalle = resumen_divisiones_desde_valores(valores, overrides_clase=ov_clase)
r = nivel_general_desde_divisiones(divs_detalle, overrides_division=ov_division)

# ---------------------------------------------------------------- nivel general
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
        "💡 El **nivel general** aparece acá arriba apenas tildes \"usar valor manual\" en "
        "alguna división que SEPA no mide (por ejemplo Comunicación), más abajo. Mientras "
        "tanto, mirá el detalle por categoría."
    )

# ---------------------------------------------------------------- 12 divisiones
st.header("Las 12 divisiones de INDEC")
st.caption(
    "Nivel nacional. Las que SEPA no releva (Comunicación, Transporte, Vivienda, Prendas, "
    "Educación, Restaurantes) se pueden completar a mano en modo simulación, tildando "
    "\"usar valor manual\"."
)

mostrar_edicion = modo_simulacion

encabezado = st.columns([2.6, 0.9, 1.1, 0.9, 1.4] if mostrar_edicion else [2.6, 0.9, 1.1, 1.8])
encabezado[0].markdown("**División**")
encabezado[1].markdown("**Peso**")
encabezado[2].markdown("**Variación**")
if mostrar_edicion:
    encabezado[3].markdown("**Usar valor manual**")
    encabezado[4].markdown("**Valor (%)**")
else:
    encabezado[3].markdown("**Estado**")

for f in r.divisiones:
    cols = st.columns([2.6, 0.9, 1.1, 0.9, 1.4] if mostrar_edicion else [2.6, 0.9, 1.1, 1.8])
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

    # ORDEN DE LA INTERACCION, a proposito: primero se tilda "usar", y
    # RECIEN AHI aparece el casillero para escribir el numero.
    #
    # POR QUE on_change Y NO "leer el valor y guardarlo aca abajo":
    # Streamlit corre el ARCHIVO ENTERO de arriba a abajo en cada
    # interaccion. "r" (el nivel general) se calcula MAS ARRIBA en este
    # mismo archivo, ANTES de llegar a este bucle. Si el valor que el
    # usuario escribe se guardara recien aca (como estaba antes), quedaria
    # grabado DESPUES de que "r" ya se calculo con el dato viejo — recien
    # se veria reflejado en la SIGUIENTE interaccion. Es exactamente el
    # bug reportado ("tengo que pasar a otro item para que cuente").
    # `on_change` corre el callback ANTES de que el script se re-ejecute
    # desde el principio, asi que el valor ya esta guardado cuando "r" se
    # calcula. Ver tests/test_callbacks_edicion.py.
    # `f.variacion_pct` es el dato medido de ESTA fila antes de aplicar
    # ningun override — sirve como valor de partida al tildar "usar", asi
    # la persona solo tiene que tocar el numero si de verdad quiere
    # cambiarlo. Si la division no tiene dato (fuente == "sin_dato"), no
    # hay nada que precargar y arranca en 0.0 como antes.
    valor_medido = f.variacion_pct if f.fuente != "sin_dato" else None
    actual = st.session_state.overrides_division.get(f.codigo)
    usar = cols[3].checkbox(
        "usar valor manual", value=(actual is not None),
        key=f"chkdiv_{f.codigo}", label_visibility="collapsed",
        on_change=_aplicar_override_division, args=(f.codigo, valor_medido),
    )
    if usar:
        valor_por_defecto = actual if actual is not None else (
            valor_medido if valor_medido is not None else 0.0)
        cols[4].number_input(
            "valor %", value=valor_por_defecto,
            step=0.1, format="%.2f", key=f"ovdiv_{f.codigo}", label_visibility="collapsed",
            on_change=_aplicar_override_division, args=(f.codigo, valor_medido),
        )
        if valor_medido is not None and actual is None:
            cols[4].caption(f"↳ precargado con el dato medido ({valor_medido:+.2f}%)")
    else:
        cols[4].caption("(dato medido)" if f.fuente != "sin_dato" else "(sin dato)")

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

        cabecera = st.columns([3, 1, 1.2, 1, 0.9, 1.2] if mostrar_edicion else [3, 1, 1.2, 1])
        cabecera[0].markdown("**Subcategoría**")
        cabecera[1].markdown("**Peso oficial**")
        cabecera[2].markdown("**Variación**")
        cabecera[3].markdown("**Aporte pp**")
        if mostrar_edicion:
            cabecera[4].markdown("**Usar manual**")
            cabecera[5].markdown("**Valor (%)**")

        for f in d.clases:
            cols = st.columns([3, 1, 1.2, 1, 0.9, 1.2] if mostrar_edicion else [3, 1, 1.2, 1])
            cols[0].write(f"**{f.codigo}** {f.nombre}")
            cols[1].write(f"{f.peso:.2f}%")
            texto_var = _color(f.variacion_pct) + (" ✏️" if f.es_manual else "")
            cols[2].write(texto_var)
            cols[3].write(_color(f.aporte_pp) if f.aporte_pp is not None else "—")

            if mostrar_edicion:
                clave = f.codigo
                # Igual criterio que en las divisiones: si NO es un valor
                # ya manual y hay dato medido, se usa como precarga al
                # tildar "usar" — asi solo hace falta tocar el numero si
                # de verdad se quiere cambiar.
                valor_medido = f.variacion_pct if not f.es_manual else None
                actual = st.session_state.overrides_clase.get(clave)
                usar = cols[4].checkbox(
                    "usar", value=(actual is not None),
                    key=f"chkcls_{clave}", label_visibility="collapsed",
                    on_change=_aplicar_override_clase, args=(clave, valor_medido),
                )
                if usar:
                    valor_por_defecto = actual if actual is not None else (
                        valor_medido if valor_medido is not None else 0.0)
                    cols[5].number_input(
                        "valor %", value=valor_por_defecto,
                        step=0.1, format="%.2f", key=f"ovcls_{clave}", label_visibility="collapsed",
                        on_change=_aplicar_override_clase, args=(clave, valor_medido),
                    )
                    if valor_medido is not None and actual is None:
                        cols[5].caption(f"↳ precargado ({valor_medido:+.2f}%)")

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
                # Pool nacional sin distinguir region (region=None): es
                # una vista exploratoria de "que producto mueve la
                # subcategoria", no el numero oficial de arriba.
                res, drivers = _productos_de_clase_cacheado(_con(), cod, D1, H1, D0, H0)
                if res:
                    st.dataframe(
                        [{"Producto": p.nombre_producto,
                          "Código": p.ean_o_id,
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
                        "mueve qué, no como peso oficial. · La columna **Código** es el "
                        "identificador con el que se cargó el producto (normalmente el código de "
                        "barras) — sirve para verificar contra la fuente original si un valor "
                        "llama la atención."
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
