# La primera carga y la recolección diaria

## Lo primero que tenés que entender: los datos son perecederos

SEPA **no publica un archivo por fecha**. Publica siete recursos nombrados
por día de la semana — "Lunes", "Martes", ... "Domingo" — y cada uno se
**sobrescribe** cada semana. El "Lunes" de hoy pisa al "Lunes" de la semana
pasada. Es una ventana móvil de 7 días.

**Consecuencia práctica: no se puede bajar histórico.** No hay archivo de
julio al que volver. Un día que no descargás se pierde para siempre.

Esto tiene dos implicancias que ordenan todo el arranque:

1. **No vas a poder comparar agosto contra julio todavía.** La comparación
   mes contra mes recién va a estar disponible cuando hayas acumulado dos
   meses recolectando. Mientras tanto, sí podés comparar semana contra
   semana en cuanto tengas dos semanas.
2. **La recolección hay que automatizarla ya.** Es la única parte del
   proyecto donde esperar tiene un costo irreversible.

---

## Arranque: automatizá la recolección hoy

### Opción A — GitHub Actions (recomendada)

Corre solo, todos los días, aunque tu computadora esté apagada. Es gratis.

1. Subí el proyecto a un repositorio de GitHub (puede ser privado).
2. En GitHub: **Settings → Actions → General → Workflow permissions** →
   marcá **"Read and write permissions"**. Sin esto el workflow no puede
   guardar los datos y falla.
3. Andá a la pestaña **Actions**, elegí "Recoleccion diaria SEPA" y apretá
   **"Run workflow"** para probarlo a mano la primera vez.
4. Listo. De ahí en adelante corre solo a las 8 AM.

El workflow (`.github/workflows/recolectar.yml`) hace cuatro cosas cada día:
baja el archivo de SEPA, lo carga en la base, commitea la base actualizada,
y guarda el ZIP crudo como artifact por 30 días (para poder reprocesar si
después mejoramos el mapeo de productos).

Si algún día falla, el workflow queda en rojo y GitHub te manda un mail.
Como la ventana de SEPA es de 7 días, tenés margen para reaccionar — pero
no lo dejes pasar más que eso.

### Opción B — En tu máquina, a mano

Si preferís no usar GitHub por ahora, cada día hábil:

```bash
python3 -m scripts.descargar_sepa --hoy --destino datos_sepa
python3 -m scripts.correr_dia --carpeta datos_sepa
```

Funciona igual, pero depende de que te acuerdes todos los días. Con datos
que no se pueden recuperar, esa dependencia es el punto débil.

---

## Recuperar lo que todavía está en la ventana

Hoy mismo, antes que nada, bajá **los 7 días que siguen disponibles**. Es
la única historia que podés rescatar:

```bash
python3 -m scripts.descargar_sepa --listar          # ver qué hay publicado

python3 -m scripts.descargar_sepa --dia lunes     --destino datos_sepa
python3 -m scripts.descargar_sepa --dia martes    --destino datos_sepa
python3 -m scripts.descargar_sepa --dia miercoles --destino datos_sepa
python3 -m scripts.descargar_sepa --dia jueves    --destino datos_sepa
python3 -m scripts.descargar_sepa --dia viernes   --destino datos_sepa
python3 -m scripts.descargar_sepa --dia sabado    --destino datos_sepa
python3 -m scripts.descargar_sepa --dia domingo   --destino datos_sepa

python3 -m scripts.correr_dia --carpeta datos_sepa
```

Cada archivo se guarda con la fecha real en el nombre
(`sepa_2026-08-14.zip`), que es lo que después usa la carga por lote.

---

## Qué vas a poder ver, y cuándo

| Cuándo | Qué está disponible |
|---|---|
| Hoy mismo | Nivel de precios por categoría y por producto; el detalle de qué productos hay y cómo se mapean. |
| A los ~7 días | Comparación semana contra semana (`consultar rango`). |
| A los ~30 días | Un mes completo cerrado, que sirve de base. |
| A los ~60 días | La primera comparación mes contra mes real, y el primer contraste contra el dato de INDEC. |
| A los ~90 días | Datos suficientes para calibrar la curva de proyección con historia propia en vez de la genérica. |

No hay atajo para esto: es el costo de que SEPA no publique histórico. Pero
el reloj arranca hoy, no el día que el sistema esté "terminado" — y por eso
conviene poner a correr la recolección aunque el análisis siga en desarrollo.

---

## Qué hacer con el ZIP

**Nada, no lo descomprimas.** El sistema lo lee tal cual. Adentro SEPA trae
carpetas por comercio con varios CSV; el lector recorre todo, se queda con
los de precios, e ignora el resto. Detecta solo el delimitador y el encoding.

Antes de la primera carga conviene mirar qué trae:

```bash
python3 -m scripts.correr_dia --inventario datos_sepa/sepa_2026-08-15.zip
```

Muestra los archivos encontrados y **sus columnas**. Si no coinciden con lo
esperado, la carga te lo dice con un mensaje que lista las columnas
disponibles, y se ajustan los nombres en `ALIAS_COLUMNAS` de
`collectors/sepa/schema.py`.

---

## Cómo funciona la acumulación

- La tabla `precios_raw` **nunca se pisa ni se borra**: cada carga suma filas.
- Los cálculos **no miran el archivo que cargaste**, consultan la base
  entera por mes. Por eso podés cargar días en cualquier orden, meter un día
  atrasado, o re-cargar el mismo archivo (no duplica: hay unicidad por
  fecha + producto + comercio).
- Todo vive en `relevamiento_precios.db`. **Ese archivo es el activo del
  proyecto** — es historia irrecuperable. Por eso se versiona en git (no
  está en `.gitignore`) y el workflow lo commitea todos los días: esa es tu
  copia de respaldo con historial.
