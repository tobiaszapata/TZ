#!/usr/bin/env python3
"""
Genera un SIMULADOR HTML interactivo y autocontenido.

    python -m scripts.generar_simulador --mes 2026-08 --contra 2026-07

Produce `simulador_2026-08.html`: un archivo que se abre con doble clic y
permite jugar con supuestos SIN tocar los datos ni volver a correr nada.
Toda la interactividad corre en el navegador de quien lo abre — no hace
falta servidor, ni Python instalado del otro lado.

QUE PERMITE HACER:
  - Editar la variacion esperada de CADA PRODUCTO y ver como cambia la
    categoria en vivo (ej. "y si la banana en vez de +60% termina en +40%?").
  - Editar directamente una CATEGORIA (override manual), ignorando sus
    productos, para cuando ya tenes una expectativa propia de esa categoria.
  - Aplicar un ESCENARIO a todas las categorias de una vez (congelamiento,
    continuidad de ritmo, patron intra-mensual) y despues ajustar a mano lo
    que quieras.
  - Ver el total de la division recalculado al instante con los
    ponderadores oficiales de INDEC.

--------------------------------------------------------------------------
DOS NIVELES DE AGREGACION, DELIBERADAMENTE DISTINGUIDOS EN LA INTERFAZ:

  producto -> categoria : usa PESOS PROXY (participacion en observaciones).
      INDEC no publica ponderadores por debajo de la categoria, asi que
      este nivel es estimacion nuestra. Se marca en naranja en la UI.

  categoria -> division : usa los PONDERADORES OFICIALES de INDEC.
      Este nivel es dato duro. Se marca en azul en la UI.

Si esa distincion no fuera visible, alguien podria presentar como oficial
un numero que arriba tiene un supuesto propio. Por eso esta en la interfaz
y no solo en la documentacion.
--------------------------------------------------------------------------
"""

from __future__ import annotations

import argparse
import calendar
import json
from datetime import date, datetime
from pathlib import Path

from config.canasta import CANASTA, Cobertura, clases_de_division
from engine.escenarios import (
    escenario_congelamiento,
    escenario_continuidad,
    escenario_patron_intramensual,
)
from engine.index_elemental import media_geometrica
from engine.proyeccion import curva_realizacion_generica
from engine.reporte import calcular_clase_y_productos
from storage.db import (
    conectar,
    nombres_de_productos,
    precios_por_producto_en_mes,
    valores_diarios_de_clase,
)

DB_PATH = Path("relevamiento_precios.db")


def _dias_habiles(anio: int, mes_num: int) -> int:
    _, ultimo = calendar.monthrange(anio, mes_num)
    return sum(1 for d in range(1, ultimo + 1) if date(anio, mes_num, d).weekday() < 5)


def _escenarios_de_clase(con, clase_codigo, mes, contra, dias_totales):
    """Calcula los 3 escenarios principales para una clase. Devuelve dict
    nombre -> variacion, o None si no hay datos suficientes."""
    serie = valores_diarios_de_clase(con, clase_codigo, mes)
    p_base = precios_por_producto_en_mes(con, clase_codigo, contra)
    if not serie or not p_base:
        return None
    nivel_base = media_geometrica([media_geometrica(v) for v in p_base.values()])
    valores = [v for _f, v in serie]
    k = len(valores)

    e_cong = escenario_congelamiento(valores, dias_totales, nivel_base)
    e_cont = escenario_continuidad(valores, dias_totales, nivel_base)
    promedio_parcial = sum(valores) / k
    var_obs = (promedio_parcial / nivel_base - 1) * 100
    fraccion = curva_realizacion_generica(k, dias_totales)
    e_pat = escenario_patron_intramensual(
        var_obs, fraccion, e_cong.variacion_pct, nivel_base, e_cong.promedio_mes_proyectado
    )
    return {
        "congelamiento": round(e_cong.variacion_pct, 3),
        "continuidad": round(e_cont.variacion_pct, 3),
        "patron": round(e_pat.variacion_pct, 3),
        "dias_con_datos": k,
        "dias_totales": dias_totales,
    }


