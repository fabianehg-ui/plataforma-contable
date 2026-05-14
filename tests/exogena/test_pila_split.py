"""
Test integral: PILA con split empleador/trabajador llega correcto a F1001.

Verifica:
   - Movimientos PILA construidos con valor_deducible y valor_no_deducible
   - Adaptador motor→v2 respeta el split y va a las columnas correctas
   - F1001 5010 (parafiscales): solo empleador (no deducible = 0)
   - F1001 5011 (salud+ARL): empleador deducible + trabajador no deducible
   - F1001 5012 (pensión): igual que 5011
   - F1009 2214 (pasivo): se agrega como pasivo al fondo
   - El cot dic se excluye de F1001 (va al F1009)
"""
import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'core/exogena')

from motor_clasificacion import MovimientoClasificado, ResultadoClasificacion, RetencionAcumulada
from integrador_pila import (
    _construir_lineas_f1001_aportes,
    _construir_lineas_f1009_2214,
)
from adaptador_motor_v2 import construir_registros_v2


# ============================================================
# Datos de prueba: Quinto Sentido SAS AG 2025
# ============================================================
# Simulamos movimientos PILA tal como los obtiene el integrador desde BD.

mov_pila = [
    # ene-2025: Aporte SALUD a Sura - 5011
    {
        'concepto_dian': '5011',
        'fondo_nit': '800088702', 'fondo_nombre': 'EPS SURA',
        'fondo_tipo': 'salud',
        'valor_empleador': 850_000, 'valor_trabajador': 500_000,
        'total_obligatorio': 1_350_000,
        'exogena_pila_planillas': {'periodo_cot': '202501'},
    },
    # feb-2025: Aporte SALUD Sura - 5011
    {
        'concepto_dian': '5011',
        'fondo_nit': '800088702', 'fondo_nombre': 'EPS SURA',
        'fondo_tipo': 'salud',
        'valor_empleador': 850_000, 'valor_trabajador': 500_000,
        'total_obligatorio': 1_350_000,
        'exogena_pila_planillas': {'periodo_cot': '202502'},
    },
    # mar-2025: PENSION a Porvenir - 5012
    {
        'concepto_dian': '5012',
        'fondo_nit': '800144331', 'fondo_nombre': 'PORVENIR S.A.',
        'fondo_tipo': 'pension',
        'valor_empleador': 1_200_000, 'valor_trabajador': 600_000,
        'total_obligatorio': 1_800_000,
        'exogena_pila_planillas': {'periodo_cot': '202503'},
    },
    # abr-2025: PARAFISCALES a Comfama (100% empleador) - 5010
    {
        'concepto_dian': '5010',
        'fondo_nit': '890900841', 'fondo_nombre': 'COMFAMA',
        'fondo_tipo': 'caja',
        'valor_empleador': 350_000, 'valor_trabajador': 0,
        'total_obligatorio': 350_000,
        'exogena_pila_planillas': {'periodo_cot': '202504'},
    },
    # dic-2025 (cot 202512): pago en 2026 → PASIVO F1009 2214
    {
        'concepto_dian': '5011',
        'fondo_nit': '800088702', 'fondo_nombre': 'EPS SURA',
        'fondo_tipo': 'salud',
        'valor_empleador': 850_000, 'valor_trabajador': 500_000,
        'total_obligatorio': 1_350_000,
        'exogena_pila_planillas': {'periodo_cot': '202512'},
    },
    {
        'concepto_dian': '5012',
        'fondo_nit': '800144331', 'fondo_nombre': 'PORVENIR S.A.',
        'fondo_tipo': 'pension',
        'valor_empleador': 1_200_000, 'valor_trabajador': 600_000,
        'total_obligatorio': 1_800_000,
        'exogena_pila_planillas': {'periodo_cot': '202512'},
    },
]


print("=" * 70)
print("TEST: Construcción de líneas F1001 desde PILA con split empleador/trabajador")
print("=" * 70)

lineas_f1001 = _construir_lineas_f1001_aportes(mov_pila, 2025)
for l in lineas_f1001:
    print(f"\n  Concepto {l.concepto_dian}, NIT {l.nit}")
    print(f"    Total:               ${l.valor:,.0f}")
    print(f"    Deducible empleador: ${l.valor_deducible or 0:,.0f}")
    print(f"    NO deducible trab:   ${l.valor_no_deducible or 0:,.0f}")

# Verificaciones
assert len(lineas_f1001) == 3, f"Esperaba 3 líneas (5010, 5011, 5012), obtuvo {len(lineas_f1001)}"

# 5011 SALUD: ene + feb = 2 meses × $1,350,000
salud = next(l for l in lineas_f1001 if l.concepto_dian == 5011)
assert salud.valor_deducible == 1_700_000, f"Salud empleador: {salud.valor_deducible}"
assert salud.valor_no_deducible == 1_000_000, f"Salud trabajador: {salud.valor_no_deducible}"
print(f"\n✅ Salud 5011: empleador=${salud.valor_deducible:,.0f}, trabajador=${salud.valor_no_deducible:,.0f}")

# 5012 PENSION: mar = $1,200,000 + $600,000
pension = next(l for l in lineas_f1001 if l.concepto_dian == 5012)
assert pension.valor_deducible == 1_200_000
assert pension.valor_no_deducible == 600_000
print(f"✅ Pensión 5012: empleador=${pension.valor_deducible:,.0f}, trabajador=${pension.valor_no_deducible:,.0f}")

