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
from engine.fechas import acotar_rango, calcular_preset, hace_falta_confirmar
from storage.db import conectar

# ANCLADAS A LA UBICACION DE ESTE ARCHIVO, no al directorio de trabajo del
# proceso. Antes eran rutas relativas (Path("relevamiento_precios.db"),
# Path("historico")), que dependen de DESDE DONDE se ejecuta el proceso.
# En la computadora del usuario eso siempre funciona porque `streamlit run`
# se corre parado en la carpeta del proyecto — pero Streamlit Cloud puede,
# en ciertas condiciones (un redeploy, un reinicio del contenedor), arrancar
# el proceso con el directorio de trabajo apuntando a otro lado. Cuando eso
# pasa, `Path("historico")` apunta a una carpeta vacia o inexistente aunque
# el repositorio SI tenga los archivos — y el sintoma es exactamente
# "No hay datos todavia" pese a que todo este bien subido a GitHub. Anclar
# al archivo (`Path(__file__).parent`) elimina esa dependencia por completo.
RAIZ = Path(__file__).resolve().parent
DB_PATH = RAIZ / "relevamiento_precios.db"
CARPETA_HISTORICO = RAIZ / "historico"

st.set_page_config(page_title="Relevamiento de Precios", layout="wide")


@st.cache_resource
def _con():
    # `@st.cache_resource` garantiza que el CUERPO de esta funcion se
    # ejecuta como maximo una vez por proceso, incluso con sesiones
    # concurrentes — asi la reconstruccion desde historico/ nunca corre
    # dos veces en paralelo (lo que causaba "database is locked").
    #
    # REGLA IMPORTANTE, causante de un bug real: esta funcion NUNCA debe
    # llamar a st.error/st.warning/st.stop() DENTRO DE SI MISMA. Una
    # version anterior lo hacia (para avisar si la reconstruccion
    # fallaba), y el resultado fue que Streamlit podia cachear ese estado
    # de "fallo" como si fuera el resultado normal de la funcion — la
    # proxima vez que se llamaba _con(), en vez de reintentar, devolvia
    # directamente ese estado congelado. El sintoma era indistinguible de
    # "nunca hubo datos": siempre el mismo mensaje, sin importar cuantas
    # veces se reintentara. La correccion: esta funcion SOLO conecta y
    # reconstruye: si algo falla, deja que la excepcion se propague hacia
    # afuera sin atraparla aca. Quien la llama (mas abajo, FUERA de
    # cualquier cache) es responsable de mostrar el error.
    #
    # PERO ESO TIENE OTRA CONSECUENCIA IMPORTANTE, que causo un bug real
    # distinto: el chequeo `if not DB_PATH.exists()` solo reconstruye la
    # PRIMERA vez que el proceso arranca. Streamlit Cloud NO reinicia el
    # proceso en cada `git push` — el codigo se actualiza, pero si el
    # proceso de Python ya estaba corriendo, la base vieja sigue en el
    # disco del servidor y esta funcion nunca vuelve a mirar `historico/`
    # de nuevo, sin importar cuantos dias nuevos se hayan subido.
    #
    # LA CORRECCION: comparar cuantos dias hay en la base contra cuantos
    # archivos hay en historico/ (ver hace_falta_reconstruir). Si
    # historico/ tiene MAS dias que la base, quiere decir que se subieron
    # datos nuevos despues de que este proceso arranco.
    historico = CARPETA_HISTORICO
    respaldos = sorted(historico.glob("*.csv.gz")) if historico.exists() else []

    dias_en_base = 0
    if DB_PATH.exists():
        con_provisoria = conectar(DB_PATH)
        dias_en_base = con_provisoria.execute(
            "SELECT COUNT(DISTINCT fecha) FROM precios_raw").fetchone()[0]
        con_provisoria.close()

    if hace_falta_reconstruir(DB_PATH.exists(), dias_en_base, len(respaldos)):
        with st.spinner(
            f"Preparando los datos ({len(respaldos)} días acumulados)... "
            "esto puede tardar un momento la primera vez que se abre la app "
            "después de un rato de inactividad. No hace falta hacer nada, "
            "solo esperar."
        ):
            from scripts.reconstruir import reconstruir
            reconstruir()  # si falla, la excepcion se propaga tal cual — no se atrapa aca

    return conectar(DB_PATH)


@st.cache_data(ttl=300)
def _rango_disponible():
    # BUG REAL QUE ESTO CORRIGE: esta funcion tenia un atajo
    # `if not DB_PATH.exists(): return None, None, 0` ANTES de llamar a
    # _con(). Eso es exactamente incorrecto en un arranque en frio real
    # (Streamlit Cloud nunca tiene la base local hasta que _con() la
    # reconstruye desde historico/): la funcion devolvia "no hay datos"
    # de inmediato, sin darle a _con() la oportunidad de reconstruir nada.
    # El sintoma era indistinguible de "nunca se cargo nada", aunque
    # historico/ tuviera 22 dias bien subidos a GitHub.
    #
    # La correccion es simple: llamar a _con() SIEMPRE primero (es la unica
    # funcion que sabe si hace falta reconstruir y lo hace si corresponde),
    # y recien despues consultar la base que ella devuelve.
    con = _con()
    cur = con.execute("SELECT MIN(fecha), MAX(fecha), COUNT(DISTINCT fecha) FROM precios_raw")
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

# El boton de refresco se dibuja SIEMPRE, ANTES que cualquier posible
# st.stop() por error — asi, si la app queda mostrando "no hay datos" o un
# error, la persona tiene una forma de reintentar sin depender de
# encontrar "Manage app -> Reboot app" en Streamlit Cloud.
with st.sidebar:
    if st.button("🔄 Actualizar datos", help="Forzá esto si acabás de subir días nuevos a "
                                             "GitHub y no los ves reflejados abajo, o si la "
                                             "app está mostrando un error viejo."):
        st.cache_resource.clear()
        st.cache_data.clear()
        st.session_state.pop("fechas_confirmadas", None)
        st.rerun()

