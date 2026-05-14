"""
Test end-to-end FINAL: los 11 formatos generados como Excel + XMLs
para Quinto Sentido SAS con datos reales (incluye PILA simulada para F2276).
"""
import sys
from pathlib import Path
from datetime import datetime, date

sys.path.insert(0, '.')
sys.path.insert(0, 'core/exogena')

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
    construir_nombre_archivo, guardar_xml,
)
from generador_excel_prevalidador import generar_excel_prevalidador


def validar_xml_xsd(xml_str, fmt):
    xsd = etree.XMLSchema(etree.parse(f'core/exogena/xsd/{fmt}.xsd'))
    doc = etree.fromstring(xml_str.encode('ISO-8859-1'))
    return xsd.validate(doc), xsd.error_log


def t_juridico(nit, raz, dpto='05', mun='001', dir_='CALLE 100 # 10-20 MEDELLIN'):
    return Tercero(nit=nit, tipo_documento=TIPO_DOC_NIT, razon_social=raz,
                   codigo_pais='169', codigo_departamento=dpto, codigo_municipio=mun,
                   direccion=dir_)


def t_natural(cc, nom, apl):
    return Tercero(nit=cc, tipo_documento=TIPO_DOC_CC, primer_nombre=nom, primer_apellido=apl,
                   codigo_pais='169', codigo_departamento='05', codigo_municipio='001')


# ============================================================
# DATOS REALES QUINTO SENTIDO SAS
# ============================================================

INFO_GLOBAL = {
    'ano': 2025,
    'nit_informante': '900533491',
    'razon_informante': 'QUINTO SENTIDO SAS',
    'fecha_generacion': '2026-04-15',
}

# F1001 — Pagos a terceros
regs_f1001 = [
    RegistroF1001(tercero=t_juridico('900380500', 'GRUPO ATOCHA SAS'),
                  concepto=5004, pago_deducible=263_157_894,
                  retencion_renta_practicada=10_526_316,
                  retencion_iva_responsables=5_000_000),
    RegistroF1001(tercero=t_juridico('800067065', 'PROMOTORA MEDICA'),
                  concepto=5002, pago_deducible=248_566_858,
                  retencion_renta_practicada=24_856_686),
    RegistroF1001(tercero=t_juridico('900900900', 'ARRENDADOR LOCAL'),
                  concepto=5005, pago_deducible=120_000_000,
                  retencion_renta_practicada=4_200_000),
]

# F1003 — Retenciones que le practicaron
regs_f1003 = [
    RegistroF1003(tercero=t_juridico('800067065', 'PROMOTORA MEDICA'),
                  concepto=1301, valor_base=100_000_000, retencion=3_500_000),
    RegistroF1003(tercero=t_juridico('900380500', 'GRUPO ATOCHA SAS'),
                  concepto=1306, valor_base=341_796_000, retencion=4_094_892),
]

# F1005 — IVA descontable (cifras reales QS)
regs_f1005 = [
    RegistroF1005(tercero=t_juridico('811000000', 'NOVAVENTA'), iva_descontable=4_510_408),
    RegistroF1005(tercero=t_juridico('900380500', 'GRUPO ATOCHA SAS'), iva_descontable=50_000_000),
    RegistroF1005(tercero=t_juridico('800067065', 'PROMOTORA MEDICA'), iva_descontable=47_227_703),
    RegistroF1005(tercero=t_juridico('900111111', 'OTRO PROVEEDOR'), iva_descontable=5_822_108),
    RegistroF1005(tercero=t_juridico('900222222', 'OTRO MAS'), iva_descontable=96_999_649),
]

# F1006 — IVA generado (cifras reales QS)
regs_f1006 = [
    RegistroF1006(tercero=t_juridico('800067065', 'PROMOTORA MEDICA'), iva_generado=53_628_800),
    RegistroF1006(tercero=t_juridico('900380500', 'SILLA TRES SAS'),
                  iva_generado=64_941_240, iva_dev_compras=27_528_172),
    RegistroF1006(tercero=Tercero(nit='222222222', tipo_documento='43',
                                   razon_social='CUANTIAS MENORES', codigo_pais='169'),
                  iva_generado=35_335_730),
    RegistroF1006(tercero=t_juridico('900100000', 'OTROS CLIENTES'), iva_generado=51_696_643),
    RegistroF1006(tercero=t_juridico('811000000', 'NOVAVENTA'), iva_dev_compras=460_486),
]

