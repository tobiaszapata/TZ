# Método de cálculo vs. Metodología INDEC N°32

| Paso | INDEC (apartado) | Qué hace el código |
|---|---|---|
| Unidad observada | artículo-negocio | (EAN, cadena, región); SEPA trae un precio diario por cada uno |
| Precio del artículo-negocio en el período | media **aritmética** de los precios positivos del mes (5.1, fórmula 6) | igual, sobre los días del período elegido |
| Panel | artículos-negocios del mes base | solo se comparan los presentes en ambos períodos |
| Relativo de un producto | media **geométrica** simple entre negocios (5.1, fórmula 7) | igual (relativos de sus negocios) |
| Relativo de la clase | media geométrica de los artículos de la variedad (5.1) | media **geométrica** de los productos con peso proxy = cantidad de observaciones del producto (ponderador por producto no existe en INDEC; se mantiene la decisión previa) |
| Faltantes | 7.1: >50% propia; 20–50% superior para los faltantes; <20% superior | >50% propia; 20–50% `propio^c × superior^(1−c)`; <20% superior. "Superior" = demás clases del mismo grupo (si no, de la división) |
| Clase → grupo → división → nivel general | suma ponderada tipo Laspeyres (5.2) | media aritmética ponderada con ponderadores oficiales (sin cambios) |
| Regiones → país | suma ponderada con Cuadro 6 (5.3) | sin cambios; regiones sin dato se excluyen y se renormaliza |

Límites que siguen declarados: no hay ponderadores oficiales por producto ni por variedad
(el peso dentro de la clase es una proxy); SEPA solo cubre supermercados (INDEC combina
supermercados y negocios tradicionales con proporciones fijas, fórmula 8); el método
anterior se conserva con `metodo="previo"` solo para comparar.

## Por que media geometrica entre productos de una clase

INDEC usa media geometrica simple (sin ponderar) para combinar los precios de una misma
variedad (5.1, formula 7) y recien arriba, entre variedades con ponderador de gasto de la
ENGHo, la suma ponderada tipo Laspeyres (5.2). SEPA no permite identificar variedades ni hay
ponderadores por producto, de modo que dentro de cada clase solo se puede aplicar el criterio
del nivel elemental: media geometrica. Usar una media aritmetica con pesos por cantidad de
observaciones aparentaria un Laspeyres que no existe (esos pesos no son gasto) y sesga hacia
arriba (el manual de numeros indice que cita INDEC prefiere la formula tipo Jevons). El
calculo anterior sigue disponible con `metodo="previo"` para comparar.

## Excluir productos (interfaz)

En el desglose de una subcategoria se pueden elegir productos para dejarlos afuera: se
recalcula la subcategoria en todas las regiones con el mismo metodo y se muestra el efecto
en la division y en el nivel general. No modifica la base ni el calculo principal.
