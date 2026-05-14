"""
Test del generador_xml_v2 — los 11 formatos del lote total contra XSD oficial DIAN.
"""
import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'core/exogena')

from datetime import datetime, date
from lxml import etree

from generador_xml_v2 import (
    Tercero, TerceroDestino, CabeceraXML,
    TIPO_DOC_NIT, TIPO_DOC_CC, TIPO_DOC_NEX, PAIS_COLOMBIA,
    RegistroF1001, RegistroF1003, RegistroF1005, RegistroF1006, RegistroF1007,
    RegistroF1008, RegistroF1009, RegistroF1011, RegistroF1012,
    RegistroF1647, RegistroF2276,
    generar_xml_f1001, generar_xml_f1003, generar_xml_f1005, generar_xml_f1006,
    generar_xml_f1007, generar_xml_f1008, generar_xml_f1009,
    generar_xml_f1011, generar_xml_f1012, generar_xml_f1647, generar_xml_f2276,
)


def validar(xml, fmt):
    xsd = etree.XMLSchema(etree.parse(f'core/exogena/xsd/{fmt}.xsd'))
    doc = etree.fromstring(xml.encode('ISO-8859-1'))
    if xsd.validate(doc):
        return True, []
    return False, [str(e) for e in xsd.error_log]


def t_juridico(nit, raz, dpto='05', mun='001', dir_='CALLE 100 # 10-20'):
    return Tercero(nit=nit, tipo_documento=TIPO_DOC_NIT, razon_social=raz,
                   codigo_pais='169', codigo_departamento=dpto, codigo_municipio=mun,
                   direccion=dir_)


def t_natural(cc, nom1, apl1):
    return Tercero(nit=cc, tipo_documento=TIPO_DOC_CC, primer_nombre=nom1,
                   primer_apellido=apl1, codigo_pais='169',
                   codigo_departamento='05', codigo_municipio='001')


def cab(fmt='1001', ver='10'):
    return CabeceraXML(ano_gravable=2025, formato=fmt, version=ver,
                       fecha_envio=datetime(2026,4,15,10,0,0),
                       fecha_inicial=date(2025,1,1), fecha_final=date(2025,12,31))


resultados = {}

# ============================================================
# Tests previos (regresión: deben seguir pasando)
# ============================================================
print("="*70)
print("REGRESIÓN — Lote 1 (F1001, F1003, F1005, F1006, F1008, F1011, F1012)")
print("="*70)

# F1001
regs = [RegistroF1001(tercero=t_juridico('900111111','PROV UNO'), concepto=5002,
                       pago_deducible=10_000_000, retencion_renta_practicada=350_000)]
xml = generar_xml_f1001(cab('1001','10'), regs)
ok, errs = validar(xml, '1001')
resultados['F1001'] = ok
print(f"  F1001: {'✅' if ok else '❌'}")
if not ok:
    for e in errs[:2]: print(f"    {e}")

# F1003
regs = [RegistroF1003(tercero=t_juridico('900333333','CLIENTE RET'), concepto=1301,
                       valor_base=100_000_000, retencion=3_500_000)]
xml = generar_xml_f1003(cab('1003','7'), regs)
ok, errs = validar(xml, '1003')
resultados['F1003'] = ok
print(f"  F1003: {'✅' if ok else '❌'}")
if not ok:
    for e in errs[:2]: print(f"    {e}")

# F1005
regs = [RegistroF1005(tercero=t_juridico('900111111','PROV'), iva_descontable=5_000_000)]
xml = generar_xml_f1005(cab('1005','8'), regs)
ok, errs = validar(xml, '1005')
resultados['F1005'] = ok
print(f"  F1005: {'✅' if ok else '❌'}")
if not ok:
    for e in errs[:2]: print(f"    {e}")

# F1006
regs = [RegistroF1006(tercero=t_juridico('800111111','CLIENTE'), iva_generado=8_500_000)]
xml = generar_xml_f1006(cab('1006','8'), regs)
ok, errs = validar(xml, '1006')
resultados['F1006'] = ok
print(f"  F1006: {'✅' if ok else '❌'}")
if not ok:
    for e in errs[:2]: print(f"    {e}")

# F1008
regs = [RegistroF1008(tercero=t_juridico('900333333','DEUDOR'), concepto=1315, saldo=45_000_000)]
xml = generar_xml_f1008(cab('1008','7'), regs)
ok, errs = validar(xml, '1008')
resultados['F1008'] = ok
print(f"  F1008: {'✅' if ok else '❌'}")
if not ok:
    for e in errs[:2]: print(f"    {e}")

# F1011
regs = [RegistroF1011(concepto=8001, saldo=1_500_000_000)]
xml = generar_xml_f1011(cab('1011','6'), regs)
ok, errs = validar(xml, '1011')
resultados['F1011'] = ok
print(f"  F1011: {'✅' if ok else '❌'}")
if not ok:
    for e in errs[:2]: print(f"    {e}")

# F1012
regs = [RegistroF1012(tercero=t_juridico('860001234','BANCO'), concepto=1110, valor=85_000_000)]
xml = generar_xml_f1012(cab('1012','7'), regs)
ok, errs = validar(xml, '1012')
resultados['F1012'] = ok
print(f"  F1012: {'✅' if ok else '❌'}")
if not ok:
    for e in errs[:2]: print(f"    {e}")


