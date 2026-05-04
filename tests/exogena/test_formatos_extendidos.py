"""
Tests para los formatos extendidos F1007, F1008, F1009 y F2276.

Cubre:
  - Generación de XML por formato
  - Pipeline desde motor v2
  - Filtrado de saldos cero (F1008/F1009)
  - Aplicación de retenciones sobre salarios (F2276)
  - Generación masiva de todos los formatos
"""
import unittest
import sys
import os
import xml.etree.ElementTree as ET
from datetime import datetime, date

sys.path.insert(0, os.path.dirname(__file__))

from generador_xml import (
    Tercero, CabeceraXML, TIPO_DOC_NIT, TIPO_DOC_CC,
    RegistroF1007, RegistroF1008, RegistroF1009, RegistroF2276,
    generar_xml_f1007, generar_xml_f1008, generar_xml_f1009, generar_xml_f2276,
    construir_registros_f1007, construir_registros_f1008,
    construir_registros_f1009, construir_registros_f2276,
    prevalidar_f1007, prevalidar_f1008, prevalidar_f1009, prevalidar_f2276,
    generar_y_validar_f1007, generar_y_validar_f1008,
    generar_y_validar_f1009, generar_y_validar_f2276,
    generar_todos_los_formatos, FORMATOS_DISPONIBLES,
)


class _MovMock:
    def __init__(self, formato_dian, concepto_dian, nit, valor):
        self.formato_dian = formato_dian
        self.concepto_dian = concepto_dian
        self.nit = nit
        self.valor = valor


class _RetMock:
    def __init__(self, f1001=0, f2276=0, exceso=0):
        self.f1001_retencion_practicada = f1001
        self.f2276_retencion_salarios = f2276
        self.exceso_periodos_anteriores = exceso


# ================================================================
# F1007 — Ingresos
# ================================================================

class TestF1007(unittest.TestCase):

    def test_xml_estructura_basica(self):
        cab = CabeceraXML(ano_gravable=2025, formato='1007', version='9')
        regs = [
            RegistroF1007(
                tercero=Tercero(nit='800123456', tipo_documento='31',
                                razon_social='CLIENTE A',
                                codigo_departamento='05', codigo_municipio='001'),
                concepto=4001,
                valor_ingreso_bruto=10_000_000,
                valor_devoluciones=500_000,
            ),
        ]
        xml = generar_xml_f1007(cab, regs)
        root = ET.fromstring(xml.encode('ISO-8859-1'))
        ingresos = root.find('{http://www.dian.gov.co}ingresos')
        self.assertIsNotNone(ingresos)
        self.assertEqual(ingresos.attrib['cpt'], '4001')
        self.assertEqual(ingresos.attrib['vbruto'], '10000000')
        self.assertEqual(ingresos.attrib['vdev'], '500000')

    def test_construye_desde_motor_filtra_ceros(self):
        movs = [
            _MovMock('1007', 4001, '800123456', 5_000_000),
            _MovMock('1007', 4001, '800123456', 3_000_000),  # se agrupa
            _MovMock('1007', 4001, '900222', 0),              # debe filtrarse
        ]
        terceros = {
            '800123456': Tercero(nit='800123456', tipo_documento='31', razon_social='A'),
            '900222': Tercero(nit='900222', tipo_documento='31', razon_social='B'),
        }
        regs = construir_registros_f1007(movs, terceros)
        # Solo 1: el de saldo cero se filtró
        self.assertEqual(len(regs), 1)
        self.assertEqual(regs[0].valor_ingreso_bruto, 8_000_000)


# ================================================================
# F1008 — CXC
# ================================================================

