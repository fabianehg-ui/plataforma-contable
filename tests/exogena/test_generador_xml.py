"""
Tests unitarios del generador de XMLs DIAN F1001 y F1003.

Cubre:
  - Cálculo de dígito de verificación NIT
  - Construcción de nombres de archivo
  - Generación de XML F1001 con retenciones por NIT
  - Generación de XML F1003 con valores netos
  - Prevalidador espejo: detección de errores comunes
  - Aplicación de exceso 236555 como menor valor
"""
import unittest
import sys
import os
import xml.etree.ElementTree as ET
from datetime import datetime, date

sys.path.insert(0, os.path.dirname(__file__))
from generador_xml import (
    Tercero,
    RegistroF1001,
    RegistroF1003,
    CabeceraXML,
    ResultadoValidacion,
    TIPO_DOC_NIT,
    TIPO_DOC_CC,
    calcular_dv,
    formatear_entero,
    formatear_fecha,
    formatear_fecha_envio,
    construir_nombre_archivo,
    normalizar_nit,
    generar_xml_f1001,
    generar_xml_f1003,
    construir_registros_f1001,
    construir_registros_f1003,
    prevalidar_f1001,
    prevalidar_f1003,
    generar_y_validar_f1001,
    generar_y_validar_f1003,
)


# ================================================================
# Tests utilidades
# ================================================================

class TestUtilidades(unittest.TestCase):

    def test_calcular_dv_nit_conocidos(self):
        # NITs reales con DV conocido (verificados con algoritmo oficial DIAN)
        self.assertEqual(calcular_dv('890903938'), '8')   # Bancolombia
        self.assertEqual(calcular_dv('899999068'), '1')   # Ecopetrol
        self.assertEqual(calcular_dv('900197268'), '7')   # ejemplo Atocha

    def test_calcular_dv_acepta_con_guiones(self):
        self.assertEqual(calcular_dv('890-903-938'), '8')

    def test_normalizar_nit(self):
        self.assertEqual(normalizar_nit('900.197.268-8'), '9001972688')
        self.assertEqual(normalizar_nit('800123456'), '800123456')
        self.assertEqual(normalizar_nit(None), '')

    def test_formatear_entero_sin_decimales(self):
        self.assertEqual(formatear_entero(1234567.89), '1234568')
        self.assertEqual(formatear_entero(0), '0')
        self.assertEqual(formatear_entero(0.4), '0')
        self.assertEqual(formatear_entero(0.5), '0')   # banker's rounding
        self.assertEqual(formatear_entero(1.5), '2')

    def test_formatear_fecha(self):
        self.assertEqual(formatear_fecha(date(2025, 12, 31)), '2025-12-31')

    def test_construir_nombre_archivo(self):
        nombre = construir_nombre_archivo(
            formato='1001', version='10', ano_envio=2026,
            tipo_envio='01', consecutivo=1
        )
        self.assertEqual(nombre, 'Dmuisca_10011020260100000001.xml')

        nombre = construir_nombre_archivo(
            formato='1003', version='07', ano_envio=2026,
            tipo_envio='01', consecutivo=42
        )
        self.assertEqual(nombre, 'Dmuisca_10030720260100000042.xml')


# ================================================================
# Tests generación XML F1001
# ================================================================

