"""
Test del helper que detecta formatos con valor total = 0.

Garantiza que un XML cuyos campos monetarios suman 0 NO se genera,
para no quemar consecutivo ni enviar archivos vacíos al DIAN.
"""
import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'core/exogena')

from adaptador_motor_v2 import (
    valor_monetario_total_formato, formato_tiene_valor,
)
from generador_xml_v2 import (
    Tercero, TIPO_DOC_NIT,
    RegistroF1001, RegistroF1003, RegistroF1005, RegistroF1006,
    RegistroF1007, RegistroF1008, RegistroF1009, RegistroF1011,
    RegistroF1012, RegistroF1647, RegistroF2276,
)


def t(nit='800123456'):
    return Tercero(nit=nit, tipo_documento=TIPO_DOC_NIT, digito_verificacion='1',
                   razon_social='ACME SAS',
                   codigo_departamento='05', codigo_municipio='001')


# ============================================================
# Caso 1: lista vacía → 0
# ============================================================

def test_lista_vacia_retorna_cero():
    assert valor_monetario_total_formato('1001', []) == 0
    assert formato_tiene_valor('1001', []) is False


# ============================================================
# Caso 2: F1001 con todos los campos monetarios en 0 → 0
# ============================================================

def test_f1001_todos_ceros_no_tiene_valor():
    regs = [
        RegistroF1001(tercero=t(), concepto=5001,
                      pago_deducible=0, retencion_renta_practicada=0),
        RegistroF1001(tercero=t('800999999'), concepto=5002,
                      pago_deducible=0, retencion_renta_practicada=0),
    ]
    total = valor_monetario_total_formato('1001', regs)
    assert total == 0, f"Esperado 0, obtenido {total}"
    assert formato_tiene_valor('1001', regs) is False


# ============================================================
# Caso 3: F1001 con un peso → SÍ tiene valor
# ============================================================

def test_f1001_con_valor_si_tiene_valor():
    regs = [
        RegistroF1001(tercero=t(), concepto=5001,
                      pago_deducible=100, retencion_renta_practicada=0),
    ]
    total = valor_monetario_total_formato('1001', regs)
    assert total == 100
    assert formato_tiene_valor('1001', regs) is True


# ============================================================
# Caso 4: F1001 con valores que se compensan (positivos y negativos)
# El helper toma valor absoluto, así que SÍ debe haber valor
# ============================================================

def test_f1001_valores_que_suman_cero_pero_son_distintos_de_cero():
    """Si hay valores reales aunque la suma sea 0 (raro), DEBE generarse."""
    regs = [
        RegistroF1001(tercero=t(), concepto=5001,
                      pago_deducible=1_000_000,
                      retencion_renta_practicada=-1_000_000),
    ]
    total = valor_monetario_total_formato('1001', regs)
    assert total == 2_000_000, f"Esperado 2M (valor absoluto), obtenido {total}"
    assert formato_tiene_valor('1001', regs) is True


# ============================================================
# Caso 5: F1009 con saldo 0 → no se genera
# ============================================================

def test_f1009_saldo_cero_no_tiene_valor():
    regs = [
        RegistroF1009(tercero=t(), concepto=2214, saldo=0),
    ]
    assert formato_tiene_valor('1009', regs) is False


def test_f1009_con_saldo_si_tiene_valor():
    regs = [
        RegistroF1009(tercero=t(), concepto=2214, saldo=5_000_000),
    ]
    assert formato_tiene_valor('1009', regs) is True


# ============================================================
# Caso 6: F2276 con todos los pagos en 0 (raro pero posible)
# ============================================================

def test_f2276_todo_cero_no_tiene_valor():
    regs = [
        RegistroF2276(entidad_informante=11, tipo_doc_beneficiario='13', nit_beneficiario='123456',
                      pagos_salarios=0, retencion_fuente=0),
    ]
    assert formato_tiene_valor('2276', regs) is False


def test_f2276_con_pagos_si_tiene_valor():
    regs = [
        RegistroF2276(entidad_informante=11, tipo_doc_beneficiario='13', nit_beneficiario='123456',
                      pagos_salarios=15_000_000, retencion_fuente=2_000_000),
    ]
    total = valor_monetario_total_formato('2276', regs)
    assert total == 17_000_000


# ============================================================
# Caso 7: F1003, F1005, F1006, F1007, F1008, F1011, F1012, F1647
# Cada uno con valor 0 → no tiene valor
# ============================================================

def test_todos_formatos_con_ceros_no_tienen_valor():
    casos = [
        ('1003', [RegistroF1003(tercero=t(), concepto=1336, valor_base=0, retencion=0)]),
        ('1005', [RegistroF1005(tercero=t(), iva_descontable=0)]),
        ('1006', [RegistroF1006(tercero=t(), iva_generado=0)]),
        ('1007', [RegistroF1007(tercero=t(), concepto=4001, ingresos_brutos=0)]),
        ('1008', [RegistroF1008(tercero=t(), concepto=1315, saldo=0)]),
        ('1011', [RegistroF1011(concepto=1101, saldo=0)]),
        ('1012', [RegistroF1012(tercero=t(), concepto=1110, valor=0)]),
    ]
    for fmt, regs in casos:
        assert not formato_tiene_valor(fmt, regs), f"F{fmt} no debería tener valor"


# ============================================================
# Caso 8: tolerancia (centavos)
# ============================================================

def test_tolerancia_centavos():
    """Un valor de 0.005 (medio centavo) NO debe contar como valor."""
    regs = [
        RegistroF1009(tercero=t(), concepto=2214, saldo=0.005),
    ]
    assert formato_tiene_valor('1009', regs, tolerancia=0.01) is False


def test_tolerancia_un_peso():
    """$1 sí debe contar como valor."""
    regs = [
        RegistroF1009(tercero=t(), concepto=2214, saldo=1.00),
    ]
    assert formato_tiene_valor('1009', regs, tolerancia=0.01) is True


# ============================================================
# Caso 9: formato desconocido (defensivo)
# ============================================================

def test_formato_desconocido_default_infinito():
    """Para formatos no mapeados retornar infinito mantiene comportamiento previo."""
    val = valor_monetario_total_formato('XXXX', [object()])
    assert val == float('inf')
    assert formato_tiene_valor('XXXX', [object()]) is True


# ============================================================
# Runner
# ============================================================

if __name__ == '__main__':
    tests = [
        test_lista_vacia_retorna_cero,
        test_f1001_todos_ceros_no_tiene_valor,
        test_f1001_con_valor_si_tiene_valor,
        test_f1001_valores_que_suman_cero_pero_son_distintos_de_cero,
        test_f1009_saldo_cero_no_tiene_valor,
        test_f1009_con_saldo_si_tiene_valor,
        test_f2276_todo_cero_no_tiene_valor,
        test_f2276_con_pagos_si_tiene_valor,
        test_todos_formatos_con_ceros_no_tienen_valor,
        test_tolerancia_centavos,
        test_tolerancia_un_peso,
        test_formato_desconocido_default_infinito,
    ]
    pasaron = fallaron = 0
    for t_fn in tests:
        try:
            t_fn()
            pasaron += 1
            print(f"✓ {t_fn.__name__}")
        except AssertionError as e:
            fallaron += 1
            print(f"✗ {t_fn.__name__}: {e}")
        except Exception as e:
            fallaron += 1
            print(f"✗ {t_fn.__name__}: {type(e).__name__}: {e}")

    print(f"\n{'='*60}\n  {pasaron}/{len(tests)} tests pasaron\n{'='*60}")
    sys.exit(0 if fallaron == 0 else 1)
