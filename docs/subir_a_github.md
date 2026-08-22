# Subir el proyecto a GitHub — paso a paso

Escrito para: cuenta **tobiaszapata**, repositorio **TZ**.

---

## Antes de empezar: dos advertencias que evitan problemas

### 1. El nombre de tu carpeta tiene un espacio

Guardaste el proyecto como **"Relevamiento IPC"**. El espacio no impide nada, pero
obliga a poner comillas cada vez que navegues por terminal:

```
cd "C:\ruta\Relevamiento IPC"
```

Si preferís evitarte eso para siempre, renombrala a `Relevamiento-IPC` (con guion) y
listo. Es opcional.

### 2. NO se sube ni la base de datos ni los ZIP de SEPA

Esto es importante y ya está resuelto en el `.gitignore`, pero conviene que entiendas
por qué:

| Qué | Por qué NO va al repo |
|---|---|
| `relevamiento_precios.db` | Crece ~37 MB por día. Git guarda una copia entera del archivo binario en **cada** commit, y GitHub bloquea archivos de más de 100 MB. A los tres días el repositorio dejaría de aceptar cambios. |
| `datos_sepa/` | Los ZIP diarios pesan cientos de MB cada uno. |
| `aplicacion.html` | Se regenera cuando se quiera. |

**Lo que sí se versiona es `historico/*.csv.gz`**: un archivo comprimido por día, de
unos pocos MB, que una vez escrito no se vuelve a tocar. Ese es el activo irrecuperable
del proyecto (SEPA solo guarda 7 días), y desde esos archivos la base se puede
reconstruir entera con `python -m scripts.reconstruir`.

---

## Parte A — Subir el proyecto (una sola vez)

### A.1 Verificá que Git esté instalado

En la terminal de VS Code:

```
git --version
```

Si dice "no se reconoce", instalá Git desde `git-scm.com` con las opciones por defecto
y reabrí VS Code.

### A.2 Configurá tu identidad (si nunca lo hiciste)

```
git config --global user.name "Tobias Zapata"
git config --global user.email "tu-email@ejemplo.com"
```

Usá el mismo mail de tu cuenta de GitHub.

### A.3 Preparate el repositorio local

Parado en la carpeta del proyecto:

```
git init
git branch -M main
git add .
git status
```

**Detenete en `git status` y leé la lista.** Tiene que aparecer el código (`scripts/`,
`engine/`, `config/`, etc.) y `historico/`. **No** tienen que aparecer
`relevamiento_precios.db` ni `datos_sepa/`. Si aparecen, el `.gitignore` no se está
aplicando — avisame antes de seguir.

### A.4 Primer commit

```
git commit -m "Relevamiento de precios: version inicial"
```

### A.5 Conectar con tu repositorio de GitHub

```
git remote add origin https://github.com/tobiaszapata/TZ.git
git push -u origin main
```

### A.6 La autenticación (acá se traba la mayoría)

GitHub **ya no acepta tu contraseña** desde la terminal. Cuando te pida credenciales:

- **Usuario:** `tobiaszapata`
- **Contraseña:** un *Personal Access Token*, no tu contraseña real.

Para generarlo: GitHub → foto de perfil (arriba a la derecha) → **Settings** →
**Developer settings** (al final del menú izquierdo) → **Personal access tokens** →
**Tokens (classic)** → **Generate new token (classic)**.

- Note: `Relevamiento IPC`
- Expiration: 90 días (o "No expiration" si preferís no renovarlo)
- Permisos: marcá **`repo`** (la casilla del grupo entero) y **`workflow`**

Copiá el token **en ese momento** — GitHub no lo vuelve a mostrar. Pegalo cuando la
terminal te pida la contraseña.

> Alternativa más simple: en VS Code, panel **Source Control** (el ícono de las ramas)
> → "Publish Branch". Te abre el navegador para autorizar con un clic y no tenés que
> manejar tokens a mano.

---

## Parte B — Activar la recolección automática

Con el proyecto ya subido:

### B.1 Dar permiso de escritura al workflow

En tu repo: **Settings** → **Actions** → **General** → bajar hasta **Workflow
permissions** → marcar **"Read and write permissions"** → **Save**.

**Sin este paso el workflow corre pero no puede guardar nada.** Es el error más común.

### B.2 Probarlo a mano antes de confiar en el cron

En tu repo: pestaña **Actions** → en la lista de la izquierda, **"Recoleccion diaria
SEPA"** → botón **"Run workflow"** → **Run workflow**.

Esperá un par de minutos y abrí la corrida para ver los pasos. Fijate especialmente en
**"Descargar el archivo de SEPA de hoy"**: es el paso que no pude probar contra el sitio
real (el entorno donde se desarrolló no tiene internet). Si falla ahí, copiame el
mensaje y lo ajustamos — el resto de la cadena ya está verificada.

### B.3 Qué hace el workflow cada día

1. **Reconstruye** la base desde `historico/` (el runner de GitHub arranca vacío).
2. **Descarga** el archivo de SEPA del día.
3. **Carga** los precios.
4. **Guarda** el ZIP crudo como *artifact* (30 días, para reprocesar si mejorás el mapeo).
5. **Exporta** el día a `historico/YYYY-MM-DD.csv.gz`.
6. **Commitea** ese archivo al repo.

Corre de lunes a viernes a las 8:00 ART. Si falla, GitHub te manda un mail.

### B.4 Traerte lo que juntó el robot

Cuando quieras trabajar en tu máquina con los días que recolectó solo:

```
git pull
python -m scripts.reconstruir
streamlit run app_streamlit.py
```

---

## Parte C — ¿Público o privado?

| | Repo privado | Repo público |
|---|---|---|
| GitHub Actions | Funciona (2.000 min/mes gratis; este workflow usa ~5 min/día, sobra) | Ilimitado |
| Streamlit Community Cloud | **No** (requiere plan pago) | Sí, gratis |
| Tus datos | Solo vos y quien invites | Cualquiera |

**Recomendación:** arrancá **privado**. La automatización funciona igual, que es lo
urgente. Si más adelante querés el link público de Streamlit para tu jefa, ahí evaluás
si los datos pueden ser públicos (son precios de góndola de fuente oficial, así que
probablemente sí, pero es una decisión que conviene consultar antes de hacer).

---

## Uso diario después de todo esto

```
git add -A
git commit -m "lo que cambiaste"
git push
```

Y si el robot subió días nuevos:

```
git pull
python -m scripts.reconstruir
```
