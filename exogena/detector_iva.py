"""
detector_iva.py
================
Detector de rol funcional de cuentas de IVA por patrón de nombre.

Estrategia: NO depender del código exacto de la cuenta auxiliar (que varía
entre empresas), sino detectar el rol por el NOMBRE de la cuenta.

Esto resuelve el problema multi-empresa donde:
- Empresa A usa cuenta 240805 con nombre "IVA GENERADO"
- Empresa B usa cuenta 24080501 con nombre "IVA GENERADO 19%"
- Empresa C usa cuenta 408010 con nombre "IVA GENERADO TARIFA 19%"

Todas se mapean al mismo rol funcional: GENERADO → F1006.

Sustento normativo:
- Res. 000227/2025 art. 1.3.5.5.1 (F1005)
- Res. 000227/2025 art. 1.3.5.5.2 (F1006)
- Res. 000233/2025 arts. 6 y 7 (cambios estructurales)
"""

from dataclasses import dataclass
from typing import Optional


# =============================================================================
# Constantes
# =============================================================================

# Formatos que tienen columna deducible/no deducible
FORMATOS_CON_DEDUCIBILIDAD = {'1001'}

# Formatos de saldo (reportan 100%)
FORMATOS_DE_SALDO = {'1008', '1009', '1011', '1012'}

# Formatos de IVA
FORMATOS_IVA = {'1005', '1006'}


# =============================================================================
# Patrones de detección (orden de prioridad importa)
# =============================================================================
#
# Cada patrón es: (palabras_clave, formato, columna, concepto, descripción)
# El primer patrón que matchee gana.

PATRONES_IVA = [
    # PRIORIDAD 10-20: RETEIVA (más específico)
    (['RETEIVA'],                          '1003', 'RETEIVA',     '1309', 'RETEIVA → F1003 conc 1309'),
    (['RET', 'IVA'],                       '1003', 'RETEIVA',     '1309', 'Retención IVA → F1003 conc 1309'),
    (['RETENCION', 'IVA'],                 '1003', 'RETEIVA',     '1309', 'Retención IVA (variante) → F1003'),

    # PRIORIDAD 20-30: Devoluciones en compras (afectan F1006)
    (['DEV', 'COMPRA'],                    '1006', 'DEV_COMPRA',   None,  'IVA dev en compras → F1006 col devolución'),
    (['DEVOL', 'COMPRA'],                  '1006', 'DEV_COMPRA',   None,  'IVA dev en compras (variante)'),
    (['DEVOLUCION', 'COMPRA'],             '1006', 'DEV_COMPRA',   None,  'IVA dev en compras (variante completa)'),

    # PRIORIDAD 30-40: Devoluciones en ventas (afectan F1005)
    (['DEV', 'VENTA'],                     '1005', 'DEV_VENTA',    None,  'IVA dev en ventas → F1005 col devolución'),
    (['DEVOL', 'VENTA'],                   '1005', 'DEV_VENTA',    None,  'IVA dev en ventas (variante)'),
    (['DEVOLUCION', 'VENTA'],              '1005', 'DEV_VENTA',    None,  'IVA dev en ventas (variante completa)'),

    # PRIORIDAD 40-50: IVA generado
    (['IVA', 'GENERADO'],                  '1006', 'GENERADO',     None,  'IVA generado → F1006'),
    (['IMPUESTO', 'VENTAS', 'GENERADO'],   '1006', 'GENERADO',     None,  'IVA generado (variante completa)'),

    # PRIORIDAD 50-60: IVA descontable
    (['IVA', 'DESCONTABLE'],               '1005', 'DESCONTABLE',  None,  'IVA descontable → F1005'),
    (['IMPUESTO', 'VENTAS', 'DESCONTABLE'],'1005', 'DESCONTABLE',  None,  'IVA descontable (variante)'),

    # PRIORIDAD 60-70: INC (Impuesto Nacional al Consumo)
    (['IMPUESTO', 'CONSUMO'],              '1006', 'INC',          None,  'INC → F1006 col INC'),
    (['IMPOCONSUMO'],                      '1006', 'INC',          None,  'INC (variante)'),

    # PRIORIDAD 90+: NO reportar (cuentas puente)
    (['TRASLADO'],                         None,   'NO_REPORTAR',  None,  'Cuenta puente - no reportar'),
]


