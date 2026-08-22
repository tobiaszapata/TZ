#!/usr/bin/env python3
"""
Herramienta de consulta - responde, sobre datos YA cargados:
  - cuanto se movio cada categoria (y que productos lo explican)
  - lo mismo pero entre dos rangos de fechas (p.ej. semana contra semana)
  - una proyeccion de como cerraria el mes si los precios se congelaran hoy

NO releva ni calcula nada nuevo: lee lo que ya esta en la base (cargado por
scripts/correr_dia.py). Se puede correr las veces que quieras.

--------------------------------------------------------------------------
MODO 1 - RESUMEN de todas las categorias, mes contra mes:
  python -m scripts.consultar resumen --mes 2026-08 --contra 2026-07

MODO 2 - UNA categoria con sus productos, mes contra mes:
  python -m scripts.consultar clase --clase 01.1.6 --mes 2026-08 --contra 2026-07

MODO 3 - UNA categoria entre dos RANGOS de fechas (semana vs semana):
  python -m scripts.consultar rango --clase 01.1.6 \
      --desde 2026-08-08 --hasta 2026-08-14 \
      --desde-base 2026-08-01 --hasta-base 2026-08-07

MODO 4 - PROYECCION de cierre de mes de una categoria:
  python -m scripts.consultar proyeccion --clase 01.1.6 --mes 2026-08 --contra 2026-07
--------------------------------------------------------------------------

Codigos de categoria (ver config/canasta.py):
  01.1.1 Pan y cereales      01.1.6 Frutas
  01.1.2 Carnes y derivados  01.1.7 Verduras, tuberculos y legumbres
  01.1.4 Leche, lacteos, huevos   01.2.1 Cafe, te, yerba
  01.1.5 Aceites y grasas    01.2.2 Aguas, gaseosas y jugos
  01.1.8 Azucar y dulces
"""

from __future__ import annotations

import argparse
import calendar
from datetime import date
from pathlib import Path

from config.canasta import CANASTA, CLASES_CON_COBERTURA_SEPA
from engine.arrastre import calcular_piso
from engine.index_elemental import media_geometrica
from engine.escenarios import (
    escenario_congela_desde,
    escenario_congelamiento,
    escenario_continuidad,
    escenario_patron_intramensual,
)
from engine.proyeccion import curva_realizacion_generica
from engine.reporte import calcular_clase_y_productos
from storage.db import (
    conectar,
    nombres_de_productos,
    precios_por_producto_en_mes,
    precios_por_producto_en_rango,
    valores_diarios_de_clase,
)

DB_PATH = Path("relevamiento_precios.db")


def _nombre(codigo):
    return CANASTA[codigo].nombre if codigo in CANASTA else codigo


def _variacion_mes(con, clase_codigo, mes, mes_anterior):
    p_mes = precios_por_producto_en_mes(con, clase_codigo, mes)
    p_ant = precios_por_producto_en_mes(con, clase_codigo, mes_anterior)
    eans = list(set(p_mes) | set(p_ant))
    return calcular_clase_y_productos(p_mes, p_ant, nombres_de_productos(con, eans))


def _imprimir_drivers(resultado, drivers, top):
    if resultado is None:
        print("  Sin productos en comun entre los dos periodos - no se puede comparar todavia.")
        return
    print(f"  Variacion: {resultado.variacion_pct:+.2f}%")
    print(f"  Productos comparados: {resultado.n_productos_comparados}"
          f"  (nuevos: {resultado.n_productos_solo_mes_actual},"
          f"  desaparecidos: {resultado.n_productos_solo_mes_anterior})\n")
    print(f"  {'producto':<34} {'var %':>8} {'peso*':>7} {'aporte pp':>10}")
    print(f"  {'-'*34} {'-'*8} {'-'*7} {'-'*10}")
    for d in drivers[:top]:
        nom = (d.nombre_producto[:32] + "..") if len(d.nombre_producto) > 34 else d.nombre_producto
        print(f"  {nom:<34} {d.variacion_pct:>+7.1f}% {d.peso_proxy_pct:>6.1f}% "
              f"{d.incidencia_aproximada_pp:>+9.2f}")
    print("\n  * 'peso' es proxy por nro de observaciones, NO el ponderador oficial de INDEC.")
    print("    'aporte pp': cuantos puntos de la variacion explica cada producto; suman el total.")


