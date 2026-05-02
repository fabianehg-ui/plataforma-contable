"""
Detector de cuentas del balance que requieren conciliación tributaria.

CONCEPTOS DIAN AG2025 - FORMATO 1001 (correctos según catálogo oficial):

SEGURIDAD SOCIAL:
    5010 = Aportes parafiscales (SENA, Cajas, ICBF)
    5011 = Pagos a EPS / Salud / ARL
    5012 = Aportes obligatorios + voluntarios a pensiones

IMPUESTOS DEDUCIBLES:
    5015 = Impuestos solicitados como deducción
           (IVA asumido, ICA, predial, vehículo, telefónico, avisos y tableros)

GMF:
    5101 = Gravamen a los movimientos financieros (50% deducible - ET art. 115)

LÓGICA DE DETECCIÓN:
    - Solo buscamos en cuentas de PASIVOS PAGADOS (prefijos 23, 25)
    - NO incluir gastos del PyG (5104, 5204, 7204) - estos están duplicados con
      las cuentas puente que sí se reportan al pagarlas
    - Detección principal por NOMBRE de la cuenta (más confiable que por código)

DEDUCIBILIDAD POR DEFECTO (antes de conciliar con PILA):
    - Salud (EPS):  100% no deducible (es la parte trabajador típicamente)
    - ARL:          100% deducible (es 100% empleador)
    - Pensión:      75% deducible / 25% no deducible
    - Parafiscales: 100% deducible
    - Impuestos:    100% deducible
    - GMF:          50% deducible
"""

from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal


# ================================================================
# CATÁLOGOS DE CONCEPTOS (según prevalidador DIAN AG2025)
# ================================================================

CONCEPTOS_SEGURIDAD_SOCIAL = {
    5010: 'Parafiscales (SENA + Cajas + ICBF)',
    5011: 'Salud / EPS / ARL',
    5012: 'Pensión (obligatoria + voluntaria)',
}

CONCEPTOS_IMPUESTOS_DEDUCIBLES = {
    5015: 'Impuestos solicitados como deducción',
}

CONCEPTOS_GMF = {
    5101: 'GMF (Gravamen movimientos financieros) - 50% deducible',
}


# ================================================================
# REGLAS DE DETECCIÓN POR NOMBRE
# ================================================================

REGLAS_SEGURIDAD_SOCIAL = {
    'salud': {
        'concepto': 5011,
        'sub_tipo': 'salud',
        'keywords': ['salud', 'eps', 'sgsss', 'famisanar', 'sanitas', 'sura eps',
                     'compensar eps', 'nueva eps', 'medimas', 'savia salud', 'mutual ser',
                     'ecoopsos', 'capital salud'],
        'deducible_default': 0.0,
        'requiere_separacion': True,
        'descripcion': 'Salud (EPS)',
    },
    'arl': {
        'concepto': 5011,
        'sub_tipo': 'arl',
        'keywords': ['arl', 'riesgos profesionales', 'riesgos laborales', 'arp',
                     'positiva', 'sura arl', 'colmena arl'],
        'deducible_default': 1.0,
        'requiere_separacion': False,
        'descripcion': 'ARL',
    },
    'pension': {
        'concepto': 5012,
        'sub_tipo': 'pension',
        'keywords': ['pension', 'pensión', 'afp', 'fondo de pension',
                     'colpensiones', 'porvenir', 'protección', 'proteccion',
                     'old mutual', 'skandia', 'colfondos'],
        'deducible_default': 0.75,
        'requiere_separacion': True,
        'descripcion': 'Pensión',
    },
    'parafiscales': {
        'concepto': 5010,
        'sub_tipo': 'parafiscales',
        'keywords': ['sena', 'icbf', 'caja compensacion', 'caja de compensacion',
                     'compensar', 'comfamiliar', 'comfenalco', 'comfandi', 'cafam',
                     'colsubsidio', 'parafiscal', 'parafiscales',
                     'subsidio familiar', 'cofrem', 'comfacauca'],
        'deducible_default': 1.0,
        'requiere_separacion': False,
        'descripcion': 'Parafiscales (SENA/Cajas/ICBF)',
    },
}

