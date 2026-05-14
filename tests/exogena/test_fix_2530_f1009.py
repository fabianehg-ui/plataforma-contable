"""
Test del fix F1009: cuentas 2530xx (provisiones por pagar al empleado) NO
deben reportarse en F1009 aunque tengan saldo final positivo. Solo van a
F2276 con sus débitos.

Las cuentas 2510, 2515, 2525 (pasivos consolidados a terceros institucionales)
SÍ mantienen el doble reporte F2276 + F1009.
"""
import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'core/exogena')

from motor_clasificacion import (
    MotorClasificacion, Movimiento,
)


# ============================================================
# Helpers
# ============================================================

def motor_vacio():
    """Motor sin reglas en BD: el guard de doble reporte es el único que aplica."""
    return MotorClasificacion(reglas_capa1=[], reglas_capa2=[], reglas_capa3=[])


def clasificar(mov):
    """Atajo para clasificar un movimiento y devolver la lista."""
    return motor_vacio().clasificar_movimiento(mov)


# ============================================================
# Caso A: cuenta 253005 (cesantías por pagar al empleado)
# ============================================================

def test_253005_con_debitos_y_saldo_positivo_solo_va_a_f2276():
    """
    253005xx con débitos del año + saldo final positivo:
    DEBE generar SOLO F2276 (no F1009).
    """
    mov = Movimiento(
        codigo_cuenta='25300501',
        nit='123456',
        debitos=10_000_000,    # pagos al empleado durante el año
        creditos=12_000_000,   # provisiones durante el año
        saldo_final=2_000_000, # saldo por pagar al cierre
        nombre_cuenta='CESANTÍAS POR PAGAR',
    )
    resultados = clasificar(mov)

    formatos = [r.formato_dian for r in resultados]
    print(f"  Resultados 253005xx: {formatos}")
    assert '2276' in formatos, f"Falta F2276 en {formatos}"
    assert '1009' not in formatos, f"NO debería haber F1009 en {formatos}"

    f2276 = [r for r in resultados if r.formato_dian == '2276'][0]
    assert f2276.valor == 10_000_000, f"F2276 debe usar débitos (10M), no {f2276.valor}"
    assert f2276.concepto_dian == 25, f"Concepto debe ser 25 (cein), no {f2276.concepto_dian}"


def test_253005_solo_saldo_positivo_sin_debitos_no_reporta_nada_en_f1009_ni_f2276():
    """
    253005xx con saldo final positivo pero SIN débitos:
    NO debe reportar nada en F1009. F2276 tampoco porque no hay débitos.
    Solo queda la bandera de doble_reporte_disparado para evitar sin_resolver.
    """
    mov = Movimiento(
        codigo_cuenta='25300501',
        nit='123456',
        debitos=0,
        creditos=5_000_000,
        saldo_final=5_000_000,  # saldo positivo
        nombre_cuenta='CESANTÍAS POR PAGAR',
    )
    resultados = clasificar(mov)

    formatos = [r.formato_dian for r in resultados]
    print(f"  Resultados 253005xx solo saldo: {formatos}")
    assert '1009' not in formatos, f"NO debería haber F1009 en {formatos}"
    # F2276 tampoco porque débitos = 0
    assert '2276' not in formatos, f"NO debería haber F2276 sin débitos en {formatos}"


# ============================================================
# Caso B: cuenta 253020 (prima de servicios por pagar al empleado, QS)
# ============================================================

def test_253020_con_debitos_y_saldo_positivo_solo_va_a_f2276():
    """253020xx con débitos + saldo positivo → solo F2276."""
    mov = Movimiento(
        codigo_cuenta='25302001',
        nit='123456',
        debitos=8_000_000,
        creditos=10_000_000,
        saldo_final=2_000_000,
        nombre_cuenta='PRIMA SERVICIOS POR PAGAR',
    )
    resultados = clasificar(mov)

    formatos = [r.formato_dian for r in resultados]
    print(f"  Resultados 253020xx: {formatos}")
    assert '2276' in formatos
    assert '1009' not in formatos


# ============================================================
# Caso C: cuenta 2510xx (cesantías al fondo) — SÍ va a F1009
# ============================================================

def test_2510_con_debitos_y_saldo_positivo_va_a_f2276_Y_f1009():
    """
    2510xx (cesantías consolidadas al fondo) mantiene doble reporte:
    - F2276 con débitos del año
    - F1009 con saldo final positivo (lo que falta consignar al fondo)
    """
    mov = Movimiento(
        codigo_cuenta='251005',
        nit='890903938',  # NIT fondo de cesantías
        debitos=15_000_000,
        creditos=18_000_000,
        saldo_final=3_000_000,
        nombre_cuenta='CESANTÍAS CONSOLIDADAS',
    )
    resultados = clasificar(mov)

    formatos = sorted([r.formato_dian for r in resultados])
    print(f"  Resultados 2510xx: {formatos}")
    assert '2276' in formatos, f"Falta F2276 en {formatos}"
    assert '1009' in formatos, f"Falta F1009 en {formatos}"

    f1009 = [r for r in resultados if r.formato_dian == '1009'][0]
    assert f1009.valor == 3_000_000, f"F1009 debe usar saldo final (3M), no {f1009.valor}"
    assert f1009.concepto_dian == 2214


# ============================================================
# Caso D: cuenta 2515 (intereses cesantías consolidadas) — SÍ va a F1009
# ============================================================

def test_2515_con_saldo_positivo_va_a_f1009():
    """2515xx con saldo final positivo → F1009 (doble reporte completo)."""
    mov = Movimiento(
        codigo_cuenta='251505',
        nit='890903938',
        debitos=1_000_000,
        creditos=1_500_000,
        saldo_final=500_000,
        nombre_cuenta='INTERESES CESANTÍAS',
    )
    resultados = clasificar(mov)

    formatos = sorted([r.formato_dian for r in resultados])
    print(f"  Resultados 2515xx: {formatos}")
    assert '1009' in formatos
    assert '2276' in formatos


