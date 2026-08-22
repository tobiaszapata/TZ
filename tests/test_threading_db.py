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
