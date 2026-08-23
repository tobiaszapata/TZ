"""
Tests del arreglo al bug reportado: "en modo edicion, hay que pasar a otro
item para que el valor puesto cuente para el nivel general".

LA CAUSA REAL (confirmada leyendo el codigo linea por linea, no solo
suponiendo): Streamlit corre TODO el archivo de arriba a abajo en cada
interaccion. `nivel_general_desde_divisiones(...)` se calculaba mas arriba
en el script que el bucle donde el usuario tilda "usar" y escribe el
numero. Guardar el valor en `st.session_state` recien en ese bucle lo
dejaba disponible DESPUES de que el nivel general ya se habia calculado en
ese mismo pase — por eso hacia falta una interaccion MAS (cualquiera) para
que el numero se viera reflejado arriba.

LA CORRECCION: los widgets ahora usan `on_change`, que Streamlit garantiza
ejecutar ANTES de volver a correr el script desde el principio. Este
archivo prueba dos cosas por separado:

  1. La logica PURA de que hacer con el diccionario de overrides
     (`engine.consultas.actualizar_override`) — esto no necesita Streamlit
     y se puede probar de verdad.
  2. Que, SIMULANDO el contrato real de `on_change` de Streamlit (el
     callback corre antes de que el cuerpo del script vuelva a leer el
     estado), el valor queda disponible a tiempo. Esto no reemplaza probar
     la app real en el navegador, pero confirma que el mecanismo elegido
     resuelve el problema de orden que causaba el bug.
"""

from engine.consultas import actualizar_override


def test_tildar_usar_guarda_el_valor():
    overrides = {}
    actualizar_override(overrides, "08", usar=True, valor=4.2)
    assert overrides == {"08": 4.2}


def test_destildar_usar_saca_el_valor():
    overrides = {"08": 4.2}
    actualizar_override(overrides, "08", usar=False, valor=4.2)
    assert overrides == {}


def test_cambiar_el_numero_con_usar_tildado_reemplaza_el_valor():
    overrides = {"08": 4.2}
    actualizar_override(overrides, "08", usar=True, valor=9.9)
    assert overrides == {"08": 9.9}


def test_destildar_algo_que_no_estaba_no_rompe():
    overrides = {}
    actualizar_override(overrides, "08", usar=False, valor=0.0)
    assert overrides == {}


def test_no_toca_otras_claves_del_diccionario():
    overrides = {"01.1.6": 12.0}
    actualizar_override(overrides, "08", usar=True, valor=4.2)
    assert overrides == {"01.1.6": 12.0, "08": 4.2}


def test_simulacion_del_contrato_on_change_de_streamlit():
    """Reproduce el contrato real de Streamlit sin necesitar instalarlo:
    cuando un widget tiene on_change, Streamlit llama al callback ANTES de
    re-ejecutar el cuerpo del script. Esta funcion simula exactamente esa
    secuencia (callback -> despues el cuerpo del script) y confirma que el
    nivel general calculado en el "cuerpo" ya ve el valor cargado en el
    callback — que es justo lo que fallaba con el diseño anterior (donde
    el guardado pasaba DENTRO del cuerpo, despues del calculo)."""
    session_state = {"overrides_division": {}, "chkdiv_08": True, "ovdiv_08": 4.2}

    def callback_on_change():
        # esto es literalmente _aplicar_override_division, sin depender
        # del modulo streamlit para poder importarlo en este entorno
        actualizar_override(
            session_state["overrides_division"], "08",
            session_state["chkdiv_08"], session_state["ovdiv_08"],
        )

    def cuerpo_del_script():
        # simula "ov_division = st.session_state.overrides_division"
        # seguido del calculo del nivel general, mas arriba en el archivo
        # real que este bucle de edicion
        return dict(session_state["overrides_division"])

    # CONTRATO REAL DE STREAMLIT: primero el callback, RECIEN DESPUES el
    # cuerpo del script se re-ejecuta de punta a punta.
    callback_on_change()
    resultado_nivel_general = cuerpo_del_script()

    assert resultado_nivel_general == {"08": 4.2}, (
        "el valor deberia estar disponible para el calculo del nivel "
        "general en el MISMO pase donde se cargo, no en el siguiente"
    )
