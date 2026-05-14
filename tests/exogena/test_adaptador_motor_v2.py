"""
Test del adaptador motor → v2:
   - Simula output del motor (MovimientoClasificado + retenciones)
   - Verifica que construir_registros_v2 produce los registros correctos
   - Valida que los XMLs generados con esos registros pasan XSD
"""
import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'core/exogena')

from datetime import datetime, date
from lxml import etree

from motor_clasificacion import (
    MovimientoClasificado, ResultadoClasificacion, RetencionAcumulada,
)
from adaptador_motor_v2 import construir_registros_v2
from generador_xml_v2 import (
    CabeceraXML,
    generar_xml_f1001, generar_xml_f1003, generar_xml_f1005, generar_xml_f1006,
    generar_xml_f1007, generar_xml_f1008, generar_xml_f1009,
    generar_xml_f1011, generar_xml_f1012, generar_xml_f2276,
)


def validar_xml(xml, fmt):
    xsd = etree.XMLSchema(etree.parse(f'core/exogena/xsd/{fmt}.xsd'))
    doc = etree.fromstring(xml.encode('ISO-8859-1'))
    return xsd.validate(doc), list(xsd.error_log)


# ============================================================
# Datos de prueba — simulan output real del motor
# ============================================================

# Maestro de terceros (como lo devuelve la BD de exogena_terceros)
TERCEROS = {
    '900380500': {
        'tipo_documento': 31,
        'razon_social': 'GRUPO ATOCHA SAS',
        'codigo_dpto': '05',
        'codigo_municipio': '001',
        'codigo_pais': '169',
        'direccion': 'CALLE 100 # 10-20',
        'dv': 6,
    },
    '800067065': {
        'tipo_documento': 31,
        'razon_social': 'PROMOTORA MEDICA',
        'codigo_dpto': '05',
        'codigo_municipio': '001',
        'codigo_pais': '169',
        'direccion': 'CALLE 50 # 25-30',
    },
    '811000000': {
        'tipo_documento': 31,
        'razon_social': 'NOVAVENTA',
        'codigo_dpto': '05',
        'codigo_municipio': '001',
        'codigo_pais': '169',
    },
    '1037612345': {  # empleado
        'tipo_documento': 13,
        'primer_apellido': 'RODRIGUEZ',
        'primer_nombre': 'LAURA',
        'codigo_dpto': '05',
        'codigo_municipio': '001',
        'codigo_pais': '169',
    },
}