def construir_datos(con, mes: str, contra: str) -> dict:
    anio, mes_num = int(mes[:4]), int(mes[5:7])
    dias_totales = _dias_habiles(anio, mes_num)
    div = CANASTA["01"]

    clases_payload = []
    for clase in clases_de_division("01"):
        if clase.cobertura != Cobertura.MEDIDA_SEPA:
            continue
        p_mes = precios_por_producto_en_mes(con, clase.codigo, mes)
        p_ant = precios_por_producto_en_mes(con, clase.codigo, contra)
        eans = list(set(p_mes) | set(p_ant))
        resultado, drivers = calcular_clase_y_productos(
            p_mes, p_ant, nombres_de_productos(con, eans)
        )
        escenarios = _escenarios_de_clase(con, clase.codigo, mes, contra, dias_totales)

        clases_payload.append({
            "codigo": clase.codigo,
            "nombre": clase.nombre,
            "peso_oficial": round(clase.peso("GBA") * 100, 4),  # % de la canasta GBA
            "tiene_datos": resultado is not None,
            "var_observada": round(resultado.variacion_pct, 3) if resultado else None,
            "escenarios": escenarios,
            "productos": [
                {
                    "nombre": d.nombre_producto,
                    "var": round(d.variacion_pct, 3),
                    "peso_proxy": round(d.peso_proxy_pct, 3),
                }
                for d in drivers
            ],
        })

    return {
        "mes": mes,
        "contra": contra,
        "generado": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "division": {"codigo": div.codigo, "nombre": div.nombre,
                     "peso": round(div.peso("GBA") * 100, 4)},
        "clases": clases_payload,
    }