# 5010 PARAFISCALES: 100% empleador
parafiscal = next(l for l in lineas_f1001 if l.concepto_dian == 5010)
assert parafiscal.valor_deducible == 350_000
assert parafiscal.valor_no_deducible == 0
print(f"✅ Parafiscal 5010: empleador=${parafiscal.valor_deducible:,.0f}, trabajador=${parafiscal.valor_no_deducible:,.0f}")


print()
print("=" * 70)
print("TEST: F1009 2214 con pasivo cot dic")
print("=" * 70)

lineas_f1009 = _construir_lineas_f1009_2214(mov_pila, [], 2025)
for l in lineas_f1009:
    print(f"\n  NIT {l.nit}, concepto {l.concepto_dian}")
    print(f"    Valor: ${l.valor:,.0f}")
    print(f"    Nota: {l.nota[:60]}")

# 2 movimientos del cot 202512 → 2 líneas F1009
assert len(lineas_f1009) == 2, f"Esperaba 2 líneas pasivo, obtuvo {len(lineas_f1009)}"
total_pasivo = sum(l.valor for l in lineas_f1009)
assert total_pasivo == 1_350_000 + 1_800_000  # salud + pensión cot dic
print(f"\n✅ F1009 2214: 2 líneas (salud + pensión) total ${total_pasivo:,.0f}")


print()
print("=" * 70)
print("TEST: Adaptador motor→v2 respeta el split en columnas F1001")
print("=" * 70)

# Construir un ResultadoClasificacion con solo PILA F1001
resultado = ResultadoClasificacion(
    movimientos=lineas_f1001 + lineas_f1009,
    sin_resolver=[],
    estadisticas={},
    conciliacion_costos=None,
    retenciones_por_nit={},
)

# Maestro de terceros con los fondos
terceros_dict = {
    '800088702': {'nit': '800088702', 'tipo_documento': 31, 'razon_social': 'EPS SURA',
                  'codigo_pais': '169', 'direccion': 'CALLE 50 # 50-50',
                  'codigo_dpto': '05', 'codigo_municipio': '001'},
    '800144331': {'nit': '800144331', 'tipo_documento': 31, 'razon_social': 'PORVENIR S.A.',
                  'codigo_pais': '169', 'direccion': 'CARRERA 7 # 90-100',
                  'codigo_dpto': '11', 'codigo_municipio': '001'},
    '890900841': {'nit': '890900841', 'tipo_documento': 31, 'razon_social': 'COMFAMA',
                  'codigo_pais': '169', 'direccion': 'CALLE 49 # 50-21',
                  'codigo_dpto': '05', 'codigo_municipio': '001'},
}

registros_v2 = construir_registros_v2(resultado, terceros_dict)

print(f"\nFormatos generados: {list(registros_v2.keys())}")
for fmt, regs in registros_v2.items():
    print(f"  {fmt}: {len(regs)} registros")

# Inspeccionar F1001
print("\n📋 Registros F1001:")
for reg in registros_v2.get('1001', []):
    print(f"  Concepto {reg.concepto}, NIT {reg.tercero.nit} ({reg.tercero.razon_social})")
    print(f"    Pago deducible:     ${reg.pago_deducible:,.0f}")
    print(f"    Pago NO deducible:  ${reg.pago_no_deducible:,.0f}")

# Verificación crítica: las columnas deducible/no_deducible del F1001 corresponden a empleador/trabajador
r_salud = next(r for r in registros_v2['1001'] if r.concepto == 5011)
assert r_salud.pago_deducible == 1_700_000, f"Esperaba 1.700.000 deducible, obtuvo {r_salud.pago_deducible}"
assert r_salud.pago_no_deducible == 1_000_000, f"Esperaba 1.000.000 NO deducible, obtuvo {r_salud.pago_no_deducible}"
print(f"\n✅ F1001 5011 (Salud): deducible=${r_salud.pago_deducible:,.0f}, no_deducible=${r_salud.pago_no_deducible:,.0f}")

r_pension = next(r for r in registros_v2['1001'] if r.concepto == 5012)
assert r_pension.pago_deducible == 1_200_000
assert r_pension.pago_no_deducible == 600_000
print(f"✅ F1001 5012 (Pensión): deducible=${r_pension.pago_deducible:,.0f}, no_deducible=${r_pension.pago_no_deducible:,.0f}")

r_para = next(r for r in registros_v2['1001'] if r.concepto == 5010)
assert r_para.pago_deducible == 350_000
assert r_para.pago_no_deducible == 0
print(f"✅ F1001 5010 (Parafiscal): deducible=${r_para.pago_deducible:,.0f}, no_deducible=0")

# Inspeccionar F1009
print("\n📋 Registros F1009:")
for reg in registros_v2.get('1009', []):
    print(f"  Concepto {reg.concepto}, NIT {reg.tercero.nit} ({reg.tercero.razon_social})")
    print(f"    Saldo: ${reg.saldo:,.0f}")

f1009_total = sum(r.saldo for r in registros_v2.get('1009', []) if r.concepto == 2214)
assert f1009_total == 3_150_000, f"Esperaba 3.150.000 F1009 2214, obtuvo {f1009_total}"
print(f"\n✅ F1009 2214: ${f1009_total:,.0f} (pasivo aportes SS cot dic)")


print()
print("=" * 70)
print("✅ TODOS LOS TESTS PASAN")
print("=" * 70)
print("""
Resumen del fix:
  ✅ Cargador PILA: ya asigna conceptos correctos 5010/5011/5012
  ✅ Integrador PILA: ahora separa empleador (deducible) vs trabajador (NO deducible)
  ✅ Adaptador motor→v2: respeta el split en columnas F1001
  ✅ F1009 2214: pasivo cot dic se reporta al NIT del fondo
  ✅ Excel borrador: ahora se llena (claves F1001 en vez de 1001)
""")
