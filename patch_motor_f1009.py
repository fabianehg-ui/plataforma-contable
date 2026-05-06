"""
PATCH MOTOR EXÓGENA — Fix F1009: Seguridad Social al 100%
============================================================

Aplicar este patch al motor de exógena (motor_exogena_v_final.py o equivalente)
para corregir el comportamiento del F1009 con cuentas de Seguridad Social.

PROBLEMA ACTUAL:
    El motor está aplicando la regla 75/25 (empleador/trabajador) o reglas de
    "no deducible" a las cuentas de pasivos por SS al construir el F1009.
    Esto genera diferencias artificiales entre saldo balance y valor reportado.

REGLA NORMATIVA:
    Art. 1.3.5.6.1 Res. 000227/2025: el F1009 reporta SALDOS DE PASIVOS al 31-Dic
    por acreedor y concepto. NO tiene columna deducible/no deducible.
    El 100% del saldo se reporta al acreedor (la entidad de SS).

UBICACIÓN DEL FIX:
    Función que clasifica movimientos hacia formatos.
    Buscar la lógica que aplica 'deducibilidad' o 'tratamiento_no_deducible'.

============================================================
"""

# ============================================================
# ANTES (código actual con bug)
# ============================================================

def clasificar_movimiento_OLD(mov, regla):
    """Versión actual con bug: aplica regla 75/25 a todos los formatos"""
    formato = regla['formato']
    deducibilidad = regla.get('deducibilidad', 100)
    
    if deducibilidad < 100:
        # ❌ BUG: aplica esto incluso al F1009 que no tiene esa columna
        valor_deducible = mov['saldo'] * (deducibilidad / 100)
        valor_no_deducible = mov['saldo'] - valor_deducible
        return {
            'formato': formato,
            'concepto': regla['concepto'],
            'valor_deducible': valor_deducible,
            'valor_no_deducible': valor_no_deducible,
            'tratamiento': 'NO_DEDUCIBLE_PARCIAL'
        }
    else:
        return {
            'formato': formato,
            'concepto': regla['concepto'],
            'valor_deducible': mov['saldo'],
            'valor_no_deducible': 0,
            'tratamiento': 'OK'
        }


# ============================================================
# DESPUÉS (código corregido)
# ============================================================

# Formatos que tienen columna deducible/no deducible (separan tratamiento fiscal)
FORMATOS_CON_DEDUCIBILIDAD = {'1001'}  # Solo F1001 tiene esta dimensión

# Formatos de saldo: reportan el 100% sin separar
FORMATOS_DE_SALDO = {'1008', '1009', '1011', '1012'}


def clasificar_movimiento_FIXED(mov, regla):
    """
    Versión corregida: la regla de deducibilidad SOLO aplica al F1001.
    Los formatos de saldo (F1008, F1009, F1011, F1012) reportan el 100%.
    """
    formato = regla['formato']
    deducibilidad = regla.get('deducibilidad', 100)
    
    # ✅ FIX: si el formato es de saldo, ignorar la regla de deducibilidad
    if formato in FORMATOS_DE_SALDO:
        return {
            'formato': formato,
            'concepto': regla['concepto'],
            'valor_reportado': mov['saldo'],   # 100% siempre
            'tratamiento': 'SALDO_COMPLETO',
            'nota': f'F{formato}: reporta saldo completo al acreedor (no tiene columna deducible)'
        }
    
    # ✅ FIX: solo F1001 separa deducible/no deducible
    if formato in FORMATOS_CON_DEDUCIBILIDAD and deducibilidad < 100:
        valor_deducible = mov['saldo'] * (deducibilidad / 100)
        valor_no_deducible = mov['saldo'] - valor_deducible
        return {
            'formato': formato,
            'concepto': regla['concepto'],
            'valor_deducible': valor_deducible,
            'valor_no_deducible': valor_no_deducible,
            'tratamiento': 'NO_DEDUCIBLE_PARCIAL'
        }
    
    # Default: 100% deducible
    return {
        'formato': formato,
        'concepto': regla['concepto'],
        'valor_deducible': mov['saldo'],
        'valor_no_deducible': 0,
        'tratamiento': 'OK'
    }


