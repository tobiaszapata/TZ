"""
Almacenamiento — SQLite, append-only.

POR QUÉ SQLITE Y NO POSTGRES EN RAILWAY (como el proyecto anterior):
Railway + Postgres resuelve un problema que todavía no tenemos: servir una
API viva 24/7 a un dashboard público. Lo que tenemos hoy es un batch diario
que corre una persona. SQLite es un archivo, no un servidor — no hay nada
que desplegar, nada que se caiga a las 3 AM, nada que pagar. El día que
esto sea un dashboard con varios usuarios, ahí se reevalúa Postgres. No
antes.

POR QUÉ NO DUCKDB TODAVÍA (a pesar de que lo recomendé en la charla
anterior para procesar los volúmenes grandes de SEPA): porque este sandbox
no tiene salida de red para instalarlo y no quería entregar código sin
poder correrlo y probarlo acá mismo. SQLite viene en la biblioteca estándar
de Python — lo que sigue SÍ se ejecutó y SÍ se testeó. Cuando este proyecto
escale a ingerir el dump nacional completo de SEPA (varios GB por día,
fase 2 en adelante), ahí conviene migrar la ingesta a DuckDB — dejalo
anotado en docs/decisiones.md como decisión pendiente, no lo resolvemos
hoy porque hoy no lo necesitamos.

POR QUÉ NO HAY ninguna función tipo "reemplazar_dia_base" o
"actualizar_precio": la tabla precios_raw es append-only por diseño. Si un
precio está mal, se corrige agregando una fila nueva con fecha de captura
más reciente, nunca pisando la vieja. Todo índice se recalcula desde acá —
si el índice de la semana pasada cambia, tiene que ser porque cambió el
código de cálculo (y eso se versiona en git y se documenta), nunca porque
alguien tocó un número a mano.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from engine.index_elemental import ObservacionVariedad

SCHEMA = """
CREATE TABLE IF NOT EXISTS precios_raw (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL,
    ean_o_id TEXT NOT NULL,
    clase_codigo TEXT NOT NULL,
    comercio TEXT NOT NULL,
    precio REAL NOT NULL,
    region TEXT,
    fuente TEXT NOT NULL DEFAULT 'sepa',
    capturado_en TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(fecha, ean_o_id, comercio, region, fuente)
);

CREATE INDEX IF NOT EXISTS idx_precios_fecha_clase
    ON precios_raw (fecha, clase_codigo, region);

CREATE INDEX IF NOT EXISTS idx_precios_producto
    ON precios_raw (clase_codigo, ean_o_id, fecha);

CREATE INDEX IF NOT EXISTS idx_precios_region
    ON precios_raw (region, clase_codigo, fecha);

