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


def test_base_con_mas_dias_que_historico_no_reconstruye():
    """No debería pasar en la práctica (la base siempre viene de
    historico/), pero si pasara, no hay que hacer nada raro: no hace
    falta reconstruir solo porque la base tenga MAS que el respaldo."""
    assert hace_falta_reconstruir(db_existe=True, dias_en_base=12, dias_en_historico=9) is False