def _variacion_rango(con, clase_codigo, desde, hasta, desde_base, hasta_base):
    p_act = precios_por_producto_en_rango(con, clase_codigo, desde, hasta)
    p_base = precios_por_producto_en_rango(con, clase_codigo, desde_base, hasta_base)
    eans = list(set(p_act) | set(p_base))
    return calcular_clase_y_productos(p_act, p_base, nombres_de_productos(con, eans))


def cmd_resumen(con, args):
    """Resumen de todas las categorias. Acepta dos modos:
      - mes contra mes:   --mes 2026-08 --contra 2026-07
      - rango contra rango: --desde .. --hasta .. --desde-base .. --hasta-base ..
    El segundo modo es el que sirve cuando todavia no hay un mes anterior
    completo en la base (por ejemplo, arrancando a mitad de mes)."""
    por_rango = bool(getattr(args, "desde", None))
    if por_rango:
        print(f"\nResumen division 01 - [{args.desde} .. {args.hasta}] "
              f"contra [{args.desde_base} .. {args.hasta_base}]")
    else:
        print(f"\nResumen division 01 - {args.mes} contra {args.contra}")

    print(f"{'clase':<9} {'nombre':<40} {'var %':>9} {'prod.':>6}")
    print(f"{'-'*9} {'-'*40} {'-'*9} {'-'*6}")
    hubo_datos = False
    for codigo in CLASES_CON_COBERTURA_SEPA:
        if por_rango:
            resultado, _ = _variacion_rango(con, codigo, args.desde, args.hasta,
                                            args.desde_base, args.hasta_base)
        else:
            resultado, _ = _variacion_mes(con, codigo, args.mes, args.contra)
        nombre = _nombre(codigo)[:40]
        if resultado:
            hubo_datos = True
            print(f"{codigo:<9} {nombre:<40} {resultado.variacion_pct:>+8.2f}% "
                  f"{resultado.n_productos_comparados:>6}")
        else:
            print(f"{codigo:<9} {nombre:<40} {'s/datos':>9} {'-':>6}")

    if not hubo_datos:
        print("\nNinguna categoria tiene datos en AMBOS periodos.")
        print("Si recien empezas y no tenes el mes anterior cargado, compara")
        print("dos rangos de fechas dentro de lo que si tenes, por ejemplo:")
        print("  python -m scripts.consultar resumen \\")
        print("      --desde 2026-08-13 --hasta 2026-08-16 \\")
        print("      --desde-base 2026-08-09 --hasta-base 2026-08-12")
    else:
        print("\nPara ver los productos de una categoria: 'clase --clase <codigo>'")


def cmd_clase(con, args):
    print(f"\n{'='*72}\n  {args.clase}  {_nombre(args.clase)}")
    print(f"  {args.mes} contra {args.contra}\n{'='*72}")
    resultado, drivers = _variacion_mes(con, args.clase, args.mes, args.contra)
    _imprimir_drivers(resultado, drivers, args.top)


def cmd_rango(con, args):
    print(f"\n{'='*72}\n  {args.clase}  {_nombre(args.clase)}")
    print(f"  [{args.desde} .. {args.hasta}] contra [{args.desde_base} .. {args.hasta_base}]\n{'='*72}")
    p_act = precios_por_producto_en_rango(con, args.clase, args.desde, args.hasta)
    p_base = precios_por_producto_en_rango(con, args.clase, args.desde_base, args.hasta_base)
    eans = list(set(p_act) | set(p_base))
    resultado, drivers = calcular_clase_y_productos(p_act, p_base, nombres_de_productos(con, eans))
    _imprimir_drivers(resultado, drivers, args.top)


def _dias_habiles(anio, mes_num):
    _, ultimo = calendar.monthrange(anio, mes_num)
    return sum(1 for d in range(1, ultimo + 1) if date(anio, mes_num, d).weekday() < 5)


