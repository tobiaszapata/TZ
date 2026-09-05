# COICOP Argentina — Notas explicativas oficiales (INDEC, noviembre 2019)

Fuente: https://www.indec.gob.ar/ftp/cuadros/menusuperior/clasificadores/coicop_argentina_2019.pdf

Este archivo guarda las notas "incluye / excluye" oficiales de cada subclase,
tal como las publica INDEC, para poder verificar cualquier regla de
`collectors/sepa/mapeo.py` contra la definición exacta en vez de contra
intuición. Cuando se agregue o corrija una regla, buscar acá la subclase
correspondiente antes de decidir qué palabras usar.

Estructura de la COICOP Argentina: División (2 dígitos) > Grupo (3) >
Clase (4) > Subclase (5) > Producto (7). 12 divisiones, 52 grupos,
128 clases, 184 subclases, 1.709 productos.

---

## 01 ALIMENTOS Y BEBIDAS NO ALCOHÓLICAS

Productos alimenticios generalmente comprados para ser consumidos en el
domicilio. Excluye: platos preparados para llevar de restaurantes/cantinas
(van a 11.1.1.1) y alimento para mascotas (09.3.4.1).

### 01.1.1 Pan y cereales
- **01.1.1.1** Productos de panadería y pastelería: pan de cualquier
  cereal (fresco/envasado/congelado/precocido), tortas y tartas.
- **01.1.1.2** Galletas, galletitas, alfajores, tostadas y grisines:
  dulces o saladas, sueltas o envasadas; pan tostado, crepes.
- **01.1.1.3** Harinas, arroz y cereales: cereales procesados o no,
  copos/láminas; arroces; féculas, sémolas, harinas; mezclas para pizza.
- **01.1.1.4** Pastas: frescas/secas/deshidratadas/preparadas, con o sin
  relleno; tapas para empanadas/tartas/panqueques.

### 01.1.2 Carnes y derivados
Excluye: pastas con carne (01.1.1.4); grasas animales comestibles (01.1.5.2).
- **01.1.2.1** Carne vacuna fresca/congelada/semipreparada: vaca,
  novillo, ternera, buey, toro; achuras y menudencias vacunas.
- **01.1.2.2** Carne de ave: pollo, perdiz, codorniz, pavo, pato, etc.;
  menudencias de ave.
- **01.1.2.3** Carne porcina u ovina: cerdo, cordero, oveja, cabra,
  cabrito, lechón, cochinillo.
- **01.1.2.4** Otras carnes frescas o congeladas: cualquier otra no
  especificada arriba.
- **01.1.2.5** Embutidos frescos: cualquier material cárnico, curados,
  que requieren cocinado, escaldados, ahumados. Excluye: grasas animales
  y salchichas frescas.
- **01.1.2.6** Fiambres: suelto o empaquetado. Excluye: salchichas
  frescas/congeladas.
- **01.1.2.7** Procesados en base a carnes: conservas, escabeches,
  **patés** y picadillos.

### 01.1.3 Pescados y mariscos
Excluye: pastas con pescado (01.1.1.4).
- **01.1.3.1** Pescados frescos/congelados, moluscos y crustáceos.
- **01.1.3.2** Pescados y mariscos en conserva.

### 01.1.4 Leche, productos lácteos, huevos y alimentos vegetales
- **01.1.4.1** Leches y alimentos vegetales líquidos. Excluye: leche
  para bebés (06.1.1.1), leche condensada/evaporada (01.1.4.3).
- **01.1.4.2** Quesos y cuajadas: curados, semicurados, tiernos, para
  untar/rallar/fundido.
- **01.1.4.3** Yogur, dulce de leche, postres y otros productos lácteos:
  yogures, postres/bebidas a base de leche, natillas, flanes, leche
  condensada/evaporada. Excluye: helados (01.1.8.3).
- **01.1.4.3** (repetido en el original) Huevos: de gallina, codorniz, etc.

**IMPORTANTE — hallazgo para el proyecto**: esta clase NO incluye snacks
con sabor a queso ("Chizitos queso"), sólo el queso en sí como alimento.
Ver bug corregido en `mapeo.py` (exclusión de "chizito"/"palito"/"snack").

### 01.1.5 Aceites, grasas y manteca
- **01.1.5.1** Aceites: girasol, oliva, maíz, soja, líquidos o en spray.
- **01.1.5.2** Grasas para cocinar: origen animal o vegetal; margarina.
- **01.1.5.3** Manteca.

### 01.1.6 Frutas
- **01.1.6.1** Frutas frescas o congeladas.
- **01.1.6.2** Frutas secas, deshidratadas y en conserva: nueces, mix de
  frutos secos, semillas. Excluye: frutos secos confitados (01.1.8.4).

