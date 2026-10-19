"""Tests de storage/carga_bajo_demanda.py (carga de dias bajo demanda)."""
import csv
import gzip
import sqlite3
import tempfile
from pathlib import Path

from storage.db import conectar
from storage import carga_bajo_demanda as c


def _dia(carpeta: Path, fecha: str, filas: int = 1, precio: float = 100.0):
    carpeta.mkdir(parents=True, exist_ok=True)
    with gzip.open(carpeta / f"{fecha}.csv.gz", "wt", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["fecha", "ean_o_id", "clase_codigo", "comercio", "precio", "region", "nombre_producto"])
        for i in range(filas):
            w.writerow([fecha, f"EAN{i}", "01.1.1", "C1", precio, "GBA", f"Prod {i}"])


def _fechas_en_base(con):
    return sorted(r[0] for r in con.execute("SELECT DISTINCT fecha FROM precios_raw"))


def test_dias_disponibles_sale_de_los_nombres_e_ignora_otros_archivos():
    with tempfile.TemporaryDirectory() as t:
        h = Path(t) / "historico"
        for f in ["2026-10-02", "2026-10-01"]:
            _dia(h, f)
        (h / "README.txt").write_text("x")
        assert c.dias_disponibles(h) == ["2026-10-01", "2026-10-02"]
        assert c.rango_disponible(h) == ("2026-10-01", "2026-10-02", 2)
        assert c.rango_disponible(Path(t) / "no_existe") == (None, None, 0)


def test_fechas_necesarias_con_rangos_y_con_tramos():
    disp = ["2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07"]
    assert c.fechas_necesarias(disp, [("2026-10-02", "2026-10-05")]) == ["2026-10-02", "2026-10-05"]
    r = c.rangos_de_la_seleccion("2026-10-05", "2026-10-07", "2026-10-01", "2026-10-02")
    assert c.fechas_necesarias(disp, r) == disp
    r2 = c.rangos_de_la_seleccion((("2026-10-01", "2026-10-01"), ("2026-10-06", "2026-10-07")),
                                  None, "2026-10-02", "2026-10-02")
    assert c.fechas_necesarias(disp, r2) == ["2026-10-01", "2026-10-02", "2026-10-06", "2026-10-07"]


def test_carga_solo_los_dias_pedidos():
    with tempfile.TemporaryDirectory() as t:
        h = Path(t) / "historico"
        for f in ["2026-10-01", "2026-10-02", "2026-10-05"]:
            _dia(h, f)
        con = conectar(Path(t) / "x.db")
        r = c.asegurar_dias_cargados(con, h, ["2026-10-02"])
        assert r["cargados"] == ["2026-10-02"]
        assert _fechas_en_base(con) == ["2026-10-02"]
        con.close()


def test_pedir_de_nuevo_no_recarga_y_pedir_otro_dia_solo_suma_ese():
    with tempfile.TemporaryDirectory() as t:
        h = Path(t) / "historico"
        for f in ["2026-10-01", "2026-10-02"]:
            _dia(h, f)
        con = conectar(Path(t) / "x.db")
        c.asegurar_dias_cargados(con, h, ["2026-10-01"])
        r = c.asegurar_dias_cargados(con, h, ["2026-10-01", "2026-10-02"])
        assert r["ya_estaban"] == ["2026-10-01"] and r["cargados"] == ["2026-10-02"]
        assert _fechas_en_base(con) == ["2026-10-01", "2026-10-02"]
        con.close()


def test_dia_reescrito_con_el_mismo_nombre_se_recarga():
    with tempfile.TemporaryDirectory() as t:
        h = Path(t) / "historico"
        _dia(h, "2026-10-01", filas=1, precio=100.0)
        con = conectar(Path(t) / "x.db")
        c.asegurar_dias_cargados(con, h, ["2026-10-01"])
        _dia(h, "2026-10-01", filas=3, precio=250.0)   # mismo nombre, otro contenido
        r = c.asegurar_dias_cargados(con, h, ["2026-10-01"])
        assert r["recargados"] == ["2026-10-01"]
        n, p = con.execute("SELECT COUNT(*), MAX(precio) FROM precios_raw").fetchone()
        assert n == 3 and p == 250.0   # no quedaron filas viejas mezcladas
        con.close()


def test_base_local_ya_poblada_no_se_recarga_solo_se_anota():
    with tempfile.TemporaryDirectory() as t:
        h = Path(t) / "historico"
        _dia(h, "2026-10-01", filas=1, precio=100.0)
        con = conectar(Path(t) / "x.db")
        con.execute("INSERT INTO precios_raw (fecha, ean_o_id, clase_codigo, comercio, precio, region)"
                    " VALUES ('2026-10-01','LOCAL','01.1.1','C9',999.0,'GBA')")
        con.commit()
        r = c.asegurar_dias_cargados(con, h, ["2026-10-01"])
        assert r["ya_estaban"] == ["2026-10-01"]
        assert con.execute("SELECT COUNT(*) FROM precios_raw").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM dias_cargados").fetchone()[0] == 1
        con.close()


def test_fecha_sin_respaldo_se_informa_y_no_rompe():
    with tempfile.TemporaryDirectory() as t:
        con = conectar(Path(t) / "x.db")
        r = c.asegurar_dias_cargados(con, Path(t) / "historico", ["2026-10-01"])
        assert r["sin_respaldo"] == ["2026-10-01"]
        con.close()


def test_resultado_del_calculo_igual_cargando_todo_o_solo_lo_necesario():
    """Lo importante: cargar solo los dias del rango da EXACTAMENTE el mismo
    resultado que cargar todos los dias."""
    from engine.consultas import variacion_clase
    with tempfile.TemporaryDirectory() as t:
        h = Path(t) / "historico"
        precios = {"2026-09-01": 100, "2026-09-02": 102, "2026-10-01": 110, "2026-10-02": 112, "2026-11-01": 500}
        for f, p in precios.items():
            _dia(h, f, filas=2, precio=p)
        con_todo, con_parcial = conectar(Path(t) / "a.db"), conectar(Path(t) / "b.db")
        c.asegurar_dias_cargados(con_todo, h, list(precios))
        disp = c.dias_disponibles(h)
        nec = c.fechas_necesarias(disp, c.rangos_de_la_seleccion("2026-10-01", "2026-10-02",
                                                                 "2026-09-01", "2026-09-02"))
        assert "2026-11-01" not in nec
        c.asegurar_dias_cargados(con_parcial, h, nec)
        args = ("2026-10-01", "2026-10-02", "2026-09-01", "2026-09-02")
        a = variacion_clase(con_todo, "01.1.1", *args, region=None)
        b = variacion_clase(con_parcial, "01.1.1", *args, region=None)
        assert a[0] == b[0]
        con_todo.close(); con_parcial.close()
