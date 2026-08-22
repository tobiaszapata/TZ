APP_HTML = r"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Relevamiento de Precios — Aplicación</title>
<style>
*{box-sizing:border-box}
body{font-family:-apple-system,"Segoe UI",Arial,sans-serif;color:#1f2933;max-width:1120px;
 margin:0 auto;padding:20px;background:#f7f8fa;line-height:1.45}
h1{color:#1F3B57;margin:0 0 2px;font-size:25px}
.sub{color:#C0522D;font-size:14px}
.meta{color:#8a8a8a;font-size:12px;font-style:italic;margin-bottom:16px}
.card{background:#fff;border-radius:8px;padding:14px 16px;margin:12px 0;box-shadow:0 1px 3px rgba(0,0,0,.09)}
.card h2{margin:0 0 10px;font-size:15px;color:#1F3B57;text-transform:uppercase;letter-spacing:.4px}
label{font-size:12px;color:#555;display:block;margin-bottom:2px}
input[type=date]{padding:5px 7px;border:1px solid #ccd4dd;border-radius:5px;font-size:13px}
.rangos{display:flex;gap:22px;flex-wrap:wrap;align-items:flex-end}
.rango{display:flex;gap:8px;align-items:flex-end}
.presets button{background:#eef1f5;border:1px solid #ccd4dd;color:#1F3B57;padding:5px 10px;
 border-radius:5px;cursor:pointer;font-size:12px;margin:3px 4px 0 0}
.presets button:hover{background:#dfe5ec}
button.esc{background:#eef1f5;border:1.5px solid #ccd4dd;color:#1F3B57;padding:6px 12px;
 border-radius:6px;cursor:pointer;margin:0 5px 4px 0;font-size:12.5px;font-weight:600}
button.esc.on{background:#1F3B57;color:#fff;border-color:#1F3B57}
button.act{background:#1F3B57;color:#fff;border:none;padding:7px 14px;border-radius:6px;
 cursor:pointer;font-size:13px;font-weight:600}
button.ghost{background:#fff;border:1.5px solid #C0522D;color:#C0522D;padding:6px 12px;
 border-radius:6px;cursor:pointer;font-size:12.5px}
table{border-collapse:collapse;width:100%;font-size:13px}
th{background:#1F3B57;color:#fff;text-align:left;padding:7px 9px;font-size:11.5px;font-weight:600}
td{border-bottom:1px solid #eee;padding:5px 9px}
.num{text-align:right;font-variant-numeric:tabular-nums}
tr.divrow{cursor:pointer} tr.divrow:hover{background:#f3f6f9}
tr.clsrow{background:#fbfcfd;cursor:pointer} tr.clsrow:hover{background:#eef3f8}
tr.prodrow{background:#fff}
.ind{display:inline-block;width:14px;color:#8a9aa8}
input.v{width:76px;text-align:right;padding:3px 5px;border:1px solid #ccd4dd;border-radius:4px;
 font-size:12.5px;font-variant-numeric:tabular-nums}
input.v.edit{border-color:#C0522D;background:#fff6f2;font-weight:600}
.up{color:#C0392B}.down{color:#1F7A3D}.flat{color:#666}
.big{font-size:30px;font-weight:700}
.badge{display:inline-block;padding:1px 7px;border-radius:9px;font-size:10.5px;font-weight:600}
.med{color:#2E7D32;background:#eaf4ea}.pend{color:#B26A00;background:#fdf3e3}
.nosc{color:#8a8a8a;background:#f0f0f0}
.nota{background:#f2eee8;border-left:4px solid #C0522D;padding:8px 12px;font-size:12px;margin:10px 0}
.warn{background:#fdf3e3;border-left:4px solid #B26A00;padding:8px 12px;font-size:12.5px;margin:10px 0}
.hint{font-size:11.5px;color:#8a8a8a}
</style></head><body>

<h1>Relevamiento de Precios</h1>
<div class="sub">Aplicación de análisis — elegí el período, navegá y simulá</div>
<div class="meta" id="meta"></div>

<div class="card">
  <h2>1 · Período a comparar</h2>
  <div class="rangos">
    <div>
      <label>Período a analizar</label>
      <div class="rango">
        <div><span class="hint">desde</span><br><input type="date" id="d1"></div>
        <div><span class="hint">hasta</span><br><input type="date" id="h1"></div>
      </div>
    </div>
    <div>
      <label>Comparado contra</label>
      <div class="rango">
        <div><span class="hint">desde</span><br><input type="date" id="d0"></div>
        <div><span class="hint">hasta</span><br><input type="date" id="h0"></div>
      </div>
    </div>
    <button class="act" onclick="render()">Actualizar</button>
  </div>
  <div class="presets" id="presets"></div>
  <div class="hint" id="disponible" style="margin-top:6px"></div>
</div>

<div class="card">
  <h2>2 · Escenario aplicado al período analizado</h2>
  <div id="botonesEsc"></div>
  <div class="hint" id="descEsc"></div>
</div>

<div class="card">
  <h2>3 · Resultado</h2>
  <div class="big" id="total">—</div>
  <div class="hint" id="cobertura"></div>
  <div style="margin-top:9px">
    <button class="ghost" onclick="resetOverrides()">Borrar valores editados</button>
    <button class="ghost" onclick="exportarCSV()">Descargar CSV (se abre en Excel)</button>
  </div>
</div>

<div class="card">
  <h2>4 · Detalle — clic para abrir cada nivel</h2>
  <div class="hint" style="margin-bottom:6px">
    División → subcategoría → producto. Podés escribir un valor en cualquier nivel para simular:
    si fijás una subcategoría, sus productos quedan informativos; si editás productos, la
    subcategoría se recalcula sola.
  </div>
  <table id="tabla"></table>
</div>

<div class="nota">
<b>Los dos niveles de peso no son igual de sólidos.</b> Subcategoría → división usa el
<b>ponderador oficial de INDEC</b>. Producto → subcategoría usa una <b>aproximación</b>
(participación en observaciones), porque INDEC no publica pesos por debajo de la categoría.
Sirve para ver qué producto mueve qué, no como peso oficial.
<br><br>
<b>Escenarios.</b> "Observado" es el dato medido. Los demás proyectan el cierre del mes del
período analizado bajo distintos supuestos; sólo "congelamiento" es aritmética sin modelo.
Todo lo que edites acá es un tablero de supuestos: no modifica los datos.
</div>

<script>
const DATA = __DATOS__;

/* ---------- utilidades de cálculo (espejo de engine/ en Python) ---------- */
function mediaGeo(xs){
  if(!xs.length) return null;
  let s=0; for(const x of xs){ if(x<=0) return null; s+=Math.log(x); }
  return Math.exp(s/xs.length);
}
function diasEnVentana(serie, desde, hasta){
  const out=[];
  for(const f in serie){ if(f>=desde && f<=hasta) out.push(serie[f]); }
  return out;
}
/* variación de un producto entre dos ventanas */
function varProducto(p, d1,h1, d0,h0){
  const a=mediaGeo(diasEnVentana(p.serie,d1,h1));
  const b=mediaGeo(diasEnVentana(p.serie,d0,h0));
  if(a===null||b===null) return null;
  return {v:(a/b-1)*100, nObs:diasEnVentana(p.serie,d1,h1).length};
}
/* tasa diaria geométrica por ajuste log-lineal (igual que escenarios.py) */
function tasaDiaria(vals){
  const n=vals.length; if(n<2) return 0;
  const ys=vals.map(Math.log); const xs=vals.map((_,i)=>i);
  const xm=xs.reduce((a,b)=>a+b,0)/n, ym=ys.reduce((a,b)=>a+b,0)/n;
  let num=0,den=0;
  for(let i=0;i<n;i++){ num+=(xs[i]-xm)*(ys[i]-ym); den+=(xs[i]-xm)**2; }
  return den? Math.exp(num/den)-1 : 0;
}
function diasHabilesMes(anio,mes){
  const ult=new Date(anio,mes,0).getDate(); let c=0;
  for(let d=1;d<=ult;d++){ const w=new Date(anio,mes-1,d).getDay(); if(w>=1&&w<=5) c++; }
  return c;
}
/* proyección de cierre de mes para un producto, sobre la ventana analizada */
function proyectarProducto(p, d1,h1, d0,h0, escenario){
  const base=varProducto(p,d1,h1,d0,h0);
  if(base===null) return null;
  if(escenario==="observado") return base.v;

  const dias=diasEnVentana(p.serie,d1,h1);
  const nivelBase=mediaGeo(diasEnVentana(p.serie,d0,h0));
  if(!dias.length||nivelBase===null) return base.v;

  const anio=+h1.slice(0,4), mes=+h1.slice(5,7);
  const D=diasHabilesMes(anio,mes), k=dias.length;
  if(k>=D) return base.v;

  const prom=a=>a.reduce((x,y)=>x+y,0)/a.length;
  const ultimo=dias[dias.length-1];
  let fut=[];
  if(escenario==="congelamiento"){
    fut=Array(D-k).fill(ultimo);
  } else if(escenario==="continuidad"){
    const g=tasaDiaria(dias);
    for(let i=1;i<=D-k;i++) fut.push(ultimo*Math.pow(1+g,i));
  } else if(escenario==="mixto"){
    const g=tasaDiaria(dias); const corte=Math.max(k+1,Math.floor(D/2));
    let v=ultimo;
    for(let d=k+1;d<=D;d++){ if(d<=corte) v=v*(1+g); fut.push(v); }
  } else if(escenario==="patron"){
    const t=k/D, fr=Math.pow(t,0.85);
    const congel=(prom(dias)*k+ultimo*(D-k))/D;
    const pisoV=(congel/nivelBase-1)*100;
    if(fr<0.20) return pisoV;
    return Math.max(base.v/fr, pisoV);
  }
  const promMes=(dias.reduce((a,b)=>a+b,0)+fut.reduce((a,b)=>a+b,0))/D;
  return (promMes/nivelBase-1)*100;
}

/* ---------- estado ---------- */
let escenario="observado";
const ovProd={}, ovClase={};
const abiertos={div:{}, cls:{}};

const ESC={
 observado:["Observado","Lo efectivamente medido en el período elegido. No proyecta nada."],
 congelamiento:["Congelamiento","Precios quedan como el último día. Piso: aritmética pura."],
 mixto:["Congela a mitad de mes","Sigue el ritmo hasta mitad de mes y después se frena."],
 patron:["Patrón intra-mensual","La categoría completa el mes como suele hacerlo (curva preliminar)."],
 continuidad:["Continuidad de ritmo","El ritmo diario del período se mantiene hasta fin de mes."]
};

const fmt=v=>(v===null||isNaN(v))?"—":((v>=0?"+":"")+v.toFixed(2)+"%");
const cl=v=>v===null?"flat":(v>0.05?"up":(v<-0.05?"down":"flat"));
const g=id=>document.getElementById(id);

/* ---------- cálculo por nivel ---------- */
function valoresProducto(c){
  const d1=g("d1").value,h1=g("h1").value,d0=g("d0").value,h0=g("h0").value;
  return c.productos.map(p=>{
    const base=varProducto(p,d1,h1,d0,h0);
    if(base===null) return {p,v:null,nObs:0};
    const k=c.codigo+"|"+p.id;
    const v=(k in ovProd)?ovProd[k]:proyectarProducto(p,d1,h1,d0,h0,escenario);
    return {p,v,nObs:base.nObs};
  });
}
function claseCalculada(c){
  const vs=valoresProducto(c).filter(x=>x.v!==null);
  if(!vs.length) return null;
  let num=0,den=0;
  for(const x of vs){ num+=x.nObs*x.v; den+=x.nObs; }
  return den?num/den:null;
}
function valorClase(c){ return (c.codigo in ovClase)?ovClase[c.codigo]:claseCalculada(c); }
function valorDivision(cod){
  let num=0,den=0;
  for(const c of DATA.clases.filter(c=>c.division===cod)){
    const v=valorClase(c); if(v===null) continue;
    num+=c.peso_oficial*v; den+=c.peso_oficial;
  }
  return {v:den?num/den:null, cub:den};
}

/* ---------- interacción ---------- */
function setEsc(k){ escenario=k; render(); }
function toggleDiv(c){ abiertos.div[c]=!abiertos.div[c]; render(); }
function toggleCls(c){ abiertos.cls[c]=!abiertos.cls[c]; render(); }
function resetOverrides(){
  for(const k in ovProd) delete ovProd[k];
  for(const k in ovClase) delete ovClase[k];
  render();
}
/* Redibuja en el proximo ciclo del navegador en vez de inmediatamente.
   Motivo: el evento `change` de un input se dispara junto con el `blur`;
   si reemplazamos la tabla entera en ese instante, el navegador se queda
   sin el nodo que estaba por procesar y tira
   "The node to be removed is no longer a child of this node".
   Diferir un tick deja que el navegador termine con el input primero. */
function renderDiferido(){ setTimeout(render, 0); }
function editP(cod,id,val){
  const k=cod+"|"+id;
  if(val===""||isNaN(parseFloat(val))) delete ovProd[k]; else ovProd[k]=parseFloat(val);
  renderDiferido();
}
function editC(cod,val){
  if(val===""||isNaN(parseFloat(val))) delete ovClase[cod]; else ovClase[cod]=parseFloat(val);
  renderDiferido();
}
function preset(tipo){
  const max=DATA.fecha_max, min=DATA.fecha_min;
  const dt=s=>new Date(s+"T00:00:00");
  const iso=d=>d.toISOString().slice(0,10);
  if(tipo==="mes"){
    const m=max.slice(0,7); const ant=new Date(dt(max+"").getFullYear(), dt(max).getMonth(),0);
    const mAnt=iso(ant).slice(0,7);
    g("d1").value=m+"-01"; g("h1").value=max;
    g("d0").value=mAnt+"-01"; g("h0").value=iso(ant);
  } else if(tipo==="semana"){
    const f=dt(max); const d1=new Date(f); d1.setDate(f.getDate()-6);
    const h0=new Date(d1); h0.setDate(d1.getDate()-1);
    const d0=new Date(h0); d0.setDate(h0.getDate()-6);
    g("d1").value=iso(d1); g("h1").value=max;
    g("d0").value=iso(d0); g("h0").value=iso(h0);
  } else if(tipo==="mitades"){
    const a=dt(min), b=dt(max);
    const medio=new Date((a.getTime()+b.getTime())/2);
    g("d0").value=min; g("h0").value=iso(medio);
    const sig=new Date(medio); sig.setDate(medio.getDate()+1);
    g("d1").value=iso(sig); g("h1").value=max;
  } else if(tipo==="todo"){
    g("d0").value=min; g("h0").value=min; g("d1").value=max; g("h1").value=max;
  }
  render();
}

/* ---------- exportación CSV ---------- */
function exportarCSV(){
  const sep=";";  // Excel en español usa punto y coma
  const filas=[["nivel","codigo","nombre","peso","variacion_pct","aporte_pp","editado"]];
  for(const d of DATA.divisiones){
    const r=valorDivision(d.codigo);
    filas.push(["division",d.codigo,d.nombre,d.peso_oficial,
      r.v===null?"":r.v.toFixed(4),"",""]);
    for(const c of DATA.clases.filter(x=>x.division===d.codigo)){
      const v=valorClase(c); const ed=(c.codigo in ovClase)?"si":"";
      const aporte=(v===null||r.cub===0)?"":(c.peso_oficial/r.cub*v).toFixed(4);
      filas.push(["subcategoria",c.codigo,c.nombre,c.peso_oficial,
        v===null?"":v.toFixed(4),aporte,ed]);
      const vs=valoresProducto(c);
      const tot=vs.filter(x=>x.v!==null).reduce((a,b)=>a+b.nObs,0);
      for(const x of vs){
        const k=c.codigo+"|"+x.p.id;
        const w=tot?x.nObs/tot*100:0;
        filas.push(["producto",x.p.id,x.p.nombre,w.toFixed(2),
          x.v===null?"":x.v.toFixed(4),
          x.v===null?"":(w/100*x.v).toFixed(4),
          (k in ovProd)?"si":""]);
      }
    }
  }
  const txt="\uFEFF"+filas.map(f=>f.map(c=>{
    const s=String(c); return /[;"\n]/.test(s)?'"'+s.replace(/"/g,'""')+'"':s;
  }).join(sep)).join("\r\n");
  const blob=new Blob([txt],{type:"text/csv;charset=utf-8;"});
  const a=document.createElement("a");
  a.href=URL.createObjectURL(blob);
  a.download=`relevamiento_${g("d1").value}_vs_${g("d0").value}.csv`;
  a.click();
}

/* ---------- render ---------- */
function render(){
  g("meta").textContent=`Generado el ${DATA.generado} · datos disponibles del ${DATA.fecha_min} al ${DATA.fecha_max} · región GBA`;
  g("disponible").textContent=`Hay datos entre ${DATA.fecha_min} y ${DATA.fecha_max}. Si elegís un período sin datos, las filas van a mostrar “—”.`;
  g("presets").innerHTML=
    `<button onclick="preset('mes')">Mes actual vs anterior</button>
     <button onclick="preset('semana')">Última semana vs previa</button>
     <button onclick="preset('mitades')">Segunda mitad vs primera</button>`;
  g("botonesEsc").innerHTML=Object.keys(ESC).map(k=>
    `<button class="esc ${k===escenario?'on':''}" onclick="setEsc('${k}')">${ESC[k][0]}</button>`).join("");
  g("descEsc").textContent=ESC[escenario][1];

  const r=valorDivision("01");
  g("total").textContent=fmt(r.v);
  g("total").className="big "+cl(r.v);
  const dv=DATA.divisiones.find(d=>d.codigo==="01");
  g("cobertura").textContent=
    `Alimentos y bebidas · cobertura ${dv.peso_oficial?(r.cub/dv.peso_oficial*100).toFixed(0):0}% del peso de la división `+
    `(${r.cub.toFixed(2)} de ${dv.peso_oficial.toFixed(2)} puntos de la canasta GBA). `+
    `Las subcategorías sin datos se excluyen y se renormaliza.`;

  let html=`<tr><th style="width:38%">Categoría / producto</th><th class="num">Peso</th>
    <th class="num">Variación</th><th class="num">Aporte pp</th><th>Estado / editar</th></tr>`;

  for(const d of DATA.divisiones){
    const rd=valorDivision(d.codigo);
    const tieneClases=DATA.clases.some(c=>c.division===d.codigo);
    const abierto=!!abiertos.div[d.codigo];
    const badge=d.cobertura==="medida_sepa"?'<span class="badge med">Medida</span>':
      d.cobertura==="pendiente"?'<span class="badge pend">Pendiente de fuente</span>':
      '<span class="badge nosc">No relevable online</span>';
    html+=`<tr class="divrow" ${tieneClases?`onclick="toggleDiv('${d.codigo}')"`:''}>
      <td><b>${tieneClases?(abierto?"▾":"▸"):"&nbsp;&nbsp;"} ${d.codigo} ${d.nombre}</b></td>
      <td class="num">${d.peso_oficial.toFixed(1)}%</td>
      <td class="num ${cl(rd.v)}"><b>${fmt(rd.v)}</b></td>
      <td class="num"></td><td>${badge}</td></tr>`;

    if(!abierto) continue;
    for(const c of DATA.clases.filter(x=>x.division===d.codigo)){
      const v=valorClase(c); const adhoc=(c.codigo in ovClase);
      const aporte=(v===null||!rd.cub)?null:c.peso_oficial/rd.cub*v;
      const ab=!!abiertos.cls[c.codigo];
      html+=`<tr class="clsrow">
        <td onclick="toggleCls('${c.codigo}')"><span class="ind">${ab?"▾":"▸"}</span>${c.nombre}</td>
        <td class="num">${c.peso_oficial.toFixed(2)}%</td>
        <td class="num ${cl(v)}">${fmt(v)}</td>
        <td class="num ${cl(aporte)}">${fmt(aporte)}</td>
        <td><input class="v ${adhoc?'edit':''}" placeholder="auto"
             value="${adhoc?ovClase[c.codigo]:''}"
             onchange="editC('${c.codigo}',this.value)"></td></tr>`;

      if(!ab) continue;
      const vs=valoresProducto(c);
      const tot=vs.filter(x=>x.v!==null).reduce((a,b)=>a+b.nObs,0);
      for(const x of vs){
        const k=c.codigo+"|"+x.p.id;
        const ed=(k in ovProd);
        const w=tot?x.nObs/tot*100:0;
        html+=`<tr class="prodrow">
          <td style="padding-left:34px">${x.p.nombre}</td>
          <td class="num">${w.toFixed(1)}%</td>
          <td class="num ${cl(x.v)}">${fmt(x.v)}</td>
          <td class="num ${cl(x.v===null?null:w/100*x.v)}">${x.v===null?"—":fmt(w/100*x.v)}</td>
          <td><input class="v ${ed?'edit':''}" ${adhoc?'disabled':''}
               value="${x.v===null?'':x.v.toFixed(2)}"
               onchange="editP('${c.codigo}','${x.p.id}',this.value)"></td></tr>`;
      }
    }
  }
  g("tabla").innerHTML=html;
}

/* arranque: última semana contra la previa, y división 01 abierta */
abiertos.div["01"]=true;
preset("semana");
</script></body></html>
"""
