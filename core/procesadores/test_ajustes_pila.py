"""
Test de la lógica de ajustes provisión vs PILA pagada.

Simula 3 escenarios:
  A) Provisión EXACTA = pagado → 0 ajustes
  B) Provisión MENOR que pagado (faltó provisionar) → Cr al pasivo
  C) Provisión MAYOR que pagado (sobró provisión) → Db al pasivo
"""
import sys
sys.path.insert(0, '/home/claude/proyecto/pila_merge')

from procesador_pila import (
    leer_planilla_pila,
    calcular_ajustes_pila,
    AporteEmpleado,
    PilaLeida,
)

# Cargar PILA real
catalogo = {
    "39177488":   "MENA COLLASOS ELIZABETH",
    "43101052":   "MORALES RAMOS MARIA YORLADIS",
    "1000895032": "GARCIA MORALES MARIA JOSE",
    "1128467903": "GARCIA MORALES YOHANA ANDREA",
}
pila = leer_planilla_pila(
    "/home/claude/proyecto/pila_merge/Prefactura_84919326.pdf",
    catalogo_empleados=catalogo,
)

# Cuentas de provisión (mock — la admin las define en su catálogo real)
cuentas = {
    "pension": "23700501",
    "salud":   "23700502",
    "arl":     "23700503",
    "caja":    "23700504",
}

print("=" * 70)
print("ESCENARIO A: Provisión EXACTA = pagado → 0 ajustes")
print("=" * 70)
provisiones_a = {}
for ced, e in pila.por_empleado.items():
    provisiones_a[ced] = {
        "pension": e.aporte_pension,
        "salud":   e.aporte_salud,
        "arl":     e.aporte_arl,
        "caja":    e.aporte_caja,
    }
ajustes_a = calcular_ajustes_pila(provisiones_a, pila, cuentas)
print(f"  Ajustes generados: {len(ajustes_a)}")
ok_a = len(ajustes_a) == 0
print(f"  {'✅' if ok_a else '❌'} (esperado 0)")
print()

print("=" * 70)
print("ESCENARIO B: Provisión MENOR (provisionó 95% de lo pagado)")
print("=" * 70)
provisiones_b = {}
for ced, e in pila.por_empleado.items():
    provisiones_b[ced] = {
        "pension": int(e.aporte_pension * 0.95),
        "salud":   int(e.aporte_salud * 0.95),
        "arl":     int(e.aporte_arl * 0.95),
        "caja":    int(e.aporte_caja * 0.95),
    }
ajustes_b = calcular_ajustes_pila(provisiones_b, pila, cuentas)
print(f"  Ajustes generados: {len(ajustes_b)}")
total_cr = sum(a.valor for a in ajustes_b if a.tr == "2")
total_db = sum(a.valor for a in ajustes_b if a.tr == "1")
print(f"  Total Cr (faltó provisión): ${int(total_cr):,}".replace(",", "."))
print(f"  Total Db (sobró provisión): ${int(total_db):,}".replace(",", "."))
# Esperado: solo Cr (provisión < pagado)
ok_b = total_cr > 0 and total_db == 0
print(f"  {'✅' if ok_b else '❌'} (esperado solo Cr)")
print()

# Ver primeras líneas
for a in ajustes_b[:6]:
    print(f"    {a.cuenta} | TR={a.tr} | ${int(a.valor):,} | {a.detalle[:50]}".replace(",", "."))
print()

print("=" * 70)
print("ESCENARIO C: Provisión MAYOR (provisionó 105% de lo pagado)")
print("=" * 70)
provisiones_c = {}
for ced, e in pila.por_empleado.items():
    provisiones_c[ced] = {
        "pension": int(e.aporte_pension * 1.05),
        "salud":   int(e.aporte_salud * 1.05),
        "arl":     int(e.aporte_arl * 1.05),
        "caja":    int(e.aporte_caja * 1.05),
    }
ajustes_c = calcular_ajustes_pila(provisiones_c, pila, cuentas)
print(f"  Ajustes generados: {len(ajustes_c)}")
total_cr_c = sum(a.valor for a in ajustes_c if a.tr == "2")
total_db_c = sum(a.valor for a in ajustes_c if a.tr == "1")
print(f"  Total Cr: ${int(total_cr_c):,}".replace(",", "."))
print(f"  Total Db (sobró): ${int(total_db_c):,}".replace(",", "."))
ok_c = total_db_c > 0 and total_cr_c == 0
print(f"  {'✅' if ok_c else '❌'} (esperado solo Db)")
print()

print("=" * 70)
print("ESCENARIO D: Empleado en PILA pero NO en provisión → ignora")
print("=" * 70)
provisiones_d = {
    "39177488": provisiones_a["39177488"],  # solo Mena tiene provisión
}
ajustes_d = calcular_ajustes_pila(provisiones_d, pila, cuentas)
empleados_ajustados = set(a.nit for a in ajustes_d)
print(f"  Ajustes generados: {len(ajustes_d)}")
print(f"  Empleados con ajuste: {empleados_ajustados}")
# Solo Mena debe tener ajustes (cuadra exacto), el resto se ignora
ok_d = len(empleados_ajustados) <= 1
print(f"  {'✅' if ok_d else '❌'} (los empleados sin provisión se omiten)")
print()

print("=" * 70)
print("ESCENARIO E: Tolerancia (diferencia de $1 → no genera ajuste)")
print("=" * 70)
provisiones_e = {}
for ced, e in pila.por_empleado.items():
    provisiones_e[ced] = {
        "pension": e.aporte_pension - 1,  # diferencia de $1
        "salud":   e.aporte_salud,
        "arl":     e.aporte_arl,
        "caja":    e.aporte_caja,
    }
ajustes_e = calcular_ajustes_pila(provisiones_e, pila, cuentas, tolerancia=1)
ok_e = len(ajustes_e) == 0
print(f"  Ajustes con dif $1 y tolerancia 1: {len(ajustes_e)}")
print(f"  {'✅' if ok_e else '❌'} (la tolerancia evita ajustes mínimos)")
print()

print("=" * 70)
total = sum([ok_a, ok_b, ok_c, ok_d, ok_e])
print(f"{'✅ TODO OK' if total == 5 else '❌ FALLOS'}: {total}/5")
