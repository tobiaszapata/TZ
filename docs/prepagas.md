# Prepagas y obras sociales (clase 06.4.1) — fuente SSSalud

## Que se mide y de donde sale
Division 06 Salud, grupo 06.4 "Gastos de prepagas y obras sociales" (2,20% del
gasto nacional; 3,18% en GBA). INDEC no publica clases dentro de este grupo, asi
que se creo la clase **06.4.1**, con el mismo peso que el grupo (config/canasta.py).

La fuente son los **cuadros tarifarios que las entidades declaran** a la
Superintendencia de Servicios de Salud (Res. 645/2025):
https://cuadrostarifarios.sssalud.gob.ar/ — 17 periodos mensuales (202507 en
adelante), ~15.000 filas por mes, ~200 entidades.

Aclaracion del propio sitio: los valores pueden no coincidir con lo efectivamente
facturado (bonificaciones/descuentos de las entidades).

## Por que mensual y no diario
Las cuotas cambian de forma discreta, una vez por mes (el sitio publica un cuadro
por periodo AAAAMM). Medirlas todos los dias no agrega informacion. Un periodo del
calculo que cruza dos meses mezcla las dos cuotas en proporcion a los dias de cada
mes (la cuota es un escalon que rige hasta el proximo cambio).

## Como se calcula (engine/prepagas.py)
1. **Unidad** = plan de una entidad en una region declarada, rango etario, tipo de
   plan, modalidad y copago (la clave de unicidad del manual de la Res. 645/2025).
2. Se comparan solo unidades presentes en los dos periodos.
3. **Relativo de una region INDEC** = media geometrica ponderada de los relativos de
   las unidades que rigen en esa region; peso = gasto del periodo base de la
   unidad (cuota x cantidad de capitas), tipo Laspeyres.
4. **Cobertura** = gasto base de lo comparado / gasto base total. Mas de 50%: dato
   propio. Entre 20% y 50%: se mezcla con la variacion de las demas clases de
   Salud. Menos de 20%: se usa la de las demas clases (Metodologia N°32, 7.1).
5. **Nacional** = las 6 regiones combinadas con su importancia en el gasto nacional
   (Cuadro 6: GBA 44,67%, Pampeana 34,19%, Noroeste 6,88%, Cuyo 5,18%, Patagonia
   4,57%, Noreste 4,51%), igual que el resto de las clases.
6. Control de calidad: un relativo fuera de [0,5; 2,0] en una unidad se descarta.

## Regiones: de texto libre a las 6 de INDEC
Las prepagas escriben la region como quieren (137 textos distintos en octubre de
2026: "CABA", "AMBA", "Pais excepto Patagonia, Bs As y CABA", ...).
config/regiones_prepagas.py los traduce usando los aglomerados de cada region de
INDEC (Metodologia N°32, Cuadro 5). Un plan que abarca varias regiones aporta a
todas ellas. Aproximaciones declaradas:
* "Provincia de Buenos Aires" aporta a GBA y a Pampeana.
* "Pais excepto ... Bs As ..." resta solo GBA.
* Textos ambiguos ("GENERAL", "Resto", "Interior", "ZONA CENTRO", "NO IDENTIFICADA")
  quedan marcados *dudosos*. `scripts/consultar_prepagas.py` muestra cuantas capitas
  caen ahi; se corrigen en `externos/prepagas/regiones.csv` (columnas
  `region_texto;regiones`, regiones separadas por coma) sin tocar codigo.

## Rutina (semanal)
* Todo en uno: `python -m scripts.actualizar` (o doble clic en `actualizar.bat`) ya
  incluye un paso "2b Prepagas": baja los meses nuevos desde 202607 y revisa los
  dos ultimos ya bajados (compara la cantidad de filas con la del sitio; si cambio,
  lo vuelve a bajar). No bloquea la carga de SEPA si falla. El push a GitHub incluye `externos/`.
* Solo prepagas: `python -m scripts.actualizar_prepagas --subir`.
* Los meses en curso llegan INCOMPLETOS (el 7/11/2026 noviembre tenia 7.748 filas y
  octubre 11.801): las entidades cargan sus cuadros durante el mes. Por eso se revisa
  cada semana.

## En la app
Tilde **"Incluir prepagas (se mide por mes)"** en la barra lateral, apagado por
defecto. Apagado: la clase no se calcula ni se leen sus archivos (las comparaciones
semanales no cambian). Prendido: entra con la logica mensual; si las dos ventanas
caen en el mismo mes su variacion es 0%.

## Limitaciones conocidas
* No distingue un plan renombrado de uno nuevo: sale de la comparacion ese mes.
* El rango etario es el que declara cada entidad (no hay una grilla unica).
* Las cuotas son las declaradas, no las facturadas.
* Los datos de la API se leyeron desde un navegador; la descarga con Python
  (scripts/descargar_prepagas.py) esta probada contra una API simulada. Si el
  sitio la rechazara, usar el plan B: scripts/prepagas_navegador.js.
* Piso por defecto: 202607 (el sitio tiene desde 202507); cambia con `--desde`.
