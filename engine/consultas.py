"""
Capa de consulta reutilizable: TODO el calculo que necesita una interfaz.

POR QUE ESTE MODULO EXISTE SEPARADO DE LA INTERFAZ:
La aplicacion de Streamlit no hace cuentas. Llama a las funciones de aca.
Eso tiene tres consecuencias buenas:

 1. Se puede TESTEAR sin levantar Streamlit (que necesita un servidor y un
    navegador). Los tests de este archivo corren en la suite normal.
 2. Si mañana la interfaz cambia (Streamlit, un HTML, un notebook, una API),
    el calculo no se toca.
 3. Elimina la duplicacion Python/JavaScript que existia con la app HTML
    estatica: habia que mantener la misma formula en dos lenguajes.

Todas las funciones son REGION-AWARE: reciben una region y usan los
ponderadores de esa region (ver config/canasta.py).

--------------------------------------------------------------------------
SOBRE LOS "OVERRIDES" (valores manuales / simulacion):

`division_completa`, `indice_region` y `resumen_divisiones` aceptan un
parametro opcional `overrides`: un diccionario {codigo_de_clase: valor_pct}.
Si una clase esta en ese diccionario, se usa ESE valor en vez del calculado
desde la base — por ejemplo, para probar "¿como quedaria la division si en
vez de nuestro dato de Frutas usamos el 8% que publico la consultora?".

ESTO NUNCA TOCA LA BASE DE DATOS. Es una sustitucion que vive solo en la
memoria de la sesion de Streamlit mientras la estas mirando. Cerrás la
pestaña y el valor real —el que releva el sistema— sigue intacto. Cada fila
que resulta de un override queda marcada `es_manual=True` para que la
interfaz la pinte distinto y nadie la confunda con un dato medido.
--------------------------------------------------------------------------
"""

from __future__ import annotations

from dataclasses import dataclass, field

from config.canasta import (
    CANASTA,
    CLASES_CON_COBERTURA_SEPA,
    PESO_REGION,
    Cobertura,
    clases_de_division,
    divisiones,
)
from engine.agregacion import laspeyres
from engine.reporte import calcular_clase_y_productos
from storage.db import (
    nombres_de_productos,
    precios_por_producto_en_rango,
)


@dataclass
class FilaClase:
    codigo: str
    nombre: str
    peso: float                 # ponderador oficial en la region, en %
    variacion_pct: float | None
    n_productos: int
    aporte_pp: float | None = None
    es_manual: bool = False     # True si este valor vino de un override, no de la base


@dataclass
class ResultadoDivision:
    codigo: str
    nombre: str
    peso: float
    variacion_pct: float | None
    cobertura: float            # fraccion del peso de la division con dato
    clases: list[FilaClase]
    tiene_manuales: bool = False


def variacion_clase(con, clase, desde, hasta, desde_base, hasta_base, region=None):
    """Variacion de una clase entre dos ventanas de fechas, con el detalle
    por producto. Devuelve (resultado, drivers) o (None, []) si no hay
    productos comparables. Esto SIEMPRE lee de la base — los overrides se
    aplican una capa mas arriba (division_completa), nunca aca."""
    p_act = precios_por_producto_en_rango(con, clase, desde, hasta, region)
    p_base = precios_por_producto_en_rango(con, clase, desde_base, hasta_base, region)
    eans = list(set(p_act) | set(p_base))
    if not eans:
        return None, []
    return calcular_clase_y_productos(p_act, p_base, nombres_de_productos(con, eans))


