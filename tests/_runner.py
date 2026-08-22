"""
Runner mínimo sin dependencias externas.

Por qué existe: este entorno donde escribí el proyecto no tiene salida de
red, así que no pude `pip install pytest`. Los archivos test_*.py de esta
carpeta son 100% compatibles con pytest (funciones `test_*` con `assert`
simple) — si vos tenés pytest instalado, correlos con `pytest tests/ -v` y
vas a tener mejor output. Esto es un sustituto liviano para poder probar
todo ACÁ, hoy, sin esa dependencia.
"""

import importlib
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

MODULOS = [
    "tests.test_index_elemental",
    "tests.test_imputacion",
    "tests.test_agregacion",
    "tests.test_arrastre",
    "tests.test_reporte",
    "tests.test_proyeccion",
    "tests.test_escenarios",
    "tests.test_zip_reader",
    "tests.test_paridad_js",
    "tests.test_consultas",
    "tests.test_fechas",
    "tests.test_threading_db",
    "tests.test_respaldo",
    "tests.test_nacional",
    "tests.test_backtest_division01",
]


def main() -> int:
    total, fallidos = 0, 0
    for nombre_modulo in MODULOS:
        modulo = importlib.import_module(nombre_modulo)
        funciones_test = [
            getattr(modulo, n) for n in dir(modulo)
            if n.startswith("test_") and callable(getattr(modulo, n))
        ]
        print(f"\n=== {nombre_modulo} ({len(funciones_test)} tests) ===")
        for fn in funciones_test:
            total += 1
            try:
                fn()
                print(f"  OK    {fn.__name__}")
            except AssertionError as e:
                fallidos += 1
                print(f"  FALLO {fn.__name__}: {e}")
            except Exception:
                fallidos += 1
                print(f"  ERROR {fn.__name__}:")
                traceback.print_exc()

    print(f"\n{'='*60}")
    print(f"Total: {total}   OK: {total - fallidos}   Fallidos: {fallidos}")
    return 1 if fallidos else 0


if __name__ == "__main__":
    raise SystemExit(main())
