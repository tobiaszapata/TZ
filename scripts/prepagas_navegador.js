/*
 PLAN B para bajar los cuadros tarifarios de prepagas SIN Python: se pega en la
 consola del navegador, estando en https://cuadrostarifarios.sssalud.gob.ar/

 Como usarlo:
   1. Abri https://cuadrostarifarios.sssalud.gob.ar/ en Chrome.
   2. Apreta F12 y anda a la pestaña "Console" (Consola).
   3. Si Chrome pide escribir "allow pasting", escribilo y Enter.
   4. Cambia PERIODO (abajo) por el mes que queres, pega TODO este archivo y Enter.
   5. Espera unos minutos: la consola muestra el progreso. Al terminar se baja un
      archivo AAAAMM.csv (carpeta Descargas).
   6. En PowerShell, desde la carpeta del proyecto:
        python -m scripts.descargar_prepagas --desde-csv C:\Users\tobia\Downloads\202610.csv

 El archivo tiene EXACTAMENTE las mismas columnas que genera el script de Python.
 Verifica la integridad igual que Python: si una entidad no baja completa, aborta.
*/
(async () => {
  const PERIODO = 202610;            // <-- CAMBIAR
  const POR_PAGINA = 50;             // mas de 50 da "Gateway Timeout" en el sitio
  const HILOS = 4;
  const COLS = ["periodo","rnemp","nombre_comercial","codigo_plan","nombre_plan","valor_capital",
    "cantidad_capitas","rango_desde","rango_hasta","region","tipo_plan","comercializable",
    "permite_copago","tasa_aumento_mensual","modalidad_adhesion","tipificacion"];
  const esc = v => { v = (v === null || v === undefined) ? "" : String(v);
    return /[",\n\r]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
  const b = v => (v === null || v === undefined) ? "" : (v ? 1 : 0);
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  async function get(url) {
    for (let i = 0; i < 6; i++) {
      try { const j = await (await fetch(url)).json(); if (j && j.data) return j; } catch (e) {}
      await sleep(1500 * (i + 1));
    }
    throw new Error("no se pudo leer " + url);
  }
  const ents = (await get("/api/getPrepagas")).data.map(e => e.rnemp);
  const filas = []; const errores = []; let hechas = 0;
  const cola = [...ents];
  async function trabajador() {
    while (cola.length) {
      const e = cola.shift(); const propias = [];
      try {
        let p = 1, ultima = 1, total = 0;
        while (p <= ultima) {
          const j = await get(`/api/getCuadrosTarifarios?page=${p}&per_page=${POR_PAGINA}&periodo=${PERIODO}&rnemp=${e}`);
          ultima = (j.paginacion && j.paginacion.ultima_pagina) || 1;
          total = (j.paginacion && j.paginacion.total) || j.data.length;
          for (const x of j.data) propias.push([x.periodo, x.rnemp, x.nombre_comercial, x.codigo_plan, x.nombre_plan,
            x.valor_capital, x.cantidad_capitas, x.rango_etario_desde, x.rango_etario_hasta, x.region, x.tipo_plan,
            b(x.comercializable), b(x.permite_copago), x.tasa_aumento_mensual, b(x.modalidad_adhesion), x.tipificacion]);
          p++;
        }
        if (propias.length !== total) throw new Error(`entidad ${e}: ${propias.length} filas de ${total}`);
        filas.push(...propias);
      } catch (err) { errores.push(String(err)); }
      hechas++; if (hechas % 10 === 0) console.log(`${hechas}/${ents.length} entidades, ${filas.length} filas`);
    }
  }
  await Promise.all(Array.from({length: HILOS}, trabajador));
  if (errores.length) { console.error("INCOMPLETO, no se descarga nada:", errores.slice(0, 10)); return; }
  filas.sort((a, c) => a[1] - c[1] || String(a[4]).localeCompare(String(c[4])));
  const csv = [COLS.join(","), ...filas.map(f => f.map(esc).join(","))].join("\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], {type: "text/csv"}));
  a.download = PERIODO + ".csv"; document.body.appendChild(a); a.click(); a.remove();
  console.log("LISTO:", filas.length, "filas ->", PERIODO + ".csv");
})();