class TestGeneracionF1001(unittest.TestCase):

    def setUp(self):
        self.cab = CabeceraXML(
            ano_gravable=2025,
            formato='1001',
            version='10',
            numero_envio=1,
            fecha_envio=datetime(2026, 4, 15, 10, 0, 0),
            fecha_inicial=date(2025, 1, 1),
            fecha_final=date(2025, 12, 31),
        )

    def test_xml_genera_estructura_basica(self):
        regs = [
            RegistroF1001(
                tercero=Tercero(
                    nit='800123456',
                    tipo_documento=TIPO_DOC_NIT,
                    razon_social='ACME COLOMBIA SAS',
                    codigo_departamento='05',
                    codigo_municipio='001',
                ),
                concepto=5004,
                valor_pago_deducible=1_000_000,
                valor_retencion_renta=25_000,
            ),
        ]
        xml = generar_xml_f1001(self.cab, regs)

        # Validar declaración encoding
        self.assertIn('iso-8859-1', xml.lower())

        # Parsear y validar estructura
        root = ET.fromstring(xml.encode('ISO-8859-1'))
        self.assertEqual(root.tag, '{http://www.dian.gov.co}mas')

        # Cabecera
        cab_el = root.find('{http://www.dian.gov.co}Cab')
        self.assertIsNotNone(cab_el)
        self.assertEqual(cab_el.find('{http://www.dian.gov.co}Ano').text, '2025')
        self.assertEqual(cab_el.find('{http://www.dian.gov.co}Formato').text, '1001')
        self.assertEqual(cab_el.find('{http://www.dian.gov.co}CantReg').text, '1')
        self.assertEqual(cab_el.find('{http://www.dian.gov.co}ValorTotal').text, '1000000')

        # Registro
        pagos = root.find('{http://www.dian.gov.co}pagos')
        self.assertIsNotNone(pagos)
        self.assertEqual(pagos.attrib['tdoc'], '31')
        self.assertEqual(pagos.attrib['nid'], '800123456')
        self.assertEqual(pagos.attrib['rs'], 'ACME COLOMBIA SAS')
        self.assertEqual(pagos.attrib['cpt'], '5004')
        self.assertEqual(pagos.attrib['vpd'], '1000000')
        self.assertEqual(pagos.attrib['vrfte'], '25000')

    def test_xml_calcula_dv_automaticamente(self):
        regs = [
            RegistroF1001(
                tercero=Tercero(
                    nit='900197268',
                    tipo_documento=TIPO_DOC_NIT,
                    razon_social='ATOCHA',
                ),
                concepto=5004,
                valor_pago_deducible=100_000,
            ),
        ]
        xml = generar_xml_f1001(self.cab, regs)
        root = ET.fromstring(xml.encode('ISO-8859-1'))
        pagos = root.find('{http://www.dian.gov.co}pagos')
        # DV calculado con algoritmo oficial DIAN para NIT 900197268
        self.assertEqual(pagos.attrib['dv'], '7')

    def test_xml_persona_natural_sin_razon_social(self):
        regs = [
            RegistroF1001(
                tercero=Tercero(
                    nit='71234567',
                    tipo_documento=TIPO_DOC_CC,
                    primer_apellido='GARCÍA',
                    segundo_apellido='LÓPEZ',
                    primer_nombre='JUAN',
                    otros_nombres='CARLOS',
                ),
                concepto=5004,
                valor_pago_deducible=500_000,
            ),
        ]
        xml = generar_xml_f1001(self.cab, regs)
        root = ET.fromstring(xml.encode('ISO-8859-1'))
        pagos = root.find('{http://www.dian.gov.co}pagos')
        self.assertEqual(pagos.attrib['pa'], 'GARCÍA')
        self.assertEqual(pagos.attrib['pn'], 'JUAN')
        self.assertNotIn('rs', pagos.attrib)
        # CC no lleva DV
        self.assertNotIn('dv', pagos.attrib)

    def test_xml_valores_son_enteros_sin_decimales(self):
        regs = [
            RegistroF1001(
                tercero=Tercero(nit='800123456', tipo_documento=TIPO_DOC_NIT,
                                razon_social='ACME'),
                concepto=5004,
                valor_pago_deducible=1234567.89,  # con decimales
                valor_retencion_renta=12345.99,
            ),
        ]
        xml = generar_xml_f1001(self.cab, regs)
        root = ET.fromstring(xml.encode('ISO-8859-1'))
        pagos = root.find('{http://www.dian.gov.co}pagos')
        # Sin decimales, sin separadores
        self.assertEqual(pagos.attrib['vpd'], '1234568')
        self.assertEqual(pagos.attrib['vrfte'], '12346')
        # Y NO debe contener punto ni coma
        self.assertNotIn('.', pagos.attrib['vpd'])
        self.assertNotIn(',', pagos.attrib['vpd'])

    def test_xml_no_tiene_campos_vacios(self):
        """DIAN no acepta campos vacíos — verificamos que cero se reporte como '0'."""
        regs = [
            RegistroF1001(
                tercero=Tercero(nit='800123456', tipo_documento=TIPO_DOC_NIT,
                                razon_social='ACME'),
                concepto=5004,
                valor_pago_deducible=1_000_000,
                # otros valores quedan en 0 por defecto
            ),
        ]
        xml = generar_xml_f1001(self.cab, regs)
        root = ET.fromstring(xml.encode('ISO-8859-1'))
        pagos = root.find('{http://www.dian.gov.co}pagos')
        # Los campos de valor deben existir y ser '0', NO vacíos
        self.assertEqual(pagos.attrib['vpnd'], '0')
        self.assertEqual(pagos.attrib['vivamc'], '0')
        self.assertEqual(pagos.attrib['vrfte'], '0')
        self.assertEqual(pagos.attrib['vriva'], '0')
        # Ningún atributo debe ser cadena vacía
        for k, v in pagos.attrib.items():
            self.assertNotEqual(v, '', f'Atributo {k} está vacío')