# ============================================================
# Caso E: cuenta 2525 (vacaciones consolidadas) — SÍ va a F1009
# ============================================================

def test_2525_con_saldo_positivo_va_a_f1009():
    """2525xx con saldo final positivo → F1009 (doble reporte completo)."""
    mov = Movimiento(
        codigo_cuenta='252505',
        nit='123456',
        debitos=2_000_000,
        creditos=3_000_000,
        saldo_final=1_000_000,
        nombre_cuenta='VACACIONES CONSOLIDADAS',
    )
    resultados = clasificar(mov)

    formatos = sorted([r.formato_dian for r in resultados])
    print(f"  Resultados 2525xx: {formatos}")
    assert '1009' in formatos
    assert '2276' in formatos


# ============================================================
# Caso F: saldo final NEGATIVO de 2510 no va a F1009
# ============================================================

def test_2510_con_saldo_negativo_no_va_a_f1009():
    """Saldo negativo es crédito residual del corte, no cuenta por pagar real."""
    mov = Movimiento(
        codigo_cuenta='251005',
        nit='890903938',
        debitos=20_000_000,
        creditos=18_000_000,
        saldo_final=-2_000_000,  # negativo
        nombre_cuenta='CESANTÍAS CONSOLIDADAS',
    )
    resultados = clasificar(mov)

    formatos = [r.formato_dian for r in resultados]
    print(f"  Resultados 2510xx saldo neg: {formatos}")
    assert '1009' not in formatos, f"NO debería haber F1009 con saldo negativo: {formatos}"
    assert '2276' in formatos, "Sí debe haber F2276 (hay débitos)"


# ============================================================
# Caso G: cuenta 2505 (salarios por pagar) — SOLO F1009 con saldo +
# ============================================================

def test_2505_con_saldo_positivo_solo_va_a_f1009():
    """
    2505xx con saldo final positivo: solo F1009, NUNCA F2276.
    Los pagos de salarios ya se reportan vía las cuentas de gasto 5xxx.
    """
    mov = Movimiento(
        codigo_cuenta='250505',
        nit='123456',
        debitos=50_000_000,    # salarios pagados
        creditos=52_000_000,   # salarios causados
        saldo_final=2_000_000, # salario por pagar al cierre
        nombre_cuenta='SALARIOS POR PAGAR',
    )
    resultados = clasificar(mov)

    formatos = [r.formato_dian for r in resultados]
    print(f"  Resultados 2505xx saldo +: {formatos}")
    assert '1009' in formatos, f"Falta F1009 en {formatos}"
    assert '2276' not in formatos, f"NO debería haber F2276 (los pagos van por 5xxx): {formatos}"

    f1009 = [r for r in resultados if r.formato_dian == '1009'][0]
    assert f1009.valor == 2_000_000
    assert f1009.concepto_dian == 2214


def test_2505_con_saldo_negativo_no_reporta_nada():
    """2505xx con saldo negativo: nada en F1009, nada en F2276."""
    mov = Movimiento(
        codigo_cuenta='250505',
        nit='123456',
        debitos=50_000_000,
        creditos=48_000_000,
        saldo_final=-2_000_000,
        nombre_cuenta='SALARIOS POR PAGAR',
    )
    resultados = clasificar(mov)

    formatos = [r.formato_dian for r in resultados]
    print(f"  Resultados 2505xx saldo neg: {formatos}")
    assert '1009' not in formatos
    assert '2276' not in formatos


def test_2505_sin_saldo_no_reporta():
    """2505xx con saldo 0: no genera nada en F1009."""
    mov = Movimiento(
        codigo_cuenta='250505',
        nit='123456',
        debitos=50_000_000,
        creditos=50_000_000,
        saldo_final=0,
        nombre_cuenta='SALARIOS POR PAGAR',
    )
    resultados = clasificar(mov)

    formatos = [r.formato_dian for r in resultados]
    print(f"  Resultados 2505xx saldo 0: {formatos}")
    assert '1009' not in formatos
    assert '2276' not in formatos


# ============================================================
# Runner
# ============================================================

if __name__ == '__main__':
    tests = [
        test_253005_con_debitos_y_saldo_positivo_solo_va_a_f2276,
        test_253005_solo_saldo_positivo_sin_debitos_no_reporta_nada_en_f1009_ni_f2276,
        test_253020_con_debitos_y_saldo_positivo_solo_va_a_f2276,
        test_2510_con_debitos_y_saldo_positivo_va_a_f2276_Y_f1009,
        test_2515_con_saldo_positivo_va_a_f1009,
        test_2525_con_saldo_positivo_va_a_f1009,
        test_2510_con_saldo_negativo_no_va_a_f1009,
        test_2505_con_saldo_positivo_solo_va_a_f1009,
        test_2505_con_saldo_negativo_no_reporta_nada,
        test_2505_sin_saldo_no_reporta,
    ]
    pasaron = 0
    fallaron = 0
    for t in tests:
        print(f"\n▶ {t.__name__}")
        try:
            t()
            pasaron += 1
            print(f"  ✓ PASS")
        except AssertionError as e:
            fallaron += 1
            print(f"  ✗ FAIL: {e}")
        except Exception as e:
            fallaron += 1
            print(f"  ✗ ERROR: {type(e).__name__}: {e}")

    print(f"\n{'='*60}")
    print(f"  {pasaron}/{len(tests)} tests pasaron")
    print(f"{'='*60}")
    sys.exit(0 if fallaron == 0 else 1)
