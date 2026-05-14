"""
Test end-to-end con datos reales de Quinto Sentido SAS:
   generar_f1005/f1006 (datos) → RegistroF1005/F1006 → XML → validación XSD oficial.

Esto cierra el ciclo completo: balance → motor de filas → XML válido.
"""
import sys
from pathlib import Path
from datetime import datetime, date

sys.path.insert(0, '.')
sys.path.insert(0, 'core/exogena')

from lxml import etree

from generador_xml import Tercero, CabeceraXML, TIPO_DOC_NIT, TIPO_DOC_CC, construir_nombre_archivo
from generador_xml_extendido import (
    RegistroF1005, RegistroF1006,
    generar_xml_f1005, generar_xml_f1006,
)

from generador_f1005_f1006 import (
    generar_f1005, generar_f1006,
    FilaF1005, FilaF1006,
)


def filaF1005_to_registro(f: FilaF1005) -> RegistroF1005:
    return RegistroF1005(
        tercero=Tercero(
            nit=f.nit,
            tipo_documento=f.tipo_doc or TIPO_DOC_NIT,
            razon_social=f.razon_social,
            digito_verificacion=f.dv or None,
            codigo_pais='169',
        ),
        iva_descontable=f.iva_descontable,
        iva_dev_ventas=f.iva_dev_ventas,
    )


def filaF1006_to_registro(f: FilaF1006) -> RegistroF1006:
    return RegistroF1006(
        tercero=Tercero(
            nit=f.nit,
            tipo_documento=f.tipo_doc or TIPO_DOC_NIT,
            razon_social=f.razon_social,
            digito_verificacion=f.dv or None,
            codigo_pais='169',
        ),
        iva_generado=f.iva_generado,
        iva_dev_compras=f.iva_dev_compras,
        impuesto_consumo=f.inc,
    )


def validar_xsd(xml_str, formato):
    xsd = etree.XMLSchema(etree.parse(f'core/exogena/xsd/{formato}.xsd'))
    doc = etree.fromstring(xml_str.encode('ISO-8859-1'))
    if xsd.validate(doc):
        return True, []
    return False, [str(e) for e in xsd.error_log]


# ============================================================
# DATOS REALES QS (copiados de los tests existentes)
# ============================================================

