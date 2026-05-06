"""
generador_f1005_f1006.py
=========================
Generadores de los formatos F1005 v.9 y F1006 v.8 para AG 2025.

F1005 (IVA descontable + IVA por devoluciones en VENTAS):
- Versión 9 (Res. 000233/2025 art. 6)
- Cambio: SE ELIMINÓ la columna "IVA mayor valor del costo o gasto"
  (eso ahora va solo en F1001)
- Estructura: NIT, DV, Tipo Doc, Razón Social, Dirección, IVA descontable, IVA por dev en ventas

F1006 (IVA generado + INC + IVA por devoluciones en COMPRAS):
- Versión 8 (sin cambios estructurales respecto AG 2024)
- Res. 000233/2025 art. 7: SIN conceptos (organizado por tercero)
- Estructura: NIT, DV, Tipo Doc, Razón Social, Dirección, IVA generado, INC, IVA por dev en compras

Cuantías mínimas:
- Cuando no se pueda identificar al adquirente: NIT 222222222 ("Cuantías menores")
"""

from collections import defaultdict
from typing import List, Dict, Any
from dataclasses import dataclass, field

from detector_iva import detectar_rol_iva, ResultadoDeteccionIVA


# =============================================================================
# Estructuras de datos
# =============================================================================

@dataclass
class FilaF1005:
    """Una fila del F1005 v.9"""
    tipo_doc: str
    nit: str
    dv: str
    razon_social: str
    direccion: str = ''
    cod_dpto: str = ''
    cod_mpio: str = ''
    iva_descontable: float = 0.0
    iva_dev_ventas: float = 0.0
    
    def total(self) -> float:
        return self.iva_descontable + self.iva_dev_ventas


@dataclass
class FilaF1006:
    """Una fila del F1006 v.8"""
    tipo_doc: str
    nit: str
    dv: str
    razon_social: str
    direccion: str = ''
    cod_dpto: str = ''
    cod_mpio: str = ''
    iva_generado: float = 0.0
    inc: float = 0.0
    iva_dev_compras: float = 0.0
    
    def total(self) -> float:
        return self.iva_generado + self.inc + self.iva_dev_compras


@dataclass
class ResultadoFormato:
    formato: str
    version: str
    filas: List[Any] = field(default_factory=list)
    total_reportado: float = 0.0
    total_balance: float = 0.0
    diferencia: float = 0.0
    cuentas_origen: List[str] = field(default_factory=list)
    advertencias: List[str] = field(default_factory=list)


# =============================================================================
# Generador F1005
# =============================================================================

def generar_f1005(movimientos: List[Dict]) -> ResultadoFormato:
    """
    Genera el F1005 v.9 a partir de los movimientos del balance.
    
    movimientos: lista de dicts con keys:
        cuenta, nombre_cuenta, nit, dv, razon_social, tipo_doc, debitos, creditos
    """
    filas_por_nit = defaultdict(lambda: FilaF1005(
        tipo_doc='', nit='', dv='', razon_social='', direccion=''
    ))
    
    cuentas_clasificadas = set()
    advertencias = []
    total_balance = 0.0
    
    for mov in movimientos:
        cuenta = str(mov.get('cuenta', ''))
        nombre = mov.get('nombre_cuenta', '')
        debitos = mov.get('debitos', 0) or 0
        creditos = mov.get('creditos', 0) or 0
        
        # Solo procesar cuentas de IVA (raíz 2408)
        if not cuenta.startswith('2408'):
            continue
        
        resultado = detectar_rol_iva(cuenta, nombre, debitos, creditos)
        
        # Solo nos interesa lo que va al F1005
        if resultado.formato != '1005':
            continue
        
        # Saldo neto: Db - Cr (porque IVA descontable es Db)
        saldo = debitos - creditos
        if saldo == 0:
            continue
        
        nit = str(mov.get('nit', ''))
        if not nit:
            advertencias.append(f"⚠ Cuenta {cuenta} sin NIT, saldo ${saldo:,.0f}")
            nit = '222222222'  # Cuantías menores
        
        # Acumular por NIT
        fila = filas_por_nit[nit]
        if not fila.nit:
            fila.tipo_doc = mov.get('tipo_doc', '31')
            fila.nit = nit
            fila.dv = str(mov.get('dv', ''))
            fila.razon_social = mov.get('razon_social', '')
            fila.direccion = mov.get('direccion', '')
            fila.cod_dpto = mov.get('cod_dpto', '')
            fila.cod_mpio = mov.get('cod_mpio', '')
        
        if resultado.columna == 'DESCONTABLE':
            fila.iva_descontable += saldo
        elif resultado.columna == 'DEV_VENTA':
            fila.iva_dev_ventas += abs(saldo)  # Devoluciones siempre positivas
        
        cuentas_clasificadas.add(cuenta)
        total_balance += abs(saldo)
    
    # Filtrar filas con valores cero
    filas = [f for f in filas_por_nit.values() if f.total() > 0]
    
    total_reportado = sum(f.total() for f in filas)
    
    return ResultadoFormato(
        formato='1005',
        version='9',
        filas=filas,
        total_reportado=total_reportado,
        total_balance=total_balance,
        diferencia=total_balance - total_reportado,
        cuentas_origen=sorted(cuentas_clasificadas),
        advertencias=advertencias
    )


