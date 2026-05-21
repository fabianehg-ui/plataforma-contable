"""
core/f350/autorretencion.py — cálculo de la autorretención sobre cuenta 4.

La autorretención especial (Decreto 1625/2016, modificado por Dec. 0261/2023,
0242/2024 — y 0572/2025 que fue suspendido) se calcula sobre los ingresos
brutos del período (clase 4 del PUC) multiplicados por la tarifa CIIU de
la empresa.

Funciones:
    calcular_autorretencion_cuenta_4(balance, tarifa_pct)
        → calcula la base y el valor sobre la cuenta 4 completa
    calcular_autorretencion_por_subcuentas(balance, tarifa_pct, incluir)
        → versión avanzada que permite excluir subcuentas
    aproximar_a_miles(valor)
        → redondea al múltiplo de mil más cercano (regla DIAN Art. 577)

Extraído de BorradorFácil 350 v2.1.5 sin modificaciones de lógica.
"""

from decimal import Decimal, ROUND_HALF_UP


def calcular_autorretencion_cuenta_4(balance_data, tarifa):
    """
    Calcula autorretención sobre TODA la cuenta 4 (ingresos).
    Base = créditos - débitos de la clase 4 en el período.

    Args:
        balance_data: dict devuelto por parsear_balance_contai().
        tarifa: tarifa de autorretención en PORCENTAJE (ej. 1.10 para 1.10%).

    Retorna dict con:
        cuenta_4_creditos, cuenta_4_debitos, ingresos_netos,
        tarifa_aplicada, autorretencion,
        cuenta_41_neto, cuenta_42_neto

    Retorna None si no encontró la cuenta 4 en el balance.
    """
    cuenta_4 = None
    cuenta_41 = None
    cuenta_42 = None

    for c in balance_data['cuentas']:
        if c['codigo'] == '4':
            cuenta_4 = c
        elif c['codigo'] == '41':
            cuenta_41 = c
        elif c['codigo'] == '42':
            cuenta_42 = c

    if not cuenta_4:
        return None

    ingresos_netos = cuenta_4['creditos'] - cuenta_4['debitos']
    autorretencion = round(ingresos_netos * tarifa / 100)

    return {
        'cuenta_4_creditos': cuenta_4['creditos'],
        'cuenta_4_debitos':  cuenta_4['debitos'],
        'ingresos_netos':    ingresos_netos,
        'tarifa_aplicada':   tarifa,
        'autorretencion':    autorretencion,
        'cuenta_41_neto':    (cuenta_41['creditos'] - cuenta_41['debitos']) if cuenta_41 else 0,
        'cuenta_42_neto':    (cuenta_42['creditos'] - cuenta_42['debitos']) if cuenta_42 else 0,
    }


def calcular_autorretencion_por_subcuentas(balance_data, tarifa, subcuentas_excluidas=None):
    """
    Versión avanzada: permite excluir subcuentas específicas del cálculo.

    Útil cuando alguna subcuenta de la 4 (ej. "Ingresos no gravados") no debe
    contribuir a la base de autorretención.

    Args:
        balance_data: dict de parsear_balance_contai().
        tarifa: porcentaje de tarifa (ej. 1.10).
        subcuentas_excluidas: set de códigos de subcuentas a excluir
            (ej. {"42", "42-95-50"}).

    Retorna dict como calcular_autorretencion_cuenta_4() pero con:
        - 'detalle_subcuentas': lista de subcuentas usadas
        - 'subcuentas_excluidas': lista de las que se excluyeron
    """
    if subcuentas_excluidas is None:
        subcuentas_excluidas = set()

    # Encontrar subcuentas hijas directas de la 4 (nivel 2: 41, 42, ...)
    subcuentas_4 = [
        c for c in balance_data['cuentas']
        if c['codigo'].startswith('4') and c['nivel'] == 2
    ]

    detalle = []
    excluidas_info = []
    base_total = 0

    for sc in subcuentas_4:
        neto = sc['creditos'] - sc['debitos']
        if sc['codigo'] in subcuentas_excluidas:
            excluidas_info.append({**sc, 'neto': neto})
            continue
        detalle.append({**sc, 'neto': neto})
        base_total += neto

    autorretencion = round(base_total * tarifa / 100)

    return {
        'base_total':            base_total,
        'tarifa_aplicada':       tarifa,
        'autorretencion':        autorretencion,
        'detalle_subcuentas':    detalle,
        'subcuentas_excluidas':  excluidas_info,
    }


def aproximar_a_miles(valor):
    """
    Aproxima un valor al múltiplo de mil más cercano.

    Regla DIAN (Art. 577 ET):
      - Últimos 3 dígitos ≥ 500 → redondear hacia arriba
      - Últimos 3 dígitos < 500 → redondear hacia abajo

    Usa redondeo tradicional (HALF_UP), no el "bancario" de round().

    Ejemplos:
      $550.000   → $550.000   (ya es múltiplo de mil)
      $61.000    → $61.000
      $450.400   → $450.000   (los últimos 3 dígitos son 400, redondea abajo)
      $450.500   → $451.000   (los últimos 3 dígitos son 500, redondea arriba)
      $7.993.164 → $7.993.000 (164 < 500)
      $726.651.300 → $726.651.000 (300 < 500)
    """
    if valor is None or valor == 0:
        return 0
    try:
        d = Decimal(str(valor)) / Decimal("1000")
        aproximado = d.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return int(aproximado) * 1000
    except (ValueError, TypeError):
        return 0
