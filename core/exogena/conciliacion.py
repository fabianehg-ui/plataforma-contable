"""
Detector de cuentas del balance que requieren conciliación tributaria.

Identifica:
    1. Cuentas asociadas a Salud (concepto 5010): salario salud, 510515, etc.
    2. Cuentas asociadas a Pensión (concepto 5011)
    3. Cuentas asociadas a ARL (concepto 5012)
    4. Cuentas asociadas a Caja Compensación (5013), SENA (5014), ICBF (5015)
    5. Cuentas de GMF (Gravamen Movimientos Financieros) - 50% deducible
    6. Otras cuentas marcadas para conciliación manual

El detector cruza:
    - Movimientos del balance (exogena_balance)
    - Reglas de mapeo aplicadas (3 capas)
    - Catálogo de conceptos sensibles

Devuelve:
    - Cuentas que necesitan conciliación con su saldo total
    - NITs involucrados (si aplica)
    - Sugerencia automática del concepto y formato
"""

from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal


# Conceptos que requieren conciliación tributaria
CONCEPTOS_SEGURIDAD_SOCIAL = {
    5010: 'Salud',
    5011: 'Pensión',
    5012: 'ARL',
    5013: 'Caja Compensación',
    5014: 'SENA',
    5015: 'ICBF',
}

# Conceptos GMF (50% deducible)
CONCEPTOS_GMF = {
    5045: 'GMF Movimientos Financieros',
}

# Patrones de cuentas PUC asociadas (para detección automática)
# Si una cuenta del balance empieza con estos prefijos, es candidata
# para conciliación de seguridad social
PATRONES_SEGURIDAD_SOCIAL = {
    # Gastos de personal - aportes empleador
    '510303': ('salud', 5010),    # Salud empleador (administración)
    '510306': ('pension', 5011),  # Pensión empleador
    '510308': ('arl', 5012),      # ARL
    '510310': ('caja', 5013),     # Caja Compensación
    '510311': ('sena', 5014),     # SENA
    '510312': ('icbf', 5015),     # ICBF
    
    '511103': ('salud', 5010),    # Salud (gastos administración)
    '520303': ('salud', 5010),    # Salud (gastos ventas)
    '520306': ('pension', 5011),  # Pensión
    '520308': ('arl', 5012),
    '530506': ('salud', 5010),    # Otros gastos personal
    
    # Pasivos - aportes pendientes (cuenta puente)
    '237005': ('salud', 5010),    # Aportes salud por pagar
    '237006': ('pension', 5011),  # Aportes pensión por pagar
    '237010': ('arl', 5012),      # ARL por pagar
    '237025': ('caja', 5013),
    '237030': ('sena', 5014),
    '237035': ('icbf', 5015),
    
    # Deducciones nómina (parte trabajador)
    '237015': ('salud_trab', 5010),   # Salud trabajador
    '237016': ('pension_trab', 5011), # Pensión trabajador
}

# Patrones de cuentas PUC asociadas a GMF
PATRONES_GMF = [
    '5305',     # GMF (gravamen movimientos financieros)
    '5305xx',   # variantes
    '535525',   # GMF específico
]


@dataclass
class CuentaConciliable:
    codigo_cuenta: str
    nombre_cuenta: str
    saldo_total: Decimal
    cantidad_movimientos: int
    cantidad_nits: int
    nits_principales: list[str]
    
    # Clasificación detectada
    tipo_conciliacion: str   # 'seguridad_social', 'gmf', 'otro'
    concepto_sugerido: int | None
    descripcion_concepto: str
    formato_sugerido: str    # '1001'
    
    # Estado de conciliación
    requiere_separacion_emp_trab: bool = False
    deducible_porcentaje: int = 100   # 100 normal, 50 GMF
    notas: list = field(default_factory=list)


@dataclass
class DictamenConciliacion:
    """Resultado del análisis: qué cuentas requieren conciliación."""
    cuentas_seguridad_social: list[CuentaConciliable] = field(default_factory=list)
    cuentas_gmf: list[CuentaConciliable] = field(default_factory=list)
    cuentas_otras: list[CuentaConciliable] = field(default_factory=list)
    
    total_seguridad_social: Decimal = Decimal('0')
    total_gmf: Decimal = Decimal('0')
    total_general: Decimal = Decimal('0')


def detectar_tipo_conciliacion(codigo_cuenta: str, formato_dian: str | None,
                                concepto_dian: int | None) -> tuple[str, int | None, str]:
    """Identifica si una cuenta requiere conciliación.
    
    Returns: (tipo, concepto_sugerido, descripcion)
    Tipo: 'seguridad_social' | 'gmf' | 'otro' | None
    """
    cuenta = str(codigo_cuenta).strip()
    
    # 1. Detección por concepto ya asignado
    if concepto_dian:
        if concepto_dian in CONCEPTOS_SEGURIDAD_SOCIAL:
            return ('seguridad_social', concepto_dian,
                    CONCEPTOS_SEGURIDAD_SOCIAL[concepto_dian])
        if concepto_dian in CONCEPTOS_GMF:
            return ('gmf', concepto_dian, CONCEPTOS_GMF[concepto_dian])
    
    # 2. Detección por patrón de cuenta - GMF
    for patron in PATRONES_GMF:
        if cuenta.startswith(patron.replace('x', '')) and len(cuenta) >= 4:
            return ('gmf', 5045, 'GMF Movimientos Financieros')
    
    # 3. Detección por patrón de cuenta - Seguridad Social
    for patron, (tipo_aporte, concepto) in PATRONES_SEGURIDAD_SOCIAL.items():
        if cuenta.startswith(patron):
            desc = CONCEPTOS_SEGURIDAD_SOCIAL.get(concepto, tipo_aporte)
            return ('seguridad_social', concepto, desc)
    
    return (None, None, '')