class TestF1008(unittest.TestCase):

    def test_solo_terceros_con_saldo(self):
        movs = [
            _MovMock('1008', 1315, '800123456', 1_000_000),  # saldo positivo
            _MovMock('1008', 1315, '900222', 0),              # saldo cero → filtrar
        ]
        terceros = {
            '800123456': Tercero(nit='800123456', tipo_documento='31', razon_social='A'),
            '900222': Tercero(nit='900222', tipo_documento='31', razon_social='B'),
        }
        regs = construir_registros_f1008(movs, terceros)
        self.assertEqual(len(regs), 1)
        self.assertEqual(regs[0].tercero.nit, '800123456')

    def test_xml_usa_valor_absoluto(self):
        cab = CabeceraXML(ano_gravable=2025, formato='1008', version='7')
        regs = [
            RegistroF1008(
                tercero=Tercero(nit='800123456', tipo_documento='31', razon_social='A'),
                concepto=1315,
                valor_saldo=-500_000,  # negativo, pero abs en XML
            ),
        ]
        xml = generar_xml_f1008(cab, regs)
        root = ET.fromstring(xml.encode('ISO-8859-1'))
        cxc = root.find('{http://www.dian.gov.co}cxc')
        self.assertEqual(cxc.attrib['vsaldo'], '500000')


# ================================================================
# F1009 — CXP
# ================================================================

class TestF1009(unittest.TestCase):

    def test_solo_terceros_con_saldo(self):
        movs = [
            _MovMock('1009', 2201, '800123456', -2_000_000),  # acreedor
            _MovMock('1009', 2201, '900222', 0),               # filtrar
        ]
        terceros = {
            '800123456': Tercero(nit='800123456', tipo_documento='31', razon_social='A'),
            '900222': Tercero(nit='900222', tipo_documento='31', razon_social='B'),
        }
        regs = construir_registros_f1009(movs, terceros)
        self.assertEqual(len(regs), 1)
        # Reporta valor absoluto
        cab = CabeceraXML(ano_gravable=2025, formato='1009', version='7')
        xml = generar_xml_f1009(cab, regs)
        root = ET.fromstring(xml.encode('ISO-8859-1'))
        cxp = root.find('{http://www.dian.gov.co}cxp')
        self.assertEqual(cxp.attrib['vsaldo'], '2000000')


# ================================================================
# F2276 — Pagos laborales
# ================================================================

class TestF2276(unittest.TestCase):

    def test_aplica_retenciones_proporcionales(self):
        movs = [
            _MovMock('2276', 5001, '71234567', 12_000_000),  # salario
            _MovMock('2276', 5002, '71234567', 3_000_000),   # bonificación
        ]
        terceros = {
            '71234567': Tercero(nit='71234567', tipo_documento='13',
                                primer_apellido='GARCÍA', primer_nombre='JUAN'),
        }
        retenciones = {
            '71234567': _RetMock(f2276=300_000),
        }
        regs = construir_registros_f2276(movs, terceros, retenciones)
        self.assertEqual(len(regs), 2)
        # 12M / 15M * 300k = 240k para concepto 5001
        # 3M / 15M * 300k = 60k para concepto 5002
        reg_5001 = next(r for r in regs if r.concepto == 5001)
        reg_5002 = next(r for r in regs if r.concepto == 5002)
        self.assertEqual(reg_5001.valor_retencion, 240_000)
        self.assertEqual(reg_5002.valor_retencion, 60_000)

    def test_xml_estructura(self):
        cab = CabeceraXML(ano_gravable=2025, formato='2276', version='4')
        regs = [
            RegistroF2276(
                tercero=Tercero(nit='71234567', tipo_documento='13',
                                primer_apellido='GARCÍA', primer_nombre='JUAN'),
                concepto=5001,
                valor_pago=12_000_000,
                valor_retencion=240_000,
                aportes_obligatorios_salud=480_000,
                aportes_obligatorios_pension=480_000,
            ),
        ]
        xml = generar_xml_f2276(cab, regs)
        root = ET.fromstring(xml.encode('ISO-8859-1'))
        rt = root.find('{http://www.dian.gov.co}rt')
        self.assertEqual(rt.attrib['vpago'], '12000000')
        self.assertEqual(rt.attrib['vrfte'], '240000')
        self.assertEqual(rt.attrib['vaos'], '480000')


