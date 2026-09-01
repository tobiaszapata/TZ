"""
Test de regresión: la conexión tiene que poder usarse desde un hilo
distinto al que la creó.

POR QUE ESTE TEST EXISTE:
Bug real reportado en Streamlit Cloud. `@st.cache_resource` guarda la
conexión entre re-corridas de la app, y Streamlit puede invocar esa función
cacheada desde un hilo distinto al que la creó originalmente. sqlite3, por
defecto, prohíbe eso y tira `ProgrammingError`. Pasó en producción apenas
el usuario tocaba cualquier widget (modo edición, elegir un producto):
cualquier interacción dispara una re-corrida, y ahí explotaba.

La corrección es `check_same_thread=False` en storage/db.py::conectar.
Este test reproduce el escenario exacto (crear la conexión en un hilo,
usarla desde otro) para que si alguna vez alguien saca ese parámetro sin
darse cuenta, la suite lo detecte antes de que vuelva a pasar en producción.
"""

import threading
import tempfile
from pathlib import Path

from storage.db import conectar


def test_conexion_se_puede_usar_desde_otro_hilo():
    with tempfile.TemporaryDirectory() as d:
        con = conectar(Path(d) / "t.db")

        resultado = {}

        def usar_desde_otro_hilo():
            try:
                con.execute("SELECT COUNT(*) FROM precios_raw")
                resultado["ok"] = True
            except Exception as e:
                resultado["error"] = f"{type(e).__name__}: {e}"

        hilo = threading.Thread(target=usar_desde_otro_hilo)
        hilo.start()
        hilo.join()

        assert resultado.get("ok") is True, (
            f"la conexion no se pudo usar desde otro hilo: {resultado.get('error')}"
        )
        con.close()


def test_conexion_espera_si_otro_proceso_tiene_un_lock_de_escritura():
    """El bug real: 'OperationalError: database is locked' cuando dos
    procesos (por ejemplo, dos reconstrucciones de Streamlit Cloud
    coincidiendo durante un redeploy) compiten por escribir al mismo
    tiempo. Sin timeout, sqlite3 falla DE INMEDIATO. Con timeout=30, en
    cambio, espera a que el otro termine — tiempo mas que suficiente para
    que una reconstruccion que ya estaba terminando lo haga."""
    import threading
    import time
    import tempfile

    with tempfile.TemporaryDirectory() as t:
        db_path = Path(t) / "t.db"
        con_a = conectar(db_path)
        con_a.execute("BEGIN IMMEDIATE")

        resultado = {}

        def otro_proceso_intenta_escribir():
            t0 = time.time()
            try:
                con_b = conectar(db_path)
                con_b.execute("BEGIN IMMEDIATE")
                resultado["ok"] = True
                resultado["tardo"] = time.time() - t0
                con_b.commit()
                con_b.close()
            except Exception as e:
                resultado["error"] = str(e)

        hilo = threading.Thread(target=otro_proceso_intenta_escribir)
        hilo.start()
        time.sleep(1)
        con_a.commit()
        hilo.join(timeout=10)

        assert resultado.get("ok") is True, (
            f"debería haber esperado y conseguido escribir, no fallar: {resultado.get('error')}"
        )
        assert resultado["tardo"] >= 0.9, "debería haber esperado, no fallar de inmediato"
        con_a.close()
