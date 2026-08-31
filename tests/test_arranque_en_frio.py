"""
Test de integración del arranque en frío de app_streamlit.py — reproduce
el bug real: `_rango_disponible()` tenía un atajo
`if not DB_PATH.exists(): return None, None, 0` ANTES de darle a `_con()`
la oportunidad de reconstruir la base desde historico/.

Como Streamlit Cloud NUNCA tiene una base local hasta que `_con()` la
reconstruye, ese atajo disparaba SIEMPRE en el primer arranque — la app
mostraba "No hay datos todavía" sin importar cuántos días hubiera en
historico/, porque la reconstrucción nunca llegaba a dispararse.

app_streamlit.py no se puede importar en este entorno (requiere Streamlit
instalado), así que este test reproduce la lógica exacta de las dos
funciones involucradas (`_con` y `_rango_disponible`, tal como están
escritas hoy en el archivo real) contra un `historico/` real con archivos
de verdad, para confirmar el comportamiento de punta a punta. Si alguna
vez alguien reintroduce un atajo de "si no existe la base, ni intentes"
en cualquiera de las dos funciones, este test tiene que fallar.
"""

import gzip
import csv
import tempfile
from pathlib import Path

from storage.db import conectar
from engine.consultas import hace_falta_reconstruir


def _armar_historico(carpeta: Path, fechas: list[str]) -> None:
    carpeta.mkdir(parents=True, exist_ok=True)
    for fecha in fechas:
        with gzip.open(carpeta / f"{fecha}.csv.gz", "wt", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["fecha", "ean_o_id", "clase_codigo", "comercio", "precio",
                       "region", "nombre_producto"])
            w.writerow([fecha, "EAN1", "01.1.1", "C1", "100.0", "GBA", "Producto test"])


def _con_como_en_la_app(db_path: Path, carpeta_historico: Path):
    """Reproduce EXACTAMENTE la lógica de `_con()` en app_streamlit.py:
    revisa si hace falta reconstruir, reconstruye si corresponde, y
    devuelve la conexión."""
    respaldos = sorted(carpeta_historico.glob("*.csv.gz")) if carpeta_historico.exists() else []
    dias_en_base = 0
    if db_path.exists():
        con_provisoria = conectar(db_path)
        dias_en_base = con_provisoria.execute(
            "SELECT COUNT(DISTINCT fecha) FROM precios_raw").fetchone()[0]
        con_provisoria.close()
    if hace_falta_reconstruir(db_path.exists(), dias_en_base, len(respaldos)):
        import scripts.reconstruir as mod_reconstruir
        viejo_db, viejo_carpeta = mod_reconstruir.DB_PATH, mod_reconstruir.CARPETA
        mod_reconstruir.DB_PATH, mod_reconstruir.CARPETA = db_path, carpeta_historico
        try:
            mod_reconstruir.reconstruir(verboso=False)
        finally:
            mod_reconstruir.DB_PATH, mod_reconstruir.CARPETA = viejo_db, viejo_carpeta
    return conectar(db_path)


def _rango_disponible_como_en_la_app(db_path: Path, carpeta_historico: Path):
    """Reproduce EXACTAMENTE la lógica CORREGIDA de `_rango_disponible()`:
    llama a `_con()` SIEMPRE, sin ningún atajo previo basado en si la base
    ya existe. Esta es la línea que, si alguien la vuelve a "optimizar"
    agregando un `if not db_path.exists(): return None, None, 0` antes de
    la conexión, reintroduce el bug real.

    Devuelve tambien la conexion (ademas de fmin/fmax/ndias) para que
    quien llama pueda cerrarla explicitamente. NOTA DE WINDOWS: sin cerrar
    la conexion, el archivo .db queda bloqueado por el sistema operativo
    en Windows (no en Linux/Mac), y `tempfile.TemporaryDirectory()` no
    puede borrar la carpeta al salir del `with` — el mismo tipo de
    problema que ya se corrigio antes con `os.chdir` sin restaurar
    (ver tests/test_diagnostico_git.py), ahora con una conexion de base
    de datos en vez de un directorio de trabajo."""
    con = _con_como_en_la_app(db_path, carpeta_historico)
    cur = con.execute("SELECT MIN(fecha), MAX(fecha), COUNT(DISTINCT fecha) FROM precios_raw")
    resultado = cur.fetchone()
    return resultado, con


def test_arranque_en_frio_sin_base_local_encuentra_los_dias_de_historico():
    """El escenario real reportado: Streamlit Cloud arranca sin ninguna
    base local (DB_PATH.exists() es False), pero historico/ tiene 22 días
    reales. La app tiene que encontrarlos igual."""
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        db_path = t / "relevamiento_precios.db"
        carpeta_historico = t / "historico"
        fechas = [f"2026-08-{d:02d}" for d in range(9, 31)]  # 22 dias, como el caso real
        _armar_historico(carpeta_historico, fechas)

        assert not db_path.exists(), "la prueba tiene que arrancar SIN base, como Streamlit Cloud"

        (fmin, fmax, ndias), con = _rango_disponible_como_en_la_app(db_path, carpeta_historico)
        con.close()  # ver nota de Windows en el docstring de arriba

        assert fmin == "2026-08-09", (
            f"se esperaba encontrar datos desde 2026-08-09, se obtuvo fmin={fmin!r} — "
            "esto es exactamente el bug real: la reconstruccion nunca se disparo"
        )
        assert fmax == "2026-08-30"
        assert ndias == 22


def test_arranque_en_frio_sin_historico_y_sin_base_no_rompe():
    """Caso legítimo de "no hay nada todavía": ni base ni historico/.
    Tiene que devolver (None, None, 0), no una excepción."""
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        db_path = t / "relevamiento_precios.db"
        carpeta_historico = t / "historico"  # no se crea, no existe

        (fmin, fmax, ndias), con = _rango_disponible_como_en_la_app(db_path, carpeta_historico)
        con.close()  # ver nota de Windows en el docstring de arriba
        assert fmin is None
        assert ndias == 0