# La llamada a _con()/_rango_disponible() se hace ACA, en el cuerpo
# principal del script — NUNCA dentro de una funcion decorada con
# @st.cache_resource o @st.cache_data. Esto es a proposito: el cuerpo
# principal se re-ejecuta COMPLETO en cada interaccion (cada rerun), asi
# que un try/except puesto aca SIEMPRE se vuelve a evaluar — nunca queda
# "pegado" mostrando un resultado viejo cacheado. Ver el comentario largo
# dentro de _con() (mas arriba) para el detalle del bug que esto corrige:
# un error dentro de una funcion cacheada podia quedar congelado, y ni
# "Clear cache" ni "Rerun" lo destrababan de forma confiable — porque el
# boton que los limpia ni siquiera se llegaba a dibujar (estaba despues
# del st.stop() del error).
try:
    fmin, fmax, ndias = _rango_disponible()
except Exception as exc:
    st.error(
        f"La reconstrucción de la base falló con un error real (esto NO significa "
        f"que falten datos): **{type(exc).__name__}: {exc}**\n\n"
        "Esto normalmente indica que algún archivo de `historico/` está corrupto, vacío, "
        "o tiene un formato distinto al esperado. Para encontrar cuál, corré en tu "
        "computadora (no en Streamlit):\n\n"
        "`python -m scripts.validar_historico`\n\n"
        "Si ya lo corregiste, apretá **'🔄 Actualizar datos'** en el panel izquierdo."
    )
    st.stop()

if not fmin:
    st.error(
        "No hay datos todavía. Si estás en tu computadora, corré "
        "`python -m scripts.correr_dia --carpeta datos_sepa/`. Si esto es la app "
        "publicada, todavía no hay ningún día guardado en `historico/` — o hace falta "
        "apretar **'🔄 Actualizar datos'** en el panel izquierdo, arriba de todo."
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
    st.header("Período")

    d_max = date.fromisoformat(fmax)
    d_min = date.fromisoformat(fmin)

    preset_sel = st.radio(
        "Comparación rápida",
        ["Última semana vs previa", "Mes actual vs anterior", "Personalizado (ver todo lo cargado)"],
        index=0,
        key="preset_sel",
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

    st.markdown("**Período a analizar** _(el más reciente, para ver cómo viene la inflación ahora)_")
    d1 = st.date_input("desde", d1, min_value=d_min, max_value=d_max, key="d1")
    h1 = st.date_input("hasta", h1, min_value=d_min, max_value=d_max, key="h1")
    st.markdown("**Comparado contra**")
    d0 = st.date_input("desde ", d0, min_value=d_min, max_value=d_max, key="d0")
    h0 = st.date_input("hasta ", h0, min_value=d_min, max_value=d_max, key="h0")

    # ------------------------------------------------------------
    # PASO DE CONFIRMACION, a pedido: en vez de calcular el resultado
    # apenas la app arranca (con el preset activo por defecto, que puede
    # no ser lo que la persona queria mirar en ese momento), se muestran
    # las fechas propuestas y NO SE CALCULA NADA hasta que se confirme.
    # Solo hace falta confirmar una vez por sesion; despues, cambiar el
    # preset o las fechas vuelve a pedir confirmacion (se detecta
    # guardando cual fue la ultima combinacion ya confirmada).
    combinacion_actual = (d1, h1, d0, h0)
    ya_confirmada = not hace_falta_confirmar(
        combinacion_actual, st.session_state.get("fechas_confirmadas")
    )

    if not ya_confirmada:
        st.warning("Revisá las fechas de arriba y confirmá para calcular.")
        if st.button("✅ Calcular con estas fechas", type="primary"):
            st.session_state.fechas_confirmadas = combinacion_actual
            st.rerun()
        st.stop()
    else:
        if st.button("↺ Elegir otro período"):
            st.session_state.pop("fechas_confirmadas", None)
            st.rerun()
    # ------------------------------------------------------------

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
                    total_productos = len(drivers)
                    ver_todos = st.checkbox(
                        f"Ver los {total_productos} productos (por defecto se muestran los "
                        "30 que más explican la variación)",
                        key=f"vertodos_{cod}",
                    )
                    a_mostrar = drivers if ver_todos else drivers[:30]
                    if not ver_todos and total_productos > 30:
                        st.caption(
                            f"Mostrando 30 de {total_productos} productos, ordenados por cuánto "
                            "explican la variación de la categoría. El cálculo de arriba "
                            "(la variación de la categoría en sí) ya incluye a los "
                            f"{total_productos} — este límite es solo para que la tabla sea "
                            "legible, tildá la casilla para ver la lista completa."
                        )
                    st.dataframe(
                        [{"Producto": p.nombre_producto,
                          "Código": p.ean_o_id,
                          "Variación": f"{p.variacion_pct:+.1f}%",
                          "Peso*": f"{p.peso_proxy_pct:.1f}%",
                          "Aporte pp": f"{p.incidencia_aproximada_pp:+.2f}"}
                         for p in a_mostrar],
                        width="stretch", hide_index=True,
                    )
                    st.caption(
                        "\\* El peso por producto es una **aproximación** (participación en las "
                        "observaciones, de todo el país sin distinguir región): INDEC no publica "
                        "ponderadores por debajo de la categoría. Sirve para ver qué producto "
                        "mueve qué, no como peso oficial. Se calcula sobre el TOTAL de productos "
                        "de la categoría, no solo sobre los que se muestran en pantalla. · La "
                        "columna **Código** es el "
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
