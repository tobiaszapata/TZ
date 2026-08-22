#!/usr/bin/env python3
"""
Genera un reporte HTML autocontenido (un solo archivo .html) que se abre con
doble clic — sin servidor, sin costo, sin nada que instalar del lado de quien
lo mira.

    python -m scripts.generar_html --mes 2026-08 --contra 2026-07

Produce `reporte_2026-08.html`. Ese archivo se puede mandar por mail, dejar
en una carpeta compartida (Drive, OneDrive) o abrir localmente. Tu jefa hace
doble clic y ve: las 12 divisiones de INDEC con su estado, y el desglose de
productos de cada categoria medida.

POR QUE ESTATICO Y NO UNA WEB CON SERVIDOR:
Un HTML estatico muestra los datos que VOS ya cargaste — no necesita
servidor porque no calcula nada en vivo, ya viene todo adentro. Lo unico que
requeriria servidor es que se actualice solo sin que nadie lo genere; pero
ese paso es el mismo "gate de automatizacion" del resto del proyecto (ver
docs/decisiones.md): primero se corre a mano, despues se publica solo. Este
mismo HTML es el que se serviria en esa etapa — no se tira nada.
"""

from __future__ import annotations

import argparse
import html
from datetime import date, datetime
from pathlib import Path

from config.canasta import Cobertura, clases_de_division, divisiones, CANASTA
from engine.reporte import calcular_clase_y_productos
from storage.db import (
    conectar,
    nombres_de_productos,
    precios_por_producto_en_mes,
)

DB_PATH = Path("relevamiento_precios.db")

COBERTURA_LABEL = {
    Cobertura.MEDIDA_SEPA: ("Medida", "#2E7D32", "#eaf4ea"),
    Cobertura.PENDIENTE: ("Pendiente de fuente", "#B26A00", "#fdf3e3"),
    Cobertura.NO_SCRAPEABLE: ("No relevable online", "#8a8a8a", "#f0f0f0"),
}


def _variacion_clase(con, clase_codigo, mes, contra):
    p_mes = precios_por_producto_en_mes(con, clase_codigo, mes)
    p_ant = precios_por_producto_en_mes(con, clase_codigo, contra)
    eans = list(set(p_mes) | set(p_ant))
    return calcular_clase_y_productos(p_mes, p_ant, nombres_de_productos(con, eans))


def _color_var(v: float) -> str:
    if v > 0.05:
        return "#C0392B"
    if v < -0.05:
        return "#1F7A3D"
    return "#555"


