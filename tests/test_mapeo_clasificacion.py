"""
Tests de collectors.sepa.mapeo.clasificar — las reglas que deciden en qué
subcategoría cae cada producto según su descripción de texto.
"""

from collectors.sepa.mapeo import clasificar


def test_algodon_medicinal_no_choca_con_textiles_del_hogar():
    """Bug real encontrado al auditar por qué las reglas de Textiles del
    hogar (05.2.1), ya escritas desde antes, nunca podían aplicarse: la
    regla de 'Otros productos medicinales' incluía la palabra suelta
    'algodón' (pensando en algodón hidrófilo de farmacia), y como esa
    regla está antes en la lista, se robaba cualquier producto textil que
    también mencionara 'algodón' en su composición (sábanas, toallas,
    acolchados). Corregido agregando una exclusión explícita."""
    assert clasificar("SABANA 2 PLAZAS 100% ALGODON") == "05.2.1"
    assert clasificar("TOALLON ALGODON GRANDE") == "05.2.1"
    assert clasificar("ACOLCHADO ALGODON KING") == "05.2.1"

    # el caso medicinal real tiene que seguir funcionando
    assert clasificar("ALGODON HIDROFILO 50G") == "06.1.2"
    assert clasificar("APOSITOS ADHESIVOS X10") == "06.1.2"


def test_bazar_del_hogar_se_clasifica_correctamente():
    assert clasificar("VASO VIDRIO X6") == "05.4.1"
    assert clasificar("OLLA ACERO INOXIDABLE 24CM") == "05.4.1"
    assert clasificar("JUEGO DE CUBIERTOS X24") == "05.4.1"


def test_prendas_de_vestir_se_clasifica_correctamente():
    """Categoría nueva: antes SEPA no aportaba nada a Prendas de vestir
    (0% medido, 5.76% de peso — la subcategoría pendiente más grande de
    todo el sistema). Se agregaron reglas basadas en palabras de bajo
    riesgo de ambigüedad con otras secciones de supermercado."""
    assert clasificar("REMERA ALGODON HOMBRE") == "03.1.2"
    assert clasificar("PANTALON JEAN MUJER") == "03.1.2"
    assert clasificar("CAMPERA INVIERNO NIÑO") == "03.1.2"
    assert clasificar("VESTIDO VERANO FLORES") == "03.1.2"


def test_ropa_no_choca_con_limpieza():
    """'Malla' de fideos o de otro alimento no debe caer en indumentaria
    (malla tambien significa 'traje de baño')."""
    assert clasificar("PAPEL HIGIENICO MALLA X4") != "03.1.2"


def test_calzado_se_clasifica_correctamente():
    """Categoría nueva: Zapatos y otros calzados, 2.09% de peso."""
    assert clasificar("ZAPATILLA DEPORTIVA RUNNING") == "03.2.1"
    assert clasificar("OJOTAS GOMA VERANO") == "03.2.1"
    assert clasificar("ALPARGATA LONA") == "03.2.1"