# ================================================================
# Prevalidador genérico
# ================================================================

class TestPrevalidadorGenerico(unittest.TestCase):

    def test_f1007_concepto_invalido(self):
        regs = [
            RegistroF1007(
                tercero=Tercero(nit='800123456', tipo_documento='31', razon_social='A'),
                concepto=9999,  # fuera de 4001-4099
                valor_ingreso_bruto=100_000,
            ),
        ]
        res = prevalidar_f1007(regs)
        self.assertFalse(res.es_valido)

    def test_f1008_caso_valido(self):
        regs = [
            RegistroF1008(
                tercero=Tercero(nit='890903938', tipo_documento='31',
                                razon_social='BANCOLOMBIA',
                                digito_verificacion='8',
                                codigo_departamento='05', codigo_municipio='001'),
                concepto=1315,
                valor_saldo=1_000_000,
            ),
        ]
        res = prevalidar_f1008(regs)
        self.assertTrue(res.es_valido)
        self.assertEqual(len(res.errores), 0)


# ================================================================
# Generación masiva
# ================================================================

class TestGeneracionMasiva(unittest.TestCase):

    def test_genera_todos_los_formatos_disponibles(self):
        movs = [
            _MovMock('1001', 5004, '800123456', 1_000_000),
            _MovMock('1003', 1306, '900222', 50_000),
            _MovMock('1007', 4001, '900222', 5_000_000),
            _MovMock('1008', 1315, '900222', 200_000),
            _MovMock('1009', 2201, '800123456', 100_000),
            _MovMock('2276', 5001, '71234567', 12_000_000),
        ]
        terceros = {
            '800123456': Tercero(nit='800123456', tipo_documento='31',
                                  razon_social='A',
                                  codigo_departamento='05', codigo_municipio='001'),
            '900222111': Tercero(nit='900222111', tipo_documento='31',
                                  razon_social='B',
                                  codigo_departamento='05', codigo_municipio='001'),
            '71234567': Tercero(nit='71234567', tipo_documento='13',
                                 primer_apellido='GARCÍA', primer_nombre='JUAN',
                                 codigo_departamento='05', codigo_municipio='001'),
        }
        # Agregar también '900222' para que matchee con _MovMock
        terceros['900222'] = Tercero(nit='900222', tipo_documento='31',
                                       razon_social='C',
                                       codigo_departamento='05', codigo_municipio='001')
        retenciones = {}
        cab = CabeceraXML(ano_gravable=2025, formato='1001', version='10')

        resultados = generar_todos_los_formatos(cab, movs, terceros, retenciones)

        # Cada formato debe haber generado al menos un registro
        self.assertIn('1001', resultados)
        self.assertIn('1003', resultados)
        self.assertIn('1007', resultados)
        self.assertIn('1008', resultados)
        self.assertIn('1009', resultados)
        self.assertIn('2276', resultados)

        # Cada resultado debe tener xml, validacion y registros
        for formato, data in resultados.items():
            self.assertIn('xml', data)
            self.assertIn('validacion', data)
            self.assertIn('registros', data)
            self.assertGreater(len(data['xml']), 100)

    def test_omite_formatos_sin_datos(self):
        # Solo movimientos F1001
        movs = [_MovMock('1001', 5004, '800123456', 1_000_000)]
        terceros = {
            '800123456': Tercero(nit='800123456', tipo_documento='31',
                                  razon_social='A',
                                  codigo_departamento='05', codigo_municipio='001'),
        }
        cab = CabeceraXML(ano_gravable=2025, formato='1001', version='10')
        resultados = generar_todos_los_formatos(cab, movs, terceros, {})

        # Solo debe estar F1001
        self.assertIn('1001', resultados)
        self.assertNotIn('1003', resultados)
        self.assertNotIn('1007', resultados)


if __name__ == '__main__':
    unittest.main(verbosity=2)