# ================================================================
# Tests F1003
# ================================================================

class TestGeneracionF1003(unittest.TestCase):

    def setUp(self):
        self.cab = CabeceraXML(
            ano_gravable=2025,
            formato='1003',
            version='7',
            fecha_envio=datetime(2026, 4, 15),
        )

    def test_xml_f1003_estructura(self):
        regs = [
            RegistroF1003(
                tercero=Tercero(
                    nit='800123456',
                    tipo_documento=TIPO_DOC_NIT,
                    razon_social='CLIENTE QUE RETUVO',
                ),
                concepto=1306,  # compras
                valor_base_retencion=10_000_000,
                valor_retencion=250_000,
            ),
        ]
        xml = generar_xml_f1003(self.cab, regs)
        root = ET.fromstring(xml.encode('ISO-8859-1'))

        cab = root.find('{http://www.dian.gov.co}Cab')
        self.assertEqual(cab.find('{http://www.dian.gov.co}Formato').text, '1003')
        self.assertEqual(cab.find('{http://www.dian.gov.co}ValorTotal').text, '250000')

        rets = root.find('{http://www.dian.gov.co}rets')
        self.assertEqual(rets.attrib['cpt'], '1306')
        self.assertEqual(rets.attrib['pago'], '10000000')
        self.assertEqual(rets.attrib['rfte'], '250000')


# ================================================================
# Tests construcción de registros desde motor
# ================================================================

class _MovMock:
    """Mock simple de MovimientoClasificado para tests sin importar el motor."""
    def __init__(self, formato_dian, concepto_dian, nit, valor):
        self.formato_dian = formato_dian
        self.concepto_dian = concepto_dian
        self.nit = nit
        self.valor = valor


class _RetMock:
    """Mock simple de RetencionAcumulada."""
    def __init__(self, f1001=0, f2276=0, exceso=0):
        self.f1001_retencion_practicada = f1001
        self.f2276_retencion_salarios = f2276
        self.exceso_periodos_anteriores = exceso


