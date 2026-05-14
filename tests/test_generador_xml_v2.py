"""
Test del generador_xml_v2: los 7 formatos del lote contra XSD oficial DIAN.
"""
import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'core/exogena')

from datetime import datetime, date
from pathlib import Path
from lxml import etree

from generador_xml_v2 import (
    Tercero, CabeceraXML,
    TIPO_DOC_NIT, TIPO_DOC_CC, TIPO_DOC_NEX, PAIS_COLOMBIA,
    RegistroF1001, RegistroF1003, RegistroF1005, RegistroF1006,
    RegistroF1008, RegistroF1011, RegistroF1012,
    generar_xml_f1001, generar_xml_f1003, generar_xml_f1005, generar_xml_f1006,
    generar_xml_f1008, generar_xml_f1011, generar_xml_f1012,
    construir_nombre_archivo,
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


def t_natural(cc, nom1, apl1, dpto='05', mun='001'):
    return Tercero(nit=cc, tipo_documento=TIPO_DOC_CC, primer_nombre=nom1,
                   primer_apellido=apl1, codigo_pais='169',
                   codigo_departamento=dpto, codigo_municipio=mun)


def cab(fmt='1001', ver='10'):
    return CabeceraXML(ano_gravable=2025, formato=fmt, version=ver,
                       fecha_envio=datetime(2026,4,15,10,0,0),
                       fecha_inicial=date(2025,1,1), fecha_final=date(2025,12,31))


resultados = {}

# ============================================================
# F1001
# ============================================================
print("="*70)
print("F1001 — Pagos o abonos en cuenta")
print("="*70)
regs = [
    RegistroF1001(
        tercero=t_juridico('900111111', 'PROVEEDOR UNO SAS'),
        concepto=5002,
        pago_deducible=10_000_000,
        retencion_renta_practicada=350_000,
    ),
    RegistroF1001(
        tercero=t_juridico('900222222', 'PROVEEDOR DOS SAS'),
        concepto=5004,
        pago_deducible=25_000_000,
        retencion_renta_practicada=1_000_000,
        retencion_iva_responsables=475_000,
    ),
]
xml = generar_xml_f1001(cab('1001','10'), regs)
ok, errs = validar(xml, '1001')
print(f"  Resultado: {'✅ VALIDA' if ok else '❌ FALLA'}")
if not ok:
    for e in errs[:3]: print(f"  - {e}")
    print("\n  XML (300 chars):")
    print(xml[:600])
resultados['F1001'] = ok

# ============================================================
# F1003
# ============================================================
print("\n" + "="*70)
print("F1003 — Retenciones que le practicaron")
print("="*70)
regs = [
    RegistroF1003(
        tercero=t_juridico('900333333', 'CLIENTE RETENEDOR SAS'),
        concepto=1301,
        valor_base=100_000_000,
        retencion=3_500_000,
    ),
]
xml = generar_xml_f1003(cab('1003','7'), regs)
ok, errs = validar(xml, '1003')
print(f"  Resultado: {'✅ VALIDA' if ok else '❌ FALLA'}")
if not ok:
    for e in errs[:3]: print(f"  - {e}")
    print("\n  XML (300 chars):")
    print(xml[:600])
resultados['F1003'] = ok

# ============================================================
# F1005
# ============================================================
print("\n" + "="*70)
print("F1005 — IVA descontable")
print("="*70)
regs = [
    RegistroF1005(tercero=t_juridico('900111111','PROVEEDOR UNO'), iva_descontable=5_000_000),
    RegistroF1005(tercero=t_juridico('900222222','PROVEEDOR DOS'), iva_descontable=12_500_000, iva_dev_ventas=350_000),
]
xml = generar_xml_f1005(cab('1005','8'), regs)
ok, errs = validar(xml, '1005')
print(f"  Resultado: {'✅ VALIDA' if ok else '❌ FALLA'}")
if not ok:
    for e in errs[:3]: print(f"  - {e}")
resultados['F1005'] = ok

# ============================================================
# F1006
# ============================================================
print("\n" + "="*70)
print("F1006 — IVA generado")
print("="*70)
regs = [
    RegistroF1006(tercero=t_juridico('800111111','CLIENTE UNO'), iva_generado=8_500_000, iva_dev_compras=100_000),
    RegistroF1006(tercero=t_juridico('800222222','CLIENTE DOS'), iva_generado=22_000_000, impuesto_consumo=450_000),
]
xml = generar_xml_f1006(cab('1006','8'), regs)
ok, errs = validar(xml, '1006')
print(f"  Resultado: {'✅ VALIDA' if ok else '❌ FALLA'}")
if not ok:
    for e in errs[:3]: print(f"  - {e}")
resultados['F1006'] = ok

# ============================================================
# F1008
# ============================================================
print("\n" + "="*70)
print("F1008 — CxC al 31-Dic")
print("="*70)
regs = [
    RegistroF1008(tercero=t_juridico('900333333','DEUDOR UNO'), concepto=1315, saldo=45_000_000),
    RegistroF1008(tercero=t_natural('80123456','PEDRO','GOMEZ'), concepto=1320, saldo=2_300_000),
]
xml = generar_xml_f1008(cab('1008','7'), regs)
ok, errs = validar(xml, '1008')
print(f"  Resultado: {'✅ VALIDA' if ok else '❌ FALLA'}")
if not ok:
    for e in errs[:3]: print(f"  - {e}")
resultados['F1008'] = ok

# ============================================================
# F1011
# ============================================================
print("\n" + "="*70)
print("F1011 — Declaraciones tributarias (agregado)")
print("="*70)
regs = [
    RegistroF1011(concepto=8001, saldo=1_500_000_000),
    RegistroF1011(concepto=8002, saldo=850_000_000),
    RegistroF1011(concepto=8003, saldo=420_000_000),
]
xml = generar_xml_f1011(cab('1011','6'), regs)
ok, errs = validar(xml, '1011')
print(f"  Resultado: {'✅ VALIDA' if ok else '❌ FALLA'}")
if not ok:
    for e in errs[:3]: print(f"  - {e}")
resultados['F1011'] = ok

# ============================================================
# F1012
# ============================================================
print("\n" + "="*70)
print("F1012 — Declaraciones tributarias (con tercero)")
print("="*70)
regs = [
    RegistroF1012(tercero=t_juridico('860001234','BANCO COLOMBIA'), concepto=1110, valor=85_000_000),
    RegistroF1012(tercero=t_juridico('890999999','BANCO BOGOTA'), concepto=1110, valor=12_500_000),
]
xml = generar_xml_f1012(cab('1012','7'), regs)
ok, errs = validar(xml, '1012')
print(f"  Resultado: {'✅ VALIDA' if ok else '❌ FALLA'}")
if not ok:
    for e in errs[:3]: print(f"  - {e}")
resultados['F1012'] = ok


# ============================================================
# RESUMEN
# ============================================================
print("\n" + "="*70)
print("RESUMEN")
print("="*70)
for fmt, ok in resultados.items():
    print(f"  {fmt}: {'✅' if ok else '❌'}")
total_ok = sum(resultados.values())
print(f"\n{total_ok}/{len(resultados)} formatos pasan validación XSD OFICIAL DIAN")
if total_ok == len(resultados):
    print("🎉 TODOS PASAN")
