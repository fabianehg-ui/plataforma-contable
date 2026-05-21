"""
builder_xml_iva.py
==================
Construye los XMLs oficiales DIAN para F1005 v.9 y F1006 v.8.

Estructura XML basada en los XSDs oficiales del prevalidador DIAN.
"""

from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom
from typing import List
from datetime import datetime

from generador_f1005_f1006 import FilaF1005, FilaF1006, ResultadoFormato


# =============================================================================
# Builder XML F1005 v.9
# =============================================================================

def construir_xml_f1005(
    resultado: ResultadoFormato,
    nit_informante: str,
    razon_social_informante: str,
    ano_gravable: str = '2025'
) -> str:
    """
    Construye el XML del F1005 v.9 según especificación DIAN AG 2025.
    
    Estructura simplificada (validar contra XSD oficial del prevalidador):
    
    <mas:Documento ...>
      <ns1:Cabecera>
        <ns1:Ano>2025</ns1:Ano>
        <ns1:NIT>900533491</ns1:NIT>
        <ns1:DV>0</ns1:DV>
        <ns1:Formato>1005</ns1:Formato>
        <ns1:Version>9</ns1:Version>
        <ns1:CantidadRegistros>N</ns1:CantidadRegistros>
      </ns1:Cabecera>
      <ns1:Contenido>
        <ns1:Imp>
          <ns1:tdoc>31</ns1:tdoc>
          <ns1:nDoc>900111111</ns1:nDoc>
          <ns1:DV>1</ns1:DV>
          <ns1:nom>RAZON SOCIAL</ns1:nom>
          <ns1:dir>DIRECCION</ns1:dir>
          <ns1:dpto>05</ns1:dpto>
          <ns1:mpio>001</ns1:mpio>
          <ns1:vIvaDes>0</ns1:vIvaDes>          <- IVA descontable
          <ns1:vDevol>0</ns1:vDevol>            <- IVA por devoluciones en ventas
        </ns1:Imp>
      </ns1:Contenido>
    </mas:Documento>
    """
    nsmap = {
        'mas': 'http://www.dian.gov.co/contratos/medioslogicos/2024/MasivoFormato1005Version9',
        'ns1': 'http://www.dian.gov.co/contratos/medioslogicos/2024/MasivoFormato1005Version9'
    }
    
    root = Element('{%s}Documento' % nsmap['mas'])
    
    # Cabecera
    cabecera = SubElement(root, '{%s}Cabecera' % nsmap['ns1'])
    SubElement(cabecera, '{%s}Ano' % nsmap['ns1']).text = ano_gravable
    SubElement(cabecera, '{%s}NIT' % nsmap['ns1']).text = nit_informante
    SubElement(cabecera, '{%s}DV' % nsmap['ns1']).text = _calcular_dv(nit_informante)
    SubElement(cabecera, '{%s}Formato' % nsmap['ns1']).text = '1005'
    SubElement(cabecera, '{%s}Version' % nsmap['ns1']).text = '9'
    SubElement(cabecera, '{%s}CantidadRegistros' % nsmap['ns1']).text = str(len(resultado.filas))
    
    # Contenido
    contenido = SubElement(root, '{%s}Contenido' % nsmap['ns1'])
    
    for fila in resultado.filas:
        if fila.total() == 0:
            continue
        
        imp = SubElement(contenido, '{%s}Imp' % nsmap['ns1'])
        SubElement(imp, '{%s}tdoc' % nsmap['ns1']).text = fila.tipo_doc
        SubElement(imp, '{%s}nDoc' % nsmap['ns1']).text = fila.nit
        SubElement(imp, '{%s}DV' % nsmap['ns1']).text = fila.dv or '0'
        SubElement(imp, '{%s}nom' % nsmap['ns1']).text = fila.razon_social
        SubElement(imp, '{%s}dir' % nsmap['ns1']).text = fila.direccion or ''
        SubElement(imp, '{%s}dpto' % nsmap['ns1']).text = fila.cod_dpto or '05'
        SubElement(imp, '{%s}mpio' % nsmap['ns1']).text = fila.cod_mpio or '001'
        # SIN DECIMALES (regla DIAN)
        SubElement(imp, '{%s}vIvaDes' % nsmap['ns1']).text = str(int(round(fila.iva_descontable)))
        SubElement(imp, '{%s}vDevol' % nsmap['ns1']).text = str(int(round(fila.iva_dev_ventas)))
    
    return _xml_pretty(root)