movs_f1005_qs = [
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

movs_f1006_qs = [
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
    {'cuenta': '24081109', 'nombre_cuenta': 'IVA DEV EN COMPRAS 19%',
     'nit': '900380500', 'dv': '5', 'razon_social': 'GRUPO ATOCHA SAS',
     'tipo_doc': '31', 'debitos': 0.0, 'creditos': 27528172.0},
    {'cuenta': '24081106', 'nombre_cuenta': 'IVA DEV EN COMPRAS 5%',
     'nit': '811000000', 'dv': '1', 'razon_social': 'NOVAVENTA',
     'tipo_doc': '31', 'debitos': 0.0, 'creditos': 460486.0},
]


# ============================================================
# Cabecera estándar AG2025
# ============================================================

cab = CabeceraXML(
    ano_gravable=2025,
    formato='1005',
    version='8',
    numero_envio=1,
    fecha_envio=datetime(2026, 4, 15, 10, 0, 0),
    fecha_inicial=date(2025, 1, 1),
    fecha_final=date(2025, 12, 31),
)


# ============================================================
# F1005 end-to-end
# ============================================================

print("="*70)
print("F1005 — Quinto Sentido SAS (datos reales)")
print("="*70)

res_f1005 = generar_f1005(movs_f1005_qs)
print(f"Filas generadas (motor): {len(res_f1005.filas)}")
print(f"Total reportado (motor): ${res_f1005.total_reportado:,.0f}")
for f in res_f1005.filas:
    print(f"  {f.nit} ({f.razon_social[:25]:25}) → "
          f"desc=${f.iva_descontable:,.0f}, dev=${f.iva_dev_ventas:,.0f}")

# Convertir a registros XML
registros_xml = [filaF1005_to_registro(f) for f in res_f1005.filas]

# Generar XML
xml_f1005 = generar_xml_f1005(cab, registros_xml)
print(f"\nXML generado: {len(xml_f1005)} bytes")

# Validar contra XSD
ok, errs = validar_xsd(xml_f1005, '1005')
if ok:
    print("✅ XML F1005 PASA validación XSD oficial DIAN")
else:
    print("❌ XML F1005 NO valida:")
    for e in errs[:5]:
        print(f"   - {e}")

# Verificar que el total del XML coincide con el motor
doc = etree.fromstring(xml_f1005.encode('ISO-8859-1'))
total_xml = int(doc.find('Cab/ValorTotal').text)
cant_xml = int(doc.find('Cab/CantReg').text)
print(f"\nVerificación XML vs motor:")
print(f"  CantReg (XML):     {cant_xml}")
print(f"  Filas (motor):     {len(res_f1005.filas)}")
print(f"  ValorTotal (XML):  ${total_xml:,}")
print(f"  Total (motor):     ${res_f1005.total_reportado:,.0f}")
assert cant_xml == len(res_f1005.filas), "Cantidad de registros no coincide"

# Nombre de archivo oficial
nombre = construir_nombre_archivo('1005', '8', 2026, '01', 1)
print(f"  Nombre archivo:    {nombre}")


# ============================================================
# F1006 end-to-end
# ============================================================

print()
print("="*70)
print("F1006 — Quinto Sentido SAS (datos reales)")
print("="*70)

res_f1006 = generar_f1006(movs_f1006_qs)
print(f"Filas generadas (motor): {len(res_f1006.filas)}")
print(f"Total reportado (motor): ${res_f1006.total_reportado:,.0f}")
for f in res_f1006.filas:
    print(f"  {f.nit} ({f.razon_social[:25]:25}) → "
          f"gen=${f.iva_generado:,.0f}, dev=${f.iva_dev_compras:,.0f}, inc=${f.inc:,.0f}")

# Convertir y generar XML
registros_xml = [filaF1006_to_registro(f) for f in res_f1006.filas]
xml_f1006 = generar_xml_f1006(cab, registros_xml)
print(f"\nXML generado: {len(xml_f1006)} bytes")

ok, errs = validar_xsd(xml_f1006, '1006')
if ok:
    print("✅ XML F1006 PASA validación XSD oficial DIAN")
else:
    print("❌ XML F1006 NO valida:")
    for e in errs[:5]:
        print(f"   - {e}")

doc = etree.fromstring(xml_f1006.encode('ISO-8859-1'))
total_xml = int(doc.find('Cab/ValorTotal').text)
cant_xml = int(doc.find('Cab/CantReg').text)
print(f"\nVerificación XML vs motor:")
print(f"  CantReg (XML):     {cant_xml}")
print(f"  Filas (motor):     {len(res_f1006.filas)}")
print(f"  ValorTotal (XML):  ${total_xml:,}")
print(f"  Total (motor):     ${res_f1006.total_reportado:,.0f}")

nombre = construir_nombre_archivo('1006', '8', 2026, '01', 1)
print(f"  Nombre archivo:    {nombre}")


# ============================================================
# Guardar XMLs para inspección
# ============================================================

out_dir = Path('/tmp/xml_qs_test')
out_dir.mkdir(exist_ok=True)
(out_dir / construir_nombre_archivo('1005', '8', 2026, '01', 1)).write_bytes(
    xml_f1005.encode('ISO-8859-1'))
(out_dir / construir_nombre_archivo('1006', '8', 2026, '01', 1)).write_bytes(
    xml_f1006.encode('ISO-8859-1'))
print(f"\n📁 XMLs guardados en {out_dir}/")
print(f"   - {construir_nombre_archivo('1005', '8', 2026, '01', 1)}")
print(f"   - {construir_nombre_archivo('1006', '8', 2026, '01', 1)}")
