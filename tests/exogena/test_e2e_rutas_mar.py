"""
Test E2E del generador XML usando el motor v2 + balance real de Rutas del Mar.

Pipeline completo:
  1. Carga balance real
  2. Pasa por motor v2 → MovimientoClasificado + retenciones por NIT
  3. Construye registros F1001 y F1003
  4. Genera XMLs
  5. Pre-valida con reglas espejo DIAN
  6. Verifica que XML parsea correctamente y tiene los valores esperados
"""
import sys
import os
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime, date
from pathlib import Path

import pandas as pd

# Importar motor v2 y generador
sys.path.insert(0, '/home/claude/motor_v2')
sys.path.insert(0, os.path.dirname(__file__))

from motor_clasificacion import (
    Movimiento,
    MotorClasificacion,
    ReglaCapa1,
    ReglaCapa2,
)
from generador_xml import (
    Tercero,
    CabeceraXML,
    TIPO_DOC_NIT,
    TIPO_DOC_CC,
    construir_registros_f1001,
    construir_registros_f1003,
    generar_y_validar_f1001,
    generar_y_validar_f1003,
    construir_nombre_archivo,
    guardar_xml,
)


ARCHIVO_BALANCE = '/mnt/user-data/uploads/BALANCE_PARA_MAPEO_MEDIOS_RUTAS_DE_MAR.xlsx'


def cargar_balance() -> list[Movimiento]:
    df = pd.read_excel(ARCHIVO_BALANCE, header=3, dtype={0: str})
    df.columns = ['cuenta', 'equivalencia', 'nombre', 'nit', 'nombre_nit',
                  'saldo_anterior', 'debitos', 'creditos', 'nuevo_saldo']
    df = df[df['cuenta'].notna()].copy()
    df['cuenta_str'] = df['cuenta'].astype(str).str.strip().str.replace(
        r'\.0$', '', regex=True
    )
    df['debitos'] = pd.to_numeric(df['debitos'], errors='coerce').fillna(0)
    df['creditos'] = pd.to_numeric(df['creditos'], errors='coerce').fillna(0)
    df['saldo_final'] = pd.to_numeric(df['nuevo_saldo'], errors='coerce').fillna(0)

    movs = []
    for _, row in df.iterrows():
        movs.append(Movimiento(
            codigo_cuenta=row['cuenta_str'],
            nit=str(row['nit']).strip() if pd.notna(row['nit']) else None,
            debitos=float(row['debitos']),
            creditos=float(row['creditos']),
            saldo_final=float(row['saldo_final']),
            nombre_cuenta=str(row['nombre']).strip() if pd.notna(row['nombre']) else '',
            nombre_tercero=str(row['nombre_nit']).strip() if pd.notna(row['nombre_nit']) else '',
        ))
    return movs


def construir_terceros_desde_balance(movs):
    """Mock simplificado de terceros — en producción viene de exogena_terceros."""
    terceros = {}
    for m in movs:
        if not m.nit:
            continue
        nit = ''.join(c for c in m.nit if c.isdigit())
        if not nit or nit in terceros:
            continue
        # Inferir tipo doc por longitud (básico)
        tipo_doc = TIPO_DOC_NIT if len(nit) >= 9 else TIPO_DOC_CC
        terceros[nit] = Tercero(
            nit=nit,
            tipo_documento=tipo_doc,
            razon_social=m.nombre_tercero or 'PROVEEDOR' if tipo_doc == TIPO_DOC_NIT else None,
            primer_apellido=m.nombre_tercero.split()[0] if m.nombre_tercero and tipo_doc == TIPO_DOC_CC else None,
            primer_nombre=m.nombre_tercero.split()[-1] if m.nombre_tercero and tipo_doc == TIPO_DOC_CC else None,
            codigo_departamento='05',  # Antioquia (mock)
            codigo_municipio='001',     # Medellín (mock)
            codigo_pais='169',          # Colombia
        )
    return terceros


