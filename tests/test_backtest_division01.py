"""
Este archivo NO prueba código nuevo — prueba que el motor de agregación
(engine/agregacion.py) reproduce lo que INDEC efectivamente publicó, cuando
se lo alimenta con los propios números que INDEC publicó.

Es el test más importante del proyecto y el único que toca datos reales.
Todos los valores de abajo (variaciones % y pesos) salen de los archivos
que nos pasaste, extraídos programáticamente en esta misma sesión — no
están tipeados de memoria. Están citados con su fuente exacta.

Fuente: sh_ipc_aperturas.xls, hoja "Variación mensual aperturas",
        bloque "Región GBA", columna 2026-07.
        sh_ipc_08_26.xls, hoja "Variación mensual IPC Nacional",
        bloque "Región GBA", columna 2026-07 (se usa para el segundo
        chequeo, independiente, de que la división coincide entre los
        dos archivos que INDEC publica por separado).

QUÉ SE VALIDA:
1. División 01 completa: combinar los DOS grupos (Alimentos + Bebidas no
   alcohólicas) con sus pesos reproduce el número de división que INDEC
   publicó. Acá no falta ningún dato — los dos grupos agotan la división,
   así que este es el test "limpio".

2. Grupo Alimentos con 7 de 9 clases: acá se documenta, a propósito, el
   límite de lo que se puede reconstruir SOLO con datos públicos a nivel
   clase. "Pescados y mariscos" y "Otros alimentos" (0,80 pp de peso
   combinado) no se publican como fila propia en sh_ipc_aperturas, así que
   no se pueden validar por separado con este archivo. Se reporta la
   brecha en vez de esconderla.
"""

import math

from engine.agregacion import laspeyres

# --- Datos reales, región GBA, variación mensual julio 2026 (%) -----------
VAR_GRUPO_ALIMENTOS_JUL26 = 2.5            # "Alimentos" (01.1)
VAR_GRUPO_BEBIDAS_NOALC_JUL26 = 2.0        # "Bebidas no alcohólicas" (01.2)
VAR_DIVISION_01_PUBLICADA_JUL26 = 2.4      # "Alimentos y bebidas no alcohólicas"
# ^ este mismo valor (2.4) aparece igual en sh_ipc_aperturas Y en
#   sh_ipc_08_26 — ya es, en sí mismo, una confirmación cruzada de que la
#   extracción de datos es consistente entre los dos archivos de INDEC.

PESO_GRUPO_ALIMENTOS_GBA = 0.2033
PESO_GRUPO_BEBIDAS_NOALC_GBA = 0.0311

VAR_CLASES_ALIMENTOS_JUL26 = {
    "01.1.1": 1.7,   # Pan y cereales
    "01.1.2": 0.0,   # Carnes y derivados
    "01.1.4": 3.4,   # Leche, productos lácteos y huevos
    "01.1.5": 2.6,   # Aceites, grasas y manteca
    "01.1.6": 7.4,   # Frutas
    "01.1.7": 9.0,   # Verduras, tubérculos y legumbres
    "01.1.8": 2.1,   # Azúcar, dulces, chocolate, golosinas, etc.
    # 01.1.3 (Pescados y mariscos) y 01.1.9 (Otros alimentos): no
    # publicados como fila propia en sh_ipc_aperturas.
}
PESOS_CLASES_ALIMENTOS_GBA = {
    "01.1.1": 0.0405,
    "01.1.2": 0.0698,
    "01.1.3": 0.0051,  # Pescados y mariscos — sin variación publicada
    "01.1.4": 0.0345,
    "01.1.5": 0.0055,
    "01.1.6": 0.0127,
    "01.1.7": 0.0223,
    "01.1.8": 0.0101,
    "01.1.9": 0.0029,  # Otros alimentos — sin variación publicada
}


def test_backtest_division_01_completa_dos_grupos():
    """Test limpio: no falta ningún componente."""
    r = laspeyres(
        variaciones_pct={
            "01.1": VAR_GRUPO_ALIMENTOS_JUL26,
            "01.2": VAR_GRUPO_BEBIDAS_NOALC_JUL26,
        },
        pesos={
            "01.1": PESO_GRUPO_ALIMENTOS_GBA,
            "01.2": PESO_GRUPO_BEBIDAS_NOALC_GBA,
        },
    )
    assert math.isclose(r.cobertura, 1.0)

    gap = abs(r.variacion_pct - VAR_DIVISION_01_PUBLICADA_JUL26)
    print(
        f"\n[backtest división 01] reconstruido={r.variacion_pct:.4f}%  "
        f"publicado={VAR_DIVISION_01_PUBLICADA_JUL26}%  "
        f"brecha={gap:.4f} pp  (cobertura {r.cobertura:.0%})"
    )
    # tolerancia generosa por el redondeo a 1 decimal de los insumos
    # publicados (2.5 y 2.0 ya vienen redondeados) — no por debilidad del
    # método de agregación.
    assert gap < 0.1, "la agregación de los dos grupos debería reproducir la división casi exacto"


def test_backtest_grupo_alimentos_7_de_9_clases_documenta_la_brecha():
    """Test con cobertura incompleta a propósito: mide y muestra el límite
    real de lo que se puede validar con datos 100% públicos a nivel clase,
    en vez de ocultarlo."""
    r = laspeyres(
        variaciones_pct=VAR_CLASES_ALIMENTOS_JUL26,
        pesos=PESOS_CLASES_ALIMENTOS_GBA,
    )
    peso_faltante = PESOS_CLASES_ALIMENTOS_GBA["01.1.3"] + PESOS_CLASES_ALIMENTOS_GBA["01.1.9"]

    gap = r.variacion_pct - VAR_GRUPO_ALIMENTOS_JUL26
    print(
        f"\n[backtest Alimentos, 7/9 clases] reconstruido={r.variacion_pct:.4f}%  "
        f"publicado={VAR_GRUPO_ALIMENTOS_JUL26}%  brecha={gap:+.4f} pp  "
        f"cobertura={r.cobertura:.1%}  "
        f"(peso no observable en este archivo: {peso_faltante:.4f} = "
        f"{peso_faltante / PESO_GRUPO_ALIMENTOS_GBA:.1%} del grupo)"
    )
    assert r.cobertura > 0.9, "con 7 de 9 clases deberíamos cubrir más del 90% del peso del grupo"
    # tolerancia amplia: sabemos que hay una brecha explicable, no estamos
    # afirmando que da exacto — estamos afirmando que la brecha es chica y
    # está explicada por el peso faltante, no por un error de cálculo.
    assert abs(gap) < 0.5, "una brecha más grande que esto ya no se explicaría solo por las 2 clases faltantes"