# ============================================================
# Lote 2: F1007, F1009, F1647, F2276
# ============================================================
print()
print("="*70)
print("LOTE 2 — Formatos nuevos (F1007, F1009, F1647, F2276)")
print("="*70)

# F1007 — Ingresos recibidos
regs = [
    RegistroF1007(
        tercero=t_juridico('800111111', 'CLIENTE UNO'),
        concepto=4001,
        ingresos_brutos=500_000_000,
        devoluciones_rebajas_descuentos=10_000_000,
    ),
    RegistroF1007(
        tercero=t_juridico('800222222', 'CLIENTE DOS'),
        concepto=4001,
        ingresos_brutos=300_000_000,
    ),
]
xml = generar_xml_f1007(cab('1007','9'), regs)
ok, errs = validar(xml, '1007')
resultados['F1007'] = ok
print(f"  F1007: {'✅' if ok else '❌'}")
if not ok:
    for e in errs[:3]: print(f"    {e}")
    print(f"  XML: {xml[:500]}")

# F1009 — CxP al 31-Dic
regs = [
    RegistroF1009(tercero=t_juridico('900333333', 'PROVEEDOR'), concepto=2201, saldo=85_000_000),
    RegistroF1009(tercero=t_juridico('900444444', 'OTRO PROV'), concepto=2214, saldo=12_500_000),
    RegistroF1009(tercero=t_natural('80123456','PEDRO','GOMEZ'), concepto=2201, saldo=2_300_000),
]
xml = generar_xml_f1009(cab('1009','7'), regs)
ok, errs = validar(xml, '1009')
resultados['F1009'] = ok
print(f"  F1009: {'✅' if ok else '❌'}")
if not ok:
    for e in errs[:3]: print(f"    {e}")
    print(f"  XML: {xml[:500]}")

# F1647 — Ingresos para terceros
dest = TerceroDestino(
    nit='900111111', tipo_documento=TIPO_DOC_NIT,
    razon_social='TERCERO DESTINO SAS',
    codigo_pais='169', codigo_departamento='05', codigo_municipio='001',
    direccion='CALLE 50 # 20-30',
)
regs = [
    RegistroF1647(
        tercero=t_juridico('800111111', 'QUIEN PAGA'),
        tercero_destino=dest,
        concepto=4040,
        valor_total=100_000_000,
        valor_ingreso_transferido=95_000_000,
        valor_retencion_transferida=2_500_000,
    ),
]
xml = generar_xml_f1647(cab('1647','2'), regs)
ok, errs = validar(xml, '1647')
resultados['F1647'] = ok
print(f"  F1647: {'✅' if ok else '❌'}")
if not ok:
    for e in errs[:3]: print(f"    {e}")
    print(f"  XML: {xml[:600]}")

# F2276 — Rentas de trabajo (el más complejo)
regs = [
    RegistroF2276(
        entidad_informante=11,
        tipo_doc_beneficiario=TIPO_DOC_CC,
        nit_beneficiario='1234567890',
        primer_apellido='PEREZ',
        primer_nombre='JUAN',
        codigo_pais='169',
        # Pagos
        pagos_salarios=84_000_000,
        # Cesantías
        cesantias_consignadas=7_000_000,
        # Total
        total_ingresos_brutos=91_000_000,
        # Aportes obligatorios
        aportes_obligatorios_salud=3_360_000,
        aportes_obligatorios_pension=3_360_000,
        # Retención
        retencion_fuente=4_500_000,
        # Promedio últimos 6m
        ingreso_laboral_promedio_6m=7_000_000,
    ),
    RegistroF2276(
        entidad_informante=11,
        tipo_doc_beneficiario=TIPO_DOC_CC,
        nit_beneficiario='9876543210',
        primer_apellido='GOMEZ',
        primer_nombre='MARIA',
        codigo_pais='169',
        pagos_honorarios=45_000_000,
        total_ingresos_brutos=45_000_000,
        retencion_fuente=4_950_000,
        ingreso_laboral_promedio_6m=3_750_000,
    ),
]
xml = generar_xml_f2276(cab('2276','4'), regs)
ok, errs = validar(xml, '2276')
resultados['F2276'] = ok
print(f"  F2276: {'✅' if ok else '❌'}")
if not ok:
    for e in errs[:5]: print(f"    {e}")
    print(f"  XML: {xml[:800]}")


# ============================================================
# RESUMEN
# ============================================================
print()
print("="*70)
print("RESUMEN")
print("="*70)
orden = ['F1001','F1003','F1005','F1006','F1007','F1008','F1009','F1011','F1012','F1647','F2276']
for fmt in orden:
    if fmt in resultados:
        print(f"  {fmt}: {'✅ VALIDA' if resultados[fmt] else '❌ FALLA'}")
total_ok = sum(resultados.values())
print(f"\n{total_ok}/{len(resultados)} formatos pasan validación XSD OFICIAL DIAN")
if total_ok == len(resultados):
    print("🎉 TODOS LOS 11 FORMATOS PASAN")