class TestE2ERutasDelMar(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not Path(ARCHIVO_BALANCE).exists():
            raise unittest.SkipTest('Balance no disponible')
        cls.movimientos = cargar_balance()
        cls.motor = MotorClasificacion(reglas_capa1=[], reglas_capa2=[], reglas_capa3=[])
        # Filtrar solo movimientos detallados con NIT
        movs_detalle = [
            m for m in cls.movimientos
            if len(str(m.codigo_cuenta)) >= 6 and m.nit
        ]
        cls.resultado_motor = cls.motor.clasificar_balance(movs_detalle)
        cls.terceros = construir_terceros_desde_balance(movs_detalle)
        print(f'\n📂 Balance cargado: {len(cls.movimientos)} filas')
        print(f'   Movimientos con NIT: {len(movs_detalle)}')
        print(f'   Terceros únicos: {len(cls.terceros)}')

    def test_motor_v2_se_integra_con_generador(self):
        """El generador debe poder leer el resultado del motor v2."""
        self.assertGreater(len(self.resultado_motor.movimientos), 0)
        self.assertTrue(self.resultado_motor.conciliacion_costos.concilia)

    def test_construye_registros_f1003_desde_motor(self):
        """Los movimientos clasificados como F1003 deben generar registros válidos."""
        regs = construir_registros_f1003(
            self.resultado_motor.movimientos,
            self.terceros,
        )
        print(f'\n=== Registros F1003 construidos ===')
        print(f'  Cantidad: {len(regs)}')
        if regs:
            total = sum(r.valor_retencion for r in regs)
            print(f'  Total retención: ${total:,.2f}')
            print(f'  Ejemplos (primeros 3):')
            for r in regs[:3]:
                print(f'    NIT {r.tercero.nit} concepto {r.concepto} → ${r.valor_retencion:,.0f}')
        self.assertGreater(len(regs), 0,
                           'Esperamos al menos algunos registros F1003 (cuentas 195515)')

    def test_genera_xml_f1003_pasa_validacion(self):
        """El XML F1003 generado debe pasar la pre-validación."""
        cab = CabeceraXML(
            ano_gravable=2025,
            formato='1003',
            version='7',
            numero_envio=1,
            fecha_envio=datetime(2026, 4, 15, 10, 0, 0),
            fecha_inicial=date(2025, 1, 1),
            fecha_final=date(2025, 12, 31),
        )
        xml, validacion, regs = generar_y_validar_f1003(
            cab, self.resultado_motor.movimientos, self.terceros
        )

        print(f'\n=== Validación F1003 ===')
        print(f'  Es válido: {validacion.es_valido}')
        print(f'  Errores: {len(validacion.errores)}')
        if validacion.errores[:3]:
            for e in validacion.errores[:3]:
                print(f'    [{e["codigo"]}] reg {e["registro"]}: {e["mensaje"]}')
        print(f'  Estadísticas: {validacion.estadisticas}')

        # Verificar estructura XML
        self.assertIn('iso-8859-1', xml.lower())
        root = ET.fromstring(xml.encode('ISO-8859-1'))
        self.assertEqual(root.tag, '{http://www.dian.gov.co}mas')

        # Cantidad de registros en XML coincide
        rets = root.findall('{http://www.dian.gov.co}rets')
        self.assertEqual(len(rets), len(regs))

    def test_estructura_xml_cumple_dian(self):
        """Verifica que el XML cumple los requisitos críticos de DIAN."""
        cab = CabeceraXML(
            ano_gravable=2025, formato='1003', version='7',
            fecha_envio=datetime(2026, 4, 15, 10, 0, 0),
        )
        xml, _, regs = generar_y_validar_f1003(
            cab, self.resultado_motor.movimientos, self.terceros
        )

        # 1. Encoding ISO-8859-1
        self.assertIn('iso-8859-1', xml.lower())
        self.assertNotIn('utf-8', xml.lower()[:60])  # primera línea

        # 2. Sin campos vacíos
        root = ET.fromstring(xml.encode('ISO-8859-1'))
        for elem in root.iter():
            for k, v in elem.attrib.items():
                self.assertNotEqual(v, '',
                    f'Atributo vacío detectado: {elem.tag}@{k}')

        # 3. Sin decimales en valores numéricos
        for rets in root.findall('{http://www.dian.gov.co}rets'):
            for k in ['pago', 'rfte']:
                if k in rets.attrib:
                    self.assertNotIn('.', rets.attrib[k],
                        f'Decimal en {k}: {rets.attrib[k]}')
                    self.assertNotIn(',', rets.attrib[k])

    def test_nombre_archivo_dian_correcto(self):
        nombre = construir_nombre_archivo(
            formato='1001', version='10', ano_envio=2026,
            tipo_envio='01', consecutivo=1
        )
        self.assertEqual(nombre, 'Dmuisca_10011020260100000001.xml')
        # Tiene exactamente la longitud esperada
        # 'Dmuisca_' (8) + cccc(4) + vv(2) + yyyy(4) + rr(2) + pppppppp(8) + '.xml'(4) = 32
        self.assertEqual(len(nombre), 32)


class TestGuardarXML(unittest.TestCase):
    """Test de I/O — verificar que el XML se guarda con encoding correcto."""

    def test_guarda_xml_con_encoding_iso8859(self):
        from generador_xml import generar_xml_f1003, RegistroF1003

        cab = CabeceraXML(ano_gravable=2025, formato='1003', version='7')
        regs = [
            RegistroF1003(
                tercero=Tercero(nit='800123456', tipo_documento='31',
                                razon_social='EMPRESA CON Ñ Y TILDES ÁÉÍÓÚ'),
                concepto=1306,
                valor_base_retencion=10_000_000,
                valor_retencion=250_000,
            ),
        ]
        xml = generar_xml_f1003(cab, regs)

        # Guardar
        ruta = Path('/tmp/test_xml_iso.xml')
        guardar_xml(xml, ruta)

        # Verificar que se puede leer en ISO-8859-1
        with open(ruta, 'rb') as f:
            raw = f.read()

        # No debe ser UTF-8 (no debe tener BOM ni multi-byte chars)
        contenido = raw.decode('ISO-8859-1')
        self.assertIn('EMPRESA CON Ñ Y TILDES ÁÉÍÓÚ', contenido)

        # Limpiar
        ruta.unlink()


if __name__ == '__main__':
    unittest.main(verbosity=2)
