"""
Aplicacion Streamlit — Relevamiento de Precios.

QUE ES Y POR QUE, FRENTE AL HTML ESTATICO:
El HTML que ya genera el proyecto no necesita servidor, pero hay que
regenerarlo y reenviarlo cada vez que hay datos nuevos. Streamlit resuelve
justamente eso: se publica una URL fija y quien entra ve siempre el ultimo
estado, sin que nadie tenga que mandar nada.

COMO SE PUBLICA (gratis):
1. Subir el repositorio a GitHub.
2. Entrar a share.streamlit.io, conectar la cuenta de GitHub.
3. Elegir el repo y el archivo `streamlit_app/app.py`.
4. Queda una URL publica que se actualiza sola cada vez que el repo cambia
   — y como el workflow diario commitea la base actualizada, el link
   muestra los datos del dia sin intervencion.

CORRER EN LOCAL PARA PROBAR:
    pip install streamlit
    streamlit run streamlit_app/app.py
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import streamlit as st

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from config.canasta import (  # noqa: E402
    CANASTA, Cobertura, REGIONES, clases_de_division, divisiones,
)
from engine.reporte import calcular_clase_y_productos  # noqa: E402
from storage.db import (  # noqa: E402
    conectar, nombres_de_productos, precios_por_producto_en_rango,
)

DB = RAIZ / "relevamiento_precios.db"

st.set_page_config(page_title="Relevamiento de Precios", page_icon="📊", layout="wide")


@st.cache_resource
def _con():
    return conectar(DB)


@st.cache_data(ttl=600)
def rango_disponible():
    cur = _con().execute("SELECT MIN(fecha), MAX(fecha) FROM precios_raw")
    return cur.fetchone()


@st.cache_data(ttl=600)
def variacion_clase(codigo, d1, h1, d0, h0, region):
    con = _con()
    pa = precios_por_producto_en_rango(con, codigo, d1, h1, region)
    pb = precios_por_producto_en_rango(con, codigo, d0, h0, region)
    nombres = nombres_de_productos(con, list(set(pa) | set(pb)))
    return calcular_clase_y_productos(pa, pb, nombres)


st.title("📊 Relevamiento de Precios")
st.caption("Índice de precios por categoría INDEC · fuente SEPA · metodología Nº32")

if not DB.exists():
    st.error("No hay base de datos todavía. Corré `python -m scripts.correr_dia` primero.")
    st.stop()

fmin, fmax = rango_disponible()
if not fmax:
    st.warning("La base está vacía. Cargá al menos un día de SEPA.")
    st.stop()

# ---------------- barra lateral: región y períodos ----------------
with st.sidebar:
    st.header("Configuración")
    region = st.selectbox("Región", REGIONES, index=0,
                          help="Cada región usa sus propios ponderadores oficiales de INDEC")
    st.caption(f"Datos disponibles: {fmin} a {fmax}")

    fmax_d = date.fromisoformat(fmax)
    preset = st.radio("Período", ["Última semana vs previa", "Mes actual vs anterior", "Personalizado"])

    if preset == "Última semana vs previa":
        h1, d1 = fmax_d, fmax_d - timedelta(days=6)
        h0, d0 = d1 - timedelta(days=1), d1 - timedelta(days=7)
    elif preset == "Mes actual vs anterior":
        d1 = fmax_d.replace(day=1); h1 = fmax_d
        h0 = d1 - timedelta(days=1); d0 = h0.replace(day=1)
    else:
        c1, c2 = st.columns(2)
        d1 = c1.date_input("Desde", fmax_d - timedelta(days=6))
        h1 = c2.date_input("Hasta", fmax_d)
        d0 = c1.date_input("Base desde", fmax_d - timedelta(days=13))
        h0 = c2.date_input("Base hasta", fmax_d - timedelta(days=7))

    st.info(f"**Analizando:** {d1} a {h1}\n\n**Contra:** {d0} a {h0}")

D1, H1, D0, H0 = str(d1), str(h1), str(d0), str(h0)

# ---------------- cálculo por división ----------------
resultados = {}
for div in divisiones():
    num = den = 0.0
    detalle = []
    for clase in clases_de_division(div.codigo):
        if clase.cobertura != Cobertura.MEDIDA_SEPA:
            continue
        r, drivers = variacion_clase(clase.codigo, D1, H1, D0, H0, region)
        if r is None:
            detalle.append((clase, None, []))
            continue
        w = clase.peso(region)
        num += w * r.variacion_pct
        den += w
        detalle.append((clase, r, drivers))
    resultados[div.codigo] = (num / den if den else None, den, detalle)

medidas = [(d, resultados[d.codigo]) for d in divisiones()
           if resultados[d.codigo][0] is not None]

# ---------------- encabezado ----------------
if medidas:
    num = sum(d.peso(region) * v for d, (v, _c, _x) in medidas)
    den = sum(d.peso(region) for d, _ in medidas)
    total = num / den
    cobertura = sum(c for _d, (_v, c, _x) in medidas)

    c1, c2, c3 = st.columns(3)
    c1.metric(f"Variación agregada · {region}", f"{total:+.2f}%")
    c2.metric("Cobertura de canasta", f"{cobertura*100:.1f}%",
              help="Porcentaje del peso total de la canasta que estamos midiendo")
    c3.metric("Divisiones con datos", f"{len(medidas)} de 12")
    st.caption("El agregado combina solo las divisiones medidas, renormalizando sus pesos. "
               "No es el nivel general del IPC: es la parte de la canasta que esta fuente permite medir.")
else:
    st.warning("No hay datos comparables en los períodos elegidos para esta región.")
    st.stop()

st.divider()

# ---------------- detalle navegable ----------------
st.subheader("Detalle por división")
for div in divisiones():
    valor, cob, detalle = resultados[div.codigo]
    if valor is None:
        etiqueta = {"pendiente": "⏳ pendiente de fuente",
                    "no_scrapeable": "🚫 no relevable online"}.get(div.cobertura.value, "sin datos")
        st.write(f"**{div.codigo} · {div.nombre}** — peso {div.peso(region)*100:.1f}% — {etiqueta}")
        continue

    with st.expander(f"**{div.codigo} · {div.nombre}** — {valor:+.2f}% "
                     f"(peso {div.peso(region)*100:.1f}%)", expanded=(div.codigo == "01")):
        filas = []
        for clase, r, _drivers in detalle:
            filas.append({
                "Código": clase.codigo,
                "Subcategoría": clase.nombre,
                "Peso %": round(clase.peso(region) * 100, 2),
                "Variación %": round(r.variacion_pct, 2) if r else None,
                "Productos": r.n_productos_comparados if r else 0,
            })
        st.dataframe(filas, use_container_width=True, hide_index=True)

        opciones = {f"{c.codigo} {c.nombre}": (c, dr)
                    for c, r, dr in detalle if r is not None}
        if opciones:
            elegida = st.selectbox("Ver productos de:", list(opciones),
                                   key=f"sel_{div.codigo}")
            _clase, drivers = opciones[elegida]
            st.dataframe([{
                "Producto": d.nombre_producto,
                "Variación %": round(d.variacion_pct, 2),
                "Peso proxy %": round(d.peso_proxy_pct, 2),
                "Aporte pp": round(d.incidencia_aproximada_pp, 3),
            } for d in drivers[:25]], use_container_width=True, hide_index=True)
            st.caption("El peso por producto es una aproximación (participación en observaciones): "
                       "INDEC no publica ponderadores por debajo de la categoría.")
