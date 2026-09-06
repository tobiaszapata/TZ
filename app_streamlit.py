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

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import streamlit as st

from config.canasta import Cobertura, clases_de_grupo, grupos_de_division
from engine.consultas import (
    actualizar_override,
    hace_falta_reconstruir,
    nivel_general_desde_divisiones,
    resumen_divisiones_desde_valores,
    valores_medidos_nacional,
    variacion_clase,
    variacion_de_grupo,
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
except sqlite3.OperationalError as exc:
    # "database is locked": otro proceso tenia el archivo abierto en el
    # instante exacto de conectar -- tipicamente Streamlit Cloud
    # reiniciando el contenedor con el proceso viejo todavia terminando de
    # escribir mientras el nuevo ya arranca. NO es corrupcion de datos, y
    # mandar a correr validar_historico() para esto es una perdida de
    # tiempo real (nunca va a encontrar nada, porque el problema no esta
    # en los archivos). Con timeout=30 en storage/db.py::conectar esto ya
    # deberia ser mucho menos frecuente, pero si aun asi pasa, lo unico
    # que hace falta es reintentar en unos segundos.
    st.error(
        f"**{exc}**\n\n"
        "Esto significa que, por un instante, otro proceso tenía la base de datos en uso "
        "— algo pasajero, típicamente cuando Streamlit Cloud reinicia el servidor. "
        "**No es un problema de tus datos ni de historico/.**\n\n"
        "Esperá unos 10-15 segundos y apretá **'🔄 Actualizar datos'** en el panel "
        "izquierdo. Si insiste varias veces seguidas, ahí sí valdría la pena revisar "
        "`Manage app` en Streamlit Cloud por si el servidor quedó en un estado raro."
    )
    st.stop()
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

    modo_multibloque = st.checkbox(
        "Elegir manualmente qué tramos de fechas incluir (en vez de tomar TODOS "
        "los días entre 'desde' y 'hasta')",
        value=False,
        key="modo_multibloque",
        help="Sin tildar: se usa un solo rango 'desde/hasta' con TODOS los días "
             "que haya cargados en el medio (el comportamiento de siempre). "
             "Tildado: armás el período con varios tramos sueltos — útil para "
             "saltar fines de semana u otros días específicos dentro de un mes. "
             "Cada tramo se junta con los demás ANTES de calcular el promedio "
             "(nunca se promedia 'el promedio de cada tramo' por separado — eso "
             "le daría el mismo peso a un tramo de 5 días que a un tramo de 1 "
             "día suelto)."
    )

    if modo_multibloque:
        st.caption(
            "Período a analizar — agregá los tramos que hagan falta (ej. lunes a "
            "viernes de cada semana del mes, saltando los fines de semana). Para meter "
            "un día suelto (ej. el 31 si cae solo en su propia semana), agregá un tramo "
            "más y poné la misma fecha en 'desde' y 'hasta' de ese tramo."
        )
        n_tramos_1 = st.number_input("Cantidad de tramos", min_value=1, max_value=10,
                                     value=st.session_state.get("n_tramos_1", 1),
                                     key="n_tramos_1")
        bloques_1: list[tuple[date, date]] = []
        for i in range(n_tramos_1):
            c1, c2 = st.columns(2)
            # Sugerencia de fecha inicial para un tramo nuevo: el día
            # siguiente al "hasta" del tramo anterior — asi, al agregar
            # un tramo (ej. para meter el ultimo dia suelto del mes),
            # alcanza con ajustar la fecha "hasta" de ese nuevo tramo en
            # vez de tener que cambiar las dos fechas desde cero.
            sugerido_desde = (bloques_1[i-1][1] + timedelta(days=1)) if i > 0 else d1
            sugerido_hasta = sugerido_desde if i > 0 else h1
            b_desde = c1.date_input(f"desde (tramo {i+1})", sugerido_desde, min_value=d_min,
                                    max_value=d_max, key=f"b1_desde_{i}")
            b_hasta = c2.date_input(f"hasta (tramo {i+1})", sugerido_hasta, min_value=d_min,
                                    max_value=d_max, key=f"b1_hasta_{i}")
            bloques_1.append((b_desde, b_hasta))
        d1, h1 = bloques_1[0][0], bloques_1[-1][1]  # solo para el resumen/preset; el cálculo real usa bloques_1

        st.markdown("**Comparado contra** — agregá los tramos equivalentes del período anterior:")
        n_tramos_0 = st.number_input("Cantidad de tramos ", min_value=1, max_value=10,
                                     value=st.session_state.get("n_tramos_0", 1),
                                     key="n_tramos_0")
        bloques_0: list[tuple[date, date]] = []
        for i in range(n_tramos_0):
            c1, c2 = st.columns(2)
            sugerido_desde = (bloques_0[i-1][1] + timedelta(days=1)) if i > 0 else d0
            sugerido_hasta = sugerido_desde if i > 0 else h0
            b_desde = c1.date_input(f"desde (tramo {i+1}, base)", sugerido_desde, min_value=d_min,
                                    max_value=d_max, key=f"b0_desde_{i}")
            b_hasta = c2.date_input(f"hasta (tramo {i+1}, base)", sugerido_hasta, min_value=d_min,
                                    max_value=d_max, key=f"b0_hasta_{i}")
            bloques_0.append((b_desde, b_hasta))
        d0, h0 = bloques_0[0][0], bloques_0[-1][1]
    else:
        bloques_1 = None
        bloques_0 = None
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
    #
    # En modo multibloque, (d1, h1, d0, h0) es solo un RESUMEN (primer y
    # ultimo tramo) — si se incluyera nada mas eso, cambiar un tramo
    # INTERMEDIO (ni el primero ni el ultimo) no dispararia una nueva
    # confirmacion, porque el resumen no habria cambiado. Se incluyen los
    # bloques completos en la combinacion para que cualquier cambio en
    # cualquier tramo si dispare la re-confirmacion.
    if st.session_state.get("modo_multibloque"):
        combinacion_actual = (tuple(bloques_1), tuple(bloques_0))
    else:
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

if st.session_state.get("modo_multibloque"):
    # Modo multiples tramos: D1/D0 son TUPLAS de (desde, hasta) en vez de
    # un solo string — ver engine.consultas.variacion_clase, que ya sabe
    # distinguir ambos casos. Se usa tupla y no lista a proposito: las
    # funciones cacheadas con @st.cache_data (mas abajo) necesitan
    # argumentos "hasheables" para armar su clave de cache, y una lista
    # de tuplas NO es hasheable en Python (una tupla de tuplas si lo es).
    # H1/H0 quedan en None porque no se usan cuando el primer argumento
    # ya es una secuencia de tramos completos.
    D1 = tuple((b[0].isoformat(), b[1].isoformat()) for b in bloques_1)
    H1 = None
    D0 = tuple((b[0].isoformat(), b[1].isoformat()) for b in bloques_0)
    H0 = None
else:
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
    if r.cobertura < 0.999:
        c2.warning(
            f"⚠️ Cobertura: solo el **{r.cobertura:.0%}** del peso total de la canasta está "
            "representado. Falta poner un valor (medido o manual) en al menos una división — "
            "mientras eso falte, este número **no es comparable** con el nivel general que "
            "publica INDEC, porque se calcula sobre menos del 100% del peso oficial. Revisá "
            "la tabla de abajo y completá con \"usar valor manual\" las divisiones que falten."
        )
    else:
        c2.caption(
            f"Cobertura: {r.cobertura:.0%} del peso total de la canasta nacional quedó "
            "representado (sumando lo medido más lo que pusiste a mano) — comparable con "
            "el nivel general que publica INDEC."
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
st.caption("Cada división medida se abre para ver sus grupos, cada grupo para ver sus clases "
           "(nivel nacional), y cada clase para ver los productos reales de SEPA. Los tres "
           "niveles —división, grupo y clase— usan el ponderador oficial de INDEC. La columna "
           "*aporte* suma la variación de la división.")

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

        # Navegación en 3 niveles: división (ya estamos adentro) > grupo >
        # clase. Se agrupan las clases de esta división por su GRUPO
        # padre (el codigo de grupo es el prefijo del codigo de clase,
        # ej. "01.1.1" pertenece al grupo "01.1") para no tener que
        # cambiar la estructura de datos que ya calcula todo bien a
        # nivel clase — es puramente una reorganizacion de presentacion.
        #
        # POR QUE 3 NIVELES Y NO 4 (con subclase): se habia empezado a
        # construir un nivel de subclase, pero INDEC no publica
        # ponderadores oficiales por debajo de clase en ninguna fuente
        # disponible (ni el informe mensual, ni el clasificador COICOP,
        # que solo trae nombres sin pesos) — agregar subclase hubiera
        # exigido inventar o estimar esos pesos sin respaldo. Los 3
        # niveles de aca SI tienen ponderador oficial confirmado
        # (ponderadores_ipc.xls, verificado sin divergencias), y dentro
        # de una clase se va directo a los productos reales de SEPA, sin
        # ningun nivel de clasificacion intermedio adicional.
        grupos_de_esta_division = grupos_de_division(d.codigo)
        clases_por_grupo: dict[str, list] = {}
        for f in d.clases:
            cod_grupo = f.codigo.rsplit(".", 1)[0]  # "01.1.1" -> "01.1"
            clases_por_grupo.setdefault(cod_grupo, []).append(f)

        for grupo_item in grupos_de_esta_division:
            clases_del_grupo = clases_por_grupo.get(grupo_item.codigo, [])
            # TODAS las clases oficiales de este grupo, medidas o no —
            # antes, un grupo sin NINGUNA clase medida (ej. "02.2 Tabaco")
            # directamente no se mostraba, desaparecia sin ningun aviso.
            # Feedback real: "no aclaras que a tabaco no se lo releva".
            # Ahora se muestran todas, marcando las no medidas de forma
            # explicita en vez de ocultarlas.
            clases_oficiales_del_grupo = clases_de_grupo(grupo_item.codigo)
            codigos_medidos = {f.codigo for f in clases_del_grupo}
            clases_no_medidas = [c for c in clases_oficiales_del_grupo
                                 if c.codigo not in codigos_medidos]

            # Caso especial (ej. "02.2 Tabaco"): el grupo tiene peso
            # oficial declarado, pero NINGUNA clase hija cargada en
            # absoluto — ni medida, ni pendiente. Sin esto, ese grupo se
            # saltaba directo y desaparecia de la pantalla sin ningun
            # aviso, igual que el caso original reportado.
            grupo_sin_ninguna_clase_declarada = (
                not clases_del_grupo and not clases_no_medidas and grupo_item.peso("GBA") > 0
            )
            if not clases_del_grupo and not clases_no_medidas and not grupo_sin_ninguna_clase_declarada:
                continue  # grupo realmente sin nada (ni siquiera peso oficial) — no hay nada que mostrar

            if grupo_sin_ninguna_clase_declarada:
                peso_grupo_medido = 0.0
                peso_grupo_total = grupo_item.peso("GBA") * 100
            else:
                peso_grupo_medido = sum(f.peso for f in clases_del_grupo)
                peso_grupo_no_medido = sum(c.peso("GBA") * 100 for c in clases_no_medidas)
                peso_grupo_total = peso_grupo_medido + peso_grupo_no_medido
            medidas_grupo = [f for f in clases_del_grupo if f.variacion_pct is not None]
            if medidas_grupo:
                # Variacion PROPIA del grupo: se calcula con el peso DEL
                # GRUPO como denominador (ver engine.consultas.variacion_de_grupo
                # para el detalle del bug real que esto corrige — antes se
                # reutilizaba f.aporte_pp, que esta en la escala de la
                # DIVISION completa, y eso podia dar un grupo con variacion
                # menor que la division, algo matematicamente imposible).
                var_grupo, _peso_medido_grupo = variacion_de_grupo(medidas_grupo)
                # El "aporte a la division" (columna de la tabla) SI usa la
                # escala de la division completa — f.aporte_pp de cada clase
                # ya esta bien calculado para eso.
                aportes_grupo = [f.aporte_pp for f in medidas_grupo if f.aporte_pp is not None]
            else:
                var_grupo = None
                aportes_grupo = []
            aporte_grupo = sum(aportes_grupo) if medidas_grupo else None

            # El grupo se muestra en la MISMA fila de columnas que las
            # clases y divisiones (en vez del texto libre st.markdown de
            # antes, que quedaba visualmente distinto e inconsistente —
            # feedback real: "cuando queremos visualizar el grupo no
            # queda tan claro"). La diferenciación es solo tipografía:
            # 📁 + negrita + fondo levemente resaltado (container con
            # borde), no una estructura de tabla distinta.
            with st.container(border=True):
                fila_grupo = st.columns([3, 1, 1.2, 1, 0.9, 1.2] if mostrar_edicion else [3, 1, 1.2, 1])
                fila_grupo[0].markdown(f"📁 **{grupo_item.codigo} · {grupo_item.nombre}**")
                fila_grupo[1].markdown(f"**{peso_grupo_total:.2f}%**")
                fila_grupo[2].markdown(f"**{_color(var_grupo)}**")
                fila_grupo[3].markdown(f"**{_color(aporte_grupo) if aporte_grupo is not None else '—'}**")
                if clases_no_medidas:
                    st.caption(
                        f"⚠️ De este grupo, SEPA no releva: "
                        + ", ".join(f"**{c.nombre}** ({c.peso('GBA')*100:.2f}%)" for c in clases_no_medidas)
                        + " — la variación de arriba solo refleja lo medido."
                    )
                elif grupo_sin_ninguna_clase_declarada:
                    st.caption(
                        f"🚫 SEPA no releva ninguna subcategoría de **{grupo_item.nombre}** "
                        f"({peso_grupo_total:.2f}% de peso oficial) — no hay ninguna variación "
                        "disponible para este grupo."
                    )

                cabecera = st.columns([3, 1, 1.2, 1, 0.9, 1.2] if mostrar_edicion else [3, 1, 1.2, 1])
                cabecera[0].markdown("**Clase**")
                cabecera[1].markdown("**Peso oficial**")
                cabecera[2].markdown("**Variación**")
                cabecera[3].markdown("**Aporte pp**")
                if mostrar_edicion:
                    cabecera[4].markdown("**Usar manual**")
                    cabecera[5].markdown("**Valor (%)**")

                for f in clases_del_grupo:
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

                # Clases oficiales que SEPA no releva: se muestran igual,
                # en la misma tabla, con una fila explicita en vez de
                # simplemente omitirlas. Esto es lo que pidio el usuario
                # con el ejemplo de Tabaco dentro de Bebidas alcoholicas.
                for c in clases_no_medidas:
                    cols = st.columns([3, 1, 1.2, 1, 0.9, 1.2] if mostrar_edicion else [3, 1, 1.2, 1])
                    cols[0].write(f"{c.codigo} {c.nombre} 🚫")
                    cols[1].write(f"{c.peso('GBA')*100:.2f}%")
                    cols[2].write("*no relevado por SEPA*")
                    cols[3].write("—")
                    if mostrar_edicion:
                        cols[4].write("")
                        cols[5].write("")
            st.markdown("")

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
                    if res.metodo_imputacion is not None:
                        etiqueta_metodo = {
                            "grupo_superior_parcial": "parcial",
                            "grupo_superior_total": "total",
                        }.get(res.metodo_imputacion, res.metodo_imputacion)
                        st.info(
                            f"ℹ️ Cobertura de productos entre los dos períodos: "
                            f"**{res.cobertura:.0%}** — por debajo del 50%, así que se aplicó "
                            f"imputación **{etiqueta_metodo}** (Metodología N°32, sección 7.1): "
                            "los productos que existían antes y ya no se ven quedan marcados "
                            "abajo como \"(sin dato — imputado)\" en vez de desaparecer en silencio."
                        )
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