def cmd_proyeccion(con, args):
    anio, mes_num = int(args.mes[:4]), int(args.mes[5:7])
    print(f"\n{'='*74}\n  ESCENARIOS DE CIERRE - {args.clase}  {_nombre(args.clase)}")
    print(f"  mes {args.mes}, comparado contra promedio de {args.contra}\n{'='*74}")

    serie = valores_diarios_de_clase(con, args.clase, args.mes)
    if not serie:
        print("  Sin datos del mes en curso para esta categoria.")
        return

    p_base = precios_por_producto_en_mes(con, args.clase, args.contra)
    if not p_base:
        print(f"  Falta el mes base {args.contra} en la base para poder comparar.")
        return
    nivel_base = media_geometrica([media_geometrica(v) for v in p_base.values()])

    valores = [v for _fecha, v in serie]
    dias_totales = _dias_habiles(anio, mes_num)
    k = len(valores)

    piso = calcular_piso(valores, dias_totales, nivel_base)
    var_observada = (piso.promedio_parcial_observado / nivel_base - 1) * 100
    fraccion = curva_realizacion_generica(k, dias_totales)

    e_cong = escenario_congelamiento(valores, dias_totales, nivel_base)
    e_cont = escenario_continuidad(valores, dias_totales, nivel_base)
    e_patron = escenario_patron_intramensual(
        var_observada, fraccion, e_cong.variacion_pct, nivel_base,
        e_cong.promedio_mes_proyectado,
    )
    dia_congela = args.congela_desde or max(k + 1, dias_totales // 2)
    e_mixto = escenario_congela_desde(valores, dias_totales, nivel_base, dia_congela)

    print(f"  Dias con datos: {k} de {dias_totales} habiles ({k/dias_totales:.0%} del mes)")
    print(f"  Variacion observada hasta hoy: {var_observada:+.2f}%\n")

    escenarios = [e_cong, e_mixto, e_patron, e_cont]
    print(f"  {'escenario':<32} {'cierre':>9}   supuesto")
    print(f"  {'-'*32} {'-'*9}   {'-'*28}")
    for esc in escenarios:
        marca = " (dato duro)" if esc.es_dato_duro else ""
        print(f"  {esc.nombre:<32} {esc.variacion_pct:>+8.2f}%   {esc.supuesto}{marca}")

    variaciones = [e.variacion_pct for e in escenarios]
    print(f"\n  Rango entre escenarios: {min(variaciones):+.2f}%  a  {max(variaciones):+.2f}%")
    print("\n  Como leerlo: 'Congelamiento' es aritmetica pura (sin modelo) y funciona")
    print("  como piso. Los otros tres son supuestos distintos sobre lo que falta del")
    print("  mes. Todos proyectan el PROMEDIO del mes, que es lo que compara INDEC.")
    print("  El patron intra-mensual usa una curva todavia PRELIMINAR (se calibra")
    print("  cuando haya varios meses cargados).")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="modo", required=True)

    p = sub.add_parser("resumen")
    p.add_argument("--mes"); p.add_argument("--contra")
    p.add_argument("--desde"); p.add_argument("--hasta")
    p.add_argument("--desde-base", dest="desde_base"); p.add_argument("--hasta-base", dest="hasta_base")
    p = sub.add_parser("clase")
    p.add_argument("--clase", required=True); p.add_argument("--mes", required=True)
    p.add_argument("--contra", required=True); p.add_argument("--top", type=int, default=10)
    p = sub.add_parser("rango")
    p.add_argument("--clase", required=True)
    p.add_argument("--desde", required=True); p.add_argument("--hasta", required=True)
    p.add_argument("--desde-base", required=True, dest="desde_base")
    p.add_argument("--hasta-base", required=True, dest="hasta_base")
    p.add_argument("--top", type=int, default=10)
    p = sub.add_parser("proyeccion")
    p.add_argument("--clase", required=True); p.add_argument("--mes", required=True)
    p.add_argument("--contra", required=True)
    p.add_argument("--congela-desde", type=int, default=None, dest="congela_desde",
                   help="dia habil a partir del cual congelar en el escenario mixto")

    args = ap.parse_args()

    if not DB_PATH.exists():
        print(f"No encuentro la base {DB_PATH}. Corriste scripts.correr_dia al menos una vez?")
        return

    con = conectar(DB_PATH)
    {"resumen": cmd_resumen, "clase": cmd_clase, "rango": cmd_rango, "proyeccion": cmd_proyeccion}[args.modo](con, args)
    con.close()


if __name__ == "__main__":
    main()