def division_completa(con, div_codigo, desde, hasta, desde_base, hasta_base,
                      region="GBA", overrides: dict[str, float] | None = None) -> ResultadoDivision:
    """Calcula una division: cada clase con cobertura, y el agregado
    ponderado con los pesos de la region indicada.

    `overrides`: {codigo_clase: valor_pct} para pisar el dato medido de esa
    clase con un valor manual, solo en esta consulta. Ver docstring del
    modulo — nunca escribe en la base."""
    overrides = overrides or {}
    div = CANASTA[div_codigo]
    filas: list[FilaClase] = []
    num = den = 0.0
    tiene_manuales = False

    for clase in clases_de_division(div_codigo):
        if clase.cobertura != Cobertura.MEDIDA_SEPA:
            continue
        peso = clase.peso(region) * 100

        if clase.codigo in overrides:
            v = overrides[clase.codigo]
            n = 0
            es_manual = True
            tiene_manuales = True
        else:
            res, _ = variacion_clase(con, clase.codigo, desde, hasta,
                                     desde_base, hasta_base, region)
            v = res.variacion_pct if res else None
            n = res.n_productos_comparados if res else 0
            es_manual = False

        filas.append(FilaClase(clase.codigo, clase.nombre, peso, v, n, es_manual=es_manual))
        if v is not None:
            num += peso * v
            den += peso

    variacion = num / den if den else None
    for f in filas:
        f.aporte_pp = (f.peso / den * f.variacion_pct) if (den and f.variacion_pct is not None) else None

    peso_total = sum(c.peso(region) * 100 for c in clases_de_division(div_codigo)
                     if c.cobertura == Cobertura.MEDIDA_SEPA)
    return ResultadoDivision(
        codigo=div_codigo, nombre=div.nombre, peso=div.peso(region) * 100,
        variacion_pct=variacion,
        cobertura=(den / peso_total) if peso_total else 0.0,
        clases=filas,
        tiene_manuales=tiene_manuales,
    )


def indice_region(con, desde, hasta, desde_base, hasta_base, region="GBA",
                  overrides: dict[str, float] | None = None):
    """Indice de una region: todas las clases medidas, ponderadas con los
    pesos de esa region. Devuelve (variacion, cobertura_sobre_canasta).
    Acepta los mismos `overrides` que division_completa."""
    overrides = overrides or {}
    num = den = 0.0
    for cod in CLASES_CON_COBERTURA_SEPA:
        peso = CANASTA[cod].peso(region) * 100
        if cod in overrides:
            v = overrides[cod]
        else:
            res, _ = variacion_clase(con, cod, desde, hasta, desde_base, hasta_base, region)
            v = res.variacion_pct if res else None
        if v is not None:
            num += peso * v
            den += peso
    if not den:
        return None, 0.0
    peso_medible = sum(CANASTA[c].peso(region) * 100 for c in CLASES_CON_COBERTURA_SEPA)
    return num / den, den / peso_medible if peso_medible else 0.0


def indice_nacional(con, desde, hasta, desde_base, hasta_base):
    """Combina las regiones con datos, ponderando por su importancia
    nacional. Las regiones sin datos se excluyen y se renormaliza; se
    informa que fraccion del pais quedo representada.

    NO acepta overrides: la simulacion manual esta pensada para explorar una
    region especifica a la vez (que es como se usa en la pantalla), no para
    combinarse con el nacional. Si hace falta mas adelante, se agrega aca
    sin tocar el resto."""
    por_region: dict[str, float] = {}
    for region in PESO_REGION:
        v, _ = indice_region(con, desde, hasta, desde_base, hasta_base, region)
        if v is not None:
            por_region[region] = v
    if not por_region:
        return None, 0.0, {}
    den = sum(PESO_REGION[r] for r in por_region)
    nacional = sum(PESO_REGION[r] * v for r, v in por_region.items()) / den
    return nacional, den / sum(PESO_REGION.values()), por_region


def resumen_divisiones(con, desde, hasta, desde_base, hasta_base, region="GBA",
                       overrides: dict[str, float] | None = None):
    """Las 12 divisiones, con su variacion cuando hay datos. `overrides`
    aplica a cualquier clase de cualquier division, con la misma clave de
    codigo — se pasa tal cual a cada llamado de division_completa."""
    salida = []
    for div in divisiones():
        tiene = any(c.cobertura == Cobertura.MEDIDA_SEPA
                    for c in clases_de_division(div.codigo))
        if tiene:
            salida.append(division_completa(con, div.codigo, desde, hasta,
                                            desde_base, hasta_base, region, overrides))
        else:
            salida.append(ResultadoDivision(
                div.codigo, div.nombre, div.peso(region) * 100, None, 0.0, []))
    return salida


@dataclass
class FilaDivision:
    codigo: str
    nombre: str
    peso: float
    variacion_pct: float | None
    fuente: str          # "medida" | "manual" | "sin_dato"
    cobertura_interna: float | None = None   # % del peso PROPIO de la division cubierto por datos


@dataclass
class ResultadoNivelGeneral:
    variacion_pct: float | None
    cobertura: float          # fraccion del peso TOTAL del pais que quedo representada
    divisiones: list[FilaDivision]