# ============================================================
# CAMBIOS A APLICAR EN EL CÓDIGO REAL
# ============================================================

CAMBIOS = """
1. EN motor_exogena_v_final.py (o equivalente):

   Buscar la función que aplica la regla de deducibilidad — probablemente
   se llama 'aplicar_regla_deducibilidad', 'clasificar_movimiento', o similar.
   
   Al inicio de esa función agregar:
   
       FORMATOS_DE_SALDO = {'1008', '1009', '1011', '1012'}
       if regla['formato'] in FORMATOS_DE_SALDO:
           # Reportar 100% del saldo, ignorar deducibilidad
           return mov['saldo'], 0, 'SALDO_COMPLETO'

2. EN excel_borrador_formatos.py (generador del Excel):

   En la sección de conciliación del F1009, asegurar que la columna
   'Diferencia' siempre muestre 0 (excepto si hay errores reales de mapeo).
   
   Si hoy muestra diferencias por 'NO_DEDUCIBLE', cambiar el motivo a:
       'OK' o 'F1009: 100% del saldo (Res 000227/2025)'

3. EN constructor_xml_f1009.py (builder XML):

   Asegurar que el campo <vrPasivo> use el saldo total y NO el 'valor_deducible'.
"""

print(CAMBIOS)


# ============================================================
# TESTS DE VALIDACIÓN
# ============================================================

def test_f1009_seguridad_social_100():
    """F1009: cuenta SS debe reportar 100% del saldo"""
    mov = {'cuenta': '25502002', 'saldo': 33133300, 'nit': '900336004'}  # Porvenir
    regla = {'formato': '1009', 'concepto': '2214', 'deducibilidad': 100}
    
    resultado = clasificar_movimiento_FIXED(mov, regla)
    
    assert resultado['valor_reportado'] == 33133300, \
        f"F1009 debe reportar 100%: {resultado}"
    assert resultado['tratamiento'] == 'SALDO_COMPLETO'
    print("✅ test_f1009_seguridad_social_100 OK")


def test_f1001_pension_75_25_sin_pila():
    """F1001: pensión sin PILA aplica 75/25 (legítimo)"""
    mov = {'cuenta': '25502002', 'saldo': 33133300, 'nit': '900336004'}
    regla = {'formato': '1001', 'concepto': '5012', 'deducibilidad': 75}
    
    resultado = clasificar_movimiento_FIXED(mov, regla)
    
    assert resultado['valor_deducible'] == 33133300 * 0.75
    assert resultado['valor_no_deducible'] == 33133300 * 0.25
    print("✅ test_f1001_pension_75_25_sin_pila OK")


def test_f1009_no_aplica_75_25_aunque_regla_lo_diga():
    """F1009: ignora deducibilidad < 100 (no tiene esa dimensión)"""
    mov = {'cuenta': '25502002', 'saldo': 33133300, 'nit': '900336004'}
    # Regla mal configurada con 75% (caso del bug)
    regla = {'formato': '1009', 'concepto': '2214', 'deducibilidad': 75}
    
    resultado = clasificar_movimiento_FIXED(mov, regla)
    
    # Aunque la regla diga 75%, F1009 debe reportar 100%
    assert resultado['valor_reportado'] == 33133300, \
        f"F1009 debe ignorar deducibilidad < 100: {resultado}"
    print("✅ test_f1009_no_aplica_75_25_aunque_regla_lo_diga OK")


def test_f1008_saldo_completo():
    """F1008 también es de saldo: 100%"""
    mov = {'cuenta': '13050501', 'saldo': 5000000, 'nit': '900111111'}
    regla = {'formato': '1008', 'concepto': '1315', 'deducibilidad': 50}  # mal configurada
    
    resultado = clasificar_movimiento_FIXED(mov, regla)
    
    assert resultado['valor_reportado'] == 5000000
    print("✅ test_f1008_saldo_completo OK")


if __name__ == '__main__':
    print("Ejecutando tests del fix F1009...")
    test_f1009_seguridad_social_100()
    test_f1001_pension_75_25_sin_pila()
    test_f1009_no_aplica_75_25_aunque_regla_lo_diga()
    test_f1008_saldo_completo()
    print("\n🎉 Todos los tests pasaron")
