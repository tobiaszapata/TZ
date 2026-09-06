"""
Tests de config.canasta: navegación división > grupo > clase, y
verificación de que los pesos coinciden con la fuente oficial de INDEC.

CONTEXTO: se había empezado a construir un cuarto nivel (subclase) para
el desglose, pero el usuario señaló correctamente que INDEC no publica
ponderadores oficiales por debajo de clase — subclase hubiera exigido
inventar pesos sin fuente verificable. La decisión final fue mostrar
división > grupo > clase (los tres niveles con ponderador oficial
confirmado) y, dentro de una clase, ir directo a los productos reales de
SEPA — sin agregar un nivel de clasificación intermedio adicional.
"""

import math

from config.canasta import (
    CANASTA, clases_de_division, clases_de_grupo, divisiones, grupos_de_division,
)


def test_grupos_de_division_devuelve_los_grupos_correctos():
    grupos = grupos_de_division("01")
    codigos = {g.codigo for g in grupos}
    assert codigos == {"01.1", "01.2"}


def test_clases_de_grupo_devuelve_las_clases_correctas():
    clases = clases_de_grupo("01.1")
    codigos = {c.codigo for c in clases}
    assert "01.1.1" in codigos  # Pan y cereales
    assert "01.1.2" in codigos  # Carnes y derivados
    assert "01.2.1" not in codigos  # eso es de OTRO grupo (01.2)


def test_grupos_de_una_division_suman_el_peso_de_la_division():
    """Coherencia interna: los grupos de una division tienen que sumar
    (aprox) el peso oficial de esa division."""
    for d in divisiones():
        grupos = grupos_de_division(d.codigo)
        if not grupos:
            continue  # divisiones sin ningun grupo declarado (huecos ya documentados)
        suma_grupos = sum(g.peso("GBA") for g in grupos)
        assert math.isclose(suma_grupos, d.peso("GBA"), abs_tol=0.002), (
            f"división {d.codigo}: grupos suman {suma_grupos}, "
            f"división dice {d.peso('GBA')}"
        )


def test_clases_de_un_grupo_suman_el_peso_del_grupo():
    for d in divisiones():
        for g in grupos_de_division(d.codigo):
            clases = clases_de_grupo(g.codigo)
            if not clases:
                continue
            suma_clases = sum(c.peso("GBA") for c in clases)
            assert math.isclose(suma_clases, g.peso("GBA"), abs_tol=0.002), (
                f"grupo {g.codigo}: clases suman {suma_clases}, grupo dice {g.peso('GBA')}"
            )


def test_clases_de_division_sigue_funcionando_igual_que_antes():
    """La función vieja (usada en el resto del proyecto) no debe romperse
    con el agregado de las funciones nuevas de navegación por grupo."""
    clases_directo = {c.codigo for c in clases_de_division("01")}
    clases_por_grupo = set()
    for g in grupos_de_division("01"):
        clases_por_grupo.update(c.codigo for c in clases_de_grupo(g.codigo))
    assert clases_directo == clases_por_grupo


def test_grupo_sin_ninguna_clase_declarada_tiene_peso_oficial_propio():
    """Caso real reportado: dentro de 'Bebidas alcoholicas y tabaco', el
    grupo Tabaco (02.2) no tenia NINGUNA clase hija declarada — antes,
    la interfaz simplemente lo saltaba sin ningun aviso, dando la
    impresion de que 'Bebidas alcoholicas y tabaco' estaba completo.
    Este test confirma que el grupo SI tiene su propio peso oficial
    declarado (para poder mostrarlo con una aclaracion explicita de que
    SEPA no lo releva, en vez de ocultarlo)."""
    tabaco = grupos_de_division("02")
    grupo_tabaco = next(g for g in tabaco if g.codigo == "02.2")
    assert grupo_tabaco.peso("GBA") > 0
    assert clases_de_grupo("02.2") == [], (
        "se esperaba que Tabaco no tuviera ninguna clase hija declarada — "
        "si esto cambio, la logica de la interfaz para este caso puede "
        "necesitar revisarse"
    )


def test_bebidas_alcoholicas_si_tiene_clases_declaradas():
    """Contraste: el grupo 02.1 (Bebidas alcoholicas) SI tiene sus 3
    clases medidas, a diferencia de Tabaco."""
    clases = clases_de_grupo("02.1")
    codigos = {c.codigo for c in clases}
    assert codigos == {"02.1.1", "02.1.2", "02.1.3"}
