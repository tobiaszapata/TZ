"""
Tests del bug real reportado: en el desglose de productos, algunos
mostraban el mismo código en la columna "Producto" y en "Código" (por
ejemplo, un producto de Pan y cereales con "7622300829568" en las dos).

LA CAUSA REAL (no la que se había arreglado antes — esta es distinta):
Cuando el archivo real de SEPA trae la descripción VACÍA para un producto
(pasa: algunos comercios chicos no completan ese campo), el filtro
`if o.nombre_producto` en `insertar_observaciones` — pensado para no
pisar un nombre bueno con uno vacío — tenía un efecto colateral no
previsto: si NUNCA hubo un nombre real para ese producto, la fila en la
tabla `productos` directamente NO SE CREABA. El precio quedaba guardado en
`precios_raw`, pero sin ninguna fila correspondiente en `productos` — y
eso es indistinguible, para `nombres_de_productos()`, de "este producto
nunca se cargó". Por eso mostraba el código como respaldo: no porque el
código estuviera guardado como nombre, sino porque no había NINGÚN nombre
guardado.

La corrección: guardar el código COMO nombre explícito cuando no hay
descripción real, y reemplazarlo apenas llegue un nombre real de
cualquier carga futura — sin que un placeholder pueda pisar un nombre
real ya guardado.
"""

import tempfile
from pathlib import Path

from engine.index_elemental import ObservacionVariedad
from storage.db import conectar, insertar_observaciones, nombres_de_productos


def test_producto_con_descripcion_siempre_vacia_no_queda_sin_nombre():
    """El bug real: reproduce un producto cuya descripción SIEMPRE viene
    vacía en el archivo de SEPA (nunca hay un nombre real disponible)."""
    with tempfile.TemporaryDirectory() as t:
        con = conectar(Path(t) / "t.db")
        insertar_observaciones(con, [
            (ObservacionVariedad("2026-08-09", "7622300829568", "C1", 800.0, "", region="GBA"),
             "01.1.1"),
        ])
        nombres = nombres_de_productos(con, ["7622300829568"])
        # antes del arreglo, esto tambien "funcionaba" en el sentido de no
        # crashear (el fallback de nombres_de_productos ya cubria el caso
        # de fila ausente) — lo que se verifica aca es que AHORA la fila
        # SI existe en la tabla productos, no que el resultado visible
        # sea distinto en este paso (el fallback da lo mismo). El
        # siguiente test es el que muestra la diferencia real.
        assert nombres["7622300829568"] == "7622300829568"
        fila = con.execute(
            "SELECT nombre_producto FROM productos WHERE ean_o_id = ?",
            ("7622300829568",),
        ).fetchone()
        assert fila is not None, (
            "la fila en 'productos' nunca se creo -- este es el bug real: "
            "un precio sin ningun registro de nombre asociado"
        )
        con.close()


def test_nombre_real_reemplaza_el_placeholder_en_una_carga_posterior():
    """Este es el caso que antes fallaba en la práctica: el producto
    aparece con descripción vacía un día, y con descripción real otro día
    (por ejemplo, otro comercio sí la completa bien)."""
    with tempfile.TemporaryDirectory() as t:
        con = conectar(Path(t) / "t.db")
        insertar_observaciones(con, [
            (ObservacionVariedad("2026-08-09", "EAN1", "C1", 800.0, "", region="GBA"), "01.1.1"),
        ])
        assert nombres_de_productos(con, ["EAN1"])["EAN1"] == "EAN1"

        insertar_observaciones(con, [
            (ObservacionVariedad("2026-08-10", "EAN1", "C2", 810.0, "Pan lactal Bimbo", region="GBA"),
             "01.1.1"),
        ])
        assert nombres_de_productos(con, ["EAN1"])["EAN1"] == "Pan lactal Bimbo"
        con.close()


def test_nombre_real_ya_guardado_no_se_pisa_con_uno_vacio_despues():
    with tempfile.TemporaryDirectory() as t:
        con = conectar(Path(t) / "t.db")
        insertar_observaciones(con, [
            (ObservacionVariedad("2026-08-09", "EAN1", "C1", 800.0, "Pan lactal Bimbo", region="GBA"),
             "01.1.1"),
        ])
        insertar_observaciones(con, [
            (ObservacionVariedad("2026-08-10", "EAN1", "C2", 810.0, "", region="GBA"), "01.1.1"),
        ])
        assert nombres_de_productos(con, ["EAN1"])["EAN1"] == "Pan lactal Bimbo"
        con.close()


def test_mismo_lote_con_vacio_y_real_gana_el_real():
    """Dentro de una misma carga (un mismo archivo de SEPA), el producto
    puede aparecer en varios comercios: uno con descripción vacía, otro
    con la real. El nombre real tiene que ganar, sin importar el orden."""
    with tempfile.TemporaryDirectory() as t:
        con = conectar(Path(t) / "t.db")
        insertar_observaciones(con, [
            (ObservacionVariedad("2026-08-11", "EAN2", "C1", 100.0, "", region="GBA"), "01.1.1"),
            (ObservacionVariedad("2026-08-11", "EAN2", "C2", 100.0, "Producto real", region="GBA"),
             "01.1.1"),
        ])
        assert nombres_de_productos(con, ["EAN2"])["EAN2"] == "Producto real"
        con.close()


def test_mismo_lote_orden_invertido_tambien_gana_el_real():
    with tempfile.TemporaryDirectory() as t:
        con = conectar(Path(t) / "t.db")
        insertar_observaciones(con, [
            (ObservacionVariedad("2026-08-11", "EAN3", "C1", 100.0, "Producto real", region="GBA"),
             "01.1.1"),
            (ObservacionVariedad("2026-08-11", "EAN3", "C2", 100.0, "", region="GBA"), "01.1.1"),
        ])
        assert nombres_de_productos(con, ["EAN3"])["EAN3"] == "Producto real"
        con.close()


def test_reparar_nombres_faltantes_crea_fila_para_productos_huerfanos():
    """El escenario real de una base que ya tenia el bug: precios cargados
    directamente en precios_raw (via una version anterior del codigo, o
    datos importados de otra forma) sin que la tabla productos se haya
    enterado nunca. La herramienta de reparacion tiene que crear esas
    filas faltantes con el codigo como nombre explicito."""
    import importlib
    with tempfile.TemporaryDirectory() as t:
        db = Path(t) / "t.db"
        con = conectar(db)
        con.execute(
            "INSERT INTO precios_raw (fecha,ean_o_id,clase_codigo,comercio,precio,region) "
            "VALUES (?,?,?,?,?,?)",
            ("2026-08-09", "HUERFANO1", "01.1.1", "C1", 800.0, "GBA"),
        )
        con.commit()

        assert nombres_de_productos(con, ["HUERFANO1"])["HUERFANO1"] == "HUERFANO1"
        fila = con.execute(
            "SELECT * FROM productos WHERE ean_o_id = ?", ("HUERFANO1",)
        ).fetchone()
        assert fila is None, "el escenario de prueba deberia arrancar SIN la fila"
        con.close()

        import scripts.reparar_nombres_faltantes as mod
        importlib.reload(mod)
        mod.DB_PATH = db
        mod.main()

        con = conectar(db)
        fila = con.execute(
            "SELECT nombre_producto FROM productos WHERE ean_o_id = ?", ("HUERFANO1",)
        ).fetchone()
        assert fila is not None, "la reparacion no creo la fila faltante"
        assert fila[0] == "HUERFANO1"
        con.close()
