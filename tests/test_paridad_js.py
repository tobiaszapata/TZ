"""
Test de PARIDAD entre el motor de Python y el de JavaScript.

POR QUE ESTE TEST ES NECESARIO:
Desde que existe la aplicacion HTML (scripts/generar_app.py), la matematica
de agregacion vive en DOS lugares: engine/ en Python, y el bloque <script>
de la app en JavaScript. Es una duplicacion deliberada — el navegador tiene
que poder recalcular cualquier ventana temporal sin volver a Python — pero
duplicar logica es exactamente como dos implementaciones se desincronizan
en silencio y empiezan a dar numeros distintos.

Este test corre las dos sobre los mismos datos y verifica que coincidan.
Si alguien toca la formula de un lado y se olvida del otro, esto falla.

REQUIERE NODE. Si `node` no esta instalado, el test se saltea con un aviso
en vez de fallar: no queremos que la ausencia de una herramienta opcional
rompa la suite completa.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from config.canasta import CANASTA
from engine.exportador import exportar
from engine.index_elemental import ObservacionVariedad
from engine.reporte import calcular_clase_y_productos
from scripts._app_template import APP_HTML
from storage.db import (
    conectar,
    insertar_observaciones,
    nombres_de_productos,
    precios_por_producto_en_rango,
)

D1, H1 = "2026-08-13", "2026-08-16"
D0, H0 = "2026-08-09", "2026-08-12"

DATOS_PRUEBA = {
    "01.1.6": [("BANANA", "Banana x kg", [100, 101, 103, 105, 107, 110, 113, 116]),
               ("MANZANA", "Manzana x kg", [150, 150, 151, 151, 152, 152, 153, 153])],
    "01.1.7": [("PAPA", "Papa x kg", [80, 82, 85, 88, 91, 94, 97, 100]),
               ("TOMATE", "Tomate x kg", [200, 198, 196, 194, 192, 190, 188, 186])],
    "01.1.1": [("PAN", "Pan x kg", [1500, 1510, 1520, 1530, 1540, 1550, 1560, 1570])],
}
DIAS = ["2026-08-09", "2026-08-10", "2026-08-11", "2026-08-12",
        "2026-08-13", "2026-08-14", "2026-08-15", "2026-08-16"]


def _base_de_prueba(path: Path):
    con = conectar(path)
    obs = []
    for clase, prods in DATOS_PRUEBA.items():
        for ean, nombre, serie in prods:
            for dia, precio in zip(DIAS, serie):
                obs.append((ObservacionVariedad(dia, ean, "Coto", float(precio), nombre), clase))
    insertar_observaciones(con, obs)
    return con


def _resultado_python(con) -> dict:
    out = {}
    num = den = 0.0
    for cod in DATOS_PRUEBA:
        pa = precios_por_producto_en_rango(con, cod, D1, H1)
        pb = precios_por_producto_en_rango(con, cod, D0, H0)
        nombres = nombres_de_productos(con, list(set(pa) | set(pb)))
        r, _ = calcular_clase_y_productos(pa, pb, nombres)
        out[cod] = r.variacion_pct
        w = CANASTA[cod].peso("GBA") * 100
        num += w * r.variacion_pct
        den += w
    out["DIVISION_01"] = num / den
    return out


def _resultado_javascript(datos: dict) -> dict:
    js = APP_HTML.split("<script>", 1)[1].split("</script>", 1)[0]
    nucleo = js[: js.index("/* ---------- estado ---------- */")]
    nucleo = nucleo.replace("__DATOS__", json.dumps(datos, ensure_ascii=False))

    script = nucleo + f"""
const D1="{D1}",H1="{H1}",D0="{D0}",H0="{H0}";
const out={{}}; let num=0,den=0;
for(const c of DATA.clases){{
  const vs=c.productos.map(p=>{{
    const b=varProducto(p,D1,H1,D0,H0);
    return b===null?null:{{v:b.v,n:b.nObs}};
  }}).filter(x=>x);
  let n2=0,d2=0;
  for(const x of vs){{ n2+=x.n*x.v; d2+=x.n; }}
  const v=d2?n2/d2:null;
  out[c.codigo]=v;
  if(v!==null){{ num+=c.peso_oficial*v; den+=c.peso_oficial; }}
}}
out["DIVISION_01"]=num/den;
console.log(JSON.stringify(out));
"""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(script)
        ruta = f.name
    salida = subprocess.run(["node", ruta], capture_output=True, text=True, timeout=60)
    if salida.returncode != 0:
        raise RuntimeError(f"node fallo: {salida.stderr[:500]}")
    return json.loads(salida.stdout)


def test_python_y_javascript_dan_el_mismo_resultado():
    if shutil.which("node") is None:
        print("    (node no instalado — test de paridad salteado)")
        return

    with tempfile.TemporaryDirectory() as d:
        db = Path(d) / "t.db"
        con = _base_de_prueba(db)
        py = _resultado_python(con)
        datos = exportar(con)
        con.close()

    js = _resultado_javascript(datos)

    assert set(py) == set(js), f"claves distintas: {set(py) ^ set(js)}"
    for k in py:
        # tolerancia amplia frente a diferencias de punto flotante entre
        # lenguajes, pero mucho mas ajustada que cualquier error real de
        # formula (que se veria en el segundo o tercer decimal).
        assert abs(py[k] - js[k]) < 1e-9, (
            f"{k}: Python={py[k]!r} vs JavaScript={js[k]!r} — "
            f"las dos implementaciones se desincronizaron"
        )