# =============================================================================
# Resultado de la detección
# =============================================================================

@dataclass
class ResultadoDeteccionIVA:
    formato: Optional[str]
    columna: Optional[str]
    concepto: Optional[str]
    descripcion: str
    matched: bool
    
    def __str__(self):
        if not self.matched:
            return f"❓ Sin clasificar: {self.descripcion}"
        if self.formato is None:
            return f"⚠ {self.descripcion}"
        return f"✅ F{self.formato} col={self.columna} concepto={self.concepto or '-'} :: {self.descripcion}"


# =============================================================================
# Función principal
# =============================================================================

def detectar_rol_iva(
    cuenta: str,
    nombre: str,
    debitos: float = 0,
    creditos: float = 0,
    cuenta_raiz: str = '2408'
) -> ResultadoDeteccionIVA:
    """
    Detecta el rol funcional de una cuenta de IVA.
    
    Args:
        cuenta: código de cuenta (ej. '240805', '24081005')
        nombre: nombre descriptivo de la cuenta (ej. 'IVA GENERADO TARIFA 19%')
        debitos: total débitos del año (para inferir naturaleza si nombre es ambiguo)
        creditos: total créditos del año
        cuenta_raiz: prefijo esperado (típicamente '2408' para IVA)
    
    Returns:
        ResultadoDeteccionIVA con formato, columna, concepto, descripción
    """
    if nombre is None:
        return ResultadoDeteccionIVA(
            formato=None, columna=None, concepto=None,
            descripcion='Sin nombre de cuenta', matched=False
        )
    
    nombre_upper = str(nombre).upper().strip()
    cuenta_str = str(cuenta).strip()
    
    # Verificar que es cuenta de IVA (típicamente raíz 2408)
    if cuenta_raiz and not cuenta_str.startswith(cuenta_raiz):
        # Permitir excepciones para INC que puede estar en otras cuentas
        if 'CONSUMO' not in nombre_upper and 'IMPOCONSUMO' not in nombre_upper:
            return ResultadoDeteccionIVA(
                formato=None, columna=None, concepto=None,
                descripcion=f'Cuenta {cuenta_str} fuera de rango {cuenta_raiz}', matched=False
            )
    
    # Evaluar patrones en orden de prioridad
    for palabras_clave, formato, columna, concepto, descripcion in PATRONES_IVA:
        if all(palabra in nombre_upper for palabra in palabras_clave):
            return ResultadoDeteccionIVA(
                formato=formato,
                columna=columna,
                concepto=concepto,
                descripcion=descripcion,
                matched=True
            )
    
    # Si llegamos aquí, no matcheó ningún patrón
    # Inferir por naturaleza si tenemos saldos
    if creditos > debitos and creditos > 0:
        return ResultadoDeteccionIVA(
            formato='1006',
            columna='GENERADO_INFERIDO',
            concepto=None,
            descripcion=f'⚠ IVA inferido por naturaleza Cr (revisar manualmente)',
            matched=True
        )
    if debitos > creditos and debitos > 0:
        return ResultadoDeteccionIVA(
            formato='1005',
            columna='DESCONTABLE_INFERIDO',
            concepto=None,
            descripcion=f'⚠ IVA inferido por naturaleza Db (revisar manualmente)',
            matched=True
        )
    
    return ResultadoDeteccionIVA(
        formato=None, columna=None, concepto=None,
        descripcion=f'❓ Cuenta {cuenta_str} "{nombre}" no clasificable',
        matched=False
    )


# =============================================================================
# Tests
# =============================================================================

def test_iva_generado():
    r = detectar_rol_iva('240805', 'IVA GENERADO')
    assert r.formato == '1006'
    assert r.columna == 'GENERADO'
    print('✅ test_iva_generado')


def test_iva_descontable():
    r = detectar_rol_iva('240810', 'IVA DESCONTABLE')
    assert r.formato == '1005'
    assert r.columna == 'DESCONTABLE'
    print('✅ test_iva_descontable')