def nivel_general(con, desde, hasta, desde_base, hasta_base, region="GBA",
                  overrides_clase: dict[str, float] | None = None,
                  overrides_division: dict[str, float] | None = None) -> ResultadoNivelGeneral:
    """Combina las 12 divisiones en un nivel general, con los ponderadores
    OFICIALES de INDEC para la region elegida.

    Esto es lo que permite responder la pregunta real del proyecto: "las
    divisiones que SEPA mide, que tomen su dato medido; las que no mide
    (Comunicacion, Transporte, Vivienda...), que el usuario pueda poner el
    dato que le da otra consultora — y ver qué nivel general resulta,
    siguiendo siempre la misma metodologia de ponderacion de INDEC".

    `overrides_clase`: pisa una SUBCATEGORIA puntual dentro de una division
        medida (ver division_completa). Sigue funcionando igual que antes.
    `overrides_division`: da un valor manual a una DIVISION ENTERA. Es lo
        nuevo — pensado sobre todo para las divisiones sin ninguna clase
        medida por SEPA (Comunicacion, Transporte, Vivienda, Prendas,
        Educacion, Restaurantes), pero funciona igual si se quiere pisar
        una division que sí tiene datos.

    Ninguno de los dos parametros escribe nada en la base — ver el
    docstring del modulo.
    """
    overrides_clase = overrides_clase or {}
    overrides_division = overrides_division or {}

    filas: list[FilaDivision] = []
    valores: dict[str, float] = {}

    for div in divisiones():
        peso = div.peso(region) * 100

        if div.codigo in overrides_division:
            v = overrides_division[div.codigo]
            fuente = "manual"
            cobertura_interna = None
        else:
            tiene_cobertura = any(c.cobertura == Cobertura.MEDIDA_SEPA
                                  for c in clases_de_division(div.codigo))
            if tiene_cobertura:
                res = division_completa(con, div.codigo, desde, hasta,
                                        desde_base, hasta_base, region, overrides_clase)
                v = res.variacion_pct
                fuente = "medida" if v is not None else "sin_dato"
                cobertura_interna = res.cobertura if v is not None else None
            else:
                v = None
                fuente = "sin_dato"
                cobertura_interna = None

        filas.append(FilaDivision(div.codigo, div.nombre, peso, v, fuente, cobertura_interna))
        if v is not None:
            valores[div.codigo] = v

    if not valores:
        return ResultadoNivelGeneral(None, 0.0, filas)

    pesos = {cod: CANASTA[cod].peso(region) * 100 for cod in valores}
    agregado = laspeyres(valores, pesos)
    peso_total_pais = sum(d.peso(region) * 100 for d in divisiones())

    return ResultadoNivelGeneral(
        variacion_pct=agregado.variacion_pct,
        cobertura=agregado.peso_cubierto / peso_total_pais if peso_total_pais else 0.0,
        divisiones=filas,
    )


# ==========================================================================
# VISTA NACIONAL — sin desglose regional visible
#
# Lo de arriba (division_completa, indice_region, nivel_general) trabaja
# SIEMPRE con una region a la vez, porque asi lo exige la metodologia de
# INDEC: los ponderadores son regionales, no hay un "peso nacional" propio
# publicado para cada categoria. Pero mostrar el desglose por region no le
# interesa a todo el mundo — para alguien que solo quiere el numero del
# pais, es ruido.
#
# Las funciones de aca abajo COMBINAN las 6 regiones puertas adentro (nunca
# se saltea el paso metodologicamente correcto) y devuelven un unico
# resultado nacional. La region deja de ser un dato que el usuario tiene
# que elegir; es un detalle de implementacion.
# ==========================================================================

def peso_nacional_clase(codigo: str) -> float:
    """Peso nacional de una clase: la suma, en las 6 regiones, del peso que
    tiene esa clase en cada region multiplicado por la importancia de esa
    region en el pais. Es la forma correcta de "nacionalizar" un peso que
    solo existe publicado a nivel regional (Metodologia N32, Cuadro 6)."""
    return sum(PESO_REGION[r] * CANASTA[codigo].peso(r) for r in PESO_REGION) * 100