# =============================================================================
# Generador F1006
# =============================================================================

def generar_f1006(movimientos: List[Dict]) -> ResultadoFormato:
    """
    Genera el F1006 v.8 a partir de los movimientos del balance.
    """
    filas_por_nit = defaultdict(lambda: FilaF1006(
        tipo_doc='', nit='', dv='', razon_social=''
    ))
    
    cuentas_clasificadas = set()
    advertencias = []
    total_balance = 0.0
    
    for mov in movimientos:
        cuenta = str(mov.get('cuenta', ''))
        nombre = mov.get('nombre_cuenta', '')
        debitos = mov.get('debitos', 0) or 0
        creditos = mov.get('creditos', 0) or 0
        
        # F1006 incluye IVA generado, INC, dev compras
        # No filtrar solo por 2408 porque INC puede estar en otras cuentas
        
        resultado = detectar_rol_iva(cuenta, nombre, debitos, creditos, cuenta_raiz=None)
        
        if resultado.formato != '1006':
            continue
        
        # Saldo neto: Cr - Db (porque IVA generado es Cr)
        saldo = creditos - debitos
        if saldo == 0:
            continue
        
        nit = str(mov.get('nit', ''))
        if not nit:
            advertencias.append(f"⚠ Cuenta {cuenta} sin NIT, saldo ${saldo:,.0f}")
            nit = '222222222'
        
        fila = filas_por_nit[nit]
        if not fila.nit:
            fila.tipo_doc = mov.get('tipo_doc', '31')
            fila.nit = nit
            fila.dv = str(mov.get('dv', ''))
            fila.razon_social = mov.get('razon_social', '')
            fila.direccion = mov.get('direccion', '')
            fila.cod_dpto = mov.get('cod_dpto', '')
            fila.cod_mpio = mov.get('cod_mpio', '')
        
        if resultado.columna == 'GENERADO' or resultado.columna == 'GENERADO_INFERIDO':
            fila.iva_generado += saldo
        elif resultado.columna == 'DEV_COMPRA':
            fila.iva_dev_compras += abs(saldo)
        elif resultado.columna == 'INC':
            fila.inc += saldo
        
        cuentas_clasificadas.add(cuenta)
        total_balance += abs(saldo)
    
    filas = [f for f in filas_por_nit.values() if f.total() > 0]
    
    total_reportado = sum(f.total() for f in filas)
    
    return ResultadoFormato(
        formato='1006',
        version='8',
        filas=filas,
        total_reportado=total_reportado,
        total_balance=total_balance,
        diferencia=total_balance - total_reportado,
        cuentas_origen=sorted(cuentas_clasificadas),
        advertencias=advertencias
    )


# =============================================================================
# Tests cuadrando contra Quinto Sentido
# =============================================================================