def construir_dictamen(movimientos_clasificados: list[dict]) -> DictamenConciliacion:
    """Analiza los movimientos clasificados y produce dictamen de conciliación.
    
    Args:
        movimientos_clasificados: lista de dicts con keys:
            codigo_cuenta, nombre_cuenta, nit, debitos, creditos,
            saldo_final, formato_dian, concepto_dian
    
    Returns:
        DictamenConciliacion con cuentas agrupadas por tipo de conciliación
    """
    dict_cuentas = {}  # cuenta → datos agregados
    
    for m in movimientos_clasificados:
        cuenta = str(m.get('codigo_cuenta', '')).strip()
        if not cuenta:
            continue
        
        tipo, concepto, desc = detectar_tipo_conciliacion(
            cuenta,
            m.get('formato_dian'),
            m.get('concepto_dian'),
        )
        
        if not tipo:
            continue  # No requiere conciliación
        
        if cuenta not in dict_cuentas:
            dict_cuentas[cuenta] = {
                'codigo_cuenta': cuenta,
                'nombre_cuenta': m.get('nombre_cuenta', ''),
                'saldo_total': Decimal('0'),
                'cantidad_movimientos': 0,
                'nits': set(),
                'nits_lista': [],
                'tipo_conciliacion': tipo,
                'concepto_sugerido': concepto,
                'descripcion_concepto': desc,
                'formato_sugerido': '1001',
            }
        
        c = dict_cuentas[cuenta]
        # Tomar la magnitud del movimiento (el lado que no es cero)
        debitos = Decimal(str(m.get('debitos', 0) or 0))
        creditos = Decimal(str(m.get('creditos', 0) or 0))
        c['saldo_total'] += max(abs(debitos), abs(creditos))
        c['cantidad_movimientos'] += 1
        
        nit = m.get('nit')
        if nit:
            if nit not in c['nits']:
                c['nits'].add(nit)
                if len(c['nits_lista']) < 5:
                    c['nits_lista'].append(f"{nit} {m.get('nombre_tercero','')[:25]}")
    
    # Construir el dictamen
    dictamen = DictamenConciliacion()
    
    for cuenta_data in dict_cuentas.values():
        cc = CuentaConciliable(
            codigo_cuenta=cuenta_data['codigo_cuenta'],
            nombre_cuenta=cuenta_data['nombre_cuenta'],
            saldo_total=cuenta_data['saldo_total'],
            cantidad_movimientos=cuenta_data['cantidad_movimientos'],
            cantidad_nits=len(cuenta_data['nits']),
            nits_principales=cuenta_data['nits_lista'],
            tipo_conciliacion=cuenta_data['tipo_conciliacion'],
            concepto_sugerido=cuenta_data['concepto_sugerido'],
            descripcion_concepto=cuenta_data['descripcion_concepto'],
            formato_sugerido=cuenta_data['formato_sugerido'],
        )
        
        if cc.tipo_conciliacion == 'seguridad_social':
            # Salud y pensión requieren separación empleador/trabajador
            if cc.concepto_sugerido in (5010, 5011):
                cc.requiere_separacion_emp_trab = True
            dictamen.cuentas_seguridad_social.append(cc)
            dictamen.total_seguridad_social += cc.saldo_total
        elif cc.tipo_conciliacion == 'gmf':
            cc.deducible_porcentaje = 50
            cc.notas.append("Solo 50% es deducible (ET art. 115)")
            dictamen.cuentas_gmf.append(cc)
            dictamen.total_gmf += cc.saldo_total
        else:
            dictamen.cuentas_otras.append(cc)
        
        dictamen.total_general += cc.saldo_total
    
    # Ordenar por saldo descendente
    dictamen.cuentas_seguridad_social.sort(key=lambda x: x.saldo_total, reverse=True)
    dictamen.cuentas_gmf.sort(key=lambda x: x.saldo_total, reverse=True)
    dictamen.cuentas_otras.sort(key=lambda x: x.saldo_total, reverse=True)
    
    return dictamen


if __name__ == '__main__':
    # Test
    movs = [
        {'codigo_cuenta': '510303', 'nombre_cuenta': 'SALUD EPS', 
         'nit': '901589040', 'debitos': 4000000, 'creditos': 0,
         'saldo_final': 4000000, 'formato_dian': '1001', 'concepto_dian': 5010},
        {'codigo_cuenta': '510306', 'nombre_cuenta': 'PENSION', 
         'nit': '901589040', 'debitos': 6000000, 'creditos': 0,
         'saldo_final': 6000000, 'formato_dian': '1001', 'concepto_dian': 5011},
        {'codigo_cuenta': '530525', 'nombre_cuenta': 'GMF',
         'nit': '890903938', 'debitos': 1000000, 'creditos': 0,
         'saldo_final': 1000000, 'formato_dian': '1001', 'concepto_dian': 5045},
    ]
    
    d = construir_dictamen(movs)
    print(f"Cuentas seguridad social: {len(d.cuentas_seguridad_social)}")
    for c in d.cuentas_seguridad_social:
        print(f"  {c.codigo_cuenta} {c.descripcion_concepto:>12}  ${c.saldo_total:,}")
    print(f"\nCuentas GMF: {len(d.cuentas_gmf)}")
    for c in d.cuentas_gmf:
        print(f"  {c.codigo_cuenta} {c.descripcion_concepto:>30}  ${c.saldo_total:,}  ({c.deducible_porcentaje}% deducible)")
    print(f"\nTotal seguridad social: ${d.total_seguridad_social:,}")
    print(f"Total GMF: ${d.total_gmf:,}")