# Movimientos clasificados — simulan output del motor
movimientos = [
    # F1001 — Pagos
    MovimientoClasificado(
        codigo_cuenta='5135', nit='900380500',
        formato_dian='1001', concepto_dian=5004,
        valor=263_157_894, base_aplicable='deducible',
        capa_resolucion='c1',
    ),
    MovimientoClasificado(
        codigo_cuenta='5140', nit='800067065',
        formato_dian='1001', concepto_dian=5002,
        valor=248_566_858, base_aplicable='deducible',
        capa_resolucion='c1',
    ),
    # F1003 — Retenciones practicadas a la empresa
    MovimientoClasificado(
        codigo_cuenta='1355', nit='800067065',
        formato_dian='1003', concepto_dian=1301,
        valor=3_500_000, base_aplicable='retencion',
        capa_resolucion='c1',
    ),
    # F1005 — IVA descontable
    MovimientoClasificado(
        codigo_cuenta='240805', nit='811000000',
        formato_dian='1005', concepto_dian=None,
        valor=4_510_408, base_aplicable='descontable',
        capa_resolucion='c1',
    ),
    MovimientoClasificado(
        codigo_cuenta='240805', nit='900380500',
        formato_dian='1005', concepto_dian=None,
        valor=50_000_000, base_aplicable='descontable',
        capa_resolucion='c1',
    ),
    # F1006 — IVA generado
    MovimientoClasificado(
        codigo_cuenta='240810', nit='800067065',
        formato_dian='1006', concepto_dian=None,
        valor=53_628_800, base_aplicable='generado',
        capa_resolucion='c1',
    ),
    # F1007 — Ingresos
    MovimientoClasificado(
        codigo_cuenta='4135', nit='800067065',
        formato_dian='1007', concepto_dian=4001,
        valor=282_257_894, base_aplicable='ingresos',
        capa_resolucion='c1',
    ),
    # F1008 — CxC
    MovimientoClasificado(
        codigo_cuenta='1305', nit='900380500',
        formato_dian='1008', concepto_dian=1315,
        valor=85_000_000, base_aplicable='saldo',
        capa_resolucion='c1',
    ),
    # F1009 — CxP
    MovimientoClasificado(
        codigo_cuenta='2205', nit='900380500',
        formato_dian='1009', concepto_dian=2201,
        valor=120_000_000, base_aplicable='saldo',
        capa_resolucion='c1',
    ),
    # F1011 — Declaraciones
    MovimientoClasificado(
        codigo_cuenta='4135', nit=None,
        formato_dian='1011', concepto_dian=8001,
        valor=2_500_000_000, base_aplicable='ingresos_brutos',
        capa_resolucion='c1',
    ),
    # F1012 — Bancos
    MovimientoClasificado(
        codigo_cuenta='1110', nit='860001234',
        formato_dian='1012', concepto_dian=1110,
        valor=185_000_000, base_aplicable='saldo',
        capa_resolucion='c1',
    ),
    # F2276 — Rentas de trabajo
    MovimientoClasificado(
        codigo_cuenta='510503', nit='1037612345',
        formato_dian='2276', concepto_dian=None,
        valor=72_000_000, base_aplicable='salarios',
        capa_resolucion='pila',
    ),
    MovimientoClasificado(
        codigo_cuenta='_pila_f2276', nit='1037612345',
        formato_dian='2276', concepto_dian=None,
        valor=6_000_000, base_aplicable='cesantias_consignadas',
        capa_resolucion='pila',
    ),
    # Movimiento EXCLUIDO (no debe ir a ningún formato)
    MovimientoClasificado(
        codigo_cuenta='6135', nit='900380500',
        formato_dian='', concepto_dian=None,
        valor=999_999, base_aplicable='',
        capa_resolucion='excluido_conciliacion_6_72_73',
    ),
]

# Retenciones 2365 acumuladas por NIT (output del motor)
ret_atocha = RetencionAcumulada(nit='900380500')
ret_atocha.f1001_retencion_practicada = 10_526_316

ret_promotora = RetencionAcumulada(nit='800067065')
ret_promotora.f1001_retencion_practicada = 24_856_686

ret_empleado = RetencionAcumulada(nit='1037612345')
ret_empleado.f2276_retencion_salarios = 3_240_000

retenciones_por_nit = {
    '900380500': ret_atocha,
    '800067065': ret_promotora,
    '1037612345': ret_empleado,
}

# Crear el ResultadoClasificacion
resultado = ResultadoClasificacion(
    movimientos=movimientos,
    sin_resolver=[],
    estadisticas={},
    retenciones_por_nit=retenciones_por_nit,
)


# ============================================================
# TEST 1: Adaptador produce registros válidos
# ============================================================
print("=" * 70)
print("TEST 1: Adaptador motor → v2")
print("=" * 70)

registros = construir_registros_v2(resultado, TERCEROS)

print(f"\nFormatos producidos: {sorted(registros.keys())}")
for fmt in sorted(registros.keys()):
    print(f"  F{fmt}: {len(registros[fmt])} registros")

# Verificaciones
assert '1001' in registros and len(registros['1001']) >= 2, "F1001 debe tener al menos 2 registros"
assert '1005' in registros and len(registros['1005']) == 2, "F1005 debe tener 2 registros"
assert '2276' in registros and len(registros['2276']) == 1, "F2276 debe tener 1 empleado"


# ============================================================
# TEST 2: Retenciones 2365 se asocian al F1001
# ============================================================
print()
print("=" * 70)
print("TEST 2: Retenciones 2365 asociadas a F1001")
print("=" * 70)

f1001_atocha = next(r for r in registros['1001'] if r.tercero.nit == '900380500')
print(f"  F1001 Atocha — retención: ${f1001_atocha.retencion_renta_practicada:,.0f}")
assert f1001_atocha.retencion_renta_practicada == 10_526_316, "Retención Atocha debe ser 10.526.316"