### 01.1.7 Verduras, tubérculos y legumbres
Incluye aceitunas.
- **01.1.7.1** Verduras y hortalizas frescas o refrigeradas.
- **01.1.7.2** Verduras/tubérculos/legumbres secas, deshidratadas o en
  conserva.

**IMPORTANTE**: no incluye caldos ni sopas (esos van a 01.1.9.3), aunque
digan "de verdura". Ver exclusión ya agregada en `mapeo.py`.

### 01.1.8 Azúcar, dulces, chocolate, golosinas, etc.
- **01.1.8.1** Azúcar y edulcorantes: refinada, orgánica, morena,
  impalpable, molida o en terrones; edulcorantes.
- **01.1.8.2** Dulces, mermeladas y miel: mermeladas, compotas, jaleas,
  miel, melaza. Excluye: gelatinas en polvo (01.1.9.3).
- **01.1.8.3** Helados: sueltos o envasados, postres y tortas heladas.
- **01.1.8.4** Chocolates y otros dulces o golosinas: chocolate,
  alfajores, barras de cereal, bombones, caramelos, turrones.

### 01.1.9 Otros alimentos
- **01.1.9.1** Sal, especias, hierbas aromáticas.
- **01.1.9.2** Salsas y aderezos: salsas, mayonesa, kétchup, mostaza,
  vinagres.
- **01.1.9.3** Sopas, preparaciones para postres, alimentos para bebés y
  levadura: sopas y **caldos** (de carne/ave/pescado/verdura, deshidratados
  o en cubitos); polvo para tortas/flanes; gelatina en polvo; levadura;
  TODO alimento para bebés (leche, cereales, papillas).

### 01.2.1 Café, té, yerba y cacao
Café, té, yerba mate y mate cocido, cacao/chocolate en polvo. Excluye:
chocolate en tableta (01.1.8.4).

### 01.2.2 Aguas minerales, bebidas gaseosas y jugos
Aguas minerales/de manantial, agua potable envasada **con o sin gas**,
soda, aguas saborizadas, aperitivos sin alcohol, gaseosas, jugos y
refrescos (polvo o líquidos), bebidas energizantes, jugos de vegetales.

**IMPORTANTE — bug real encontrado**: la definición oficial habla de
"agua... con o sin gas" siempre en el contexto de AGUA — nunca como
palabra suelta "s/gas" o "c/gas" que pueda matchear cualquier otro
producto (como "PISTOLA AGUA C/GAS", un juguete que debería ir a 09.3.1).
Corregido en `mapeo.py`: las claves de gas ahora requieren la palabra
"agua" en la misma frase.

---

## 02 BEBIDAS ALCOHÓLICAS Y TABACO

### 02.1.1 Bebidas espirituosas, destiladas y licores
Brandy, coñac, whisky, aguardientes, licores, vermuts y aperitivos cuya
base NO es el vino.

### 02.1.2 Vinos
Vino de mesa, espumantes, sidras, bebidas de fruta con alcohol (no uva).

### 02.1.3 Cerveza
Con o sin alcohol, artesanal e industrial, botella/lata/suelta.

### 02.2.1 Tabaco
Cigarrillos, tabaco para liar, papel de fumar, tabaco de pipa, puros.
**SEPA no releva esta subclase** (verificado contra 3 días reales de
datos, sin ninguna coincidencia — ver conversación del proyecto).

### 02.3.1 Estupefacientes
Marihuana, opio, cocaína, narcóticos. No relevable por ninguna fuente
comercial legal, obviamente.

---

## 03 PRENDAS DE VESTIR Y CALZADO

### 03.1.1 Materiales textiles, telas e hilados
- **03.1.1.1** Telas para confección en el hogar. Excluye: tejidos para
  mobiliario (05.2.1.2).
- **03.1.1.2** Hilados para tejer.

### 03.1.2 Prendas de vestir
- **03.1.2.1** Ropa exterior para hombre.
- **03.1.2.2** Ropa exterior para mujer.
- **03.1.2.3** Ropa exterior para niños y bebés. Excluye: pañales
  (12.1.3.1), baberos y gorritos (03.1.3.2).
- **03.1.2.4** Ropa interior para hombre: calzoncillos, camisetas,
  medias, pijamas.
- **03.1.2.5** Ropa interior para mujer: bombachas, corpiños, medias,
  camisones.
- **03.1.2.6** Ropa interior para niños: bombachas, calzoncillos,
  escarpines, medias, pañales.

**IMPORTANTE**: uniformes escolares van acá (03.1.2), no en Educación.

