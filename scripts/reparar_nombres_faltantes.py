#!/usr/bin/env python3
"""
Repara productos que tienen precio guardado pero nunca llegaron a tener
una fila en la tabla de nombres (el bug de descripción vacía — ver
storage/db.py::insertar_observaciones y tests/test_nombre_producto_vacio.py).

    python -m scripts.reparar_nombres_faltantes

Encuentra todo `ean_o_id` que aparece en `precios_raw` pero no en
`productos`, y les crea una fila con el propio código como nombre
explícito — para que a partir de ahora tengan un registro consultable en
vez de estar ausentes en silencio. Si en una carga futura llega el nombre
real de ese producto, lo reemplaza automáticamente.

Se corre UNA VEZ para poner al día una base que ya tenía el problema.
"""

from __future__ import annotations

from pathlib import Path

from storage.db import conectar

DB_PATH = Path("relevamiento_precios.db")


def main() -> None:
    if not DB_PATH.exists():
        print(f"No encuentro la base {DB_PATH}.")
        return

    con = conectar(DB_PATH)
    cur = con.execute(
        """SELECT DISTINCT p.ean_o_id FROM precios_raw p
           LEFT JOIN productos pr ON pr.ean_o_id = p.ean_o_id
           WHERE pr.ean_o_id IS NULL"""
    )
    faltantes = [r[0] for r in cur.fetchall()]

    if not faltantes:
        print("No hay ningún producto sin nombre registrado. Nada para reparar.")
        con.close()
        return

    print(f"Encontrados {len(faltantes):,} productos con precio pero sin nombre registrado.")
    con.executemany(
        "INSERT OR IGNORE INTO productos (ean_o_id, nombre_producto, actualizado_en) "
        "VALUES (?, ?, datetime('now'))",
        [(ean, ean) for ean in faltantes],
    )
    con.commit()
    con.close()

    print("Reparados: se creó una fila con el código como nombre para cada uno.")
    print("Si en algún momento se carga un día donde ese producto sí trae su descripción")
    print("real, el nombre se actualiza solo — no hace falta correr esto de nuevo por eso.")
    print("\nPara que el respaldo (historico/) refleje el arreglo:")
    print("  python -m scripts.exportar_dia --rehacer")
    print('  git add historico/ && git commit -m "reparar nombres" && git push')


if __name__ == "__main__":
    main()
