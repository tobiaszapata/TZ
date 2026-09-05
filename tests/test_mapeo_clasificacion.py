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
    coincidencias falsas.

    NOTA: 'P HIG' (papel higienico) se movio de 05.6.1 a 12.1.3 tras
    auditar la definicion oficial completa de INDEC — ver
    docs/coicop_notas_explicativas.md, subclase 12.1.3.1, que dice
    explicitamente 'papel higienico' como descartable de cuidado
    personal, no de limpieza del hogar."""
    assert clasificar("JAB TOC ANTIBACTERIA") == "12.1.3"
    assert clasificar("CREM DENT TRIP BENEF") == "12.1.3"
    assert clasificar("TAMPON SUPER") == "12.1.3"
    assert clasificar("SH ANTI CAIDA ROMERO") == "12.1.3"
    assert clasificar("P HIG DOBLE HOJA 30M") == "12.1.3"
    assert clasificar("LAVAVAJI BIOACT LIMA") == "05.6.1"


def test_baguette_es_pan_y_cereales():
    assert clasificar("BAGUETTE") == "01.1.1"


def test_snacks_de_cereales_van_a_pan_y_cereales_no_a_lacteos():
    """Hallazgo del documento README_Metodologia_INDEC.pdf subido por el
    usuario: los snacks a base de cereal/maiz van con panificados (misma
    logica de 'finalidad del gasto' que separa mascotas de carnes), no
    con la materia prima que evoca su sabor. Bug real encontrado:
    'CHIZITOS QUESO' caia en Lacteos (01.1.4) por la palabra suelta
    'queso', en vez de en Pan y cereales (01.1.1)."""
    assert clasificar("NACHOS SABOR ORIGINAL") == "01.1.1"
    assert clasificar("CHIZITOS QUESO") == "01.1.1"
    assert clasificar("PALITOS SALADOS") == "01.1.1"
    # el caso real que motivo la exclusion: sigue siendo lacteo
    assert clasificar("QUESO CREMOSO") == "01.1.4"


def test_leberwurst_y_pate_son_carnes():
    assert clasificar("LEBERWURST") == "01.1.2"
    assert clasificar("PATE DE HIGADO") == "01.1.2"


def test_caldo_de_verdura_es_otros_alimentos_no_verdura():
    """Bug real: la palabra suelta 'verdura' en la regla de Verduras
    (01.1.7) se robaba 'CALDO DE VERDURA', que es un producto procesado
    y deberia ir a Otros alimentos (01.1.9) junto con 'caldo' comun."""
    assert clasificar("CALDO DE VERDURA") == "01.1.9"
    assert clasificar("CALDO DE POLLO") == "01.1.9"
    # las verduras frescas reales siguen funcionando
    assert clasificar("ZANAHORIA X KG") == "01.1.7"
    assert clasificar("VERDURA MIXTA CONGELADA") == "01.1.7"  # esto SI es verdura


def test_polvo_de_hornear_es_otros_alimentos():
    assert clasificar("POLVO DE HORNEAR") == "01.1.9"


def test_preservativos_son_salud_no_cuidado_personal():
    """CORREGIDO: se había puesto antes en Cuidado personal (12.1.3) por
    intuición propia, sin leer la definición oficial completa de INDEC.
    El documento COICOP Argentina (docs/coicop_notas_explicativas.md,
    subclase 06.1.2) dice explícitamente: "elementos para primeros
    auxilios... termómetros, preservativos" — van en Salud (06.1.2), no
    en Cuidado personal. Esta es una corrección real de un error de
    clasificación, no un ajuste de abreviatura."""
    assert clasificar("PRESERVATIVOS X3") == "06.1.2"


def test_aluminio_y_pilas_son_limpieza_del_hogar_sin_atrapar_bazar():
    """Del documento de INDEC: rollo/papel de aluminio y pilas van con
    'bienes para el hogar' (05.6.1). Se verifica ademas que la palabra
    NO sea tan generica como para atrapar ollas o sartenes de aluminio,
    que van a Bazar (05.4.1) — ese fue un riesgo real detectado antes
    de agregar la regla."""
    assert clasificar("ROLLO DE ALUMINIO") == "05.6.1"
    assert clasificar("PAPEL ALUMINIO 30M") == "05.6.1"
    assert clasificar("PILAS AA X4") == "05.6.1"
    # riesgo de colision verificado: utensilios de cocina de aluminio
    # tienen que seguir yendo a Bazar, no a Limpieza del hogar
    assert clasificar("OLLA DE ALUMINIO") == "05.4.1"
    assert clasificar("SARTEN ALUMINIO ANTIADHERENTE") == "05.4.1"


def test_pistola_de_agua_es_juguete_no_bebida():
    """Bug real reportado por el usuario: 'PISTOLA AGUA C/GAS' caía en
    Aguas y bebidas (01.2.2) por las abreviaturas sueltas de gas
    ('s/gas', 'c/gas') agregadas para capturar 'agua con/sin gas'. Según
    la definición oficial de INDEC (docs/coicop_notas_explicativas.md,
    subclase 09.3.1: 'juguetes de todo tipo'), una pistola de agua es
    un juguete. Corregido exigiendo que las claves de gas aparezcan
    junto a la palabra 'agua' real, y agregando el patrón específico
    'pistola...agua' a la regla de juguetes (que está antes en el orden
    de evaluación)."""
    assert clasificar("PISTOLA AGUA C/GAS") == "09.3.1"
    assert clasificar("PISTOLA AGUA JUGUETE") == "09.3.1"

    # el agua real, con o sin gas, tiene que seguir clasificando bien
    assert clasificar("AGUA S/GAS MINERAL") == "01.2.2"
    assert clasificar("AGUA C/GAS 1.5L") == "01.2.2"
    assert clasificar("AGUA MINERAL S/GAS") == "01.2.2"

    # riesgo de colision verificado: "pistola" sola no debe matchear
    # herramientas de ferreteria (pistola de silicona)
    assert clasificar("PISTOLA SILICONA CALIENTE") is None


def test_libros_infantiles_de_actividades_van_a_juguetes():
    """Hallazgo real al analizar volumen disperso de SEPA: el 100% de las
    123 descripciones con 'libro' encontradas en 2 dias reales resultaron
    ser libros de colorear/actividades con licencias infantiles (Toy
    Story, Bluey, Star Wars, etc.), no libros de lectura — segun el
    documento oficial de INDEC, estos van a Juguetes (09.3.1), no a
    Libros (09.5.1). Se verifico que la subclase 09.5.1 (libros de
    lectura reales) no tiene volumen real en SEPA, asi que no se declaro
    medida."""
    assert clasificar("LB PAW PATROL MI LIBRO ACTIVIDADES") == "09.3.1"
    assert clasificar("LB MI GRAN LIBRO DE LAS EMOCIONES") == "09.3.1"
    assert clasificar("LIBRO CUENTOS CLASICOS BLANCANIEVES 1UN") == "09.3.1"
    assert clasificar("LB STITCH DESTROZA ESTE LIBRO") == "09.3.1"
    assert clasificar("LB STITCH Y ANGEL DESTROZAN ESTE LIBRO") == "09.3.1"

    # casos ambiguos (posibles novelas reales con numero de tomo) tienen
    # que seguir sin clasificar, no forzarse a Juguetes
    assert clasificar("LB EL DIABLO REGRESA (LIBRO 3)") is None
    assert clasificar("LIBRO UNA HERMANA ANORMAL") is None


def test_medios_de_grabacion_se_clasifican():
    """Verificado con 23 productos reales de SEPA (Kingston, Maxell,
    HikSemi, SanDisk) en 3 dias."""
    assert clasificar("PENDRIVE 64GB USB 2") == "09.1.4"
    assert clasificar("MEMORIA 128 GB KINGSTON MICROSD CLASE10") == "09.1.4"
    assert clasificar("MEMORIA MICROSD HIKSEMI 32GB CON ADAPTADOR") == "09.1.4"


def test_accesorios_para_vestir_se_clasifican_sin_atrapar_adornos():
    """Verificado con 146 coincidencias reales de SEPA (billeteras,
    bufandas, gorros). Se excluye explicitamente un caso real de
    adorno navideno encontrado (ADORNO GNOMO C GORRO) que colisionaba
    con la palabra suelta 'gorro'."""
    assert clasificar("BILLETERA BOOK PU 10.7X8.8CM") == "03.1.3"
    assert clasificar("BUFANDA LISA HOMBRE") == "03.1.3"
    assert clasificar("GORRO DE LANA DAMAS") == "03.1.3"
    assert clasificar("ADORNO GNOMO C GORRO 6X16 CM") is None


def test_hilado_no_se_confunde_con_queso_hilado():
    """Verificacion negativa: se investigo declarar Materiales textiles
    (03.1.1) para hilados de tejer, pero el 100% del volumen real de
    'hilado' en SEPA resulto ser queso hilado (Nonna Pia, Vacalin,
    Lucrecia) — ya clasificado correctamente como lacteo. Por eso no se
    declaro esa subclase como medida: no habia volumen textil real."""
    assert clasificar("QUES.D/CAMP.HILADO AHUMADO NONNA PIA PAQ 210 GRM") == "01.1.4"
    assert clasificar("QUESO PROVOLONE HILADO LUCRECIA X KG.") == "01.1.4"


def test_ques_abreviado_es_queso_pero_sab_ques_es_snack():
    """Hallazgo real al verificar 'QUES.' abreviado: el patron distingue
    'QUES.D/CAMP...' (queso real, al inicio) de 'SAB.QUES...' (sabor a
    queso de un snack, no lacteo) — mismo tipo de ambiguedad que ya se
    corrigio con 'CHIZITOS QUESO'."""
    assert clasificar("QUES.MUZZAREL. SIN SAL VACALIN PAQ 500 GRM") == "01.1.4"
    assert clasificar("GALL.CRACK.SAB.QUES.KESITAS TRAVIATA PAQ 288 GRM") == "01.1.1"
    # "papas fritas sabor queso" es ambiguo (podria ir a snacks) y se deja
    # sin clasificar en vez de forzarlo a Verduras por la palabra "papa"
    assert clasificar("PAPAS FRITAS SAB.QUES.CREMA Y CEBOLLA LAYS PAQ 34 GRM") is None