# F1007 — Ingresos recibidos
regs_f1007 = [
    RegistroF1007(tercero=t_juridico('800067065', 'PROMOTORA MEDICA'),
                  concepto=4001, ingresos_brutos=282_257_894),
    RegistroF1007(tercero=t_juridico('900380500', 'SILLA TRES SAS'),
                  concepto=4001, ingresos_brutos=341_796_000),
    RegistroF1007(tercero=Tercero(nit='222222222', tipo_documento='43',
                                   razon_social='CUANTIAS MENORES', codigo_pais='169'),
                  concepto=4001, ingresos_brutos=185_977_526),
    RegistroF1007(tercero=t_juridico('900100000', 'OTROS CLIENTES'),
                  concepto=4001, ingresos_brutos=272_087_595),
]

# F1008 — CxC al 31-Dic
regs_f1008 = [
    RegistroF1008(tercero=t_juridico('900380500', 'GRUPO ATOCHA SAS'),
                  concepto=1315, saldo=85_000_000),
    RegistroF1008(tercero=t_juridico('800067065', 'PROMOTORA MEDICA'),
                  concepto=1315, saldo=45_000_000),
]

# F1009 — CxP al 31-Dic (incluye proveedores + aportes SS)
regs_f1009 = [
    RegistroF1009(tercero=t_juridico('900380500', 'GRUPO ATOCHA SAS'),
                  concepto=2201, saldo=120_000_000),
    RegistroF1009(tercero=t_juridico('800067065', 'PROMOTORA MEDICA'),
                  concepto=2201, saldo=85_000_000),
    # Aportes SS (PILA) — concepto 2214
    RegistroF1009(tercero=t_juridico('800173052', 'EPS SURA'),
                  concepto=2214, saldo=2_500_000),
    RegistroF1009(tercero=t_juridico('800253960', 'PROTECCION SA'),
                  concepto=2214, saldo=3_200_000),
]

# F1011 — Declaraciones tributarias (Renta)
regs_f1011 = [
    RegistroF1011(concepto=8001, saldo=2_500_000_000),  # Ingresos brutos
    RegistroF1011(concepto=8002, saldo=1_200_000_000),  # Costos
    RegistroF1011(concepto=8003, saldo=850_000_000),    # Deducciones
]

# F1012 — Cuentas bancarias
regs_f1012 = [
    RegistroF1012(tercero=t_juridico('860001234', 'BANCOLOMBIA SA'),
                  concepto=1110, valor=185_000_000),
    RegistroF1012(tercero=t_juridico('890999999', 'BANCO BOGOTA'),
                  concepto=1110, valor=42_500_000),
]

# F1647 — Ingresos para terceros (típico: facturación a nombre propio, distribución luego)
# Ejemplo: QS recibe pago por colaboración empresarial, transfiere parte a SILLA TRES
dest = TerceroDestino(
    nit='900380500', tipo_documento=TIPO_DOC_NIT,
    razon_social='SILLA TRES SAS', codigo_pais='169',
    codigo_departamento='05', codigo_municipio='001',
    direccion='CALLE 33 # 65-100',
)
regs_f1647 = [
    RegistroF1647(
        tercero=t_juridico('800067065', 'PROMOTORA MEDICA'),
        tercero_destino=dest,
        concepto=4040,
        valor_total=50_000_000,
        valor_ingreso_transferido=25_000_000,
        valor_retencion_transferida=1_250_000,
    ),
]

# F2276 — Rentas de trabajo (datos PILA reales típicos)
regs_f2276 = [
    RegistroF2276(
        entidad_informante=11,
        tipo_doc_beneficiario=TIPO_DOC_CC,
        nit_beneficiario='1037612345',
        primer_apellido='RODRIGUEZ',
        primer_nombre='LAURA',
        codigo_pais='169',
        codigo_departamento='05',
        codigo_municipio='001',
        direccion='CRA 70 # 50-30',
        pagos_salarios=72_000_000,
        cesantias_consignadas=6_000_000,
        total_ingresos_brutos=78_000_000,
        aportes_obligatorios_salud=2_880_000,
        aportes_obligatorios_pension=2_880_000,
        retencion_fuente=3_240_000,
        ingreso_laboral_promedio_6m=6_000_000,
    ),
    RegistroF2276(
        entidad_informante=11,
        tipo_doc_beneficiario=TIPO_DOC_CC,
        nit_beneficiario='71666555',
        primer_apellido='MARTINEZ',
        primer_nombre='ANDRES',
        codigo_pais='169',
        codigo_departamento='05',
        codigo_municipio='001',
        pagos_salarios=54_000_000,
        cesantias_consignadas=4_500_000,
        total_ingresos_brutos=58_500_000,
        aportes_obligatorios_salud=2_160_000,
        aportes_obligatorios_pension=2_160_000,
        retencion_fuente=1_800_000,
        ingreso_laboral_promedio_6m=4_500_000,
    ),
    RegistroF2276(
        entidad_informante=11,
        tipo_doc_beneficiario=TIPO_DOC_CC,
        nit_beneficiario='43987654',
        primer_apellido='GOMEZ',
        primer_nombre='CARMEN',
        codigo_pais='169',
        codigo_departamento='05',
        codigo_municipio='001',
        pagos_honorarios=45_000_000,
        total_ingresos_brutos=45_000_000,
        retencion_fuente=4_950_000,
        ingreso_laboral_promedio_6m=3_750_000,
    ),
]