def peso_nacional_division(codigo: str) -> float:
    """Igual que `peso_nacional_clase` pero para una division completa."""
    return sum(PESO_REGION[r] * CANASTA[codigo].peso(r) for r in PESO_REGION) * 100


def _combinar_regiones(valores: dict[str, float], pesos: dict[str, float]) -> tuple[float | None, float]:
    """Combina valores regionales con sus pesos, excluyendo las regiones
    sin dato y renormalizando — el mismo criterio de siempre, aplicado al
    eje geografico en vez de al eje de categorias."""
    comunes = set(valores) & set(pesos)
    if not comunes:
        return None, 0.0
    num = sum(pesos[r] * valores[r] for r in comunes)
    den = sum(pesos[r] for r in comunes)
    peso_total = sum(pesos.values())
    return (num / den if den else None), (den / peso_total if peso_total else 0.0)


def variacion_clase_nacional(con, clase: str, desde, hasta, desde_base, hasta_base):
    """Variacion NACIONAL de una clase: la misma clase, calculada en cada
    una de las 6 regiones (con sus propios precios y su propio peso dentro
    de la region) y combinada con la importancia relativa de cada region.
    No es un promedio simple entre regiones ni un pool de precios sin
    ponderar — ambas formas estarian mal (la primera le daria a Cuyo el
    mismo peso que a GBA; la segunda sobre-representaria las regiones
    donde SEPA tiene mas sucursales, que no son las mismas donde vive mas
    gente)."""
    valores = {}
    for region in PESO_REGION:
        res, _ = variacion_clase(con, clase, desde, hasta, desde_base, hasta_base, region)
        if res is not None:
            valores[region] = res.variacion_pct
    return _combinar_regiones(valores, PESO_REGION)


def division_completa_nacional(con, div_codigo, desde, hasta, desde_base, hasta_base,
                               overrides_clase: dict[str, float] | None = None) -> ResultadoDivision:
    """Version nacional de `division_completa`: cada clase de la division
    se calcula a nivel pais (combinando regiones), y despues se agregan
    las clases con el peso nacional de cada una."""
    overrides_clase = overrides_clase or {}
    div = CANASTA[div_codigo]
    filas: list[FilaClase] = []
    num = den = 0.0
    tiene_manuales = False

    for clase in clases_de_division(div_codigo):
        if clase.cobertura != Cobertura.MEDIDA_SEPA:
            continue
        peso = peso_nacional_clase(clase.codigo)

        if clase.codigo in overrides_clase:
            v = overrides_clase[clase.codigo]
            es_manual = True
            tiene_manuales = True
        else:
            v, _cob = variacion_clase_nacional(con, clase.codigo, desde, hasta, desde_base, hasta_base)
            es_manual = False

        filas.append(FilaClase(clase.codigo, clase.nombre, peso, v, 0, es_manual=es_manual))
        if v is not None:
            num += peso * v
            den += peso

    variacion = num / den if den else None
    for f in filas:
        f.aporte_pp = (f.peso / den * f.variacion_pct) if (den and f.variacion_pct is not None) else None

    peso_total = sum(peso_nacional_clase(c.codigo) for c in clases_de_division(div_codigo)
                     if c.cobertura == Cobertura.MEDIDA_SEPA)
    return ResultadoDivision(
        codigo=div_codigo, nombre=div.nombre, peso=peso_nacional_division(div_codigo),
        variacion_pct=variacion,
        cobertura=(den / peso_total) if peso_total else 0.0,
        clases=filas,
        tiene_manuales=tiene_manuales,
    )


def resumen_divisiones_nacional(con, desde, hasta, desde_base, hasta_base,
                                overrides_clase: dict[str, float] | None = None):
    """Version nacional de `resumen_divisiones` — las 12 divisiones, cada
    una calculada a nivel pais."""
    salida = []
    for div in divisiones():
        tiene = any(c.cobertura == Cobertura.MEDIDA_SEPA for c in clases_de_division(div.codigo))
        if tiene:
            salida.append(division_completa_nacional(con, div.codigo, desde, hasta,
                                                      desde_base, hasta_base, overrides_clase))
        else:
            salida.append(ResultadoDivision(
                div.codigo, div.nombre, peso_nacional_division(div.codigo), None, 0.0, []))
    return salida