class TestConstruccionRegistros(unittest.TestCase):

    def test_agrupa_por_nit_concepto(self):
        movs = [
            _MovMock('1001', 5004, '800123456', 100_000),
            _MovMock('1001', 5004, '800123456', 50_000),  # mismo NIT+concepto: agrupa
            _MovMock('1001', 5001, '800123456', 200_000), # mismo NIT, otro concepto
            _MovMock('1001', 5004, '900111222', 80_000),  # otro NIT
        ]
        terceros = {
            '800123456': Tercero(nit='800123456', tipo_documento='31', razon_social='A'),
            '900111222': Tercero(nit='900111222', tipo_documento='31', razon_social='B'),
        }
        regs = construir_registros_f1001(movs, terceros, retenciones_por_nit={})
        self.assertEqual(len(regs), 3)
        # Verificar el agrupado
        reg_a_5004 = next(r for r in regs
                          if r.tercero.nit == '800123456' and r.concepto == 5004)
        self.assertEqual(reg_a_5004.valor_pago_deducible, 150_000)

    def test_aplica_retencion_proporcional_por_nit(self):
        movs = [
            _MovMock('1001', 5004, '800123456', 600_000),
            _MovMock('1001', 5001, '800123456', 400_000),
        ]
        terceros = {
            '800123456': Tercero(nit='800123456', tipo_documento='31', razon_social='A'),
        }
        retenciones = {
            '800123456': _RetMock(f1001=100_000),  # $100k de retención total
        }
        regs = construir_registros_f1001(movs, terceros, retenciones)
        self.assertEqual(len(regs), 2)
        # 60% para concepto 5004, 40% para 5001
        reg_5004 = next(r for r in regs if r.concepto == 5004)
        reg_5001 = next(r for r in regs if r.concepto == 5001)
        self.assertEqual(reg_5004.valor_retencion_renta, 60_000)
        self.assertEqual(reg_5001.valor_retencion_renta, 40_000)

    def test_aplica_exceso_236555_como_menor_valor(self):
        movs = [
            _MovMock('1001', 5004, '800123456', 1_000_000),
        ]
        terceros = {
            '800123456': Tercero(nit='800123456', tipo_documento='31', razon_social='A'),
        }
        retenciones = {
            '800123456': _RetMock(f1001=100_000, exceso=20_000),
        }
        regs = construir_registros_f1001(movs, terceros, retenciones)
        # Retención neta: 100k - 20k (exceso) = 80k
        self.assertEqual(regs[0].valor_retencion_renta, 80_000)

    def test_construir_registros_f1003(self):
        movs = [
            _MovMock('1003', 1306, '800123456', 50_000),
            _MovMock('1003', 1306, '800123456', 30_000),  # mismo: agrupa
            _MovMock('1003', 1301, '900222', 100_000),
        ]
        terceros = {
            '800123456': Tercero(nit='800123456', tipo_documento='31', razon_social='A'),
            '900222': Tercero(nit='900222', tipo_documento='31', razon_social='B'),
        }
        regs = construir_registros_f1003(movs, terceros)
        self.assertEqual(len(regs), 2)
        reg_compras = next(r for r in regs if r.concepto == 1306)
        self.assertEqual(reg_compras.valor_retencion, 80_000)


# ================================================================
# Tests prevalidador
# ================================================================

