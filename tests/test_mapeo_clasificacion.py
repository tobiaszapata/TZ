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


def test_abreviaturas_reales_de_cerveza_y_bebidas_se_clasifican():
    """Hallazgo real: revisando con scripts/diagnosticar_mapeo.py que hay
    en el 'sin clasificar', aparecieron con mucha frecuencia abreviaturas
    que SEPA genera por limite de caracteres en algunos comercios: 'CERV'
    en vez de 'cerveza', 'GASEO' en vez de 'gaseosa', 'S/GAS' o 'C/GAS'
    en vez de 'sin gas'/'con gas'. Verificado contra 3 dias reales antes
    de agregarlas: sin coincidencias falsas con 'cervatillo' u otras
    palabras no relacionadas."""
    assert clasificar("CERV LATA") == "02.1.3"
    assert clasificar("CERV RUBIA") == "02.1.3"
    assert clasificar("GASEO COLA") == "01.2.2"
    assert clasificar("AGUA S/GAS MINERAL") == "01.2.2"
    assert clasificar("AGUA C/GAS") == "01.2.2"

    # el caso teorico de colision no aparecio en 40+ millones de filas
    # reales. Ademas, en la practica "CERVATILLO PELUCHE" ya cae en
    # Juguetes (09.3.1) por la palabra "peluche", que tiene su propia
    # regla ANTES en la lista — asi que ni siquiera llega a competir con
    # la de cerveza. Documentado para que quede claro por que.
    assert clasificar("CERVATILLO PELUCHE") == "09.3.1"


def test_abreviaturas_de_higiene_y_limpieza_se_clasifican():
    """Mismo hallazgo, para cuidado personal y limpieza del hogar:
    'JAB TOC' (jabon de tocador), 'CREM DENT' (crema dental), 'TAMPON',
    'P HIG' (papel higienico) y 'LAVAVAJI' (lavavajilla) — todas
    verificadas contra los 3 dias reales antes de agregarlas, sin
    coincidencias falsas."""
    assert clasificar("JAB TOC ANTIBACTERIA") == "12.1.3"
    assert clasificar("CREM DENT TRIP BENEF") == "12.1.3"
    assert clasificar("TAMPON SUPER") == "12.1.3"
    assert clasificar("SH ANTI CAIDA ROMERO") == "12.1.3"
    assert clasificar("P HIG DOBLE HOJA 30M") == "05.6.1"
    assert clasificar("LAVAVAJI BIOACT LIMA") == "05.6.1"


def test_baguette_es_pan_y_cereales():
    assert clasificar("BAGUETTE") == "01.1.1"