def nivel_general_nacional(con, desde, hasta, desde_base, hasta_base,
                           overrides_clase: dict[str, float] | None = None,
                           overrides_division: dict[str, float] | None = None) -> ResultadoNivelGeneral:
    """Version nacional de `nivel_general`: combina las 12 divisiones a
    nivel pais (sin exponer ninguna region), con la misma logica de
    overrides para poner a mano el dato de una categoria que SEPA no mide
    (Comunicacion, Transporte, Vivienda, Prendas, Educacion, Restaurantes)."""
    overrides_clase = overrides_clase or {}
    overrides_division = overrides_division or {}

    filas: list[FilaDivision] = []
    valores: dict[str, float] = {}

    for div in divisiones():
        peso = peso_nacional_division(div.codigo)

        if div.codigo in overrides_division:
            v = overrides_division[div.codigo]
            fuente = "manual"
            cobertura_interna = None
        else:
            tiene_cobertura = any(c.cobertura == Cobertura.MEDIDA_SEPA
                                  for c in clases_de_division(div.codigo))
            if tiene_cobertura:
                res = division_completa_nacional(con, div.codigo, desde, hasta,
                                                  desde_base, hasta_base, overrides_clase)
                v = res.variacion_pct
                fuente = "medida" if v is not None else "sin_dato"
                cobertura_interna = res.cobertura if v is not None else None
            else:
                v = None
                fuente = "sin_dato"
                cobertura_interna = None

        filas.append(FilaDivision(div.codigo, div.nombre, peso, v, fuente, cobertura_interna))
        if v is not None:
            valores[div.codigo] = v

    if not valores:
        return ResultadoNivelGeneral(None, 0.0, filas)

    pesos = {cod: peso_nacional_division(cod) for cod in valores}
    agregado = laspeyres(valores, pesos)
    peso_total_pais = sum(peso_nacional_division(d.codigo) for d in divisiones())

    return ResultadoNivelGeneral(
        variacion_pct=agregado.variacion_pct,
        cobertura=agregado.peso_cubierto / peso_total_pais if peso_total_pais else 0.0,
        divisiones=filas,
    )


# ==========================================================================
# CAPA DE RENDIMIENTO: separar "leer de la base" (caro) de "combinar
# numeros" (barato), para que la interfaz pueda cachear solo lo primero.
#
# POR QUE ESTO EXISTE:
# `nivel_general_nacional` y `resumen_divisiones_nacional` hacen, cada vez
# que se llaman, una consulta SQL + una media geometrica por CADA una de
# las ~19 subcategorias medidas, en CADA una de las 6 regiones — para
# despues combinarlas. Eso es el trabajo pesado. Pero en modo simulacion,
# la persona interactua tildando casillas y escribiendo numeros — cambios
# que no requieren volver a leer nada de la base, porque no afectan a las
# subcategorias que SI se miden. Antes de este cambio, cada click volvia a
# hacer todo el trabajo pesado de nuevo, lo cual se sentia lento.
#
# La solucion: `valores_medidos_nacional` hace SOLO la parte cara (leer y
# calcular), y depende nada mas que del rango de fechas — la interfaz la
# puede cachear con `@st.cache_data` sin que los overrides formen parte de
# la clave de cache. `resumen_divisiones_desde_valores` y
# `nivel_general_desde_divisiones` hacen SOLO la parte barata (aplicar
# overrides y sumar con pesos), que es instantanea y se puede repetir en
# cada interaccion sin costo.
# ==========================================================================

def valores_medidos_nacional(con, desde, hasta, desde_base, hasta_base) -> dict[str, float]:
    """La parte CARA: la variacion nacional de cada subcategoria medida por
    SEPA (combinando las 6 regiones). No conoce overrides — es el dato tal
    cual lo releva el sistema. Se calcula una vez por rango de fechas."""
    valores: dict[str, float] = {}
    for codigo in CLASES_CON_COBERTURA_SEPA:
        v, _cobertura = variacion_clase_nacional(con, codigo, desde, hasta, desde_base, hasta_base)
        if v is not None:
            valores[codigo] = v
    return valores