KEYWORDS_IMPUESTOS_5015 = [
    ('iva asumido',                'IVA asumido'),
    ('iva mayor valor',             'IVA mayor valor'),
    ('industria y comercio',        'ICA - Industria y Comercio'),
    ('reteica',                     'ReteICA'),
    ('retencion ica',               'ReteICA'),
    ('ica ',                        'ICA'),
    ('predial',                     'Impuesto Predial'),
    ('impuesto vehiculo',           'Impuesto vehículo'),
    ('impuesto vehículo',           'Impuesto vehículo'),
    ('impuesto telefonico',         'Impuesto telefónico'),
    ('impuesto teléfonico',         'Impuesto telefónico'),
    ('telefonico',                  'Impuesto telefónico'),
    ('avisos y tableros',           'Avisos y tableros'),
    ('cree',                        'CREE'),
    ('estampilla',                  'Estampillas'),
]

PREFIJO_GMF = '5305'
KEYWORDS_GMF = [
    '4x1000', '4 x 1000', '4*1000', '4 por mil', 'cuatro por mil',
    'gravamen movimientos', 'gravamen a los movimientos',
    'gmf',
]
KEYWORDS_NO_GMF = [
    'comision', 'comisión', 'manejo', 'cuota manejo',
    'interes', 'interés', 'intereses',
    'chequera', 'talonario', 'transferencia',
    'cuota de', 'estudio', 'aval', 'seguro deudor',
    'descuento bancario', 'gastos bancarios', 'cobranza',
]

PREFIJOS_PASIVOS_VALIDOS = ['23', '25']

PREFIJOS_EXCLUIR_SS = ['5104', '5204', '7204']


# ================================================================
# DATACLASSES
# ================================================================

@dataclass
class CuentaConciliable:
    codigo_cuenta: str
    nombre_cuenta: str
    saldo_total: Decimal
    cantidad_movimientos: int
    cantidad_nits: int
    nits_principales: list[str]
    
    tipo_conciliacion: str
    sub_tipo: str
    concepto_sugerido: int | None
    descripcion_concepto: str
    formato_sugerido: str
    
    requiere_separacion_emp_trab: bool = False
    deducible_porcentaje: float = 1.0
    no_deducible_porcentaje: float = 0.0
    
    valor_deducible_default: Decimal = Decimal('0')
    valor_no_deducible_default: Decimal = Decimal('0')
    
    notas: list = field(default_factory=list)


@dataclass
class DictamenConciliacion:
    cuentas_seguridad_social: list[CuentaConciliable] = field(default_factory=list)
    cuentas_impuestos: list[CuentaConciliable] = field(default_factory=list)
    cuentas_gmf: list[CuentaConciliable] = field(default_factory=list)
    cuentas_otras: list[CuentaConciliable] = field(default_factory=list)
    
    total_seguridad_social: Decimal = Decimal('0')
    total_impuestos: Decimal = Decimal('0')
    total_gmf: Decimal = Decimal('0')
    total_general: Decimal = Decimal('0')


# ================================================================
# FUNCIONES DE DETECCIÓN
# ================================================================

def _normalize(s) -> str:
    if s is None:
        return ''
    s = str(s).strip().lower()
    repl = {'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u', 'ñ': 'n'}
    for k, v in repl.items():
        s = s.replace(k, v)
    return s


def _es_cuenta_pasivo_valido(codigo_cuenta: str) -> bool:
    cuenta = str(codigo_cuenta).strip()
    if not cuenta:
        return False
    for excl in PREFIJOS_EXCLUIR_SS:
        if cuenta.startswith(excl):
            return False
    return any(cuenta.startswith(p) for p in PREFIJOS_PASIVOS_VALIDOS)


def _detectar_seguridad_social(codigo_cuenta: str, nombre_cuenta: str) -> dict | None:
    if not _es_cuenta_pasivo_valido(codigo_cuenta):
        return None
    
    nombre_norm = _normalize(nombre_cuenta)
    if not nombre_norm:
        return None
    
    # ARL primero
    arl = REGLAS_SEGURIDAD_SOCIAL['arl']
    for kw in arl['keywords']:
        if kw in nombre_norm:
            return arl
    
    salud = REGLAS_SEGURIDAD_SOCIAL['salud']
    for kw in salud['keywords']:
        if kw in nombre_norm:
            return salud
    
    pension = REGLAS_SEGURIDAD_SOCIAL['pension']
    for kw in pension['keywords']:
        if kw in nombre_norm:
            return pension
    
    parafis = REGLAS_SEGURIDAD_SOCIAL['parafiscales']
    for kw in parafis['keywords']:
        if kw in nombre_norm:
            return parafis
    
    return None