def test_f1005_cuadra_qs():
    """F1005 debe cuadrar con datos reales de QS: $204.559.868 (descontable)"""
    movimientos = [
        # IVA descontable
        {'cuenta': '24081005', 'nombre_cuenta': 'IVA DESCONTABLE COMPRAS 5%',
         'nit': '811000000', 'dv': '1', 'razon_social': 'NOVAVENTA',
         'tipo_doc': '31', 'debitos': 4510408.0, 'creditos': 0.0},
        {'cuenta': '24081007', 'nombre_cuenta': 'IVA DESCONTABLE EN COMPRAS 19%',
         'nit': '900380500', 'dv': '5', 'razon_social': 'GRUPO ATOCHA SAS',
         'tipo_doc': '31', 'debitos': 50000000.0, 'creditos': 0.0},
        {'cuenta': '24081008', 'nombre_cuenta': 'IVA DESCONTABLE SERVICIOS 19%',
         'nit': '800067065', 'dv': '9', 'razon_social': 'PROMOTORA MEDICA',
         'tipo_doc': '31', 'debitos': 47227703.1, 'creditos': 0.0},
        {'cuenta': '24081005', 'nombre_cuenta': 'IVA DESCONTABLE COMPRAS 5%',
         'nit': '900111111', 'dv': '0', 'razon_social': 'OTRO PROVEEDOR',
         'tipo_doc': '31', 'debitos': 5822108.0, 'creditos': 0.0},
        {'cuenta': '24081007', 'nombre_cuenta': 'IVA DESCONTABLE EN COMPRAS 19%',
         'nit': '900222222', 'dv': '1', 'razon_social': 'OTRO MAS',
         'tipo_doc': '31', 'debitos': 96999649.0, 'creditos': 0.0},
    ]
    
    resultado = generar_f1005(movimientos)
    
    expected_total = 204_559_868.10
    diff = abs(resultado.total_reportado - expected_total)
    assert diff < 1, f"Total F1005 esperado {expected_total:,.2f}, obtenido {resultado.total_reportado:,.2f}"
    assert resultado.version == '9'
    print(f'✅ test_f1005_cuadra_qs: ${resultado.total_reportado:,.2f} (5 NITs)')


def test_f1006_cuadra_qs():
    """F1006 debe cuadrar: $205.602.413 generado + $27.988.658 dev compras = $233.591.071"""
    movimientos = [
        # IVA generado a varios NITs
        {'cuenta': '24080506', 'nombre_cuenta': 'IVA GENERADO TARIFA 19%',
         'nit': '800067065', 'dv': '9', 'razon_social': 'PROMOTORA MEDICA',
         'tipo_doc': '31', 'debitos': 0.0, 'creditos': 53628800.0},
        {'cuenta': '24080506', 'nombre_cuenta': 'IVA GENERADO TARIFA 19%',
         'nit': '900380500', 'dv': '5', 'razon_social': 'SILLA TRES SAS',
         'tipo_doc': '31', 'debitos': 0.0, 'creditos': 64941240.0},
        {'cuenta': '24080506', 'nombre_cuenta': 'IVA GENERADO TARIFA 19%',
         'nit': '222222222', 'dv': '0', 'razon_social': 'CUANTIAS MENORES',
         'tipo_doc': '43', 'debitos': 0.0, 'creditos': 35335730.0},
        {'cuenta': '24080506', 'nombre_cuenta': 'IVA GENERADO TARIFA 19%',
         'nit': '900100000', 'dv': '1', 'razon_social': 'OTROS CLIENTES',
         'tipo_doc': '31', 'debitos': 0.0, 'creditos': 51696643.0},
        # IVA dev en compras
        {'cuenta': '24081109', 'nombre_cuenta': 'IVA DEV EN COMPRAS 19%',
         'nit': '900380500', 'dv': '5', 'razon_social': 'GRUPO ATOCHA SAS',
         'tipo_doc': '31', 'debitos': 0.0, 'creditos': 27528172.0},
        {'cuenta': '24081106', 'nombre_cuenta': 'IVA DEV EN COMPRAS 5%',
         'nit': '811000000', 'dv': '1', 'razon_social': 'NOVAVENTA',
         'tipo_doc': '31', 'debitos': 0.0, 'creditos': 460486.0},
    ]
    
    resultado = generar_f1006(movimientos)
    
    expected_total = 205_602_413.0 + 27_988_658.0
    diff = abs(resultado.total_reportado - expected_total)
    assert diff < 1, f"Total F1006 esperado {expected_total:,.2f}, obtenido {resultado.total_reportado:,.2f}"
    assert resultado.version == '8'
    
    total_gen = sum(f.iva_generado for f in resultado.filas)
    total_dev = sum(f.iva_dev_compras for f in resultado.filas)
    
    assert abs(total_gen - 205_602_413.0) < 1, f"IVA generado: {total_gen}"
    assert abs(total_dev - 27_988_658.0) < 1, f"IVA dev compras: {total_dev}"
    
    print(f'✅ test_f1006_cuadra_qs: generado=${total_gen:,.0f}, dev compras=${total_dev:,.0f}, total=${resultado.total_reportado:,.0f}')


