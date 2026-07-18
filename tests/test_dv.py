from core.contable.dv import digito_verificacion, nit_con_dv, dv_valido

CASOS = {"800180687":2,"811001713":1,"890900608":9,"890903938":8,"890903939":5,
         "900480569":1,"800197268":4,"901630218":1,"860002964":4}

def test_dv_contra_nits_reales():
    for nit, esp in CASOS.items():
        assert digito_verificacion(nit) == esp, nit

def test_ignora_puntos_y_espacios():
    assert digito_verificacion("800.197.268") == 4
    assert digito_verificacion(" 800197268 ") == 4

def test_nit_con_dv():
    assert nit_con_dv("800197268") == "800197268-4"

def test_dv_valido():
    assert dv_valido("800197268", "4") is True
    assert dv_valido("800197268", 9) is False