class TestPrevalidador(unittest.TestCase):

    def test_f1001_detecta_dv_incorrecto(self):
        regs = [
            RegistroF1001(
                tercero=Tercero(
                    nit='900197268',
                    tipo_documento='31',
                    razon_social='X',
                    digito_verificacion='3',  # incorrecto, real es 8
                ),
                concepto=5004,
                valor_pago_deducible=100_000,
            ),
        ]
        res = prevalidar_f1001(regs)
        self.assertFalse(res.es_valido)
        codigos = [e['codigo'] for e in res.errores]
        self.assertIn('F1001-E003', codigos)

    def test_f1001_detecta_concepto_invalido(self):
        regs = [
            RegistroF1001(
                tercero=Tercero(nit='800123456', tipo_documento='31', razon_social='A'),
                concepto=9999,  # fuera de 5001-5099
                valor_pago_deducible=100_000,
            ),
        ]
        res = prevalidar_f1001(regs)
        self.assertFalse(res.es_valido)
        codigos = [e['codigo'] for e in res.errores]
        self.assertIn('F1001-E004', codigos)

    def test_f1001_detecta_tipo_doc_invalido(self):
        regs = [
            RegistroF1001(
                tercero=Tercero(nit='800123456', tipo_documento='99', razon_social='A'),
                concepto=5004,
                valor_pago_deducible=100_000,
            ),
        ]
        res = prevalidar_f1001(regs)
        self.assertFalse(res.es_valido)

    def test_f1001_detecta_persona_juridica_sin_razon_social(self):
        regs = [
            RegistroF1001(
                tercero=Tercero(nit='800123456', tipo_documento='31', razon_social=None),
                concepto=5004,
                valor_pago_deducible=100_000,
            ),
        ]
        res = prevalidar_f1001(regs)
        self.assertFalse(res.es_valido)

    def test_f1001_advertencia_sin_localizacion(self):
        regs = [
            RegistroF1001(
                tercero=Tercero(nit='800123456', tipo_documento='31', razon_social='A',
                                codigo_pais='169'),
                concepto=5004,
                valor_pago_deducible=100_000,
            ),
        ]
        res = prevalidar_f1001(regs)
        codigos_adv = [a['codigo'] for a in res.advertencias]
        self.assertIn('F1001-A003', codigos_adv)

    def test_f1001_caso_valido_completo(self):
        regs = [
            RegistroF1001(
                tercero=Tercero(
                    nit='900197268',
                    tipo_documento='31',
                    razon_social='ATOCHA',
                    digito_verificacion='7',  # DV correcto calculado
                    codigo_departamento='05',
                    codigo_municipio='001',
                ),
                concepto=5004,
                valor_pago_deducible=1_000_000,
                valor_retencion_renta=25_000,
            ),
        ]
        res = prevalidar_f1001(regs)
        self.assertTrue(res.es_valido)
        self.assertEqual(len(res.errores), 0)

    def test_f1003_detecta_concepto_fuera_rango(self):
        regs = [
            RegistroF1003(
                tercero=Tercero(nit='800123456', tipo_documento='31', razon_social='A'),
                concepto=5004,  # rango F1001, no F1003
                valor_retencion=100_000,
            ),
        ]
        res = prevalidar_f1003(regs)
        self.assertFalse(res.es_valido)

    def test_f1003_detecta_retencion_cero(self):
        regs = [
            RegistroF1003(
                tercero=Tercero(nit='800123456', tipo_documento='31', razon_social='A'),
                concepto=1306,
                valor_retencion=0,
            ),
        ]
        res = prevalidar_f1003(regs)
        self.assertFalse(res.es_valido)


# ================================================================
# Test E2E pipeline completo
# ================================================================

class TestPipelineE2E(unittest.TestCase):

    def test_pipeline_f1001_completo(self):
        movs = [
            _MovMock('1001', 5004, '800123456', 1_000_000),
            _MovMock('1001', 5001, '800123456', 500_000),
            _MovMock('1001', 5004, '900222111', 200_000),
        ]
        terceros = {
            '800123456': Tercero(nit='800123456', tipo_documento='31',
                                  razon_social='ACME', codigo_departamento='05',
                                  codigo_municipio='001'),
            '900222111': Tercero(nit='900222111', tipo_documento='31',
                                  razon_social='OTRO', codigo_departamento='11',
                                  codigo_municipio='001'),
        }
        retenciones = {
            '800123456': _RetMock(f1001=30_000, exceso=5_000),  # neta 25k
        }
        cab = CabeceraXML(ano_gravable=2025, formato='1001', version='10')

        xml, validacion, registros = generar_y_validar_f1001(
            cab, movs, terceros, retenciones
        )

        # XML válido
        self.assertIn('iso-8859-1', xml.lower())
        root = ET.fromstring(xml.encode('ISO-8859-1'))
        pagos = root.findall('{http://www.dian.gov.co}pagos')
        self.assertEqual(len(pagos), 3)

        # Validación pasa
        self.assertTrue(validacion.es_valido,
                        f'Errores: {validacion.errores}')

        # Retención repartida correctamente
        # NIT 800123456: total $1.5M, retención neta $25k
        # Concepto 5004: $1M / $1.5M * $25k = $16.667
        # Concepto 5001: $500k / $1.5M * $25k = $8.333
        reg_5004 = next(r for r in registros
                        if r.tercero.nit == '800123456' and r.concepto == 5004)
        reg_5001 = next(r for r in registros
                        if r.tercero.nit == '800123456' and r.concepto == 5001)
        self.assertAlmostEqual(reg_5004.valor_retencion_renta, 16667, delta=1)
        self.assertAlmostEqual(reg_5001.valor_retencion_renta, 8333, delta=1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
