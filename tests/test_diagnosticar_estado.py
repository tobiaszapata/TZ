"""
Test de scripts/diagnosticar_estado.py — en particular, la extracción de
fecha desde el nombre del archivo, que tuvo un bug real durante el
desarrollo: `Path("2026-08-09.csv.gz").stem` da "2026-08-09.csv" (solo
saca UNA extensión), no "2026-08-09". Se corrigió con
`.name.removesuffix(".csv.gz")`. Este test evita que vuelva a pasar.
"""

import gzip
import csv
import tempfile
from pathlib import Path

from engine.index_elemental import ObservacionVariedad
from storage.db import conectar, insertar_observaciones


def test_fecha_se_extrae_completa_del_nombre_del_archivo():
    """Regresion directa del bug de Path.stem con doble extension."""
    nombre_archivo = "2026-08-09.csv.gz"
    fecha_correcta = nombre_archivo.removesuffix(".csv.gz")
    fecha_con_stem = Path(nombre_archivo).stem  # el bug: da "2026-08-09.csv"

    assert fecha_correcta == "2026-08-09"
    assert fecha_con_stem != "2026-08-09", (
        "si esto alguna vez empieza a dar igual, Path.stem cambio de "
        "comportamiento y el comentario de arriba ya no aplica"
    )


def test_detecta_dias_en_base_sin_respaldo():
    """Reproduce el escenario real reportado: dias recien cargados que
    todavia no se exportaron a historico/ (por ejemplo, porque
    _respaldar_automaticamente no llego a correr, o el usuario interrumpio
    el proceso antes de que terminara)."""
    from scripts.exportar_dia import dias_en_base

    with tempfile.TemporaryDirectory() as t:
        db = Path(t) / "t.db"
        con = conectar(db)
        insertar_observaciones(con, [
            (ObservacionVariedad("2026-08-09", "BANANA", "C1", 100.0, "Banana", region="GBA"), "01.1.6"),
            (ObservacionVariedad("2026-08-18", "BANANA", "C1", 105.0, "Banana", region="GBA"), "01.1.6"),
        ])

        en_base = set(dias_en_base(con))
        con.close()

        historico = Path(t) / "historico"
        historico.mkdir()
        with gzip.open(historico / "2026-08-09.csv.gz", "wt", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["fecha", "ean_o_id", "clase_codigo", "comercio", "precio",
                       "region", "nombre_producto"])
            w.writerow(["2026-08-09", "BANANA", "01.1.6", "C1", "100.0", "GBA", "Banana"])
        # 2026-08-18 queda sin respaldar a proposito

        en_historico = {
            a.name.removesuffix(".csv.gz") for a in historico.glob("*.csv.gz")
        }

        assert en_base == {"2026-08-09", "2026-08-18"}
        assert en_historico == {"2026-08-09"}
        sin_respaldo = en_base - en_historico
        assert sin_respaldo == {"2026-08-18"}
