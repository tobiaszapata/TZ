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
                                      "peluche","ladrillos","juego de mesa")]),

    # --- 06.1 Salud (venta libre en gondola)
    ReglaClase("06.1.1", incluir=[_p("ibuprofeno","paracetamol","aspirina","antiacido",
                                      "analgesico","curita","alcohol en gel","gasa","venda",
                                      "termometro","suero fisiologico","repelente")]),
    ReglaClase("06.1.2", incluir=[_p("algodon","apositos","agua oxigenada")]),

    # --- 12.1.3 Cuidado personal
    ReglaClase("12.1.3", incluir=[_p("shamp","shampoo","champu","acond","acondicionador","jabon de tocador",
                                      "jab.d/tocador","desodorante","antitranspirante",
                                      "pasta dental","crema dental","cepillo dental",
                                      "hilo dental","enjuague bucal","panal","panales",
                                      "toallitas fem","protectores diarios","afeitar",
                                      "maquinita","coloracion","tintura","crema corporal",
                                      "protector solar","talco","algodon hisopo","hisopos")]),

    # --- 05.6.1 Limpieza del hogar
    ReglaClase("05.6.1", incluir=[_p("detergente","lavandina","jabon en polvo","jabon liquido",
                                      "suavizante","limpiador","desinfectante","desengrasante",
                                      "limpia vidrios","quitamanchas","insecticida","apresto",
                                      "esponja","virulana","trapo","escoba","secador",
                                      "bolsas de residuos","bolsa de residuo","papel higienico",
                                      "rollo de cocina","servilletas","antihumedad",
                                      "lustramuebles","enjuague concent","aromatizante","desengras",
                                      "limpiavidrio","jabon para la ropa","perfumina")]),

    # --- 05.4.1 Bazar y menaje
    ReglaClase("05.4.1", incluir=[_p("vaso","plato","taza","jarro","olla","sarten","cacerola",
                                      "cubiertos","tenedor","cuchillo","cuchara","bowl",
                                      "fuente","bandeja","tupper","recipiente","pinza cocina",
                                      "colador","rallador","tabla de picar")]),
    # --- 05.2.1 Textiles del hogar
    ReglaClase("05.2.1", incluir=[_p("sabana","sabanas","toallon","toalla","acolchado",
                                      "almohada","funda","cortina","mantel","repasador",
                                      "frazada","manta")]),

    # --- 02 Bebidas alcoholicas
    ReglaClase("02.1.2", incluir=[_p("vino","vinos","espumante","champagne","sidra")]),
    ReglaClase("02.1.3", incluir=[_p("cerveza","cervezas","birra")]),
    ReglaClase("02.1.1", incluir=[_p("whisky","vodka","gin","ron","fernet","aperitivo",
                                      "licor","tequila","aperital","vermut")]),

    # --- 01.1 Alimentos
    ReglaClase("01.1.1", incluir=[_p("pan","panes","galletitas","galleta","gall","harina",
                                      "fideo","fideos","arroz","avena","cereal","tostadas",
                                      "budin","bizcochuelo","premezcla","polenta","salvado",
                                      "pastas","noquis","gnocchetti","ravioles","tapa empanada")]),
    ReglaClase("01.1.2", incluir=[_p("asado","carne","carnicero","pollo","milanesa","hamburguesa",
                                      "salchicha","jamon","salame","salamin","fiambre","mortadela",
                                      "bondiola","matambre","chorizo","morcilla","pechuga",
                                      "nalga","cuadril","peceto","paleta","costilla","vacio",
                                      "medallon","panceta","lomo")],
               excluir=[_p("lomo d/atun","atun",
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
                                      "flan","mantecol")]),
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
                                      "champignon","verdura","verduras","jardinera")]),
    ReglaClase("01.1.8", incluir=[_p("azucar","dulce","mermelada","chocolate","golosina","caramelo",
                                      "caram","alfajor","miel","gomitas","turron","bombon",
                                      "pastillas","past","chicle","edulcorante","cacao","oblea",
                                      "cubanito","tableta","barra de cereal","helado",
                                      "postre","budin","torta","brownie","nugaton")],
               excluir=[_p("dulce de leche")]),
    ReglaClase("01.1.9", incluir=[_p("sal","condimento","especias","molinillo especias","vinagre",
                                      "mayonesa","ketchup","mostaza","salsa","aderezo","caldo",
                                      "sopa","pure","saborizador","aceitunas","conserva",
                                      "escabeche","levadura","gelatina")]),

    # --- 01.2 Bebidas no alcoholicas
    ReglaClase("01.2.1", incluir=[_p("cafe","yerba","yerba mate","te","cacao en polvo","mate cocido",
                                      "capuccino","cappuccino","infusion","saquitos")]),
    ReglaClase("01.2.2", incluir=[_p("gaseosa","agua mineral","agua saborizada","jugo","jugos",
                                      "soda","energizante","isotonica","bebida sin alcohol",
                                      "amargo serrano","tonica")]),
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