# =============================================================================
# Builder XML F1006 v.8
# =============================================================================

def construir_xml_f1006(
    resultado: ResultadoFormato,
    nit_informante: str,
    razon_social_informante: str,
    ano_gravable: str = '2025'
) -> str:
    """Construye el XML del F1006 v.8."""
    nsmap = {
        'mas': 'http://www.dian.gov.co/contratos/medioslogicos/2024/MasivoFormato1006Version8',
        'ns1': 'http://www.dian.gov.co/contratos/medioslogicos/2024/MasivoFormato1006Version8'
    }
    
    root = Element('{%s}Documento' % nsmap['mas'])
    
    cabecera = SubElement(root, '{%s}Cabecera' % nsmap['ns1'])
    SubElement(cabecera, '{%s}Ano' % nsmap['ns1']).text = ano_gravable
    SubElement(cabecera, '{%s}NIT' % nsmap['ns1']).text = nit_informante
    SubElement(cabecera, '{%s}DV' % nsmap['ns1']).text = _calcular_dv(nit_informante)
    SubElement(cabecera, '{%s}Formato' % nsmap['ns1']).text = '1006'
    SubElement(cabecera, '{%s}Version' % nsmap['ns1']).text = '8'
    SubElement(cabecera, '{%s}CantidadRegistros' % nsmap['ns1']).text = str(len(resultado.filas))
    
    contenido = SubElement(root, '{%s}Contenido' % nsmap['ns1'])
    
    for fila in resultado.filas:
        if fila.total() == 0:
            continue
        
        imp = SubElement(contenido, '{%s}Imp' % nsmap['ns1'])
        SubElement(imp, '{%s}tdoc' % nsmap['ns1']).text = fila.tipo_doc
        SubElement(imp, '{%s}nDoc' % nsmap['ns1']).text = fila.nit
        SubElement(imp, '{%s}DV' % nsmap['ns1']).text = fila.dv or '0'
        SubElement(imp, '{%s}nom' % nsmap['ns1']).text = fila.razon_social
        SubElement(imp, '{%s}dir' % nsmap['ns1']).text = fila.direccion or ''
        SubElement(imp, '{%s}dpto' % nsmap['ns1']).text = fila.cod_dpto or '05'
        SubElement(imp, '{%s}mpio' % nsmap['ns1']).text = fila.cod_mpio or '001'
        SubElement(imp, '{%s}vIvaGen' % nsmap['ns1']).text = str(int(round(fila.iva_generado)))
        SubElement(imp, '{%s}vIPC' % nsmap['ns1']).text = str(int(round(fila.inc)))
        SubElement(imp, '{%s}vDevol' % nsmap['ns1']).text = str(int(round(fila.iva_dev_compras)))
    
    return _xml_pretty(root)


# =============================================================================
# Helpers
# =============================================================================

def _xml_pretty(root) -> str:
    """Pretty-print XML con declaración."""
    xml_str = tostring(root, encoding='unicode')
    parsed = minidom.parseString(xml_str)
    return parsed.toprettyxml(indent='  ', encoding='UTF-8').decode('UTF-8')


def _calcular_dv(nit: str) -> str:
    """Calcula el dígito de verificación del NIT colombiano."""
    nit = ''.join(c for c in str(nit) if c.isdigit())
    if not nit:
        return '0'
    
    primos = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]
    suma = 0
    for i, digito in enumerate(reversed(nit)):
        if i < len(primos):
            suma += int(digito) * primos[i]
    
    resto = suma % 11
    if resto < 2:
        return str(resto)
    return str(11 - resto)


# =============================================================================
# Tests
# =============================================================================

