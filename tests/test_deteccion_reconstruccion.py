"""
Tests de engine.consultas.hace_falta_reconstruir — corrige el bug real
reportado: se subían días nuevos a historico/ con git push, pero la app
publicada seguía mostrando los datos viejos hasta que Streamlit Cloud
reiniciaba el proceso por su cuenta, sin ningún patrón visible desde
afuera de "cuándo sí, cuándo no".
"""

from engine.consultas import hace_falta_reconstruir


def test_sin_base_y_con_historico_hay_que_reconstruir():
    assert hace_falta_reconstruir(db_existe=False, dias_en_base=0, dias_en_historico=5) is True


def test_sin_base_y_sin_historico_no_hay_nada_que_hacer():
    assert hace_falta_reconstruir(db_existe=False, dias_en_base=0, dias_en_historico=0) is False


def test_base_con_menos_dias_que_historico_hay_que_reconstruir():
    """El caso real reportado: se subieron días nuevos (historico/ los
    tiene) pero el proceso de Streamlit ya venía corriendo con una base
    vieja que no los incluye."""
    assert hace_falta_reconstruir(db_existe=True, dias_en_base=9, dias_en_historico=12) is True


def test_base_al_dia_con_historico_no_hace_falta_reconstruir():
    """Caso normal, la mayoría de las veces: no hay que reconstruir en
    cada interacción, solo cuando de verdad hay algo nuevo."""
    assert hace_falta_reconstruir(db_existe=True, dias_en_base=12, dias_en_historico=12) is False


def test_base_con_mas_dias_que_historico_si_reconstruye():
    """CORREGIDO: este es exactamente el caso real que le pasó al usuario
    — reinició todo y volvió a cargar con MENOS días (sacó los días no
    hábiles: de 28 a 19). La base en memoria de Streamlit Cloud (que
    sigue con el proceso viejo corriendo) tenía MAS días que el
    historico/ actualizado, y con la logica vieja ("reconstruir solo si
    hay MAS en historico") nunca se disparaba la reconstruccion —
    Streamlit seguia mostrando los 28 días viejos. La logica correcta:
    cualquier DIFERENCIA (para mas o para menos) tiene que disparar la
    reconstruccion, porque el historico/ es la fuente de verdad real."""
    assert hace_falta_reconstruir(db_existe=True, dias_en_base=12, dias_en_historico=9) is True


def test_caso_real_reiniciar_con_menos_dias_dispara_reconstruccion():
    """Caso real reportado: el usuario reinicio la base+historico, cargo
    solo dias habiles (19 dias, en vez de los 28 que tenia antes con
    fines de semana incluidos), subio el historico/ actualizado a
    GitHub, pero Streamlit Cloud seguia mostrando 28 dias — porque el
    proceso de Python en el servidor segui corriendo con la base vieja
    en memoria, y la logica anterior no detectaba una REDUCCION de
    dias como un cambio que ameritara reconstruir."""
    assert hace_falta_reconstruir(db_existe=True, dias_en_base=28, dias_en_historico=19) is True
