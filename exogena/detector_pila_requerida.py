"""
Detector de necesidad de cargar PILA basado en el balance de la empresa.

Analiza el balance ya cargado (tabla exogena_balance) y determina:
  - Si la empresa tiene nómina (cuentas 237xxx, 25500x, 25502x, 2510x)
  - Si necesita cargar planillas PILA
  - Si necesita cargar informes de cesantías
  - Qué archivos están pendientes

Es agnóstico de la empresa: funciona para Quinto Sentido y para cualquier
otra empresa que se cargue al sistema.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional


# ============================================================
# Cuentas indicadoras de necesidad de PILA
# ============================================================

# Cuentas de aportes pendientes (pasivo F1009 cpto 2214)
CUENTAS_APORTES_POR_PAGAR = [
    '237005',  # Salud por pagar
    '237006',  # Pensión por pagar
    '237010',  # ARL por pagar
    '237025',  # Cajas por pagar
    '237030',  # SENA por pagar
    '237035',  # ICBF por pagar
]

# Cuentas de aportes pagados (gasto)
CUENTAS_APORTES_PAGADOS = [
    '25500502',  # EPS pagada
    '25500602',  # ARL pagada
    '25501002',  # Parafiscales pagados
    '25502002',  # Pensión pagada
]

# Cuentas cesantías consolidadas (pasivo)
PREFIJO_CESANTIAS_CONSOLIDADAS = '2510'

# Cuentas intereses sobre cesantías
PREFIJO_INTERESES_CESANTIAS = '2515'

# Cuentas vacaciones
PREFIJO_VACACIONES = '2525'

# Umbral mínimo (en pesos) para considerar que hay saldo
UMBRAL_MATERIALIDAD = Decimal('1000')


# ============================================================
# Modelo de diagnóstico
# ============================================================

@dataclass
class DiagnosticoPilaEmpresa:
    """Diagnóstico sobre si la empresa necesita cargar PILA."""

    # Resumen
    necesita_pila: bool = False
    tiene_nomina: bool = False
    motivo: str = ''

    # Detalle por tipo de cuenta
    saldo_aportes_por_pagar: Decimal = Decimal('0')
    saldo_aportes_pagados: Decimal = Decimal('0')
    saldo_cesantias_consolidadas: Decimal = Decimal('0')
    saldo_intereses_cesantias: Decimal = Decimal('0')
    saldo_vacaciones: Decimal = Decimal('0')

    # Cuentas individuales encontradas
    cuentas_237_con_saldo: list = field(default_factory=list)
    cuentas_2510_con_saldo: list = field(default_factory=list)
    cuentas_255_con_saldo: list = field(default_factory=list)

    # Archivos PILA requeridos (cuáles, cuáles están cargados)
    requiere_planilla_anual: bool = False
    requiere_planilla_pasivo: bool = False
    requiere_cesantias_pagadas: bool = False
    requiere_cesantias_pasivo: bool = False

    # Estado de carga
    planilla_anual_cargada: bool = False
    planilla_pasivo_cargada: bool = False
    cesantias_pagadas_cargadas: bool = False
    cesantias_pasivo_cargadas: bool = False

    # Lista de pendientes (para UI)
    pendientes: list = field(default_factory=list)

    @property
    def porcentaje_completitud(self) -> int:
        """Porcentaje 0-100 de archivos PILA cargados sobre los requeridos."""
        requeridos = sum([
            self.requiere_planilla_anual,
            self.requiere_planilla_pasivo,
            self.requiere_cesantias_pagadas,
            self.requiere_cesantias_pasivo,
        ])
        if requeridos == 0:
            return 100  # No requiere nada → 100% completo
        cargados = sum([
            self.requiere_planilla_anual and self.planilla_anual_cargada,
            self.requiere_planilla_pasivo and self.planilla_pasivo_cargada,
            self.requiere_cesantias_pagadas and self.cesantias_pagadas_cargadas,
            self.requiere_cesantias_pasivo and self.cesantias_pasivo_cargadas,
        ])
        return int(cargados * 100 / requeridos)

    @property
    def esta_completo(self) -> bool:
        return self.porcentaje_completitud == 100


# ============================================================
# Análisis del balance
# ============================================================

def _suma_saldos(saldos: list[dict]) -> Decimal:
    """Suma saldo_final de una lista de filas exogena_balance (valor absoluto)."""
    total = Decimal('0')
    for s in saldos:
        v = s.get('saldo_final') or 0
        try:
            total += abs(Decimal(str(v)))
        except Exception:
            pass
    return total


def analizar_necesidad_pila(supabase, empresa_id: str, año_gravable: int) -> DiagnosticoPilaEmpresa:
    """Analiza balance + estado de carga PILA y devuelve diagnóstico completo.

    Args:
        supabase: cliente Supabase
        empresa_id: UUID empresa
        año_gravable: año gravable a evaluar

    Returns:
        DiagnosticoPilaEmpresa
    """
    diag = DiagnosticoPilaEmpresa()

    # 1) Obtener periodo
    try:
        periodo = supabase.table('exogena_periodos') \
            .select('id') \
            .eq('empresa_id', empresa_id) \
            .eq('año_gravable', año_gravable) \
            .single() \
            .execute()
        if not periodo.data:
            diag.motivo = 'No hay periodo creado para el año gravable'
            return diag
        periodo_id = periodo.data['id']
    except Exception:
        diag.motivo = 'No se pudo cargar el periodo'
        return diag

    # 2) Leer balance — buscar cuentas indicadoras
    try:
        balance_resp = supabase.table('exogena_balance') \
            .select('codigo_cuenta, nombre_cuenta, nit, nombre_tercero, saldo_final') \
            .eq('periodo_id', periodo_id) \
            .execute()
        balance = balance_resp.data or []
    except Exception:
        diag.motivo = 'No se pudo leer el balance'
        return diag

    if not balance:
        diag.motivo = 'No hay balance cargado todavía'
        return diag

    # 3) Clasificar saldos relevantes
    for fila in balance:
        cuenta = (fila.get('codigo_cuenta') or '').strip()
        saldo_str = fila.get('saldo_final')
        try:
            saldo = abs(Decimal(str(saldo_str or 0)))
        except Exception:
            saldo = Decimal('0')

        if saldo < UMBRAL_MATERIALIDAD:
            continue

        # Aportes por pagar (237xxx)
        if any(cuenta.startswith(c) for c in CUENTAS_APORTES_POR_PAGAR):
            diag.saldo_aportes_por_pagar += saldo
            diag.cuentas_237_con_saldo.append({
                'cuenta': cuenta,
                'nombre': fila.get('nombre_cuenta', ''),
                'saldo': float(saldo),
            })

        # Aportes pagados (25500x, 25501x, 25502x)
        elif any(cuenta.startswith(c) for c in CUENTAS_APORTES_PAGADOS):
            diag.saldo_aportes_pagados += saldo
            diag.cuentas_255_con_saldo.append({
                'cuenta': cuenta,
                'nombre': fila.get('nombre_cuenta', ''),
                'saldo': float(saldo),
            })

        # Cesantías consolidadas
        elif cuenta.startswith(PREFIJO_CESANTIAS_CONSOLIDADAS):
            diag.saldo_cesantias_consolidadas += saldo
            diag.cuentas_2510_con_saldo.append({
                'cuenta': cuenta,
                'nombre': fila.get('nombre_cuenta', ''),
                'saldo': float(saldo),
            })

        # Intereses cesantías
        elif cuenta.startswith(PREFIJO_INTERESES_CESANTIAS):
            diag.saldo_intereses_cesantias += saldo

        # Vacaciones
        elif cuenta.startswith(PREFIJO_VACACIONES):
            diag.saldo_vacaciones += saldo

    # 4) Determinar si hay nómina
    diag.tiene_nomina = (
        diag.saldo_aportes_por_pagar > UMBRAL_MATERIALIDAD
        or diag.saldo_aportes_pagados > UMBRAL_MATERIALIDAD
        or diag.saldo_cesantias_consolidadas > UMBRAL_MATERIALIDAD
        or diag.saldo_intereses_cesantias > UMBRAL_MATERIALIDAD
        or diag.saldo_vacaciones > UMBRAL_MATERIALIDAD
    )

    if not diag.tiene_nomina:
        diag.necesita_pila = False
        diag.motivo = (
            'Esta empresa no tiene cuentas de aportes a seguridad social ni cesantías '
            'con saldo material. No requiere cargar PILA. Es típico de empresas que '
            'sólo trabajan con contratistas independientes.'
        )
        return diag

    diag.necesita_pila = True

    # 5) Determinar qué archivos PILA requiere
    # Si hay aportes pagados durante el año → necesita planilla anual
    if diag.saldo_aportes_pagados > UMBRAL_MATERIALIDAD:
        diag.requiere_planilla_anual = True

    # Si hay aportes por pagar al 31-dic (237xxx) → necesita planilla cot diciembre
    if diag.saldo_aportes_por_pagar > UMBRAL_MATERIALIDAD:
        diag.requiere_planilla_pasivo = True

    # Si hay cesantías consolidadas o pagó cesantías → necesita ambos informes
    if diag.saldo_cesantias_consolidadas > UMBRAL_MATERIALIDAD:
        # Tanto las del año pasado pagadas en feb-año (F1001 5016 + F2276)
        # como las del año actual a 31-dic pasivo (F1009 2214)
        diag.requiere_cesantias_pagadas = True
        diag.requiere_cesantias_pasivo = True

    # 6) Verificar qué ya está cargado
    try:
        planillas_resp = supabase.table('exogena_pila_planillas') \
            .select('numero_planilla, periodo_cot, fecha_pago') \
            .eq('empresa_id', empresa_id) \
            .eq('año_gravable', año_gravable) \
            .execute()
        planillas = planillas_resp.data or []
    except Exception:
        planillas = []

    # Planilla "anual" = cualquier planilla con periodo_cot != año12
    periodo_pasivo = f'{año_gravable}12'
    planillas_anuales = [p for p in planillas if p.get('periodo_cot') != periodo_pasivo]
    planillas_pasivo = [p for p in planillas if p.get('periodo_cot') == periodo_pasivo]
    diag.planilla_anual_cargada = len(planillas_anuales) > 0
    diag.planilla_pasivo_cargada = len(planillas_pasivo) > 0

    try:
        ces_resp = supabase.table('exogena_pila_cesantias') \
            .select('año_causado, es_pasivo') \
            .eq('empresa_id', empresa_id) \
            .eq('año_gravable', año_gravable) \
            .execute()
        cesantias = ces_resp.data or []
    except Exception:
        cesantias = []

    diag.cesantias_pagadas_cargadas = any(not c.get('es_pasivo') for c in cesantias)
    diag.cesantias_pasivo_cargadas = any(c.get('es_pasivo') for c in cesantias)

    # 7) Lista de pendientes para UI
    if diag.requiere_planilla_anual and not diag.planilla_anual_cargada:
        diag.pendientes.append({
            'archivo': f'Comprobante MM SuAporte {año_gravable} (12 planillas anuales)',
            'tipo': 'planilla_anual',
            'destino': 'F1001 conceptos 5010, 5011, 5012',
            'razon': f'Hay ${diag.saldo_aportes_pagados:,.0f} en cuentas 255xx (aportes pagados)',
        })
    if diag.requiere_planilla_pasivo and not diag.planilla_pasivo_cargada:
        diag.pendientes.append({
            'archivo': f'Comprobante MM SuAporte ene-{año_gravable+1} (planilla cot {año_gravable}12)',
            'tipo': 'planilla_pasivo',
            'destino': 'F1009 concepto 2214 (aportes pendientes)',
            'razon': f'Hay ${diag.saldo_aportes_por_pagar:,.0f} en cuentas 237xxx (por pagar)',
        })
    if diag.requiere_cesantias_pagadas and not diag.cesantias_pagadas_cargadas:
        diag.pendientes.append({
            'archivo': f'Informe del Fondo — cesantías {año_gravable-1} pagadas feb-{año_gravable}',
            'tipo': 'cesantias_pagadas',
            'destino': 'F1001 cpto 5016 + F2276 cesantías por empleado',
            'razon': f'Hay cuentas 2510 con saldo (cesantías consolidadas año anterior)',
        })
    if diag.requiere_cesantias_pasivo and not diag.cesantias_pasivo_cargadas:
        diag.pendientes.append({
            'archivo': f'Informe del Fondo — cesantías {año_gravable} pagadas feb-{año_gravable+1}',
            'tipo': 'cesantias_pasivo',
            'destino': 'F1009 concepto 2214 (cesantías consolidadas 31-dic)',
            'razon': f'Hay ${diag.saldo_cesantias_consolidadas:,.0f} en cuentas 2510 (pasivo 31-dic)',
        })

    return diag


# ============================================================
# Helpers para UI
# ============================================================

def emoji_estado(diag: DiagnosticoPilaEmpresa) -> str:
    """Devuelve el emoji que representa el estado de PILA para la UI."""
    if not diag.necesita_pila:
        return '⚪'  # No aplica
    if diag.esta_completo:
        return '✅'  # Completo
    if diag.porcentaje_completitud > 0:
        return '⚠️'  # Parcial
    return '❌'  # Sin cargar


def texto_estado(diag: DiagnosticoPilaEmpresa) -> str:
    """Texto corto para mostrar el estado de PILA."""
    if not diag.necesita_pila:
        return 'No aplica — empresa sin nómina'
    if diag.esta_completo:
        return f'Completo ({diag.porcentaje_completitud}%)'
    if diag.porcentaje_completitud == 0:
        return f'Pendiente: {len(diag.pendientes)} archivo(s) por cargar'
    return f'Parcial ({diag.porcentaje_completitud}%) — falta {len(diag.pendientes)} archivo(s)'
