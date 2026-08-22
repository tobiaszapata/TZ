"""
Exporta TODO el dataset a una estructura JSON, para que la aplicacion HTML
pueda calcular cualquier rango de fechas sin volver a Python.

CAMBIO DE ENFOQUE RESPECTO DE generar_html.py / generar_simulador.py:
Aquellos generan una FOTO para dos fechas fijas: si queres otra comparacion,
hay que volver a correr Python. Este exporta la serie diaria completa y deja
que el navegador haga el corte. Un solo archivo sirve para todas las
preguntas.

QUE SE EXPORTA (y por que en este nivel de detalle):
Para cada producto, la serie de PRECIOS PROMEDIO DIARIOS (media geometrica
sobre los comercios que lo reportaron ese dia). Ese es el nivel minimo que
permite recalcular cualquier ventana temporal:

  - promedio de un producto en [desde, hasta]  -> media geometrica de sus
    dias en esa ventana
  - variacion de un producto entre dos ventanas -> cociente de esos dos
    promedios
  - variacion de la categoria -> combinacion ponderada de sus productos
  - variacion de la division -> combinacion ponderada de sus categorias,
    con ponderadores OFICIALES de INDEC

No se exportan los precios por comercio individuales: multiplicaria el
tamano del archivo sin cambiar ninguno de los calculos de arriba (el
promedio diario por producto ya los resume). Si en el futuro se quiere
abrir por cadena, se agrega otra dimension aca.

TAMANO: aproximadamente (productos x dias) numeros. Con 500 productos y 6
meses de datos son ~90.000 valores, que en JSON comprimido son pocos MB —
perfectamente manejable para un archivo que se abre con doble clic.
"""

from __future__ import annotations

from datetime import datetime

from config.canasta import Cobertura, clases_de_division, divisiones
from storage.db import nombres_de_productos, valores_diarios_por_producto


def exportar(con, meses: list[str] | None = None) -> dict:
    """Arma el diccionario completo. `meses` limita que meses exportar; si
    es None, exporta todos los que haya en la base."""
    if meses is None:
        cur = con.execute("SELECT DISTINCT substr(fecha,1,7) FROM precios_raw ORDER BY 1")
        meses = [r[0] for r in cur.fetchall()]

    clases_payload = []
    for div in divisiones():
        for clase in clases_de_division(div.codigo):
            if clase.cobertura != Cobertura.MEDIDA_SEPA:
                continue

            # juntar la serie diaria de todos los meses disponibles
            series_por_producto: dict[str, dict[str, float]] = {}
            for mes in meses:
                for ean, serie in valores_diarios_por_producto(con, clase.codigo, mes).items():
                    for fecha, precio in serie:
                        series_por_producto.setdefault(ean, {})[fecha] = round(precio, 4)

            if not series_por_producto:
                continue

            nombres = nombres_de_productos(con, list(series_por_producto))
            productos = [{
                "id": ean,
                "nombre": nombres.get(ean, ean),
                # serie como {fecha: precio}; el navegador filtra por ventana
                "serie": dict(sorted(dias.items())),
            } for ean, dias in sorted(series_por_producto.items())]

            clases_payload.append({
                "codigo": clase.codigo,
                "nombre": clase.nombre,
                "division": div.codigo,
                "peso_oficial": round(clase.peso("GBA") * 100, 4),
                "productos": productos,
            })

    # rango de fechas disponible, para poner limites a los selectores
    cur = con.execute("SELECT MIN(fecha), MAX(fecha) FROM precios_raw")
    fecha_min, fecha_max = cur.fetchone()

    return {
        "generado": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "fecha_min": fecha_min,
        "fecha_max": fecha_max,
        "meses": meses,
        "divisiones": [{
            "codigo": d.codigo,
            "nombre": d.nombre,
            "peso_oficial": round(d.peso("GBA") * 100, 4),
            "cobertura": d.cobertura.value,
        } for d in divisiones()],
        "clases": clases_payload,
    }
