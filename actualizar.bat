@echo off
REM ===================================================================
REM  ACTUALIZACION DIARIA DEL RELEVAMIENTO DE PRECIOS
REM
REM  Este archivo hace todo el ciclo del dia: descarga el archivo de
REM  SEPA, lo carga en la base y deja todo listo para analizar.
REM
REM  Se puede usar de dos formas:
REM    1) Doble clic, cuando quieras actualizar a mano.
REM    2) Programado con el Programador de tareas de Windows, para que
REM       corra solo todos los dias (ver la guia de GitHub, seccion 8bis).
REM
REM  POR QUE UN .BAT Y NO PONER EL COMANDO DIRECTO EN LA TAREA:
REM  El Programador de tareas es muy quisquilloso con las rutas y con la
REM  carpeta de trabajo. Este archivo se ubica solo (usa %~dp0, que es
REM  "la carpeta donde esta este .bat"), asi que la tarea solo tiene que
REM  apuntar aca y no hay forma de equivocarse con las rutas.
REM ===================================================================

REM Pararse en la carpeta donde esta este archivo
cd /d "%~dp0"

REM Carpeta de registros
if not exist "logs" mkdir "logs"

REM Nombre del log con la fecha de hoy (formato AAAA-MM-DD)
for /f "tokens=1-3 delims=/-. " %%a in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set HOY=%%a

echo ===================================================== >> "logs\actualizar.log"
echo Corrida del %DATE% %TIME% >> "logs\actualizar.log"
echo ===================================================== >> "logs\actualizar.log"

REM Correr el proceso. Todo lo que imprime queda guardado en el log.
python -m scripts.actualizar >> "logs\actualizar.log" 2>&1

if %ERRORLEVEL% NEQ 0 (
    echo. >> "logs\actualizar.log"
    echo *** LA CORRIDA TERMINO CON ERROR ^(codigo %ERRORLEVEL%^) *** >> "logs\actualizar.log"
    echo Revisar el detalle mas arriba en este mismo archivo. >> "logs\actualizar.log"
)

echo. >> "logs\actualizar.log"

REM Si se ejecuto con doble clic, dejar la ventana abierta para ver que paso.
REM Cuando lo corre el Programador de tareas esto no molesta.
if "%1"=="" (
    echo.
    echo ==========================================
    echo   Termino. El detalle quedo en:
    echo   logs\actualizar.log
    echo ==========================================
    echo.
    type "logs\actualizar.log" | more +1
    pause
)