f1001_promotora = next(r for r in registros['1001'] if r.tercero.nit == '800067065')
print(f"  F1001 Promotora — retención: ${f1001_promotora.retencion_renta_practicada:,.0f}")
assert f1001_promotora.retencion_renta_practicada == 24_856_686


# ============================================================
# TEST 3: F2276 con retención y agrupación por empleado
# ============================================================
print()
print("=" * 70)
print("TEST 3: F2276 — empleado con salario + cesantías + retención")
print("=" * 70)

f2276_laura = registros['2276'][0]
print(f"  Empleado: {f2276_laura.primer_apellido} {f2276_laura.primer_nombre}")
print(f"  Salarios: ${f2276_laura.pagos_salarios:,.0f}")
print(f"  Cesantías consignadas: ${f2276_laura.cesantias_consignadas:,.0f}")
print(f"  Total brutos: ${f2276_laura.total_ingresos_brutos:,.0f}")
print(f"  Retención fuente: ${f2276_laura.retencion_fuente:,.0f}")
assert f2276_laura.pagos_salarios == 72_000_000
assert f2276_laura.cesantias_consignadas == 6_000_000
assert f2276_laura.total_ingresos_brutos == 78_000_000
assert f2276_laura.retencion_fuente == 3_240_000


# ============================================================
# TEST 4: Movimientos excluidos NO van a ningún formato
# ============================================================
print()
print("=" * 70)
print("TEST 4: Movimientos excluidos se filtran correctamente")
print("=" * 70)

# El movimiento de la cuenta 6135 estaba excluido — verificar que NO aparece
total_pagos_atocha = sum(r.pago_deducible for r in registros['1001']
                          if r.tercero.nit == '900380500')
print(f"  Total pagos Atocha F1001: ${total_pagos_atocha:,.0f}")
# Solo debería ser el 263.157.894, NO incluir el 999.999 excluido
assert total_pagos_atocha == 263_157_894, "El movimiento excluido no debe contar"
print("  ✅ Movimiento excluido_conciliacion_6_72_73 filtrado correctamente")


# ============================================================
# TEST 5: Los XMLs generados pasan validación XSD
# ============================================================
print()
print("=" * 70)
print("TEST 5: XMLs generados con datos del adaptador pasan XSD")
print("=" * 70)

generadores = {
    '1001': generar_xml_f1001, '1003': generar_xml_f1003,
    '1005': generar_xml_f1005, '1006': generar_xml_f1006,
    '1007': generar_xml_f1007, '1008': generar_xml_f1008,
    '1009': generar_xml_f1009, '1011': generar_xml_f1011,
    '1012': generar_xml_f1012, '2276': generar_xml_f2276,
}
versiones = {'1001':'10', '1003':'7', '1005':'8', '1006':'8',
             '1007':'9', '1008':'7', '1009':'7', '1011':'6',
             '1012':'7', '2276':'4'}

todos_ok = True
for fmt, fn in generadores.items():
    if fmt not in registros:
        continue
    cab = CabeceraXML(
        ano_gravable=2025, formato=fmt, version=versiones[fmt],
        fecha_envio=datetime(2026,4,15,10,0,0),
        fecha_inicial=date(2025,1,1), fecha_final=date(2025,12,31),
    )
    xml = fn(cab, registros[fmt])
    ok, errs = validar_xml(xml, fmt)
    print(f"  F{fmt}: {'✅' if ok else '❌'}", end='')
    if not ok:
        todos_ok = False
        for e in errs[:2]:
            print(f"\n     {e}", end='')
    print()


# ============================================================
# RESUMEN
# ============================================================
print()
print("=" * 70)
print("RESUMEN")
print("=" * 70)
print(f"✅ Adaptador motor → v2 funcional")
print(f"✅ Retenciones 2365 asociadas correctamente")
print(f"✅ F2276 agrupa empleado con salarios + cesantías + retención")
print(f"✅ Movimientos excluidos filtrados")
print(f"{'✅' if todos_ok else '❌'} Todos los XMLs pasan validación XSD oficial DIAN")
