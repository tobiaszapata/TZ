"""
Mapeo de producto SEPA -> clase COICOP.

ESTE ES EL ACTIVO CENTRAL DEL PROYECTO, no el scraper. Ya lo hablamos: el
scraping es plomería, el mapeo es el trabajo intelectual. Y por eso hay que
ser honesto sobre en qué estado está.

DOS NIVELES DE CONFIANZA, A PROPÓSITO:

1. REGLAS POR PALABRA CLAVE (lo que hay acá abajo): bootstrap para arrancar
   sin haber visto un solo archivo real de SEPA todavía. Son best-effort,
   en español rioplatense, pensadas para clasificar por texto libre de
   "nombre_producto" — parecido a cómo INDEC define sus "especificaciones
   abiertas" (Metodología 32, sección 2.4: una descripción genérica en vez
   de un código cerrado). Van a tener falsos positivos y negativos.

2. EAN FIJADO A MANO (mapeo_ean, vacío por ahora): una vez que corras esto
   contra un archivo real, mirá qué EAN aparecen con más frecuencia en cada
   clase y fijalos acá con el código exacto. Un EAN fijado siempre le gana
   a una regla de texto — así el sistema converge con el uso, en vez de
   depender para siempre de reglas de texto ambiguas. Esto es al revés de
   cómo lo hacía el proyecto anterior, que buscaba por término libre TODOS
   los días ("smart tv", "notebook") sin nunca fijar identidad estable.

NO INVENTAMOS CÓDIGOS EAN ACÁ. Cualquier EAN de ejemplo sería falso — los
reales solo se conocen mirando un archivo real de SEPA, que este entorno no
puede descargar (ver el aviso en schema.py). El diccionario `mapeo_ean`
queda vacío a propósito, con la estructura lista para completarlo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ReglaClase:
    clase_codigo: str
    incluir: list[str]     # patrones regex, cualquiera que matchee alcanza
    excluir: list[str] = None  # patrones que descalifican aunque matcheó "incluir"

    def __post_init__(self):
        if self.excluir is None:
            self.excluir = []


def normalizar(texto: str) -> str:
    """Pasa a minusculas y SACA LOS ACENTOS.

    POR QUE: probando contra datos reales de SEPA aparecio que muchisimas
    descripciones vienen acentuadas ("CAFE TOSTADO" pero tambien "CAFÉ
    TOSTADO", "MANÍ", "LIMÓN"). Una regla que busca "cafe" no matchea
    "café", y se perdian miles de productos en silencio. Normalizar de un
    lado y escribir las reglas sin acento del otro resuelve el problema de
    raiz, sin tener que duplicar cada palabra.
    """
    texto = texto.lower()
    reemplazos = {"á":"a","é":"e","í":"i","ó":"o","ú":"u","ü":"u","ñ":"n"}
    for a, b in reemplazos.items():
        texto = texto.replace(a, b)
    return texto


def _p(*palabras: str) -> str:
    """Arma un patron regex de "empieza con cualquiera de estas palabras".

    Usa limite de palabra al INICIO pero no al final, para que una regla
    escrita en singular tambien tome el plural y las formas derivadas:
    "salchicha" matchea "salchichas", "galletita" matchea "galletitas".
    Probando contra datos reales, exigir la palabra completa perdia todos
    los plurales — que en las descripciones de SEPA son mayoria.

    Para terminos de 3 letras o menos se exige palabra completa, porque un
    prefijo tan corto genera falsos positivos (p.ej. "te" matcheando
    "tela" o "sal" matcheando "salchicha").
    """
    partes = []
    for w in palabras:
        w_norm = normalizar(w)
        if len(w_norm.replace(" ", "")) <= 3:
            partes.append(w_norm + r"\b")
        else:
            partes.append(w_norm + r"\w*")
    return r"\b(" + "|".join(partes) + r")"


REGLAS: list[ReglaClase] = [
    # NOTA: el orden IMPORTA. Se evalua de arriba hacia abajo y gana la
    # primera que matchea. Las reglas mas especificas van primero para que
    # no las "robe" una mas general (p.ej. alimento para mascotas antes que
    # los alimentos de consumo humano).

    # --- 09.3.4 Mascotas (va PRIMERO: "alimento perro" no es alimento humano)
    # NOTA: la clase 09.3.4 (Mascotas) fue excluida a pedido. Las reglas
    # que la detectaban se quitaron, asi que los productos de alimento
    # balanceado quedan SIN CLASIFICAR (no se cuelan en Carnes, porque las
    # marcas de balanceado se excluyen explicitamente abajo en 01.1.2).

    # --- 09.3.1 Juguetes
    ReglaClase("09.3.1", incluir=[_p("juguete","muneca","muneco","rompecabeza","puzzle",
                                      "peluche","ladrillos","juego de mesa","videojuego",
                                      # libros de actividades/colorear infantiles: segun
                                      # el documento oficial de INDEC, estos van con
                                      # Juguetes (09.3.1), no con Libros de lectura
                                      # (09.5.1) — verificado con 123 descripciones reales
                                      # de SEPA con la palabra "libro": son casi todas
                                      # libros de colorear con licencias (Toy Story,
                                      # Bluey, etc.), no novelas ni libros de lectura.
                                      "libro para colorear","libro de actividades",
                                      "libro de colorear","libro coloring","libro coloreable",
                                      "libro de cuentos","libro de mascaras","libro linterna",
                                      "libro peluche","libro sorpresa",
                                      "mi primer libro","libro de goma eva"),
                                  # Patron amplio para variantes que no entraban con las
                                  # frases exactas de arriba: "libro de actividades/
                                  # preguntas/arte/trivias/emociones/colorear/kawaii/
                                  # universo" en cualquier orden, y la serie real
                                  # "destroza/desarma este libro". Verificado que NO
                                  # atrapa casos ambiguos como titulos de novela con
                                  # numero de tomo ("EL DIABLO REGRESA (LIBRO 3)").
                                  r"libro.{0,20}(actividad|pregunta|colorear|arte|trivia|"
                                  r"emocion|secreto|kawaii|universo)",
                                  r"(destroza|desarma)n?.{0,10}este libro",
                                  r"libro.{0,15}cuentos clasicos",
                                  # "consola" sola es ambigua (consola de sonido,
                                  # de audio); se exige el contexto de videojuegos
                                  r"consola.{0,15}(videojuego|playstation|xbox|nintendo|switch)",
                                  # "pistola de agua" es juguete (COICOP 09.3.1), pero
                                  # "pistola" sola tambien atraparia "pistola de silicona"
                                  # (herramienta de ferreteria) — se exige la palabra
                                  # "agua" junto a "pistola" para acotarlo al caso real.
                                  # Bug real: sin esto, "PISTOLA AGUA C/GAS" caia en
                                  # Aguas y bebidas (01.2.2) por las palabras sueltas de
                                  # gas, en vez de en Juguetes.
                                  r"pistola.{0,10}agua"]),

    # --- 06.1 Salud (venta libre en gondola)
    # CORREGIDO segun la nota oficial (docs/coicop_notas_explicativas.md):
    # 06.1.1 son especificamente MEDICAMENTOS ("medicamentos patentados...
    # alopaticos u homeopaticos, vacunas, vitaminas, antibioticos,
    # antiinflamatorios"). Curita/gasa/venda/termometro/suero fisiologico
    # son "elementos para primeros auxilios" segun la definicion oficial,
    # y esos van a 06.1.2, no aca. Se habian puesto juntos por intuicion
    # propia sin verificar la separacion oficial entre las dos subclases.
    ReglaClase("06.1.1", incluir=[_p("ibuprofeno","paracetamol","aspirina","antiacido",
                                      "analgesico","antibiotico","antiinflamatorio",
                                      "vitamina","vitaminas","antigripal")]),
    # "algodon" solo (medicinal): excluye textiles y prendas que tambien
    # mencionan "algodon" en su composicion (sabana, toalla, remera,
    # pantalon, etc.) — sin esto, "REMERA ALGODON HOMBRE" o "SABANA 100%
    # ALGODON" caian aca en vez de en indumentaria/textiles del hogar.
    # Bug real encontrado al auditar por que las reglas de esas
    # categorias, ya escritas desde antes, nunca aplicaban.
    ReglaClase("06.1.2", incluir=[_p("algodon","apositos","agua oxigenada","alcohol en gel",
                                      "alcohol medicinal",
                                      # curita/gasa/venda/termometro/suero: movidos aca
                                      # desde 06.1.1 segun la definicion oficial de
                                      # "elementos para primeros auxilios" (ver arriba).
                                      "curita","gasa","venda","termometro",
                                      "suero fisiologico","repelente",
                                      # CORREGIDO segun la nota explicativa oficial de
                                      # INDEC (docs/coicop_notas_explicativas.md, 06.1.2):
                                      # "elementos para primeros auxilios... termometros,
                                      # PRESERVATIVOS". Se habia puesto antes en Cuidado
                                      # personal (12.1.3) por intuicion propia, sin
                                      # verificar contra la definicion oficial completa —
                                      # esa fue una suposicion equivocada.
                                      "preservativo","preservativos","forro")],
              excluir=[_p("sabana","sabanas","toalla","toallon","acolchado",
                          "almohada","funda","cortina","mantel","repasador",
                          "frazada","manta","tela","hilado",
                          "remera","musculosa","buzo","campera","pantalon",
                          "short","bermuda","pollera","vestido","camisa",
                          "bombacha","calzoncillo","media","medias")]),

    # --- 05.3.1 Artefactos para el hogar (electrodomesticos)
    # Verificado contra 3 dias reales de SEPA: existe volumen real con
    # nombres de marca reconocibles (BGH, Whirlpool, Samsung, Drean,
    # Philco), aunque en menos comercios que Alimentos (7 de 17 para
    # heladeras, por ejemplo) — se releva igual, con la salvedad de que
    # la muestra de esta clase depende de menos puntos de venta.
    ReglaClase("05.3.1", incluir=[_p("heladera","microondas","calefactor","cafetera",
                                      "termotanque","licuadora","freidora","aspiradora",
                                      "ventilador","tostadora","horno electrico","batidora",
                                      "secador de pelo","anafe","estufa","pava electrica",
                                      "lavarropa","minicomponente","multiprocesadora",
                                      "smart tv","televisor","parlante",
                                      # "lavavajillas" es ambiguo: el ELECTRODOMESTICO
                                      # (LAVAVAJILLAS WHIRLPOOL 14C) y el DETERGENTE
                                      # (DETERGENTE PARA LAVAVAJILLAS) comparten la
                                      # palabra. Se exige marca o numero de cubiertos
                                      # ("14C") junto a la palabra para distinguir el
                                      # electrodomestico real — el detergente sigue
                                      # yendo a 05.6.1 (Limpieza del hogar) via "lavavaji".
                                      r"lavavajillas.{0,25}(whirlpool|drean|bgh|samsung|electrolux|philco|\d+c\b)")]),

    # --- 05.1.1 Muebles, accesorios, alfombras y otros materiales para pisos
    # Verificado contra datos reales: "colchon" tiene volumen alto (7.937
    # filas, 9 comercios) pero colisiona con "yogur con colchon de
    # frutas" (producto lacteo real y frecuente) — se excluye "yogur"
    # explicitamente, aunque en la practica la regla de yogur (que esta
    # antes en el orden) ya lo captura primero. "espejo" se descarta: en
    # los datos reales aparece sobre todo como espejo de mano/maquillaje
    # (cuidado personal), no como mueble del hogar.
    ReglaClase("05.1.1", incluir=[_p("colchon","colchones","sommier","almohadon",
                                      "banqueta","reposera","sombrilla","silla plegable",
                                      "mesa plegable","perchero","estanteria","placard",
                                      "ropero")],
              excluir=[_p("yogur","yogurt")]),

    # --- 05.5.1 Herramientas y equipos para el hogar y jardin
    # "pala" y "pinza" se DESCARTAN a proposito: en los datos reales
    # aparecen casi siempre como "pala de residuos/limpieza" (05.6.1) y
    # "pinza de depilar" (12.1.3), no como herramientas — el volumen alto
    # (10.576 y 4.091 filas) era ambiguedad, no senal real.
    ReglaClase("05.5.1", incluir=[_p("taladro","destornillador","martillo","manguera",
                                      "rastrillo","amoladora","escalera","caja de herramientas",
                                      "motosierra","regadera","tijera de podar","carretilla",
                                      "soplador de hojas")]),

    # --- 09.5.4 Papel y utiles de oficina y materiales de dibujo
    # "fibra" se DESCARTA: en los datos reales es fibra de limpieza
    # (esponja) o "hamburguesa con fibra" (alimento), no marcador
    # escolar — 16.208 filas de ruido, cero relacionadas con papeleria.
    ReglaClase("09.5.4", incluir=[_p("cuaderno","lapiz","lapicera","birome","marcador",
                                      "resaltador","goma de borrar","sacapuntas","regla",
                                      "carpeta","folio","corrector liquido","plasticola",
                                      "tijera escolar","cartuchera","mochila escolar",
                                      "crayon","acuarela","plastilina")]),

    # --- 12.1.3 Cuidado personal
    ReglaClase("12.1.3", incluir=[_p("shamp","shampoo","champu","acond","acondicionador","jabon de tocador",
                                      "jab.d/tocador","desodorante","antitranspirante",
                                      "pasta dental","crema dental","cepillo dental",
                                      "hilo dental","enjuague bucal","panal","panales",
                                      "toallitas fem","protectores diarios","afeitar",
                                      "maquinita","coloracion","tintura","crema corporal",
                                      "protector solar","talco","algodon hisopo","hisopos",
                                      "pinza de depilar","alicate de unas",
                                      # abreviaturas reales encontradas en SEPA
                                      "jab toc","crem dent","tampon","tampones","sh anti caida",
                                      # CORREGIDO segun la nota oficial de INDEC
                                      # (docs/coicop_notas_explicativas.md, 12.1.3.1):
                                      # "descartables para cuidado personal: cepillos
                                      # dentales, hilo dental, repuestos de afeitar,
                                      # panales, PAPEL HIGIENICO, toallas higienicas,
                                      # protectores diarios". Estaba puesto en Limpieza
                                      # del hogar (05.6.1) por intuicion propia — la
                                      # definicion oficial lo pone aca.
                                      "papel higienico","p hig")]),

    # --- 05.6.1 Limpieza del hogar
    ReglaClase("05.6.1", incluir=[_p("detergente","lavandina","jabon en polvo","jabon liquido",
                                      "suavizante","limpiador","desinfectante","desengrasante",
                                      "limpia vidrios","quitamanchas","insecticida","apresto",
                                      "esponja","virulana","trapo","escoba","secador",
                                      "fibra limpieza","fibra de limpieza",
                                      "bolsas de residuos","bolsa de residuo",
                                      "rollo de cocina","servilletas","antihumedad",
                                      "mantel papel","mantel descartable",
                                      "lustramuebles","enjuague concent","aromatizante","desengras",
                                      "limpiavidrio","jabon para la ropa","perfumina",
                                      # abreviaturas reales encontradas en SEPA (ver
                                      # scripts/diagnosticar_mapeo.py): muchos comercios
                                      # truncan la descripcion por limite de caracteres.
                                      # "p hig"/"papel higienico" SE SACARON de aca: segun
                                      # la definicion oficial van a Cuidado personal
                                      # (12.1.3.1), ver arriba.
                                      "lavavaji",
                                      # "pala" sola es ambigua; se agrega el patron completo
                                      "pala de residuos","pala de basura",
                                      # vasos/platos descartables van aca segun la
                                      # definicion oficial (05.6.1.3), no en Bazar (05.4.1).
                                      # Patron flexible porque en la practica suele
                                      # aparecer "VASO PLASTICO DESCARTABLE", con una
                                      # palabra en el medio.
                                      r"(vaso|plato)s?.{0,15}descartables?",
                                      # del documento de INDEC: rollos de aluminio/film y
                                      # pilas/lamparas van con "bienes para el hogar",
                                      # no con electro ni con alimentos. Patron propio
                                      # (no _p()) para "papel/rollo de aluminio" — la
                                      # palabra "aluminio" sola es demasiado generica y
                                      # atrapaba ollas/sartenes de aluminio (que van a
                                      # Bazar, 05.4.1, no a Limpieza del hogar).
                                      r"(papel|rollo).{0,15}aluminio",
                                      "papel film","film transparente",
                                      "pilas aa","pilas aaa","lampara","lamparita")]),

    # --- 05.4.1 Bazar y menaje
    # CORREGIDO segun la nota oficial (05.4.1: vajilla y utensilios
    # REUTILIZABLES; excluye explicitamente vasos/platos DESCARTABLES,
    # que van a 05.6.1 "articulos descartables"). Se excluye la palabra
    # "descartable" para que un vaso/plato de un solo uso no caiga aca.
    ReglaClase("05.4.1", incluir=[_p("vaso","plato","taza","jarro","olla","sarten","cacerola",
                                      "cubiertos","tenedor","cuchillo","cuchara","bowl",
                                      "fuente","bandeja","tupper","recipiente","pinza cocina",
                                      "colador","rallador","tabla de picar")],
              excluir=[_p("descartable","descartables")]),
    # --- 05.2.1 Textiles del hogar
    ReglaClase("05.2.1", incluir=[_p("sabana","sabanas","toallon","toalla","acolchado",
                                      "almohada","funda","cortina","mantel","repasador",
                                      "frazada","manta")],
              # mantel/servilleta de PAPEL (descartable) va a 05.6.1, no
              # a textiles del hogar — la definicion oficial de 05.2.1.2
              # dice explicitamente "manteles" pero se refiere a los de
              # tela; los de papel son "articulos descartables" (05.6.1.3).
              excluir=[_p("papel","descartable")]),

    # --- 03.2.1 Zapatos y otros calzados
    # Palabras deliberadamente ESPECIFICAS de calzado, evitando terminos
    # ambiguos con otras secciones de un hiper/super (ej. "chancho" de
    # alimentos, o "bota" que en SEPA a veces aparece en botellas).
    ReglaClase("03.2.1", incluir=[_p("zapatilla","zapatillas","calzado","ojota","ojotas",
                                      "chinela","chinelas","borcego","alpargata")]),

    # --- 03.1.2 Prendas de vestir
    # Igual criterio: palabras que en la practica de SEPA (hiper/super
    # grandes con seccion de indumentaria basica) casi no tienen
    # ambiguedad con alimentos, limpieza u otras secciones.
    ReglaClase("03.1.2", incluir=[_p("remera","remeras","musculosa","buzo","buzos",
                                      "campera","camperas","pantalon","pantalones",
                                      "short","bermuda","pollera","polleras",
                                      "vestido","vestidos","camisa","camisas",
                                      "ropa interior","bombacha","bombachas",
                                      "calzoncillo","calzoncillos","malla",
                                      "conjunto deportivo")],
              excluir=[_p("papel","detergente","jabon","suavizante")]),  # "malla" de fideos, etc.

    # --- 02 Bebidas alcoholicas
    ReglaClase("02.1.2", incluir=[_p("vino","vinos","espumante","champagne","sidra")]),
    ReglaClase("02.1.3", incluir=[_p("cerveza","cervezas","birra","cerv")]),
    ReglaClase("02.1.1", incluir=[_p("whisky","vodka","gin","ron","fernet","aperitivo",
                                      "licor","tequila","aperital","vermut",
                                      "brandy","conac","cognac","aguardiente")]),

    # --- 01.1 Alimentos
    ReglaClase("01.1.1", incluir=[_p("pan","panes","galletitas","galleta","gall","harina",
                                      "fideo","fideos","arroz","avena","cereal","tostadas",
                                      "budin","bizcochuelo","premezcla","polenta","salvado",
                                      "pastas","noquis","gnocchetti","ravioles","tapa empanada",
                                      "baguette","torta","brownie",
                                      # snacks de cereales/maiz, segun el criterio de
                                      # finalidad del documento de INDEC (van con
                                      # panificados y snacks a base de cereal, no
                                      # con la materia prima que evoca el sabor)
                                      "nachos","chizito","chisito","palito salado","palitos salados")],
              # "torta helada" es un excepcion oficial explicita: la nota de
              # 01.1.8.3 (Helados) dice "helados... incluye postres y
              # TORTAS HELADAS" — sin esto, "TORTA HELADA CHOCOLATE" caia
              # en Pan y cereales por la palabra "torta".
              excluir=[_p("torta helada","helado")]),
    ReglaClase("01.1.2", incluir=[_p("asado","carne","carnicero","pollo","milanesa","hamburguesa",
                                      "salchicha","jamon","salame","salamin","fiambre","mortadela",
                                      "bondiola","matambre","chorizo","morcilla","pechuga",
                                      "nalga","cuadril","peceto","paleta","costilla","vacio",
                                      "medallon","panceta","lomo","leberwurst","pate")],
               excluir=[_p("lomo d/atun","atun","caldo","cubito de caldo",
                            # marcas y terminos de alimento para mascotas:
                            # sin esto, "BOCADITOS D/POLLO RAZA" caeria aca
                            "raza","pedigree","whiskas","dogchow","cat chow",
                            "vitalcan","eukanuba","proplan","purina","sieger",
                            "old prince","nutripet","balanceado","perro","gato",
                            "mascota","canino","felino")]),
    ReglaClase("01.1.3", incluir=[_p("atun","merluza","pescado","sardina","caballa","salmon",
                                      "camaron","langostino","calamar","mariscos")]),
    ReglaClase("01.1.4", incluir=[_p("leche","yogur","yoghurt","queso","manteca","crema de leche",
                                      "dulce de leche","huevo","huevos","postre lacteo","ricota",
                                      "flan","mantecol"),
                                  # "QUES." abreviado al inicio de palabra: "QUES.D/CAMP.
                                  # HILADO..." o "QUES.MUZZAREL." son queso real. Se excluye
                                  # cuando va precedido de "SAB." (sabor a queso), que es un
                                  # snack con sabor, no lacteo — mismo caso que "queso" suelto
                                  # se robaba "CHIZITOS QUESO" antes de esa correccion.
                                  r"(?<!sab\.)ques\."],
              # snacks/papas fritas con sabor a queso van a Pan y cereales
              # (01.1.1), no aca — la palabra "queso"/"ques." sola no
              # debe atraparlos.
              excluir=[_p("chizito","chisito","palito","snack","papas fritas")]),
    ReglaClase("01.1.5", incluir=[_p("aceite","aceites","margarina","grasa","oliva","fritolim")]),
    ReglaClase("01.1.6", incluir=[_p("manzana","banana","naranja","limon","mandarina","pera",
                                      "uva","durazno","frutilla","kiwi","anana","sandia","melon",
                                      "ciruela","pomelo","palta","higo","cereza","frutas")],
               excluir=[_p("jugo","gaseosa","agua saborizada","yogur","mermelada",
                            "helado","alfajor","caramelo","galletita","tarta")]),
    ReglaClase("01.1.7", incluir=[_p("papa","batata","cebolla","tomate","lechuga","zanahoria",
                                      "zapallo","zapallito","acelga","espinaca","morron","ajo",
                                      "choclo","lenteja","lentejas","arveja","arvejas","poroto",
                                      "porotos","garbanzo","brocoli","coliflor","pepino","apio",
                                      "puerro","remolacha","berenjena","chaucha","chauchas",
                                      "champignon","verdura","verduras","jardinera")],
              # "CALDO DE VERDURA" no es una verdura fresca, es un producto
              # procesado (misma logica de "finalidad del gasto" del
              # documento de INDEC): sin esto, la palabra suelta "verdura"
              # se lo robaba a Otros alimentos (01.1.9), donde ya esta
              # declarado "caldo" como palabra clave.
              # "PAPAS FRITAS" (snack) no es la hortaliza fresca — mismo
              # criterio.
              excluir=[_p("caldo","sopa","cubito","papas fritas","papa frita")]),
    ReglaClase("01.1.8", incluir=[_p("azucar","dulce","mermelada","chocolate","golosina","caramelo",
                                      "caram","alfajor","miel","gomitas","turron","bombon",
                                      "pastillas","past","chicle","edulcorante","cacao","oblea",
                                      "cubanito","tableta","barra de cereal","helado",
                                      "postre","nugaton")],
               excluir=[_p("dulce de leche")]),
    ReglaClase("01.1.9", incluir=[_p("sal","condimento","especias","molinillo especias","vinagre",
                                      "mayonesa","ketchup","mostaza","salsa","aderezo","caldo",
                                      "sopa","pure","saborizador","aceitunas","conserva",
                                      "escabeche","levadura","gelatina","polvo de hornear",
                                      "polvo p/hornear","aceto")]),

    # --- 01.2 Bebidas no alcoholicas
    ReglaClase("01.2.1", incluir=[_p("cafe","yerba","yerba mate","te","cacao en polvo","mate cocido",
                                      "capuccino","cappuccino","infusion","saquitos")]),
    ReglaClase("01.2.2", incluir=[_p("gaseosa","agua mineral","agua saborizada","jugo","jugos",
                                      "soda","energizante","isotonica","bebida sin alcohol",
                                      "amargo serrano","tonica","gaseo",
                                      # "s/gas" y "c/gas" SUELTOS son ambiguos: matcheaban
                                      # "PISTOLA AGUA C/GAS" (un juguete, deberia ir a
                                      # 09.3.1) ademas de "AGUA S/GAS" real. La definicion
                                      # oficial de INDEC para esta subclase habla siempre
                                      # de "agua... con o sin gas" en la misma frase, nunca
                                      # como abreviatura aislada — se corrige exigiendo la
                                      # palabra "agua" junto al gas.
                                      r"agua.{0,10}(s/gas|c/gas)")]),

    # --- 09.1.4 Medios para grabacion
    # Verificado con datos reales de SEPA: 23 productos con marcas
    # identificables (Kingston, Maxell, HikSemi, SanDisk) en 3 dias.
    ReglaClase("09.1.4", incluir=[_p("pendrive","pen drive","microsd","micro sd",
                                      "memoria usb","tarjeta sd","cd virgen","dvd virgen")]),

    # --- 03.1.3 Otros accesorios para el vestir
    # Verificado con datos reales de SEPA: 146 coincidencias de "billetera"
    # y "bufanda"/"gorro" en 3 dias — volumen real, marroquineria y
    # accesorios segun la definicion oficial de INDEC.
    ReglaClase("03.1.3", incluir=[_p("billetera","cartera de mano","cinturon","pañuelo",
                                      "bufanda","sombrero","gorro","gorra")],
              # "gorro" solo atrapa un adorno navideno real encontrado
              # (ADORNO GNOMO C GORRO): se excluye explicitamente sin
              # perder el resto de gorros reales de indumentaria.
              excluir=[_p("adorno","gnomo")]),
]

# EAN fijados a mano después de revisar un archivo real. Formato:
# {"7790xxxxxxxxx": "01.1.4"}. Se consulta ANTES que las reglas de texto.
MAPEO_EAN: dict[str, str] = {}


def clasificar(nombre_producto: str, ean: str | None = None) -> str | None:
    """Devuelve el código de clase COICOP o None si no matchea ninguna
    regla (en ese caso el producto queda sin mapear — mejor eso que
    mapearlo mal; ver conteo de no-mapeados en el reporte diario)."""
    if ean and ean in MAPEO_EAN:
        return MAPEO_EAN[ean]

    texto = normalizar(nombre_producto)
    for regla in REGLAS:
        if any(re.search(pat, texto) for pat in regla.excluir):
            continue
        if any(re.search(pat, texto) for pat in regla.incluir):
            return regla.clase_codigo
    return None