CREATE TABLE IF NOT EXISTS productos (
    ean_o_id TEXT PRIMARY KEY,
    nombre_producto TEXT NOT NULL,
    actualizado_en TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pesos (
    codigo TEXT NOT NULL,
    nivel TEXT NOT NULL,
    padre TEXT,
    peso_gba REAL NOT NULL,
    vigente_desde TEXT NOT NULL,
    PRIMARY KEY (codigo, vigente_desde)
);

CREATE TABLE IF NOT EXISTS corridas_diarias (
    fecha TEXT PRIMARY KEY,
    n_filas_leidas INTEGER,
    n_mapeadas INTEGER,
    n_sin_mapear INTEGER,
    tasa_mapeo REAL,
    ejecutado_en TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _migrar(con: sqlite3.Connection) -> None:
    """Agrega columnas nuevas a bases creadas por versiones anteriores.

    POR QUE: al sumar el etiquetado por region aparecio que una base vieja
    (sin la columna `region`) hacia fallar todo el arranque. Preferimos
    migrar en silencio a obligar a borrar y recargar dias que quiza ya no
    se pueden volver a descargar — recordar que SEPA solo conserva 7 dias.
    """
    cur = con.execute("PRAGMA table_info(precios_raw)")
    columnas = {fila[1] for fila in cur.fetchall()}
    if not columnas:
        return  # tabla nueva, la crea el SCHEMA
    if "region" not in columnas:
        con.execute("ALTER TABLE precios_raw ADD COLUMN region TEXT")
        con.commit()


def conectar(path: Path) -> sqlite3.Connection:
    # check_same_thread=False es necesario para Streamlit: la conexion se
    # guarda en cache (@st.cache_resource) y Streamlit puede reutilizarla
    # desde un hilo distinto al que la creo en cada re-corrida de la app.
    # Sin esto, sqlite3 tira "ProgrammingError: SQLite objects created in
    # a thread can only be used in that same thread" apenas se interactua
    # con un widget. Es seguro en este caso porque la app de Streamlit SOLO
    # LEE de la base — nunca escribe — y SQLite permite lecturas
    # concurrentes sin problema.
    con = sqlite3.connect(path, check_same_thread=False)
    # WAL (Write-Ahead Logging): permite que lecturas y una escritura
    # convivan sin bloquearse mutuamente. Sin esto, si dos personas entran
    # a la app al mismo tiempo justo cuando se esta reconstruyendo la base
    # (ver scripts/reconstruir.py y el arranque de app_streamlit.py), una
    # puede toparse con "database is locked" — que fue exactamente lo que
    # paso en produccion. No es la solucion completa (ver el arreglo real
    # en app_streamlit.py, que evita que la reconstruccion se dispare mas
    # de una vez), pero es una capa extra de seguridad barata.
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA foreign_keys = ON")
    _migrar(con)
    con.executescript(SCHEMA)
    return con


def insertar_observaciones(
    con: sqlite3.Connection, observaciones: list[tuple[ObservacionVariedad, str]]
) -> int:
    """Inserta observaciones nuevas. Usa INSERT OR IGNORE sobre la UNIQUE
    (fecha, ean_o_id, comercio, fuente): si corrés el script dos veces para
    el mismo día no duplica filas — es seguro re-ejecutar.

    De paso, actualiza la tabla `productos` con el último nombre visto de
    cada ean_o_id — así los reportes pueden mostrar "Banana" en vez de un
    código. Se guarda el ÚLTIMO nombre, no el primero: si SEPA cambia
    ligeramente la descripción de un producto de un día a otro, el
    identificador (ean_o_id) sigue siendo el mismo y el reporte usa la
    descripción más reciente.
    """
    filas = [
        (o.fecha, o.ean_o_id, clase, o.comercio, o.precio, o.region)
        for o, clase in observaciones
    ]
    cur = con.executemany(
        """INSERT OR IGNORE INTO precios_raw
           (fecha, ean_o_id, clase_codigo, comercio, precio, region)
           VALUES (?, ?, ?, ?, ?, ?)""",
        filas,
    )

    # Se guarda un nombre para TODOS los productos vistos, no solo los que
    # traen descripcion real. Antes, si `o.nombre_producto` venia vacio
    # (pasa en la practica: algunos comercios chicos no completan ese
    # campo en SEPA), la fila en `productos` directamente NUNCA SE CREABA
    # — el precio quedaba en precios_raw pero sin ninguna fila
    # correspondiente en productos. Eso es indistinguible de "nunca se
    # cargo este producto" para nombres_de_productos(), que solo puede
    # mostrar el codigo como respaldo cuando no encuentra la fila. Ahora
    # se guarda el codigo COMO nombre explicitamente en ese caso.
    #
    # El "ganador" cuando hay varios nombres para un mismo ean_o_id en
    # este mismo lote se resuelve ACA, en Python (no con SQL dinamico
    # dependiente de la version de sqlite3): un nombre real siempre le
    # gana a un codigo-como-nombre, y entre dos nombres reales gana el
    # ultimo visto — mismo criterio que ya describia el docstring de
    # arriba, ahora tambien aplicado dentro de un mismo lote de insercion.
    mejor_nombre: dict[str, tuple[str, bool]] = {}
    for o, _clase in observaciones:
        es_real = bool(o.nombre_producto)
        candidato = o.nombre_producto if es_real else o.ean_o_id
        anterior = mejor_nombre.get(o.ean_o_id)
        if anterior is None or es_real or not anterior[1]:
            mejor_nombre[o.ean_o_id] = (candidato, es_real)

    nombres_reales = [(ean, nombre) for ean, (nombre, real) in mejor_nombre.items() if real]
    nombres_placeholder = [(ean, nombre) for ean, (nombre, real) in mejor_nombre.items() if not real]

    if nombres_reales:
        con.executemany(
            """INSERT INTO productos (ean_o_id, nombre_producto, actualizado_en)
               VALUES (?, ?, datetime('now'))
               ON CONFLICT(ean_o_id) DO UPDATE SET
                   nombre_producto = excluded.nombre_producto,
                   actualizado_en = excluded.actualizado_en""",
            nombres_reales,
        )
    if nombres_placeholder:
        # INSERT OR IGNORE: si ya existe una fila (con nombre real o con
        # otro placeholder de una carga anterior), NO se pisa — nunca
        # queremos que un placeholder reemplace algo que ya estaba.
        con.executemany(
            """INSERT OR IGNORE INTO productos (ean_o_id, nombre_producto, actualizado_en)
               VALUES (?, ?, datetime('now'))""",
            nombres_placeholder,
        )

    con.commit()
    return cur.rowcount


def precios_de_clase_en_mes(
    con: sqlite3.Connection, clase_codigo: str, mes: str
) -> list[float]:
    """`mes` en formato 'YYYY-MM'. Devuelve TODOS los precios crudos de esa
    clase en ese mes, mezclados entre productos distintos — sirve para
    mostrar un nivel de precio de referencia ("promedio parcial: $X"),
    pero NO es la base del cálculo de variación oficial de la clase desde
    que existe `precios_por_producto_en_mes` (ver engine/reporte.py):
    mezclar productos de unidades y pesos distintos en una sola bolsa
    subestima o sobreestima según qué producto tenga más observaciones
    ese mes, no según cuánto pesa realmente en el consumo. Se deja acá
    porque sigue siendo útil como número de contexto, no como el dato
    final."""
    cur = con.execute(
        "SELECT precio FROM precios_raw WHERE clase_codigo = ? AND fecha LIKE ?",
        (clase_codigo, f"{mes}%"),
    )
    return [row[0] for row in cur.fetchall()]


def precios_por_producto_en_mes(
    con: sqlite3.Connection, clase_codigo: str, mes: str,
    region: str | None = None
) -> dict[str, list[float]]:
    """Igual que la anterior, pero SIN mezclar productos: devuelve
    {ean_o_id: [precios del mes]}. Es el insumo correcto para calcular la
    variación de una clase (ver engine/reporte.py): primero se promedia
    cada producto por separado, después se combinan con un peso — nunca
    se deben promediar directamente precios de productos distintos."""
    if region:
        cur = con.execute(
            """SELECT ean_o_id, precio FROM precios_raw
               WHERE clase_codigo = ? AND fecha LIKE ? AND region = ?""",
            (clase_codigo, f"{mes}%", region),
        )
    else:
        cur = con.execute(
            "SELECT ean_o_id, precio FROM precios_raw WHERE clase_codigo = ? AND fecha LIKE ?",
            (clase_codigo, f"{mes}%"),
        )
    resultado: dict[str, list[float]] = {}
    for ean_o_id, precio in cur.fetchall():
        resultado.setdefault(ean_o_id, []).append(precio)
    return resultado


def precios_por_producto_en_rango(
    con: sqlite3.Connection, clase_codigo: str, desde: str, hasta: str,
    region: str | None = None
) -> dict[str, list[float]]:
    """Igual que `precios_por_producto_en_mes` pero para un rango de fechas
    arbitrario [desde, hasta], ambas inclusive, en formato 'YYYY-MM-DD'.
    Sirve para comparar, por ejemplo, la semana 2 de agosto contra la
    semana 1 — algo que la comparación mes-contra-mes no permite.

    Se compara por rangos de igual longitud para que tenga sentido: no
    tiene sentido comparar una semana contra un mes entero. Quien llama es
    responsable de pasar rangos comparables (ver scripts/consultar.py)."""
    if region:
        cur = con.execute(
            """SELECT ean_o_id, precio FROM precios_raw
               WHERE clase_codigo = ? AND fecha >= ? AND fecha <= ? AND region = ?""",
            (clase_codigo, desde, hasta, region),
        )
    else:
        cur = con.execute(
            """SELECT ean_o_id, precio FROM precios_raw
               WHERE clase_codigo = ? AND fecha >= ? AND fecha <= ?""",
            (clase_codigo, desde, hasta),
        )
    resultado: dict[str, list[float]] = {}
    for ean_o_id, precio in cur.fetchall():
        resultado.setdefault(ean_o_id, []).append(precio)
    return resultado


def valores_diarios_de_clase(
    con: sqlite3.Connection, clase_codigo: str, mes: str
) -> list[tuple[str, float]]:
    """Para cada día del mes con datos, el precio promedio (media
    geométrica) de la clase ese día. Devuelve [(fecha, promedio), ...]
    ordenado por fecha. Es el insumo del cálculo de piso a fin de mes
    (engine/arrastre.py): necesita la serie día a día, no el pool del mes."""
    import math

    cur = con.execute(
        """SELECT fecha, precio FROM precios_raw
           WHERE clase_codigo = ? AND fecha LIKE ?
           ORDER BY fecha""",
        (clase_codigo, f"{mes}%"),
    )
    por_dia: dict[str, list[float]] = {}
    for fecha, precio in cur.fetchall():
        por_dia.setdefault(fecha, []).append(precio)

    serie = []
    for fecha in sorted(por_dia):
        precios = por_dia[fecha]
        geo = math.exp(sum(math.log(p) for p in precios) / len(precios))
        serie.append((fecha, geo))
    return serie


def valores_diarios_por_producto(
    con: sqlite3.Connection, clase_codigo: str, mes: str
) -> dict[str, list[tuple[str, float]]]:
    """Serie diaria por producto: {ean_o_id: [(fecha, precio_promedio_dia)]}.

    Es el insumo para calcular ESCENARIOS DE CIERRE POR PRODUCTO, que es lo
    que permite que el simulador deje tocar el valor de un producto puntual
    y recalcular la categoria. Sin esto solo se pueden hacer escenarios a
    nivel categoria, que es mas grueso.

    El promedio diario por producto es geometrico sobre los comercios que
    reportaron ese producto ese dia."""
    import math

    cur = con.execute(
        """SELECT ean_o_id, fecha, precio FROM precios_raw
           WHERE clase_codigo = ? AND fecha LIKE ?
           ORDER BY ean_o_id, fecha""",
        (clase_codigo, f"{mes}%"),
    )
    acumulado: dict[str, dict[str, list[float]]] = {}
    for ean, fecha, precio in cur.fetchall():
        acumulado.setdefault(ean, {}).setdefault(fecha, []).append(precio)

    resultado: dict[str, list[tuple[str, float]]] = {}
    for ean, por_dia in acumulado.items():
        serie = []
        for fecha in sorted(por_dia):
            precios = por_dia[fecha]
            geo = math.exp(sum(math.log(p) for p in precios) / len(precios))
            serie.append((fecha, geo))
        resultado[ean] = serie
    return resultado


def nombres_de_productos(con: sqlite3.Connection, eans: list[str]) -> dict[str, str]:
    """Resuelve ean_o_id -> nombre_producto para mostrar en reportes. Si un
    producto no tiene nombre guardado (no debería pasar si vino de
    parser.py, pero puede pasar con datos cargados a mano), devuelve el
    propio ean_o_id como nombre — nunca deja un hueco en blanco."""
    if not eans:
        return {}
    placeholders = ",".join("?" * len(eans))
    cur = con.execute(
        f"SELECT ean_o_id, nombre_producto FROM productos WHERE ean_o_id IN ({placeholders})",
        eans,
    )
    encontrados = dict(cur.fetchall())
    return {e: encontrados.get(e, e) for e in eans}


def registrar_corrida(con: sqlite3.Connection, fecha: str, stats: dict) -> None:
    con.execute(
        """INSERT OR REPLACE INTO corridas_diarias
           (fecha, n_filas_leidas, n_mapeadas, n_sin_mapear, tasa_mapeo)
           VALUES (?, ?, ?, ?, ?)""",
        (fecha, stats["n_filas"], stats["n_mapeadas"], stats["n_sin_mapear"], stats["tasa_mapeo"]),
    )
    con.commit()


def regiones_disponibles(con: sqlite3.Connection) -> list[str]:
    """Regiones que efectivamente tienen datos cargados."""
    cur = con.execute("SELECT DISTINCT region FROM precios_raw WHERE region <> '' ORDER BY 1")
    return [r[0] for r in cur.fetchall()]