def _detectar_impuesto_5015(codigo_cuenta: str, nombre_cuenta: str) -> str | None:
    nombre_norm = _normalize(nombre_cuenta)
    if not nombre_norm:
        return None
    
    for keyword, descripcion in KEYWORDS_IMPUESTOS_5015:
        if keyword in nombre_norm:
            return descripcion
    
    return None


def _es_cuenta_gmf(codigo_cuenta: str, nombre_cuenta: str) -> bool:
    cuenta = str(codigo_cuenta).strip()
    if not cuenta.startswith(PREFIJO_GMF):
        return False
    
    nombre_norm = _normalize(nombre_cuenta)
    
    for kw_excl in KEYWORDS_NO_GMF:
        if kw_excl in nombre_norm:
            return False
    
    for kw_inc in KEYWORDS_GMF:
        if kw_inc in nombre_norm:
            return True
    
    return False


def detectar_tipo_conciliacion(codigo_cuenta: str, nombre_cuenta: str,
                                formato_dian: str | None,
                                concepto_dian: int | None) -> dict:
    regla_ss = _detectar_seguridad_social(codigo_cuenta, nombre_cuenta)
    if regla_ss:
        return {
            'tipo': 'seguridad_social',
            'concepto_sugerido': regla_ss['concepto'],
            'descripcion': regla_ss['descripcion'],
            'sub_tipo': regla_ss['sub_tipo'],
            'deducible_default': regla_ss['deducible_default'],
            'requiere_separacion': regla_ss['requiere_separacion'],
        }
    
    if _es_cuenta_gmf(codigo_cuenta, nombre_cuenta):
        return {
            'tipo': 'gmf',
            'concepto_sugerido': 5101,
            'descripcion': CONCEPTOS_GMF[5101],
            'sub_tipo': 'gmf',
            'deducible_default': 0.5,
            'requiere_separacion': False,
        }
    
    desc_imp = _detectar_impuesto_5015(codigo_cuenta, nombre_cuenta)
    if desc_imp:
        return {
            'tipo': 'impuestos',
            'concepto_sugerido': 5015,
            'descripcion': desc_imp,
            'sub_tipo': 'impuesto_deducible',
            'deducible_default': 1.0,
            'requiere_separacion': False,
        }
    
    return {'tipo': None}