### 03.1.3 Otros artículos y accesorios para el vestir
- **03.1.3.1** Marroquinería: billeteras, carteras, cinturones.
- **03.1.3.2** Complementos y accesorios: pañuelos, paraguas, bufandas,
  sombreros, gorros, baberos. Excluye: guantes de plástico (05.6.1.2),
  equipo de protección deportiva (09.3.2.1), relojes/joyas (12.3.1.1).
- **03.1.3.3** Artículos para coser y tejer: agujas, botones, hilos.

### 03.1.4 Limpieza, reparación, alquiler de ropa
Lavaderos, tintorerías, reparación de prendas.

### 03.2.1 Zapatos y otros calzados
Calzado para hombre/mujer/niño: zapatos, botas, sandalias, zapatillas.
Excluye: calzado exclusivamente deportivo (09.3.2.1), zapatos
ortopédicos (06.1.3.1).

### 03.2.2 Limpieza, reparación y alquiler de calzado

---

## 04 VIVIENDA, AGUA, ELECTRICIDAD, GAS Y OTROS COMBUSTIBLES

No relevable por SEPA (servicios/tarifas/alquileres, sin precio de lista
en góndola). Detalle de subclases disponible en el PDF fuente si en
algún momento se evalúa scraping de tarifas reguladas.

---

## 05 EQUIPAMIENTO Y MANTENIMIENTO DEL HOGAR

### 05.1.1 Muebles y accesorios
Camas, roperos, colchones, mesas, sillas, artefactos de iluminación,
espejos. No relevado hoy (PENDIENTE en canasta.py).

### 05.2.1 Artículos textiles para el hogar
- **05.2.1.1** Ropa de cama (incluye almohada): almohadas, mantas,
  colchas, **sábanas**, cubrecamas.
- **05.2.1.2** Otros artículos textiles: **cortinas**, toallones,
  toldos, **manteles**. Excluye: alfombras (05.1.2.1).

**IMPORTANTE — bug real corregido**: "algodón" (06.1.2, primeros
auxilios) se robaba sábanas/toallas que mencionan su composición. Ver
exclusión agregada en `mapeo.py`.

### 05.3.1 / 05.3.2 Artefactos grandes/pequeños para el hogar
Heladeras, hornos, lavarropas, microondas (grandes); batidoras,
exprimidores, planchas (pequeños). No relevado hoy.

### 05.4.1 Vajilla, utensilios, loza y cristalería
- **05.4.1.1** Vajilla y utensilios: ollas, sartenes, fuentes, mate,
  pava. Excluye: vasos/platos **descartables** (05.6.1.3).
- **05.4.1.2** Loza, cerámica, cristalería: copas, vasos, tazas.
- **05.4.1.3** Plástico y madera para cocina.
- **05.4.1.4** Otros no eléctricos: heladeras portátiles, changos.

**IMPORTANTE**: "olla de aluminio" / "sartén de aluminio" van ACÁ, no a
Limpieza del hogar — ya verificado y corregido en `mapeo.py`.

### 05.5.1 / 05.5.2 Herramientas y equipos para el hogar y jardín
Taladros, sierras; martillos, destornilladores; **pilas, cables,
lámparas** (05.5.2.2, "materiales eléctricos y de iluminación"). No
relevado hoy como clase completa, aunque ya agregamos pilas/aluminio a
Limpieza del hogar (05.6.1) — **revisar si conviene mover a 05.5.2**
cuando se declare esa clase.

### 05.6.1 Bienes para el hogar no durables
- **05.6.1.1** Productos de limpieza: detergentes, suavizantes, jabones,
  lustramuebles, ceras.
- **05.6.1.2** Utensilios de limpieza: baldes, escobas, guantes de goma,
  trapos.
