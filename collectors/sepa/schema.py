"""
Esquema de columnas de los archivos de SEPA.

VERIFICADO CONTRA ARCHIVOS REALES (agosto 2026). El productos.csv de SEPA
usa delimitador "|", encoding utf-8 con BOM, y estas columnas:

  id_comercio | id_bandera | id_sucursal | id_producto | productos_ean |
  productos_descripcion | productos_cantidad_presentacion |
  productos_unidad_medida_presentacion | productos_marca |
  productos_precio_lista | productos_precio_referencia |
  productos_cantidad_referencia | productos_unidad_medida_referencia |
  productos_precio_unitario_promo1 | productos_leyenda_promo1 |
  productos_precio_unitario_promo2 | productos_leyenda_promo2

DOS SORPRESAS QUE CONVIENE SABER:
1. `id_producto` es el CODIGO DE BARRAS (EAN de 13 digitos), no un id
   interno. `productos_ean` es un flag 0/1, no el codigo — usar
   `id_producto` como identificador.
2. No hay columna de fecha ni de cadena con nombre legible: la cadena es
   `id_comercio` (numerico) y la fecha viene de la carpeta del ZIP.

Este archivo mapea esos nombres reales a las claves internas del sistema.
Se conservan alias genericos por si en el futuro se suma otra fuente.
"""

from __future__ import annotations

ALIAS_COLUMNAS: dict[str, list[str]] = {
    "ean": ["id_producto", "ean", "codigo_ean", "cod_barras"],
    "nombre_producto": ["productos_descripcion", "nombre_producto", "descripcion",
                        "producto", "nombre"],
    "marca": ["productos_marca", "marca"],
    "precio": ["productos_precio_lista", "precio_lista", "precio", "precio_unitario"],
    "cadena": ["id_comercio", "cadena", "bandera", "comercio"],
    "sucursal_id": ["id_sucursal", "sucursal_id", "sucursal"],
    "provincia": ["provincia"],
    "localidad": ["localidad"],
    "fecha": ["fecha", "fecha_relevamiento", "fecha_actualizacion"],
    # utiles para normalizar por unidad (precio por kilo / litro)
    "precio_referencia": ["productos_precio_referencia"],
    "cantidad_referencia": ["productos_cantidad_referencia"],
    "unidad_referencia": ["productos_unidad_medida_referencia"],
}

# Columnas sin las cuales no se puede procesar una fila.
# OJO: "fecha" NO esta aca a proposito. La aporta quien carga (de la carpeta
# interna del ZIP, del nombre del archivo, o de --fecha), porque el archivo
# diario de SEPA ES de ese dia y no repite la fecha en cada fila.
COLUMNAS_REQUERIDAS = ["ean", "nombre_producto", "precio", "cadena"]


class EsquemaSepaError(Exception):
    pass


def resolver_columnas(columnas_archivo: list[str]) -> dict[str, str]:
    """Dado el listado de columnas de un archivo real, arma el mapeo
    {clave_canonica: nombre_columna_real}. Falla con un mensaje claro si
    falta algo requerido, en vez de ingerir una columna equivocada."""
    resuelto: dict[str, str] = {}
    cols_lower = {c.lower(): c for c in columnas_archivo}

    for clave, candidatos in ALIAS_COLUMNAS.items():
        for candidato in candidatos:
            if candidato.lower() in cols_lower:
                resuelto[clave] = cols_lower[candidato.lower()]
                break

    faltantes = [c for c in COLUMNAS_REQUERIDAS if c not in resuelto]
    if faltantes:
        raise EsquemaSepaError(
            f"No encontre columnas para: {faltantes}. "
            f"Columnas disponibles en el archivo: {columnas_archivo}. "
            f"Agrega el alias correcto en ALIAS_COLUMNAS."
        )
    return resuelto