def construir_dictamen(movimientos_clasificados: list[dict]) -> DictamenConciliacion:
    dict_cuentas = {}
    
    for m in movimientos_clasificados:
        cuenta = str(m.get('codigo_cuenta', '')).strip()
        if not cuenta:
            continue
        
        deteccion = detectar_tipo_conciliacion(
            cuenta,
            m.get('nombre_cuenta', ''),
            m.get('formato_dian'),
            m.get('concepto_dian'),
        )
        
        if not deteccion.get('tipo'):
            continue
        
        if cuenta not in dict_cuentas:
            dict_cuentas[cuenta] = {
                'codigo_cuenta': cuenta,
                'nombre_cuenta': m.get('nombre_cuenta', ''),
                'saldo_total': Decimal('0'),
                'cantidad_movimientos': 0,
                'nits': set(),
                'nits_lista': [],
                'deteccion': deteccion,
            }
        
        c = dict_cuentas[cuenta]
        debitos = Decimal(str(m.get('debitos', 0) or 0))
        creditos = Decimal(str(m.get('creditos', 0) or 0))
        # Para pasivos pagados (23xx, 25xx), los pagos = débitos
        if cuenta.startswith(('23', '25')):
            c['saldo_total'] += abs(debitos)
        else:
            c['saldo_total'] += max(abs(debitos), abs(creditos))
        c['cantidad_movimientos'] += 1
        
        nit = m.get('nit')
        if nit:
            if nit not in c['nits']:
                c['nits'].add(nit)
                if len(c['nits_lista']) < 5:
                    c['nits_lista'].append(f"{nit} {m.get('nombre_tercero','')[:25]}")
    
    dictamen = DictamenConciliacion()
    
    for cuenta_data in dict_cuentas.values():
        d = cuenta_data['deteccion']
        saldo = cuenta_data['saldo_total']
        deducible_pct = d.get('deducible_default', 1.0)
        
        cc = CuentaConciliable(
            codigo_cuenta=cuenta_data['codigo_cuenta'],
            nombre_cuenta=cuenta_data['nombre_cuenta'],
            saldo_total=saldo,
            cantidad_movimientos=cuenta_data['cantidad_movimientos'],
            cantidad_nits=len(cuenta_data['nits']),
            nits_principales=cuenta_data['nits_lista'],
            tipo_conciliacion=d['tipo'],
            sub_tipo=d.get('sub_tipo', ''),
            concepto_sugerido=d['concepto_sugerido'],
            descripcion_concepto=d['descripcion'],
            formato_sugerido='1001',
            requiere_separacion_emp_trab=d.get('requiere_separacion', False),
            deducible_porcentaje=deducible_pct,
            no_deducible_porcentaje=1.0 - deducible_pct,
            valor_deducible_default=saldo * Decimal(str(deducible_pct)),
            valor_no_deducible_default=saldo * Decimal(str(1.0 - deducible_pct)),
        )
        
        if cc.tipo_conciliacion == 'seguridad_social':
            if cc.sub_tipo == 'salud':
                cc.notas.append("Default: 100% no deducible (parte trabajador). Conciliar con PILA.")
            elif cc.sub_tipo == 'arl':
                cc.notas.append("Default: 100% deducible (100% empleador).")
            elif cc.sub_tipo == 'pension':
                cc.notas.append("Default: 75% deducible / 25% no deducible. Conciliar con PILA.")
            elif cc.sub_tipo == 'parafiscales':
                cc.notas.append("Default: 100% deducible.")
            
            dictamen.cuentas_seguridad_social.append(cc)
            dictamen.total_seguridad_social += saldo
        
        elif cc.tipo_conciliacion == 'gmf':
            cc.notas.append("Solo 50% es deducible (ET art. 115).")
            dictamen.cuentas_gmf.append(cc)
            dictamen.total_gmf += saldo
        
        elif cc.tipo_conciliacion == 'impuestos':
            cc.notas.append("Concepto 5015: impuestos solicitados como deducción.")
            dictamen.cuentas_impuestos.append(cc)
            dictamen.total_impuestos += saldo
        
        else:
            dictamen.cuentas_otras.append(cc)
        
        dictamen.total_general += saldo
    
    dictamen.cuentas_seguridad_social.sort(key=lambda x: x.saldo_total, reverse=True)
    dictamen.cuentas_impuestos.sort(key=lambda x: x.saldo_total, reverse=True)
    dictamen.cuentas_gmf.sort(key=lambda x: x.saldo_total, reverse=True)
    dictamen.cuentas_otras.sort(key=lambda x: x.saldo_total, reverse=True)
    
    return dictamen


# ================================================================
# DICTAMEN POR FORMATO (vista alternativa)
# ================================================================

@dataclass
class ConceptoDictamen:
    formato_dian: str
    concepto_dian: int
    descripcion_concepto: str
    cuentas: list[dict] = field(default_factory=list)
    total: Decimal = Decimal('0')


@dataclass
class FormatoDictamen:
    formato_dian: str
    nombre_formato: str
    conceptos: dict = field(default_factory=dict)
    total_formato: Decimal = Decimal('0')


def construir_dictamen_por_formato(movimientos_clasificados: list[dict]) -> dict:
    """Agrupa movimientos clasificados por formato → concepto → cuentas."""
    formatos = {}
    
    for m in movimientos_clasificados:
        fmt = m.get('formato_dian')
        cpt = m.get('concepto_dian')
        if not fmt or fmt == '999999':
            continue
        
        cuenta = str(m.get('codigo_cuenta', '')).strip()
        nombre = m.get('nombre_cuenta', '')
        
        debitos = Decimal(str(m.get('debitos', 0) or 0))
        creditos = Decimal(str(m.get('creditos', 0) or 0))
        valor = max(abs(debitos), abs(creditos))
        
        if fmt not in formatos:
            formatos[fmt] = FormatoDictamen(
                formato_dian=fmt,
                nombre_formato=f"Formato {fmt}",
            )
        
        f = formatos[fmt]
        cpt_key = cpt if cpt else 0
        
        if cpt_key not in f.conceptos:
            f.conceptos[cpt_key] = ConceptoDictamen(
                formato_dian=fmt,
                concepto_dian=cpt_key,
                descripcion_concepto='',
            )
        
        c = f.conceptos[cpt_key]
        cuenta_existente = next((x for x in c.cuentas if x['codigo_cuenta'] == cuenta), None)
        if cuenta_existente:
            cuenta_existente['saldo'] += valor
            cuenta_existente['movimientos'] += 1
        else:
            c.cuentas.append({
                'codigo_cuenta': cuenta,
                'nombre_cuenta': nombre,
                'saldo': valor,
                'movimientos': 1,
            })
        
        c.total += valor
        f.total_formato += valor
    
    for f in formatos.values():
        for c in f.conceptos.values():
            c.cuentas.sort(key=lambda x: x['saldo'], reverse=True)
    
    return formatos


