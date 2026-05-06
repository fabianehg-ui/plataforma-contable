"""
Validación end-to-end con datos reales de Quinto Sentido SAS
"""
import sys
sys.path.insert(0, '/home/claude/iva_completo')

import pandas as pd
from generador_f1005_f1006 import generar_f1005, generar_f1006
from builder_xml_iva import construir_xml_f1005, construir_xml_f1006

# Cargar balance
df = pd.read_excel('/home/claude/balance.xlsx', sheet_name='Datos', header=3)
df.columns = ['Cuenta', 'Equivalencia', 'Nombre', 'NIT', 'Nombre_NIT',
              'Saldo_Ant', 'Debitos', 'Creditos', 'Nuevo_Saldo']
df['Cuenta'] = df['Cuenta'].astype(str).str.strip()

# Filtrar movimientos con NIT (auxiliares con tercero)
movs = df[df['NIT'].notna() & df['Cuenta'].str.startswith('2408')].copy()

# Convertir a formato esperado
movimientos = []
for _, row in movs.iterrows():
    movimientos.append({
        'cuenta': row['Cuenta'],
        'nombre_cuenta': row['Nombre'],
        'nit': str(row['NIT']).replace('.', '').replace('-', '').replace(' ', '').strip().split('-')[0],
        'dv': '0',
        'razon_social': str(row['Nombre_NIT']).strip() if pd.notna(row['Nombre_NIT']) else '',
        'tipo_doc': '31' if str(row['NIT']).startswith('9') or str(row['NIT']).startswith('8') else '13',
        'debitos': float(row['Debitos']) if pd.notna(row['Debitos']) else 0,
        'creditos': float(row['Creditos']) if pd.notna(row['Creditos']) else 0,
    })

print(f'📊 Movimientos cargados: {len(movimientos)}')
print()

# === GENERAR F1005 ===
print('=' * 70)
print('F1005 v.9 — IVA Descontable + IVA Dev Ventas')
print('=' * 70)
r1005 = generar_f1005(movimientos)
print(f'Total reportado:   ${r1005.total_reportado:>15,.2f}')
print(f'Filas (NITs):      {len(r1005.filas)}')
print(f'Cuentas origen:    {", ".join(r1005.cuentas_origen)}')
print(f'Versión:           {r1005.version}')

# Top 5 NITs
filas_orden = sorted(r1005.filas, key=lambda f: -f.total())[:5]
print('\nTop 5 NITs:')
for f in filas_orden:
    print(f'   {f.nit:<12} {f.razon_social[:30]:<30} desc=${f.iva_descontable:>13,.0f}  dev=${f.iva_dev_ventas:>10,.0f}')

# === GENERAR F1006 ===
print()
print('=' * 70)
print('F1006 v.8 — IVA Generado + INC + IVA Dev Compras')
print('=' * 70)
r1006 = generar_f1006(movimientos)
print(f'Total reportado:   ${r1006.total_reportado:>15,.2f}')
print(f'Filas (NITs):      {len(r1006.filas)}')
print(f'Cuentas origen:    {", ".join(r1006.cuentas_origen)}')
print(f'Versión:           {r1006.version}')

total_gen = sum(f.iva_generado for f in r1006.filas)
total_dev_comp = sum(f.iva_dev_compras for f in r1006.filas)
total_inc = sum(f.inc for f in r1006.filas)
print(f'\nDesglose:')
print(f'   IVA generado:        ${total_gen:>15,.2f}')
print(f'   INC:                 ${total_inc:>15,.2f}')
print(f'   IVA dev en compras:  ${total_dev_comp:>15,.2f}')

filas_orden_06 = sorted(r1006.filas, key=lambda f: -f.total())[:5]
print('\nTop 5 NITs:')
for f in filas_orden_06:
    print(f'   {f.nit:<12} {f.razon_social[:30]:<30} gen=${f.iva_generado:>13,.0f}  dev=${f.iva_dev_compras:>10,.0f}')

# === CUADRE TOTAL ===
print()
print('=' * 70)
print('CUADRE TOTAL IVA')
print('=' * 70)
print(f'F1005 (descontable + dev ventas): ${r1005.total_reportado:>15,.2f}')
print(f'F1006 (generado + INC + dev comp): ${r1006.total_reportado:>15,.2f}')
print(f'                            TOTAL: ${r1005.total_reportado + r1006.total_reportado:>15,.2f}')
print()
print('Esperado según balance:')
print('   IVA descontable:      $204,559,868.10')
print('   IVA generado:         $205,602,413.00')
print('   IVA dev en compras:   $ 27,988,658.00')
print(f'   TOTAL ESPERADO:       ${204559868.10 + 205602413 + 27988658:>15,.2f}')
print()
diff_total = (204559868.10 + 205602413 + 27988658) - (r1005.total_reportado + r1006.total_reportado)
print(f'   DIFERENCIA:           ${diff_total:>15,.2f}')

# === GENERAR XMLs ===
print()
print('=' * 70)
print('GENERACIÓN DE XMLs')
print('=' * 70)

xml_1005 = construir_xml_f1005(r1005, '900533491', 'QUINTO SENTIDO SAS')
xml_1006 = construir_xml_f1006(r1006, '900533491', 'QUINTO SENTIDO SAS')

with open('/home/claude/iva_completo/F1005_QS_2025.xml', 'w', encoding='utf-8') as f:
    f.write(xml_1005)
with open('/home/claude/iva_completo/F1006_QS_2025.xml', 'w', encoding='utf-8') as f:
    f.write(xml_1006)

print(f'F1005 XML: {len(xml_1005):,} chars')
print(f'F1006 XML: {len(xml_1006):,} chars')

# Verificar que NO hay decimales en valores
import re
matches_1006 = re.findall(r'<ns1:vIvaGen>(\d+\.?\d*)</ns1:vIvaGen>', xml_1006)
con_decimales = [m for m in matches_1006 if '.' in m]
print(f'\nValidación XML F1006:')
print(f'   Valores con decimales: {len(con_decimales)} (debe ser 0)')
print(f'   Total nodos vIvaGen:   {len(matches_1006)}')