def generar(con, mes: str, contra: str) -> str:
    e = html.escape
    partes: list[str] = []
    partes.append(f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Relevamiento de Precios — {e(mes)}</title>
<style>
 body{{font-family:-apple-system,"Segoe UI",Arial,sans-serif;color:#1f2933;max-width:1000px;
   margin:0 auto;padding:24px;background:#fafafa;line-height:1.5;}}
 h1{{color:#1F3B57;margin-bottom:2px;}} .sub{{color:#C0522D;font-size:15px;margin-bottom:2px;}}
 .meta{{color:#888;font-size:13px;font-style:italic;margin-bottom:24px;}}
 h2{{color:#1F3B57;border-bottom:2px solid #1F3B57;padding-bottom:4px;margin-top:34px;}}
 table{{border-collapse:collapse;width:100%;background:white;box-shadow:0 1px 3px rgba(0,0,0,.08);
   border-radius:6px;overflow:hidden;margin:14px 0;}}
 th{{background:#1F3B57;color:white;text-align:left;padding:9px 12px;font-size:13px;}}
 td{{border-bottom:1px solid #eee;padding:8px 12px;font-size:13px;}}
 .num{{text-align:right;font-variant-numeric:tabular-nums;font-weight:600;}}
 .badge{{display:inline-block;padding:2px 9px;border-radius:11px;font-size:11px;font-weight:600;}}
 details{{background:white;border-radius:6px;margin:10px 0;box-shadow:0 1px 3px rgba(0,0,0,.08);}}
 summary{{padding:12px 14px;cursor:pointer;font-weight:600;color:#1F3B57;font-size:14px;}}
 summary:hover{{background:#f5f7fa;}}
 details table{{margin:0;box-shadow:none;}}
 .foot{{color:#888;font-size:12px;margin-top:30px;border-top:1px solid #ddd;padding-top:12px;}}
 .aviso{{background:#fdf3e3;border-left:4px solid #B26A00;padding:8px 12px;font-size:12.5px;margin:10px 0;}}
</style></head><body>""")

    partes.append(f"""<h1>Relevamiento de Precios</h1>
<div class="sub">Desglose por categoria — {e(mes)} contra {e(contra)}</div>
<div class="meta">Generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} · region GBA ·
fuente de precios: SEPA (Secretaria de Comercio) · metodologia trazable a INDEC N32</div>""")

    # --- Tabla resumen de las 12 divisiones ---
    partes.append("<h2>Las 12 divisiones del IPC</h2>")
    partes.append("""<table><tr><th>Cod.</th><th>Division</th><th>Peso GBA</th>
<th>Variacion</th><th>Estado</th></tr>""")
    for div in divisiones():
        label, color, bg = COBERTURA_LABEL[div.cobertura]
        var_cell = "—"
        if div.cobertura == Cobertura.MEDIDA_SEPA:
            # variacion de la division = promedio simple de sus clases medidas,
            # ponderado por peso (aproximacion; el detalle real esta por clase)
            clases = [c for c in clases_de_division(div.codigo)
                      if c.cobertura == Cobertura.MEDIDA_SEPA]
            num, den = 0.0, 0.0
            for c in clases:
                res, _ = _variacion_clase(con, c.codigo, mes, contra)
                if res is not None:
                    num += c.peso("GBA") * res.variacion_pct
                    den += c.peso("GBA")
            if den > 0:
                v = num / den
                var_cell = f'<span style="color:{_color_var(v)}">{v:+.2f}%</span>'
        partes.append(
            f'<tr><td>{e(div.codigo)}</td><td>{e(div.nombre)}</td>'
            f'<td class="num">{div.peso("GBA")*100:.1f}%</td>'
            f'<td class="num">{var_cell}</td>'
            f'<td><span class="badge" style="color:{color};background:{bg}">{label}</span></td></tr>'
        )
    partes.append("</table>")
    partes.append("""<div class="aviso">Las categorias marcadas <b>Pendiente</b> tienen la
estructura y el peso oficial cargados, pero todavia no se conecto una fuente de datos para
ellas. Las <b>No relevables online</b> (alquileres, educacion formal, etc.) no tienen forma
razonable de medirse por precios web. Esto se muestra a proposito: es preferible declarar que
una casilla esta vacia a rellenarla con un supuesto disfrazado de dato.</div>""")

    # --- Detalle expandible por clase medida ---
    partes.append("<h2>Detalle por categoria (Alimentos y bebidas)</h2>")
    partes.append("<p style='font-size:13px;color:#555'>Cada categoria se abre para ver los "
                  "productos que explican su movimiento. La columna <b>aporte</b> suma la "
                  "variacion de la categoria.</p>")

    clases_medidas = [c for c in clases_de_division("01") if c.cobertura == Cobertura.MEDIDA_SEPA]
    for clase in clases_medidas:
        res, drivers = _variacion_clase(con, clase.codigo, mes, contra)
        if res is None:
            partes.append(f'<details><summary>{e(clase.nombre)} — sin datos comparables</summary></details>')
            continue
        v = res.variacion_pct
        partes.append(
            f'<details><summary>{e(clase.nombre)} '
            f'<span style="color:{_color_var(v)}">{v:+.2f}%</span> '
            f'<span style="font-weight:400;color:#999">· {res.n_productos_comparados} productos</span>'
            f'</summary>'
        )
        partes.append('<table><tr><th>Producto</th><th>Var. %</th><th>Peso*</th><th>Aporte pp</th></tr>')
        for d in drivers[:15]:
            partes.append(
                f'<tr><td>{e(d.nombre_producto)}</td>'
                f'<td class="num" style="color:{_color_var(d.variacion_pct)}">{d.variacion_pct:+.1f}%</td>'
                f'<td class="num">{d.peso_proxy_pct:.1f}%</td>'
                f'<td class="num">{d.incidencia_aproximada_pp:+.2f}</td></tr>'
            )
        partes.append('</table></details>')

    partes.append("""<div class="foot">* El "peso" del desglose por producto es una proxy por
cantidad de observaciones, NO el ponderador oficial de INDEC (que no existe por debajo de la
categoria). Sirve para identificar que producto mueve cada categoria. Metodologia completa en
el repositorio, docs/metodologia.md.</div>""")
    partes.append("</body></html>")
    return "".join(partes)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mes", required=True)
    ap.add_argument("--contra", required=True)
    ap.add_argument("--salida", default=None, help="nombre del archivo (default reporte_MES.html)")
    args = ap.parse_args()

    if not DB_PATH.exists():
        print(f"No encuentro la base {DB_PATH}. Corriste scripts.correr_dia al menos una vez?")
        return

    con = conectar(DB_PATH)
    contenido = generar(con, args.mes, args.contra)
    con.close()

    salida = Path(args.salida or f"reporte_{args.mes}.html")
    salida.write_text(contenido, encoding="utf-8")
    print(f"Reporte generado: {salida.resolve()}")
    print("Abrilo con doble clic, o mandaselo a quien quiera verlo. No necesita servidor.")


if __name__ == "__main__":
    main()