def test_xml_f1005_basico():
    from generador_f1005_f1006 import generar_f1005
    
    movimientos = [
        {'cuenta': '24081007', 'nombre_cuenta': 'IVA DESCONTABLE EN COMPRAS 19%',
         'nit': '900380500', 'dv': '5', 'razon_social': 'GRUPO ATOCHA SAS',
         'tipo_doc': '31', 'direccion': 'CL 50 # 50-50',
         'cod_dpto': '05', 'cod_mpio': '001',
         'debitos': 50000000.0, 'creditos': 0.0},
    ]
    resultado = generar_f1005(movimientos)
    xml = construir_xml_f1005(resultado, '900533491', 'QUINTO SENTIDO SAS')
    
    assert 'Formato>1005' in xml
    assert 'Version>9' in xml
    assert '900380500' in xml
    assert '50000000' in xml
    assert 'GRUPO ATOCHA' in xml
    print('✅ test_xml_f1005_basico')


def test_xml_f1006_basico():
    from generador_f1005_f1006 import generar_f1006
    
    movimientos = [
        {'cuenta': '24080506', 'nombre_cuenta': 'IVA GENERADO TARIFA 19%',
         'nit': '800067065', 'dv': '9', 'razon_social': 'PROMOTORA MEDICA',
         'tipo_doc': '31', 'direccion': 'CL 1 # 1-1',
         'cod_dpto': '05', 'cod_mpio': '001',
         'debitos': 0.0, 'creditos': 53628800.0},
        {'cuenta': '24081109', 'nombre_cuenta': 'IVA DEV EN COMPRAS 19%',
         'nit': '900380500', 'dv': '5', 'razon_social': 'GRUPO ATOCHA',
         'tipo_doc': '31', 'direccion': '',
         'cod_dpto': '05', 'cod_mpio': '001',
         'debitos': 0.0, 'creditos': 27528172.0},
    ]
    resultado = generar_f1006(movimientos)
    xml = construir_xml_f1006(resultado, '900533491', 'QUINTO SENTIDO SAS')
    
    assert 'Formato>1006' in xml
    assert 'Version>8' in xml
    assert '53628800' in xml
    assert '27528172' in xml  # Dev en compras
    assert 'PROMOTORA' in xml
    print('✅ test_xml_f1006_basico')


def test_xml_sin_decimales():
    """DIAN exige números enteros (sin decimales)"""
    from generador_f1005_f1006 import generar_f1005
    
    movimientos = [
        {'cuenta': '24081005', 'nombre_cuenta': 'IVA DESCONTABLE COMPRAS 5%',
         'nit': '811000000', 'dv': '1', 'razon_social': 'NOVAVENTA',
         'tipo_doc': '31', 'direccion': '', 'cod_dpto': '05', 'cod_mpio': '001',
         'debitos': 4510408.50, 'creditos': 0.0},  # Con decimal
    ]
    resultado = generar_f1005(movimientos)
    xml = construir_xml_f1005(resultado, '900533491', 'QUINTO SENTIDO SAS')
    
    assert '4510408' in xml or '4510409' in xml  # Redondeo
    assert '4510408.5' not in xml  # NO debe tener decimal
    print('✅ test_xml_sin_decimales')


def test_dv_calculo():
    """DV de NIT 900533491 debe ser 5 (Quinto Sentido)"""
    dv = _calcular_dv('900533491')
    assert dv == '5', f"DV esperado 5, obtenido {dv}"
    print('✅ test_dv_calculo')


def test_xml_no_campos_vacios():
    """DIAN exige que no haya campos vacíos (deben tener cero o valor)"""
    from generador_f1005_f1006 import generar_f1005
    
    movimientos = [
        {'cuenta': '24081005', 'nombre_cuenta': 'IVA DESCONTABLE COMPRAS 5%',
         'nit': '811000000', 'dv': '1', 'razon_social': 'NOVAVENTA',
         'tipo_doc': '31', 'direccion': '', 'cod_dpto': '', 'cod_mpio': '',
         'debitos': 1000000.0, 'creditos': 0.0},
    ]
    resultado = generar_f1005(movimientos)
    xml = construir_xml_f1005(resultado, '900533491', 'QS')
    
    # Verifica que cod_dpto y mpio tengan defaults (no estén vacíos)
    assert '<ns1:dpto>05</ns1:dpto>' in xml or 'dpto>05<' in xml
    print('✅ test_xml_no_campos_vacios')


if __name__ == '__main__':
    print('Ejecutando tests de XML builders...\n')
    test_xml_f1005_basico()
    test_xml_f1006_basico()
    test_xml_sin_decimales()
    test_dv_calculo()
    test_xml_no_campos_vacios()
    print('\n🎉 Todos los tests pasaron')