def resumen_divisiones_desde_valores(
    valores_medidos: dict[str, float],
    overrides_clase: dict[str, float] | None = None,
) -> list[ResultadoDivision]:
    """La parte BARATA: arma las 12 divisiones a partir de valores YA
    CALCULADOS (ver valores_medidos_nacional), sin tocar la base. Aplicar
    un override acá es instantáneo."""
    overrides_clase = overrides_clase or {}
    salida = []
    for div in divisiones():
        clases_div = [c for c in clases_de_division(div.codigo)
                      if c.cobertura == Cobertura.MEDIDA_SEPA]
        if not clases_div:
            salida.append(ResultadoDivision(
                div.codigo, div.nombre, peso_nacional_division(div.codigo), None, 0.0, []))
            continue

        filas: list[FilaClase] = []
        num = den = 0.0
        tiene_manuales = False
        for clase in clases_div:
            peso = peso_nacional_clase(clase.codigo)
            if clase.codigo in overrides_clase:
                v = overrides_clase[clase.codigo]
                es_manual = True
                tiene_manuales = True
            else:
                v = valores_medidos.get(clase.codigo)
                es_manual = False
            filas.append(FilaClase(clase.codigo, clase.nombre, peso, v, 0, es_manual=es_manual))
            if v is not None:
                num += peso * v
                den += peso

        variacion = num / den if den else None
        for f in filas:
            f.aporte_pp = (f.peso / den * f.variacion_pct) if (den and f.variacion_pct is not None) else None

        peso_total = sum(peso_nacional_clase(c.codigo) for c in clases_div)
        salida.append(ResultadoDivision(
            codigo=div.codigo, nombre=div.nombre, peso=peso_nacional_division(div.codigo),
            variacion_pct=variacion,
            cobertura=(den / peso_total) if peso_total else 0.0,
            clases=filas, tiene_manuales=tiene_manuales,
        ))
    return salida


def actualizar_override(overrides: dict[str, float], codigo: str, usar: bool, valor: float) -> None:
    """Lógica pura de qué hacer con un diccionario de overrides dado el
    estado de los dos controles de edición (checkbox "usar", número
    escrito). Muta el diccionario en el lugar, igual que hace
    `st.session_state`, para que quien llama no tenga que reasignar nada.

    Se separa de app_streamlit.py a propósito: la app no hace cuentas, y
    esto —aunque parezca trivial— es la lógica que decide si un valor
    manual cuenta o no. Vive acá para poder testearla sin necesitar
    Streamlit instalado (ver tests/test_callbacks_edicion.py), que es el
    módulo que corrige el bug real reportado: "hay que pasar a otro ítem
    para que el valor cuente en el nivel general". La causa era de orden
    de ejecución del script (Streamlit corre todo de arriba a abajo, y el
    nivel general se calculaba antes de llegar a los controles de
    edición); la corrección usa `on_change` para que esta función se
    ejecute ANTES de que el script vuelva a correr desde el principio, en
    vez de guardar el valor más abajo en el mismo pase donde ya era tarde."""
    if usar:
        overrides[codigo] = valor
    else:
        overrides.pop(codigo, None)


def nivel_general_desde_divisiones(
    divs: list[ResultadoDivision],
    overrides_division: dict[str, float] | None = None,
) -> ResultadoNivelGeneral:
    """La parte BARATA equivalente para el nivel general: combina
    divisiones YA CALCULADAS (ver resumen_divisiones_desde_valores) con
    los overrides de división. Instantáneo — no toca la base."""
    overrides_division = overrides_division or {}
    filas: list[FilaDivision] = []
    valores: dict[str, float] = {}

    for d in divs:
        if d.codigo in overrides_division:
            v = overrides_division[d.codigo]
            fuente = "manual"
            cobertura_interna = None
        elif d.variacion_pct is not None:
            v = d.variacion_pct
            fuente = "medida"
            cobertura_interna = d.cobertura
        else:
            v = None
            fuente = "sin_dato"
            cobertura_interna = None
        filas.append(FilaDivision(d.codigo, d.nombre, d.peso, v, fuente, cobertura_interna))
        if v is not None:
            valores[d.codigo] = v

    if not valores:
        return ResultadoNivelGeneral(None, 0.0, filas)

    pesos = {cod: peso_nacional_division(cod) for cod in valores}
    agregado = laspeyres(valores, pesos)
    peso_total_pais = sum(peso_nacional_division(d.codigo) for d in divisiones())

    return ResultadoNivelGeneral(
        variacion_pct=agregado.variacion_pct,
        cobertura=agregado.peso_cubierto / peso_total_pais if peso_total_pais else 0.0,
        divisiones=filas,
    )