# ================================================================
# TESTS
# ================================================================

if __name__ == '__main__':
    print("=" * 70)
    print("TEST 1: Detección de seguridad social (solo cuentas 23/25)")
    print("=" * 70)
    
    casos_ss = [
        ('255005', 'PAGOS SALUD EPS', 5011, 'salud'),
        ('237005', 'EPS SANITAS', 5011, 'salud'),
        ('255010', 'PAGOS ARL POSITIVA', 5011, 'arl'),
        ('237010', 'RIESGOS PROFESIONALES', 5011, 'arl'),
        ('255015', 'PAGOS AFP PORVENIR', 5012, 'pension'),
        ('237006', 'COLPENSIONES PENSION', 5012, 'pension'),
        ('255020', 'CAJA COMPENSACION COMFAMA', 5010, 'parafiscales'),
        ('237030', 'SENA APORTES', 5010, 'parafiscales'),
        ('237035', 'ICBF APORTES', 5010, 'parafiscales'),
        # Excluir gastos PyG
        ('510303', 'SALUD EPS', None, None),
        ('520306', 'PENSION', None, None),
        ('510568', 'APORTE RIESGOS PROFESIONALES', None, None),
        ('730506', 'PARAFISCAL', None, None),
    ]
    
    for cuenta, nombre, exp_concepto, exp_subtipo in casos_ss:
        d = detectar_tipo_conciliacion(cuenta, nombre, '1001', None)
        if exp_concepto is None:
            ok = d.get('tipo') is None
            marca = "✓" if ok else "✗"
            print(f"  {marca} {cuenta:>8} {nombre[:35]:<35} → tipo={d.get('tipo')} (esperado: None)")
        else:
            ok = d.get('concepto_sugerido') == exp_concepto and d.get('sub_tipo') == exp_subtipo
            marca = "✓" if ok else "✗"
            print(f"  {marca} {cuenta:>8} {nombre[:35]:<35} → concepto={d.get('concepto_sugerido')} sub={d.get('sub_tipo')} (esperado: {exp_concepto}/{exp_subtipo})")
    
    print()
    print("=" * 70)
    print("TEST 2: Detección de impuestos deducibles (5015)")
    print("=" * 70)
    
    casos_imp = [
        ('731570', 'IVA ASUMIDO', True),
        ('521570', 'IVA ASUMIDO', True),
        ('511570', 'IVA ASUMIDO', True),
        ('511595', 'IMPUESTO TELEFONICO', True),
        ('511502', 'INDUSTRIA Y COMERCIO', True),
        ('511503', 'PREDIAL', True),
        ('511504', 'IMPUESTO VEHICULO', True),
    ]
    
    for cuenta, nombre, deberia in casos_imp:
        d = detectar_tipo_conciliacion(cuenta, nombre, '1001', None)
        es_imp = d.get('concepto_sugerido') == 5015
        ok = es_imp == deberia
        marca = "✓" if ok else "✗"
        print(f"  {marca} {cuenta:>8} {nombre[:30]:<30} → tipo={d.get('tipo')} concepto={d.get('concepto_sugerido')} desc={d.get('descripcion','')}")
    
    print()
    print("=" * 70)
    print("TEST 3: Detección GMF")
    print("=" * 70)
    
    casos_gmf = [
        ('530525', 'GRAVAMEN MOVIMIENTOS FINANCIEROS 4X1000', True),
        ('530530', 'GMF BANCOLOMBIA', True),
        ('530595', '4 X 1000 BANCOS', True),
        ('530505', 'COMISIONES BANCARIAS', False),
        ('530510', 'INTERESES BANCARIOS', False),
        ('530515', 'CUOTA DE MANEJO', False),
    ]
    
    for cuenta, nombre, esperado in casos_gmf:
        d = detectar_tipo_conciliacion(cuenta, nombre, '1001', None)
        es_gmf = d.get('tipo') == 'gmf'
        marca = "✓" if es_gmf == esperado else "✗"
        print(f"  {marca} {cuenta:>8} {nombre[:45]:<45} → GMF={es_gmf} (esperado: {esperado})")
    
    print()
    print("=" * 70)
    print("TEST 4: Dictamen completo con datos reales")
    print("=" * 70)
    
    movs = [
        # SS válidas
        {'codigo_cuenta': '255005', 'nombre_cuenta': 'PAGOS SALUD EPS',
         'nit': '901589040', 'debitos': 4000000, 'creditos': 0,
         'saldo_final': 0, 'formato_dian': '1001', 'concepto_dian': None},
        {'codigo_cuenta': '237010', 'nombre_cuenta': 'PAGOS ARL POSITIVA',
         'nit': '901589040', 'debitos': 1500000, 'creditos': 0,
         'saldo_final': 0, 'formato_dian': '1001', 'concepto_dian': None},
        {'codigo_cuenta': '255015', 'nombre_cuenta': 'PAGOS AFP PORVENIR',
         'nit': '901589040', 'debitos': 6000000, 'creditos': 0,
         'saldo_final': 0, 'formato_dian': '1001', 'concepto_dian': None},
        {'codigo_cuenta': '237030', 'nombre_cuenta': 'SENA APORTES',
         'nit': '901589040', 'debitos': 1000000, 'creditos': 0,
         'saldo_final': 0, 'formato_dian': '1001', 'concepto_dian': None},
        # GMF válido
        {'codigo_cuenta': '530525', 'nombre_cuenta': 'GMF 4X1000',
         'nit': '890903938', 'debitos': 1500000, 'creditos': 0,
         'saldo_final': 0, 'formato_dian': '1001', 'concepto_dian': None},
        # Impuestos 5015
        {'codigo_cuenta': '731570', 'nombre_cuenta': 'IVA ASUMIDO',
         'nit': None, 'debitos': 58079892, 'creditos': 0,
         'saldo_final': 0, 'formato_dian': '1001', 'concepto_dian': None},
        {'codigo_cuenta': '511595', 'nombre_cuenta': 'IMPUESTO TELEFONICO',
         'nit': None, 'debitos': 186, 'creditos': 0,
         'saldo_final': 0, 'formato_dian': '1001', 'concepto_dian': None},
        # Excluir: gasto PyG (está en 5xxx pero no es 23/25)
        {'codigo_cuenta': '510568', 'nombre_cuenta': 'APORTE RIESGOS PROFESIONALES',
         'nit': '901589040', 'debitos': 477800, 'creditos': 0,
         'saldo_final': 0, 'formato_dian': '1001', 'concepto_dian': None},
    ]
    
    d = construir_dictamen(movs)
    
    print(f"\nSeguridad Social: {len(d.cuentas_seguridad_social)} cuentas")
    for c in d.cuentas_seguridad_social:
        print(f"  {c.codigo_cuenta} {c.nombre_cuenta[:30]:<30} concepto={c.concepto_sugerido} sub={c.sub_tipo}")
        print(f"    Saldo: ${c.saldo_total:,}  Deducible default: ${c.valor_deducible_default:,.0f} ({c.deducible_porcentaje*100:.0f}%)")
    
    print(f"\nImpuestos (5015): {len(d.cuentas_impuestos)} cuentas")
    for c in d.cuentas_impuestos:
        print(f"  {c.codigo_cuenta} {c.nombre_cuenta[:30]:<30} → {c.descripcion_concepto}  Saldo: ${c.saldo_total:,}")
    
    print(f"\nGMF: {len(d.cuentas_gmf)} cuentas")
    for c in d.cuentas_gmf:
        print(f"  {c.codigo_cuenta} {c.nombre_cuenta[:30]:<30}  Saldo: ${c.saldo_total:,}  Deducible 50%: ${c.valor_deducible_default:,.0f}")
    
    print(f"\nOtras: {len(d.cuentas_otras)} (debe ser 0 - 510568 fue excluida)")
    
    print(f"\n=== TOTALES ===")
    print(f"Seguridad social: ${d.total_seguridad_social:,}")
    print(f"Impuestos:        ${d.total_impuestos:,}")
    print(f"GMF:              ${d.total_gmf:,}")
    print(f"TOTAL GENERAL:    ${d.total_general:,}")