- **05.6.1.3** Artículos descartables: manteles/servilletas de papel,
  vasos/platos descartables, fósforos, **filtros de agua, bolsas de
  residuos**, papel higiénico (por extensión de "descartables para el
  hogar").

### 05.6.2 Servicios domésticos y para el hogar
Servicio doméstico, tintorería de textiles del hogar, fumigación. No
relevable (servicio).

---

## 06 SALUD

### 06.1.1 Productos farmacéuticos
Medicamentos, vacunas, leche medicamentosa, vitaminas, antibióticos.

### 06.1.2 Otros productos medicinales
- **06.1.2.1** Elementos para primeros auxilios: alcohol, **algodón**,
  gasas, vendas, desinfectantes, jeringas; termómetros, **preservativos**.

**IMPORTANTE**: el documento SÍ pone preservativos acá (06.1.2), no en
Cuidado personal (12.1.3) como habíamos asumido antes por intuición
propia. Esto contradice la regla que agregamos — revisar.

### 06.1.3 Artefactos y equipos terapéuticos
Anteojos, lentes de contacto, anticonceptivos mecánicos, accesorios
ortopédicos, nebulizadores. No relevado hoy.

### 06.2.x Servicios para pacientes externos / 06.3 Hospitalarios / 06.4 Prepagas
Servicios, no relevables por SEPA.

---

## 07 TRANSPORTE

Vehículos, combustibles, transporte público — mayormente servicios y
bienes de alto valor no relevados por SEPA (supermercados no venden
autos ni pasajes). Candidato de scraping a futuro solo para
combustibles (07.2.2), según lo ya conversado.

---

## 08 COMUNICACIÓN

Equipos y servicios de telefonía/internet — no relevado por SEPA
(supermercados no suelen vender celulares con plan, y los servicios de
telefonía son abonos, no productos de góndola).

---

## 09 RECREACIÓN Y CULTURA

### 09.1.1 a 09.1.4 Equipos audiovisuales, fotográficos, informática
TV, radios, cámaras, PC, medios de grabación. No relevado hoy.

### 09.3.1 Juegos, juguetes y hobbies
Juegos de mesa, **juguetes de todo tipo**, pequeños instrumentos
musicales de juguete, consolas de videojuegos.

**IMPORTANTE — bug real encontrado en esta conversación**: "pistola de
agua" (juguete) es 09.3.1, no 01.2.2. El error salía de las palabras
sueltas de gas agregadas a la regla de aguas — ya corregido.

### 09.3.2 Equipo para deporte, campamento y recreación al aire libre
Pelotas, raquetas, palos de golf, patines, calzado deportivo, armas de
caza, cañas de pesca, equipo de camping.

### 09.3.3 Plantas, flores y artículos de jardinería
Plantas, flores, fertilizantes, semillas, macetas.

### 09.3.4 Mascotas y productos conexos
Alimento para mascotas, collares, correas, arena higiénica, jaulas,
acuarios. **Excluido a propósito del proyecto** (ver `mapeo.py`,
exclusiones de marcas de pet food en la regla de Carnes).

### 09.5.1 Libros / 09.5.2 Diarios y revistas / 09.5.4 Papel y útiles de oficina
Libros, diarios, revistas; blocks, cuadernos, lápices, bolígrafos,
materiales de dibujo. No relevado hoy.

---

## 10 EDUCACIÓN

Exclusivamente servicios educativos (aranceles, matrícula). Excluye
explícitamente: material escolar (va a 09.5.1/09.5.4), uniformes
(03.1.2), transporte (07.3), comedores escolares (11.1.1.2). **No
relevable por SEPA de ninguna forma** — coincide con que INDEC mismo no
publica esta división abierta en grupos (Cuadro 19 de los informes
mensuales).

---

## 11 RESTAURANTES Y HOTELES

Consumo en el lugar (restaurantes, bares, comedores) y alojamiento. No
relevable por SEPA (es consumo en el local, no venta de producto de
góndola).

---

## 12 BIENES Y SERVICIOS VARIOS

### 12.1.1 Salones de peluquería
Servicios de peluquería, depilación, manicuría. No relevable (servicio).

### 12.1.2 Aparatos eléctricos para el cuidado personal
Máquinas de afeitar, depiladoras, secadores de pelo. No relevado hoy.

### 12.1.3 Otros aparatos, artículos y productos para la atención personal
- **12.1.3.1** Descartables para cuidado personal: cepillos dentales,
  hilo dental, repuestos de afeitar, **pañales, papel higiénico, toallas
  higiénicas, protectores diarios**.
- **12.1.3.2** Artículos de tocador y belleza: cosméticos, **champú,
  desodorante**, cremas, **jabón de tocador**, tinturas.
- **12.1.3.3** Utensilios para cuidado personal: alicate, tijera,
  balanzas, peine, cepillos.

**IMPORTANTE — a revisar**: el documento pone "papel higiénico" en
12.1.3.1 (cuidado personal), pero nuestra regla actual lo tiene en
05.6.1 (limpieza del hogar) por ser un "descartable del hogar". Es una
diferencia real de clasificación oficial que conviene corregir cuando
se revise esta subclase a fondo — no se corrige en este documento
todavía, queda anotado como pendiente de revisión.

### 12.3.1 Joyería y relojes / marroquinería
No relevado hoy.

### 12.2, 12.4, 12.5, 12.6, 12.7
Prostitución, protección social, seguros, servicios financieros, otros
servicios — todos servicios, no relevables por SEPA.