# ============================================================
# 1) Generar EXCEL maestro con los 11 formatos
# ============================================================

print("="*70)
print("1) GENERAR EXCEL MAESTRO (11 formatos)")
print("="*70)

registros_por_formato = {
    'F1001': {'registros': regs_f1001},
    'F1003': {'registros': regs_f1003},
    'F1005': {'registros': regs_f1005},
    'F1006': {'registros': regs_f1006},
    'F1007': {'registros': regs_f1007},
    'F1008': {'registros': regs_f1008},
    'F1009': {'registros': regs_f1009},
    'F1011': {'registros': regs_f1011},
    'F1012': {'registros': regs_f1012},
    'F1647': {'registros': regs_f1647},
    'F2276': {'registros': regs_f2276},
}

out_xlsx = Path('/tmp/qs_test_final/Exogena_QuintoSentido_AG2025_FINAL.xlsx')
generar_excel_prevalidador(out_xlsx, INFO_GLOBAL, registros_por_formato)
print(f"✅ Excel generado: {out_xlsx.name}")
print(f"   Tamaño: {out_xlsx.stat().st_size:,} bytes")


# ============================================================
# 2) Generar XMLs VALIDADOS contra XSD oficial
# ============================================================

print()
print("="*70)
print("2) GENERAR LOS 11 XMLs VALIDADOS CONTRA XSD OFICIAL")
print("="*70)

generadores = {
    '1001': (generar_xml_f1001, '10', regs_f1001),
    '1003': (generar_xml_f1003,  '7', regs_f1003),
    '1005': (generar_xml_f1005,  '8', regs_f1005),
    '1006': (generar_xml_f1006,  '8', regs_f1006),
    '1007': (generar_xml_f1007,  '9', regs_f1007),
    '1008': (generar_xml_f1008,  '7', regs_f1008),
    '1009': (generar_xml_f1009,  '7', regs_f1009),
    '1011': (generar_xml_f1011,  '6', regs_f1011),
    '1012': (generar_xml_f1012,  '7', regs_f1012),
    '1647': (generar_xml_f1647,  '2', regs_f1647),
    '2276': (generar_xml_f2276,  '4', regs_f2276),
}

xml_dir = Path('/tmp/qs_test_final/xml')
xml_dir.mkdir(parents=True, exist_ok=True)

todos_validos = True
totales = {}
for fmt, (fn, ver, regs) in generadores.items():
    cab = CabeceraXML(
        ano_gravable=2025, formato=fmt, version=ver,
        fecha_envio=datetime(2026,4,15,10,0,0),
        fecha_inicial=date(2025,1,1), fecha_final=date(2025,12,31),
    )
    xml = fn(cab, regs)
    ok, errs = validar_xml_xsd(xml, fmt)
    
    nombre = construir_nombre_archivo(fmt, ver, 2026, '01', 1)
    ruta = xml_dir / nombre
    guardar_xml(xml, ruta)
    
    # Extraer ValorTotal del XML
    doc = etree.fromstring(xml.encode('ISO-8859-1'))
    valor_total = int(doc.find('Cab/ValorTotal').text)
    totales[fmt] = valor_total
    
    estado = '✅' if ok else '❌'
    print(f"  {estado} F{fmt} v.{ver} ({len(regs)} regs, ${valor_total:>15,}) → {nombre}")
    if not ok:
        todos_validos = False
        for e in list(errs)[:3]:
            print(f"     {e}")


# ============================================================
# RESUMEN
# ============================================================

print()
print("="*70)
print("RESUMEN FINAL — QUINTO SENTIDO SAS — AG 2025")
print("="*70)
print(f"📊 Excel maestro:   {out_xlsx.name}")
print(f"📁 XMLs validados:  {len(generadores)} archivos en {xml_dir}/")
print()
print(f"{'Formato':10s} {'Versión':8s} {'Registros':10s} {'Valor':>20s}")
print("-" * 60)
total_general = 0
for fmt, (fn, ver, regs) in generadores.items():
    valor = totales[fmt]
    total_general += valor
    print(f"F{fmt:9s} v.{ver:6s} {len(regs):10d} ${valor:>18,}")
print("-" * 60)
print(f"{'TOTAL':36s} ${total_general:>18,}")
print()
estado_final = '✅ TODOS PASAN' if todos_validos else '❌ HAY FORMATOS QUE FALLAN'
print(f"Estado: {estado_final}")