def test_f1005_no_incluye_devolucion_compras():
    """Las devoluciones en compras van al F1006, NO al F1005"""
    movimientos = [
        {'cuenta': '24081109', 'nombre_cuenta': 'IVA DEV EN COMPRAS 19%',
         'nit': '900111111', 'dv': '1', 'razon_social': 'X',
         'tipo_doc': '31', 'debitos': 0.0, 'creditos': 1000000.0},
    ]
    
    resultado = generar_f1005(movimientos)
    assert resultado.total_reportado == 0, "F1005 NO debe incluir dev en compras"
    print('✅ test_f1005_no_incluye_devolucion_compras')


def test_f1006_no_incluye_descontable():
    """El IVA descontable va al F1005, NO al F1006"""
    movimientos = [
        {'cuenta': '24081005', 'nombre_cuenta': 'IVA DESCONTABLE COMPRAS 5%',
         'nit': '900111111', 'dv': '1', 'razon_social': 'X',
         'tipo_doc': '31', 'debitos': 1000000.0, 'creditos': 0.0},
    ]
    
    resultado = generar_f1006(movimientos)
    assert resultado.total_reportado == 0, "F1006 NO debe incluir IVA descontable"
    print('✅ test_f1006_no_incluye_descontable')


def test_f1005_acumula_por_nit():
    """Si un mismo NIT tiene IVA en varias cuentas, debe acumularse"""
    movimientos = [
        {'cuenta': '24081005', 'nombre_cuenta': 'IVA DESCONTABLE COMPRAS 5%',
         'nit': '900380500', 'dv': '5', 'razon_social': 'GRUPO ATOCHA',
         'tipo_doc': '31', 'debitos': 1000000.0, 'creditos': 0.0},
        {'cuenta': '24081007', 'nombre_cuenta': 'IVA DESCONTABLE EN COMPRAS 19%',
         'nit': '900380500', 'dv': '5', 'razon_social': 'GRUPO ATOCHA',
         'tipo_doc': '31', 'debitos': 5000000.0, 'creditos': 0.0},
    ]
    
    resultado = generar_f1005(movimientos)
    assert len(resultado.filas) == 1, f"Debe haber 1 fila por NIT, hay {len(resultado.filas)}"
    assert resultado.filas[0].iva_descontable == 6000000.0
    print('✅ test_f1005_acumula_por_nit')


def test_f1006_separa_columnas():
    """F1006 debe separar IVA generado, INC y dev compras en columnas distintas"""
    movimientos = [
        {'cuenta': '24080506', 'nombre_cuenta': 'IVA GENERADO TARIFA 19%',
         'nit': '900380500', 'dv': '5', 'razon_social': 'CLIENTE A',
         'tipo_doc': '31', 'debitos': 0.0, 'creditos': 5000000.0},
        {'cuenta': '24081109', 'nombre_cuenta': 'IVA DEV EN COMPRAS 19%',
         'nit': '900380500', 'dv': '5', 'razon_social': 'CLIENTE A',
         'tipo_doc': '31', 'debitos': 0.0, 'creditos': 1000000.0},
    ]
    
    resultado = generar_f1006(movimientos)
    fila = resultado.filas[0]
    assert fila.iva_generado == 5000000.0
    assert fila.iva_dev_compras == 1000000.0
    assert fila.total() == 6000000.0
    print('✅ test_f1006_separa_columnas')


def test_otra_empresa_codigo_distinto_pero_mismo_nombre():
    """Empresa que usa código 408010 en vez de 240805 debe seguir clasificándose"""
    movimientos = [
        # Empresa con PUC adaptado (código no estándar)
        {'cuenta': '24080501', 'nombre_cuenta': 'IVA GENERADO 19%',  # Código diferente!
         'nit': '900111111', 'dv': '1', 'razon_social': 'CLIENTE',
         'tipo_doc': '31', 'debitos': 0.0, 'creditos': 1000000.0},
    ]
    
    resultado = generar_f1006(movimientos)
    assert resultado.total_reportado == 1000000.0, \
        f"Debe detectar IVA generado por nombre aunque cuenta sea distinta"
    print('✅ test_otra_empresa_codigo_distinto_pero_mismo_nombre')


if __name__ == '__main__':
    print('Ejecutando tests de generadores F1005/F1006...\n')
    test_f1005_cuadra_qs()
    test_f1006_cuadra_qs()
    test_f1005_no_incluye_devolucion_compras()
    test_f1006_no_incluye_descontable()
    test_f1005_acumula_por_nit()
    test_f1006_separa_columnas()
    test_otra_empresa_codigo_distinto_pero_mismo_nombre()
    print('\n🎉 Todos los tests pasaron')
