"""
Test del ciclo de respaldo: exportar -> borrar -> reconstruir.

POR QUE IMPORTA: el historial de precios es irrecuperable (SEPA solo guarda
7 dias). Si el respaldo no reconstruye EXACTAMENTE lo mismo, el proyecto
pierde su activo sin que nadie se entere hasta que sea tarde.
"""

import tempfile
from pathlib import Path

from engine.index_elemental import ObservacionVariedad
from storage.db import conectar, insertar_observaciones


def _huella(con):
    n, s = con.execute("SELECT COUNT(*), ROUND(SUM(precio),4) FROM precios_raw").fetchone()
    return n, s


def test_exportar_y_reconstruir_da_exactamente_lo_mismo(monkeypatch=None):
    import csv, gzip
    with tempfile.TemporaryDirectory() as d:
        base = Path(d) / "t.db"
        carpeta = Path(d) / "historico"
        carpeta.mkdir()

        con = conectar(base)
        obs = []
        for i, region in enumerate(["GBA", "Pampeana", "Noreste"]):
            for dia in ["2026-08-10", "2026-08-11"]:
                obs.append((ObservacionVariedad(
                    dia, f"EAN{i}", "C1", 100.0 + i, f"Prod {i}", region=region), "01.1.6"))
        insertar_observaciones(con, obs)
        original = _huella(con)

        # exportar (misma logica que scripts/exportar_dia.py)
        cols = ["fecha", "ean_o_id", "clase_codigo", "comercio", "precio", "region"]
        for fecha in [r[0] for r in con.execute("SELECT DISTINCT fecha FROM precios_raw")]:
            with gzip.open(carpeta / f"{fecha}.csv.gz", "wt", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(cols)
                for fila in con.execute(
                        f"SELECT {','.join(cols)} FROM precios_raw WHERE fecha = ?", (fecha,)):
                    w.writerow(fila)
        con.close()
        base.unlink()

        # reconstruir
        con2 = conectar(base)
        for archivo in sorted(carpeta.glob("*.csv.gz")):
            with gzip.open(archivo, "rt", encoding="utf-8") as fh:
                filas = [(r["fecha"], r["ean_o_id"], r["clase_codigo"], r["comercio"],
                          float(r["precio"]), r["region"]) for r in csv.DictReader(fh)]
            con2.executemany(
                """INSERT OR IGNORE INTO precios_raw
                   (fecha, ean_o_id, clase_codigo, comercio, precio, region)
                   VALUES (?,?,?,?,?,?)""", filas)
        con2.commit()
        reconstruida = _huella(con2)
        con2.close()

        assert original == reconstruida, f"{original} != {reconstruida}"
        assert original[0] == 6


def test_el_respaldo_conserva_la_region():
    """La region es la que permite ponderar bien: si se perdiera en el
    respaldo, la base reconstruida daria numeros distintos."""
    import csv, gzip
    with tempfile.TemporaryDirectory() as d:
        base = Path(d) / "t.db"
        con = conectar(base)
        insertar_observaciones(con, [(ObservacionVariedad(
            "2026-08-10", "E1", "C1", 100.0, "P", region="Patagonia"), "01.1.6")])
        fila = con.execute("SELECT region FROM precios_raw").fetchone()
        assert fila[0] == "Patagonia"
        con.close()
