"""Tests de scripts/quitar_dias.py."""
import gzip
import sqlite3
import tempfile
from pathlib import Path

from scripts import quitar_dias as q


def _armar(t: Path):
    db = t / "x.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE precios_raw (fecha TEXT, ean_o_id TEXT, precio REAL)")
    hist = t / "historico"
    hist.mkdir()
    for f in ["2026-08-14", "2026-08-15", "2026-08-17"]:   # vie, sab, lun
        con.execute("INSERT INTO precios_raw VALUES (?, 'a', 1.0)", (f,))
        con.execute("INSERT INTO precios_raw VALUES (?, 'b', 2.0)", (f,))
        with gzip.open(hist / f"{f}.csv.gz", "wt") as fh:
            fh.write("x\n")
    con.commit()
    con.close()
    return db, hist, t / "quitados"


def test_quita_solo_las_fechas_pedidas_y_mueve_respaldo():
    with tempfile.TemporaryDirectory() as d:
        db, hist, dest = _armar(Path(d))
        r = q.quitar(["2026-08-15"], db, hist, dest)
        con = sqlite3.connect(db)
        fechas = sorted(x[0] for x in con.execute("SELECT DISTINCT fecha FROM precios_raw"))
        con.close()
        assert fechas == ["2026-08-14", "2026-08-17"]
        assert r["filas"] == {"2026-08-15": 2}
        assert not (hist / "2026-08-15.csv.gz").exists()
        assert (dest / "2026-08-15.csv.gz").exists()
        assert (hist / "2026-08-14.csv.gz").exists()


def test_simular_no_cambia_nada():
    with tempfile.TemporaryDirectory() as d:
        db, hist, dest = _armar(Path(d))
        q.quitar(["2026-08-15", "2026-08-17"], db, hist, dest, simular=True)
        con = sqlite3.connect(db)
        n = con.execute("SELECT COUNT(*) FROM precios_raw").fetchone()[0]
        con.close()
        assert n == 6
        assert len(list(hist.glob("*.csv.gz"))) == 3
        assert not dest.exists()


def test_fechas_cargadas_une_base_e_historico_y_detecta_fin_de_semana():
    with tempfile.TemporaryDirectory() as d:
        db, hist, _ = _armar(Path(d))
        f = q.fechas_cargadas(db, hist)
        assert f == {"2026-08-14", "2026-08-15", "2026-08-17"}
        assert [x for x in sorted(f) if q._es_fin_de_semana(x)] == ["2026-08-15"]
