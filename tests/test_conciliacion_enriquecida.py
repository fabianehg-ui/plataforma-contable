"""
Smoke test del backend de conciliación enriquecida.
Valida que la lógica de agrupación y cálculo de diferencias funciona.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from decimal import Decimal
from core.exogena import conciliacion_enriquecida as ce


# ============================================================================
# Mock simplificado
# ============================================================================

class MockResp:
    def __init__(self, data):
        self.data = data


class MockTable:
    def __init__(self, data):
        self._data = data
        self._filters = []

    def select(self, _):
        return self

    def eq(self, k, v):
        self._filters.append((k, v))
        return self

    def execute(self):
        rows = self._data
        for k, v in self._filters:
            rows = [r for r in rows if r.get(k) == v]
        return MockResp(rows)


class MockSb:
    def __init__(self, movs):
        self.movs = movs

    def table(self, _):
        return MockTable(self.movs)


# ============================================================================
# Datos de prueba — simulan movimientos de Quinto Sentido
# ============================================================================

def setup_movimientos():
    """Simula el balance auxiliar después de la migración 010."""
    return [
        # F1001 / Concepto 5002 (Honorarios) — 2 cuentas que aportan
        {
            'empresa_id': 'qs', 'año_gravable': 2025,
            'codigo_cuenta': '510515', 'nombre_cuenta': 'HONORARIOS GTOS ADMON',
            'nit': '900111', 'saldo_final': 50_000_000,
            'formato_dian': '1001', 'concepto_dian': 5002,
            'descripcion_concepto': 'Honorarios',
            'capa_resolucion': 1, 'excluido': False, 'nota': None,
        },
        {
            'empresa_id': 'qs', 'año_gravable': 2025,
            'codigo_cuenta': '510515', 'nombre_cuenta': 'HONORARIOS GTOS ADMON',
            'nit': '900222', 'saldo_final': 30_000_000,
            'formato_dian': '1001', 'concepto_dian': 5002,
            'descripcion_concepto': 'Honorarios',
            'capa_resolucion': 1, 'excluido': False, 'nota': None,
        },
        {
            'empresa_id': 'qs', 'año_gravable': 2025,
            'codigo_cuenta': '236515', 'nombre_cuenta': 'RETENCION HONORARIOS',
            'nit': '900111', 'saldo_final': 5_500_000,
            'formato_dian': '1001', 'concepto_dian': 5002,
            'descripcion_concepto': 'Honorarios',
            'capa_resolucion': 1, 'excluido': False, 'nota': None,
        },

        # F1009 / Concepto 2206 — cuenta excluida
        {
            'empresa_id': 'qs', 'año_gravable': 2025,
            'codigo_cuenta': '236515', 'nombre_cuenta': 'RETENCION HONORARIOS',
            'nit': '900111', 'saldo_final': 5_500_000,
            'formato_dian': '1009', 'concepto_dian': 2206,
            'descripcion_concepto': 'Cuentas por pagar',
            'capa_resolucion': 1, 'excluido': True,
            'nota': 'Retención en la fuente practicada — transitoria',
        },

        # F1009 / Concepto 2206 — cuenta legítima (proveedor)
        {
            'empresa_id': 'qs', 'año_gravable': 2025,
            'codigo_cuenta': '2335', 'nombre_cuenta': 'COSTOS Y GTOS POR PAGAR',
            'nit': '901500', 'saldo_final': 12_000_000,
            'formato_dian': '1009', 'concepto_dian': 2206,
            'descripcion_concepto': 'Cuentas por pagar',
            'capa_resolucion': 1, 'excluido': False, 'nota': None,
        },
    ]


# ============================================================================
# Tests
# ============================================================================

def test_agrupacion_por_formato_concepto():
    sb = MockSb(setup_movimientos())
    dictamen = ce.construir_conciliacion_enriquecida(sb, 'qs', 2025)

    # Debe haber 2 bloques: F1001/5002 y F1009/2206
    assert len(dictamen.bloques) == 2, f"Esperaba 2 bloques, hay {len(dictamen.bloques)}"

    # F1001/5002 debe tener 2 cuentas únicas (510515 y 236515)
    b_1001 = next(b for b in dictamen.bloques if b.formato_dian == '1001')
    assert len(b_1001.cuentas) == 2
    print('✅ test_agrupacion_por_formato_concepto')


def test_calculo_totales_balance_y_reportado():
    sb = MockSb(setup_movimientos())
    dictamen = ce.construir_conciliacion_enriquecida(sb, 'qs', 2025)

    # F1001/5002:
    #   - 510515 con 2 NITs: 50M + 30M = 80M (todo reportado)
    #   - 236515 con 1 NIT: 5.5M (todo reportado, no excluido en este formato)
    #   Total balance: 85.5M, total reportado: 85.5M, diferencia: 0
    b_1001 = next(b for b in dictamen.bloques if b.formato_dian == '1001')
    assert b_1001.total_balance == Decimal('85500000'), \
        f"Total balance esperado 85.5M, recibido {b_1001.total_balance}"
    assert b_1001.total_reportado == Decimal('85500000')
    assert b_1001.diferencia == Decimal('0')
    assert b_1001.estado == 'cuadrado'
    print('✅ test_calculo_totales_balance_y_reportado')


def test_cuenta_excluida_genera_diferencia_explicada():
    sb = MockSb(setup_movimientos())
    dictamen = ce.construir_conciliacion_enriquecida(sb, 'qs', 2025)

    # F1009/2206:
    #   - 236515 EXCLUIDA: balance 5.5M, reportado 0, diferencia 5.5M (explicada)
    #   - 2335: balance 12M, reportado 12M, diferencia 0
    #   Total balance: 17.5M, total reportado: 12M, diferencia: 5.5M
    b_1009 = next(b for b in dictamen.bloques if b.formato_dian == '1009')
    assert b_1009.total_balance == Decimal('17500000')
    assert b_1009.total_reportado == Decimal('12000000')
    assert b_1009.diferencia == Decimal('5500000')

    # La cuenta excluida debe tener motivo
    excluida = next(c for c in b_1009.cuentas if c.codigo_cuenta == '236515')
    assert excluida.excluida is True
    assert excluida.motivo_diferencia is not None
    assert 'transitoria' in excluida.motivo_diferencia.lower()

    # El estado del bloque debe ser 'diferencia_explicada'
    assert b_1009.estado == 'diferencia_explicada', \
        f"Esperaba 'diferencia_explicada', recibí '{b_1009.estado}'"
    print('✅ test_cuenta_excluida_genera_diferencia_explicada')


def test_resumen_ejecutivo():
    sb = MockSb(setup_movimientos())
    dictamen = ce.construir_conciliacion_enriquecida(sb, 'qs', 2025)
    resumen = ce.dictamen_a_resumen_dict(dictamen)

    assert resumen['total_conceptos'] == 2
    assert resumen['conceptos_cuadrados'] == 1   # F1001
    assert resumen['conceptos_con_diferencia_explicada'] == 1  # F1009
    assert resumen['conceptos_pendientes'] == 0
    assert resumen['porcentaje_cuadrado'] == 50.0
    print('✅ test_resumen_ejecutivo')


def test_filas_excel():
    sb = MockSb(setup_movimientos())
    dictamen = ce.construir_conciliacion_enriquecida(sb, 'qs', 2025)
    filas = ce.dictamen_a_filas_excel(dictamen)

    # Debe haber: 2 cuentas F1001 + 1 total + 2 cuentas F1009 + 1 total = 6
    assert len(filas) == 6, f"Esperaba 6 filas, recibí {len(filas)}"

    # Las filas TOTAL CONCEPTO deben aparecer
    totales = [f for f in filas if f['Cuenta'] == 'TOTAL CONCEPTO']
    assert len(totales) == 2
    print('✅ test_filas_excel')


def test_nits_distintos_se_cuentan():
    sb = MockSb(setup_movimientos())
    dictamen = ce.construir_conciliacion_enriquecida(sb, 'qs', 2025)

    b_1001 = next(b for b in dictamen.bloques if b.formato_dian == '1001')
    cuenta_510515 = next(c for c in b_1001.cuentas if c.codigo_cuenta == '510515')

    # 510515 tiene 2 NITs distintos (900111 y 900222)
    assert cuenta_510515.nits_distintos == 2
    print('✅ test_nits_distintos_se_cuentan')


# ============================================================================
# Runner
# ============================================================================

if __name__ == '__main__':
    import traceback
    tests = [
        test_agrupacion_por_formato_concepto,
        test_calculo_totales_balance_y_reportado,
        test_cuenta_excluida_genera_diferencia_explicada,
        test_resumen_ejecutivo,
        test_filas_excel,
        test_nits_distintos_se_cuentan,
    ]
    pasados = 0
    fallidos = []
    for t in tests:
        try:
            t()
            pasados += 1
        except Exception as e:
            fallidos.append((t.__name__, str(e)))
            print(f'❌ {t.__name__}: {e}')
            traceback.print_exc()
    print()
    print(f'{"=" * 50}')
    print(f'✅ {pasados}/{len(tests)} tests pasaron')
    if fallidos:
        sys.exit(1)