def test_iva_dev_compras():
    r = detectar_rol_iva('240811', 'IVA DEV EN COMPRAS')
    assert r.formato == '1006'
    assert r.columna == 'DEV_COMPRA'
    print('✅ test_iva_dev_compras')


def test_iva_dev_compras_19():
    r = detectar_rol_iva('24081109', 'IVA DEV EN COMPRAS 19%')
    assert r.formato == '1006'
    assert r.columna == 'DEV_COMPRA'
    print('✅ test_iva_dev_compras_19')


def test_reteiva():
    r = detectar_rol_iva('240825', 'RETEIVA')
    assert r.formato == '1003'
    assert r.concepto == '1309'
    print('✅ test_reteiva')


def test_reteiva_variantes():
    for nombre in ['RET IVA', 'RETENCION IVA', 'RETENCION DE IVA', 'RET. IVA']:
        r = detectar_rol_iva('240825', nombre)
        assert r.formato == '1003', f"Falló con '{nombre}': {r}"
    print('✅ test_reteiva_variantes')


def test_traslados():
    r = detectar_rol_iva('240899', 'TRASLADOS DE IVA')
    assert r.formato is None
    assert r.columna == 'NO_REPORTAR'
    print('✅ test_traslados')


def test_descontable_servicios():
    """Cuenta auxiliar de Quinto Sentido"""
    r = detectar_rol_iva('24081008', 'IVA DESCONTABLE SERVICIOS 19%')
    assert r.formato == '1005'
    assert r.columna == 'DESCONTABLE'
    print('✅ test_descontable_servicios')


def test_dev_compras_5():
    """Variante con porcentaje"""
    r = detectar_rol_iva('24081106', 'IVA DEV EN COMPRAS 5%')
    assert r.formato == '1006'
    assert r.columna == 'DEV_COMPRA'
    print('✅ test_dev_compras_5')


def test_devolucion_completa():
    """Variante completa: 'DEVOLUCION'"""
    r = detectar_rol_iva('240811', 'IVA DEVOLUCION COMPRAS 19%')
    assert r.formato == '1006'
    assert r.columna == 'DEV_COMPRA'
    print('✅ test_devolucion_completa')


def test_inc():
    r = detectar_rol_iva('236801', 'IMPUESTO AL CONSUMO', cuenta_raiz=None)
    assert r.formato == '1006'
    assert r.columna == 'INC'
    print('✅ test_inc')


def test_otra_empresa_codigo_distinto():
    """Empresa con código de cuenta totalmente distinto pero mismo nombre"""
    r = detectar_rol_iva('408010', 'IVA GENERADO 19%', cuenta_raiz=None)
    assert r.formato == '1006'
    assert r.columna == 'GENERADO'
    print('✅ test_otra_empresa_codigo_distinto')


def test_iva_inferido_naturaleza():
    """Si nombre es ambiguo pero naturaleza es clara"""
    r = detectar_rol_iva('240850', 'IVA OTROS', creditos=1000000, debitos=0)
    assert r.formato == '1006'
    assert 'inferido' in r.descripcion.lower()
    print('✅ test_iva_inferido_naturaleza')


def test_sin_clasificar():
    """Cuenta sin nombre claro y sin saldos"""
    r = detectar_rol_iva('240899', 'OTRO')
    assert not r.matched or r.columna == 'NO_REPORTAR' or 'inferido' in r.descripcion.lower()
    print('✅ test_sin_clasificar')


if __name__ == '__main__':
    print('Ejecutando tests del detector IVA...\n')
    test_iva_generado()
    test_iva_descontable()
    test_iva_dev_compras()
    test_iva_dev_compras_19()
    test_reteiva()
    test_reteiva_variantes()
    test_traslados()
    test_descontable_servicios()
    test_dev_compras_5()
    test_devolucion_completa()
    test_inc()
    test_otra_empresa_codigo_distinto()
    test_iva_inferido_naturaleza()
    test_sin_clasificar()
    print('\n🎉 Todos los tests pasaron')