PLANTILLA = """<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Simulador — Relevamiento de Precios __MES__</title>
<style>
 *{box-sizing:border-box}
 body{font-family:-apple-system,"Segoe UI",Arial,sans-serif;color:#1f2933;max-width:1080px;
   margin:0 auto;padding:22px;background:#f6f7f9;line-height:1.45;}
 h1{color:#1F3B57;margin:0 0 2px;font-size:26px;}
 .sub{color:#C0522D;font-size:15px;} .meta{color:#888;font-size:12.5px;font-style:italic;margin-bottom:18px;}
 .panel{background:white;border-radius:8px;padding:16px 18px;margin-bottom:14px;
   box-shadow:0 1px 4px rgba(0,0,0,.09);}
 .total{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;
   background:#1F3B57;color:white;border-radius:8px;padding:18px 22px;margin-bottom:14px;}
 .total .lbl{font-size:13px;opacity:.85;} .total .big{font-size:40px;font-weight:700;line-height:1;}
 .total .cov{font-size:12px;opacity:.8;margin-top:4px;}
 .btns{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0 4px;}
 button{border:1px solid #ccc;background:#fff;border-radius:6px;padding:7px 13px;cursor:pointer;
   font-size:13px;font-family:inherit;}
 button:hover{background:#eef2f6;border-color:#1F3B57;}
 button.primary{background:#1F3B57;color:white;border-color:#1F3B57;}
 button.primary:hover{background:#2a4f74;}
 .clase{border:1px solid #e3e3e3;border-radius:8px;margin-bottom:10px;background:white;overflow:hidden;}
 .clase-head{display:flex;align-items:center;gap:12px;padding:11px 14px;background:#fbfcfd;
   border-bottom:1px solid #eee;flex-wrap:wrap;}
 .clase-nombre{font-weight:600;color:#1F3B57;flex:1;min-width:190px;font-size:14px;}
 .peso{font-size:11.5px;color:#1F3B57;background:#e8eef4;padding:2px 8px;border-radius:10px;font-weight:600;}
 .valor-clase{font-size:19px;font-weight:700;min-width:88px;text-align:right;font-variant-numeric:tabular-nums;}
 input[type=number]{width:82px;padding:5px 7px;border:1px solid #ccc;border-radius:5px;
   text-align:right;font-family:inherit;font-size:13px;font-variant-numeric:tabular-nums;}
 input[type=number]:focus{outline:2px solid #C0522D;border-color:#C0522D;}
 .modo{font-size:11px;padding:2px 7px;border-radius:9px;font-weight:600;}
 .modo.auto{background:#eaf4ea;color:#2E7D32;} .modo.manual{background:#fdf3e3;color:#B26A00;}
 .prods{padding:6px 14px 12px;background:#fcfcfd;}
 .prod{display:flex;align-items:center;gap:10px;padding:5px 0;border-bottom:1px solid #f0f0f0;
   font-size:13px;flex-wrap:wrap;}
 .prod:last-child{border-bottom:none;}
 .prod-nombre{flex:1;min-width:150px;}
 .prod-peso{font-size:11px;color:#B26A00;background:#fdf3e3;padding:1px 7px;border-radius:9px;
   font-weight:600;min-width:52px;text-align:center;}
 .aporte{font-size:12px;color:#666;min-width:76px;text-align:right;font-variant-numeric:tabular-nums;}
 .toggle{background:none;border:none;color:#1F3B57;cursor:pointer;font-size:12.5px;
   text-decoration:underline;padding:2px 4px;}
 .up{color:#C0392B;} .down{color:#1F7A3D;} .flat{color:#666;}
 .aviso{background:#fdf3e3;border-left:4px solid #B26A00;padding:9px 13px;font-size:12.5px;margin:12px 0;}
 .leyenda{font-size:12px;color:#666;background:#f0f3f6;padding:9px 13px;border-radius:6px;margin-top:12px;}
 .sindatos{color:#999;font-style:italic;font-size:13px;}
 @media print{button{display:none}}
</style></head><body>

<h1>Simulador de escenarios</h1>
<div class="sub">__DIVNOMBRE__ — __MES__ contra __CONTRA__</div>
<div class="meta">Generado el __GENERADO__ · región GBA · fuente SEPA · los cambios que hagas acá
no modifican los datos: es un tablero para probar supuestos.</div>

<div class="total">
  <div>
    <div class="lbl">__DIVNOMBRE__ (división __DIVCOD__)</div>
    <div class="big" id="total">—</div>
    <div class="cov" id="cobertura"></div>
  </div>
  <div style="text-align:right;font-size:12.5px;opacity:.9;max-width:330px;">
    Agregado con <b>ponderadores oficiales de INDEC</b>.<br>
    Se renormaliza sobre las categorías con dato.
  </div>
</div>

<div class="panel">
  <b style="font-size:14px;color:#1F3B57">Aplicar un escenario a todas las categorías</b>
  <div class="btns">
    <button onclick="aplicarEscenario('congelamiento')">Congelamiento (piso)</button>
    <button onclick="aplicarEscenario('patron')">Patrón intra-mensual</button>
    <button onclick="aplicarEscenario('continuidad')">Continuidad de ritmo</button>
    <button class="primary" onclick="resetear()">Volver a lo observado</button>
  </div>
  <div style="font-size:12.5px;color:#666;margin-top:6px;">
    Cada botón carga ese escenario en todas las categorías que tengan datos suficientes.
    Después podés ajustar a mano las que quieras.
  </div>
</div>

<div id="clases"></div>

<div class="leyenda">
  <b>Los dos niveles de agregación no son iguales:</b><br>
  <span class="peso">peso oficial</span> categoría → división usa los <b>ponderadores publicados por
  INDEC</b>. Es dato duro.<br>
  <span class="prod-peso">peso proxy</span> producto → categoría usa una <b>aproximación nuestra</b>
  (participación en la cantidad de observaciones), porque INDEC no publica ponderadores por debajo
  de la categoría. Sirve para ver qué producto mueve qué, no como peso oficial.
</div>

<script>
const DATOS = __DATOS__;
const estado = {};   // codigo -> {modo:'auto'|'manual', override:number, prods:{nombre:var}}

function initEstado(){
  DATOS.clases.forEach(c=>{
    estado[c.codigo] = {modo:'auto', override:null, prods:{}};
    c.productos.forEach(p=>{ estado[c.codigo].prods[p.nombre] = p.var; });
  });
}

function varDeClase(c){
  const st = estado[c.codigo];
  if(st.modo==='manual' && st.override!==null) return st.override;
  if(!c.productos.length) return c.var_observada;
  // producto -> categoria con pesos proxy (suman ~100)
  let num=0, den=0;
  c.productos.forEach(p=>{
    const v = st.prods[p.nombre];
    if(v===null || v===undefined || isNaN(v)) return;
    num += p.peso_proxy * v; den += p.peso_proxy;
  });
  return den>0 ? num/den : null;
}

function cls(v){ if(v===null||v===undefined) return 'flat'; return v>0.05?'up':(v<-0.05?'down':'flat'); }
function fmt(v){ return (v===null||v===undefined||isNaN(v)) ? '—' : (v>=0?'+':'')+v.toFixed(2)+'%'; }

function recalcular(){
  // categoria -> division con pesos OFICIALES, renormalizado por cobertura
  let num=0, pesoConDato=0, pesoTotal=0;
  DATOS.clases.forEach(c=>{
    pesoTotal += c.peso_oficial;
    const v = varDeClase(c);
    if(v!==null && !isNaN(v)){ num += c.peso_oficial*v; pesoConDato += c.peso_oficial; }
    const el = document.getElementById('val-'+c.codigo);
    if(el){ el.textContent = fmt(v); el.className = 'valor-clase '+cls(v); }
    // aportes por producto
    c.productos.forEach((p,i)=>{
      const st = estado[c.codigo];
      const pv = st.prods[p.nombre];
      const ap = document.getElementById('ap-'+c.codigo+'-'+i);
      if(ap){
        const aporte = (p.peso_proxy/100)*pv;
        ap.textContent = (aporte>=0?'+':'')+aporte.toFixed(2)+' pp';
        ap.className = 'aporte '+cls(aporte);
      }
    });
    const m = document.getElementById('modo-'+c.codigo);
    if(m){ const st=estado[c.codigo];
      m.textContent = st.modo==='manual' ? 'manual' : 'desde productos';
      m.className = 'modo '+(st.modo==='manual'?'manual':'auto'); }
  });
  const total = pesoConDato>0 ? num/pesoConDato : null;
  document.getElementById('total').textContent = fmt(total);
  document.getElementById('total').className = 'big';
  const cob = pesoTotal>0 ? (pesoConDato/pesoTotal*100) : 0;
  document.getElementById('cobertura').textContent =
    'Cobertura: '+cob.toFixed(0)+'% del peso de las categorías medidas'+
    (cob<99.5?' (el resto sin dato en este período)':'');
}

function setProd(codigo, nombre, valor){
  const v = parseFloat(valor);
  estado[codigo].prods[nombre] = isNaN(v)?null:v;
  estado[codigo].modo='auto'; estado[codigo].override=null;
  const inp = document.getElementById('ov-'+codigo); if(inp) inp.value='';
  recalcular();
}
function setOverride(codigo, valor){
  const v = parseFloat(valor);
  if(valor===''||isNaN(v)){ estado[codigo].modo='auto'; estado[codigo].override=null; }
  else { estado[codigo].modo='manual'; estado[codigo].override=v; }
  recalcular();
}
function aplicarEscenario(nombre){
  DATOS.clases.forEach(c=>{
    if(c.escenarios && c.escenarios[nombre]!==undefined && c.escenarios[nombre]!==null){
      estado[c.codigo].modo='manual';
      estado[c.codigo].override=c.escenarios[nombre];
      const inp=document.getElementById('ov-'+c.codigo);
      if(inp) inp.value=c.escenarios[nombre].toFixed(2);
    }
  });
  recalcular();
}
function resetear(){
  initEstado();
  DATOS.clases.forEach(c=>{
    const inp=document.getElementById('ov-'+c.codigo); if(inp) inp.value='';
    c.productos.forEach((p,i)=>{
      const pi=document.getElementById('pi-'+c.codigo+'-'+i); if(pi) pi.value=p.var.toFixed(2);
    });
  });
  recalcular();
}
function toggleProds(codigo){
  const d=document.getElementById('prods-'+codigo);
  const b=document.getElementById('tg-'+codigo);
  const oculto = d.style.display==='none';
  d.style.display = oculto?'block':'none';
  b.textContent = oculto?'ocultar productos':'ver / editar productos';
}

function render(){
  const cont=document.getElementById('clases');
  cont.innerHTML = DATOS.clases.map(c=>{
    if(!c.tiene_datos){
      return `<div class="clase"><div class="clase-head">
        <span class="clase-nombre">${c.nombre}</span>
        <span class="peso">${c.peso_oficial.toFixed(2)}% canasta</span>
        <span class="sindatos">sin datos en este período — podés cargar un valor a mano:</span>
        <input type="number" step="0.1" id="ov-${c.codigo}" placeholder="%"
               oninput="setOverride('${c.codigo}', this.value)">
        <span class="valor-clase" id="val-${c.codigo}">—</span>
        <span class="modo auto" id="modo-${c.codigo}">—</span>
      </div></div>`;
    }
    const prods = c.productos.map((p,i)=>`
      <div class="prod">
        <span class="prod-nombre">${p.nombre}</span>
        <span class="prod-peso">${p.peso_proxy.toFixed(1)}%</span>
        <input type="number" step="0.1" id="pi-${c.codigo}-${i}" value="${p.var.toFixed(2)}"
               oninput="setProd('${c.codigo}','${p.nombre.replace(/'/g,"\\\\'")}', this.value)">
        <span class="aporte" id="ap-${c.codigo}-${i}"></span>
      </div>`).join('');
    return `<div class="clase">
      <div class="clase-head">
        <span class="clase-nombre">${c.nombre}</span>
        <span class="peso">${c.peso_oficial.toFixed(2)}% canasta</span>
        <button class="toggle" id="tg-${c.codigo}" onclick="toggleProds('${c.codigo}')">ver / editar productos</button>
        <span style="font-size:12px;color:#666">o fijar categoría:</span>
        <input type="number" step="0.1" id="ov-${c.codigo}" placeholder="auto"
               oninput="setOverride('${c.codigo}', this.value)">
        <span class="valor-clase" id="val-${c.codigo}">—</span>
        <span class="modo auto" id="modo-${c.codigo}">desde productos</span>
      </div>
      <div class="prods" id="prods-${c.codigo}" style="display:none">${prods}
        <div style="font-size:11.5px;color:#888;margin-top:7px">
          Editá la variación esperada de cada producto y la categoría se recalcula sola.
          La columna de la derecha es cuántos puntos aporta cada producto al total de la categoría.
        </div>
      </div>
    </div>`;
  }).join('');
}

initEstado(); render(); recalcular();
</script>
</body></html>"""


def generar(datos: dict) -> str:
    div = datos["division"]
    return (PLANTILLA
            .replace("__DATOS__", json.dumps(datos, ensure_ascii=False))
            .replace("__DIVNOMBRE__", div["nombre"])
            .replace("__DIVCOD__", div["codigo"])
            .replace("__MES__", datos["mes"])
            .replace("__CONTRA__", datos["contra"])
            .replace("__GENERADO__", datos["generado"]))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mes", required=True)
    ap.add_argument("--contra", required=True)
    ap.add_argument("--salida", default=None)
    args = ap.parse_args()

    if not DB_PATH.exists():
        print(f"No encuentro la base {DB_PATH}. Corriste scripts.correr_dia al menos una vez?")
        return

    con = conectar(DB_PATH)
    datos = construir_datos(con, args.mes, args.contra)
    con.close()

    salida = Path(args.salida or f"simulador_{args.mes}.html")
    salida.write_text(generar(datos), encoding="utf-8")
    print(f"Simulador generado: {salida.resolve()}")
    print("Abrilo con doble clic. Todo lo que edites ahi es solo un tablero de supuestos:")
    print("no modifica la base de datos ni los relevamientos.")


if __name__ == "__main__":
    main()
