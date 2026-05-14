"""
Test del fix F2276 — pasivos prestacionales solo reportan débitos del año.

Reproduce el escenario de la captura del usuario:
   - 252501 VACACIONES CONSOLIDADAS: saldo final NEGATIVO (-3.100.314)
   - 251010 CESANTIAS CONSOLIDADAS:  saldo final NEGATIVO (-12.117.346)
   - 251505 INTERESES CESANTIAS:     saldo final NEGATIVO (-1.454.082)
   - 25500503 DEDUCCION EMPLEADOS:   saldo final NEGATIVO (-8.159.730)

Comportamiento esperado:
   - F2276 reporta SOLO los débitos del año (positivos)
   - F1009 reporta SOLO si saldo final positivo (NO los negativos)
   - NO debe aparecer "Sin clasificar" para estas cuentas
   - NO debe haber doble reporte F1009
"""
import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'core/exogena')

from motor_clasificacion import (
    MotorClasificacion, Movimiento, ReglaCapa1, ReglaCapa2, ReglaCapa3,
)


def hacer_motor_vacio():
    """Motor sin reglas de capa 1/2/3 — para forzar que solo el guard dispare."""
    return MotorClasificacion(reglas_capa1=[], reglas_capa2=[], reglas_capa3=[])


print("=" * 70)
print("TEST: Vacaciones consolidadas (252501) con saldo negativo")
print("=" * 70)
print("Caso: empleado consumió todas sus vacaciones (saldo cierra negativo)")
print("Esperado: F2276 concepto 24 con débitos > 0; NO F1009 (saldo<0); NO sin_resolver")

motor = hacer_motor_vacio()
mov = Movimiento(
    codigo_cuenta='252501',
    nit='1037612345',
    debitos=6_534_456,       # pagos al empleado en el año
    creditos=3_434_142,      # provisiones
    saldo_final=-3_100_314,  # neto negativo (sobre-uso)
    nombre_cuenta='VACACIONES CONSOLIDADAS',
)
resultados = motor.clasificar_movimiento(mov)

print(f"\nMovimientos generados: {len(resultados)}")
for r in resultados:
    print(f"  → Formato={r.formato_dian or '—'}, "
          f"concepto={r.concepto_dian}, valor=${r.valor:,.0f}, "
          f"capa={r.capa_resolucion}")

# Verificaciones
formatos_generados = {r.formato_dian for r in resultados}
assert '2276' in formatos_generados, "Debe reportar F2276 con débitos del año"
assert '1009' not in formatos_generados, "NO debe reportar F1009 (saldo < 0)"
assert 'sin_resolver' not in {r.capa_resolucion for r in resultados}, \
    "NO debe quedar sin_resolver"

f2276 = next(r for r in resultados if r.formato_dian == '2276')
assert f2276.valor == 6_534_456, f"Esperaba débitos 6.534.456, obtuvo {f2276.valor:,.0f}"
print(f"\n✅ F2276 = ${f2276.valor:,.0f} (débitos del año, sin negativo)")


print()
print("=" * 70)
print("TEST: Cesantías consolidadas (251010) saldo negativo")
print("=" * 70)
motor = hacer_motor_vacio()
mov = Movimiento(
    codigo_cuenta='251010',
    nit='1037612345',
    debitos=14_000_000,
    creditos=1_882_654,
    saldo_final=-12_117_346,
    nombre_cuenta='CESANTIAS CONSOLIDADAS',
)
resultados = motor.clasificar_movimiento(mov)
for r in resultados:
    print(f"  → Formato={r.formato_dian or '—'}, "
          f"concepto={r.concepto_dian}, valor=${r.valor:,.0f}")
f2276 = next(r for r in resultados if r.formato_dian == '2276')
assert f2276.concepto_dian == 26, "Concepto 26 (ceco) para 2510"
assert f2276.valor == 14_000_000
assert '1009' not in {r.formato_dian for r in resultados}
print("\n✅ F2276 concepto 26 con débitos; SIN F1009 (saldo<0)")


print()
print("=" * 70)
print("TEST: Cesantías con saldo POSITIVO al cierre (cuenta por pagar real)")
print("=" * 70)
motor = hacer_motor_vacio()
mov = Movimiento(
    codigo_cuenta='251010',
    nit='1037612345',
    debitos=10_000_000,
    creditos=15_000_000,
    saldo_final=5_000_000,   # POSITIVO: hay deuda al cierre
    nombre_cuenta='CESANTIAS CONSOLIDADAS',
)
resultados = motor.clasificar_movimiento(mov)
for r in resultados:
    print(f"  → Formato={r.formato_dian or '—'}, "
          f"concepto={r.concepto_dian}, valor=${r.valor:,.0f}")

formatos = {r.formato_dian for r in resultados}
assert '2276' in formatos, "Debe reportar F2276"
assert '1009' in formatos, "Debe reportar F1009 (saldo > 0)"

f2276 = next(r for r in resultados if r.formato_dian == '2276')
f1009 = next(r for r in resultados if r.formato_dian == '1009')
assert f2276.valor == 10_000_000, "F2276 = débitos del año"
assert f1009.valor == 5_000_000, "F1009 = saldo final positivo"
print(f"\n✅ F2276 = ${f2276.valor:,.0f} (débitos)")
print(f"✅ F1009 = ${f1009.valor:,.0f} (saldo positivo)")


print()
print("=" * 70)
print("TEST: Sin débitos, sin saldo positivo → NO reportar nada")
print("=" * 70)
motor = hacer_motor_vacio()
mov = Movimiento(
    codigo_cuenta='251010',
    nit='1037612345',
    debitos=0,
    creditos=5_000_000,
    saldo_final=-5_000_000,  # solo créditos, neto negativo
)
resultados = motor.clasificar_movimiento(mov)
print(f"Movimientos generados: {len(resultados)}")
assert len(resultados) == 0, "No debe generar nada (cuenta sin actividad reportable)"
print("✅ Cuenta filtrada correctamente (sin débitos ni saldo positivo)")


print()
print("=" * 70)
print("TEST: Sin guard (cuenta normal sin reglas) → debe quedar sin_resolver")
print("=" * 70)
motor = hacer_motor_vacio()
mov = Movimiento(
    codigo_cuenta='519999',  # cuenta cualquiera no prestacional
    nit='900380500',
    debitos=1_000_000,
    saldo_final=1_000_000,
)
resultados = motor.clasificar_movimiento(mov)
for r in resultados:
    print(f"  → Formato={r.formato_dian or '—'}, capa={r.capa_resolucion}")
assert any(r.capa_resolucion == 'sin_resolver' for r in resultados), \
    "Cuenta sin guard ni regla debe quedar sin_resolver"
print("✅ Cuenta no prestacional cae correctamente en sin_resolver")


print()
print("=" * 70)
print("RESUMEN")
print("=" * 70)
print("✅ Vacaciones (2525) con saldo negativo → solo F2276 débitos, no F1009")
print("✅ Cesantías (2510) con saldo negativo → solo F2276 débitos, no F1009")
print("✅ Cesantías con saldo positivo → F2276 débitos + F1009 saldo")
print("✅ Cuenta sin actividad → filtrada (no genera sin_resolver fantasma)")
print("✅ Cuentas no prestacionales siguen marcando sin_resolver normalmente")
print()
print("🎯 BUG ARREGLADO: ya no hay valores negativos en el reporte F2276")
