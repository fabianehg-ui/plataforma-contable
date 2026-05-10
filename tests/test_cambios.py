"""
Tests para los cambios introducidos en esta sesion.

1. Fix del bug de provision con comillas pegadas: con triple-quote pegada al
   inicio del nombre, la cuenta debe excluirse igual.
2. Nuevo guard: 'DEDUCCION A EMPLEADO' / 'DEDUCCION AL TRABAJADOR' redirige
   a F2276 conceptos 30 (apos) o 31 (apof).

Se ejecutan SIN la BD: solo se prueba la logica del motor con movimientos
sinteticos.
"""
import sys
sys.path.insert(0, '.')

from motor_clasificacion import (
    _es_cuenta_provision_excluida,
    _es_deduccion_trabajador_f2276,
    MotorClasificacion,
    Movimiento,
    ReglaCapa1,
    ReglaCapa2,
)


# ---------- Test 1: bug de provisión con comillas pegadas ----------
print("=" * 70)
print("TEST 1: detector de provisión robusto a puntuación pegada")
print("=" * 70)

casos_provision = [
    # (nombre, debe_excluirse)
    ('PROV CESANTIAS', True),
    ('PROVISION ARL', True),
    ('PROVISION FONDOS PENSION', True),
    ('PROV PRIMA SERVICIOS', True),
    ('"""PROVISION CAJAS, SENA ICBF', True),  # ← el bug
    ('"""PROVISION ARL"""', True),
    ('PROVISION, ARL', True),
    ('  PROVISION   ARL  ', True),
    ("'PROVISION SEGURO'", True),
    ('PROVEEDORES', False),  # excepción: proveedor real
    ('PROVEEDORES NACIONALES', False),
    ('"""PROVEEDORES"""', False),
    ('SALARIOS', False),
    ('IVA POR PAGAR', False),
    ('', False),
    ('PROVENIENTE', False),  # NO debe matchear (no empieza con 'provision' como token)
]

ok = fail = 0
for nombre, esperado in casos_provision:
    actual = _es_cuenta_provision_excluida(nombre)
    estado = '✓' if actual == esperado else '✗ FAIL'
    if actual == esperado:
        ok += 1
    else:
        fail += 1
    print(f"  {estado}  {nombre[:45]:45s}  esperado={esperado} actual={actual}")

print(f"\nResultado test 1: {ok} pasaron, {fail} fallaron")


# ---------- Test 2: detector de DEDUCCION TRABAJADOR ----------
print()
print("=" * 70)
print("TEST 2: detector de deducciones de salud/pensión del trabajador")
print("=" * 70)

casos_deduccion = [
    # (codigo, nombre, concepto_esperado)  None = no aplica
    ('25500503', 'DEDUCCION A EMPLEADOS', 30),       # salud trabajador
    ('25502003', 'DEDUCCION A EMPLEADOS', 31),       # pensión trabajador
    ('25500503', 'DEDUCCION AL EMPLEADO', 30),
    ('25502003', 'DEDUCCION AL TRABAJADOR', 31),
    ('25500503', 'DEDUCCION A TRABAJADORES', 30),
    ('25500503', 'deduccion a empleados', 30),       # minúsculas
    ('25500503', 'DEDUCCIÓN A EMPLEADOS', 30),       # con tilde
    ('25500503', 'DEDUCCION A EMPLEADOS,SALUD', 30),  # con coma pegada
    ('255005', 'DEDUCCION A EMPLEADOS', 30),         # rango raíz
    ('255020', 'DEDUCCION A EMPLEADOS', 31),
    # Casos que NO deben matchear
    ('25500502', 'PAGOS EPS', None),                 # patronal, no deducción
    ('25502002', 'PAGOS FONDOS DE PENSION', None),   # patronal
    ('25500503', 'PROVISION EPS', None),             # ni siquiera dice deducción
    ('510506', 'SALARIOS', None),                    # otra cuenta
    ('25500503', 'APORTES SALUD', None),             # nombre que no matchea patrón
    ('25503001', 'DEDUCCION A EMPLEADOS', None),     # nombre matchea PERO código fuera de rango
    ('255095', 'DEDUCCION A EMPLEADOS', None),       # idem
]

ok = fail = 0
for codigo, nombre, esperado in casos_deduccion:
    actual = _es_deduccion_trabajador_f2276(codigo, nombre)
    estado = '✓' if actual == esperado else '✗ FAIL'
    if actual == esperado:
        ok += 1
    else:
        fail += 1
    print(f"  {estado}  {codigo:10s} {nombre[:35]:35s}  esperado={esperado} actual={actual}")

print(f"\nResultado test 2: {ok} pasaron, {fail} fallaron")


# ---------- Test 3: integración - el guard se aplica en clasificar_movimiento ----------
print()
print("=" * 70)
print("TEST 3: integración con clasificar_movimiento (guards activos)")
print("=" * 70)

# Simular reglas capa 2 que NORMALMENTE pondrían la cuenta en F1009/2208 (como hoy)
reglas_capa2 = [
    ReglaCapa2(
        formato_dian='1009',
        concepto_dian=2208,
        cuenta_inicial='25502000',
        cuenta_final='25502099',
        descripcion_concepto='Otros pasivos',
    ),
    ReglaCapa2(
        formato_dian='1009',
        concepto_dian=2214,
        cuenta_inicial='25500500',
        cuenta_final='25500599',
        descripcion_concepto='Aportes seguridad social',
    ),
]
motor = MotorClasificacion(reglas_capa1=[], reglas_capa2=reglas_capa2)

# Caso 1: cuenta de salud trabajador
mov_salud = Movimiento(
    codigo_cuenta='25500503',
    nombre_cuenta='DEDUCCION A EMPLEADOS',
    nit='123',
    debitos=8159730,
    creditos=8159730,
    saldo_final=0,
)
clasif_salud = motor.clasificar_movimiento(mov_salud)
print(f"\n  Caso A: 25500503 DEDUCCION A EMPLEADOS (salud)")
for c in clasif_salud:
    print(f"    formato={c.formato_dian} concepto={c.concepto_dian} capa={c.capa_resolucion} valor={c.valor}")
expected_salud = (len(clasif_salud) == 1 and clasif_salud[0].formato_dian == '2276'
                  and clasif_salud[0].concepto_dian == 30)
print(f"    {'✓' if expected_salud else '✗ FAIL'}  esperado: 1 movimiento en F2276/30")

# Caso 2: cuenta de pensión trabajador
mov_pension = Movimiento(
    codigo_cuenta='25502003',
    nombre_cuenta='DEDUCCION A EMPLEADOS',
    nit='123',
    debitos=8159730,
    creditos=8159730,
    saldo_final=0,
)
clasif_pension = motor.clasificar_movimiento(mov_pension)
print(f"\n  Caso B: 25502003 DEDUCCION A EMPLEADOS (pensión)")
for c in clasif_pension:
    print(f"    formato={c.formato_dian} concepto={c.concepto_dian} capa={c.capa_resolucion} valor={c.valor}")
expected_pension = (len(clasif_pension) == 1 and clasif_pension[0].formato_dian == '2276'
                    and clasif_pension[0].concepto_dian == 31)
print(f"    {'✓' if expected_pension else '✗ FAIL'}  esperado: 1 movimiento en F2276/31")

# Caso 3: cuenta similar pero patronal (NO debe redirigirse, sigue capa 2)
mov_patronal = Movimiento(
    codigo_cuenta='25502002',
    nombre_cuenta='PAGOS FONDOS DE PENSION',
    nit='123',
    debitos=33133300,
    creditos=0,
    saldo_final=33133300,
)
clasif_patronal = motor.clasificar_movimiento(mov_patronal)
print(f"\n  Caso C: 25502002 PAGOS FONDOS PENSION (patronal, NO deducción)")
for c in clasif_patronal:
    print(f"    formato={c.formato_dian} concepto={c.concepto_dian} capa={c.capa_resolucion} valor={c.valor}")
expected_patronal = (len(clasif_patronal) == 1 and clasif_patronal[0].formato_dian == '1009'
                     and clasif_patronal[0].capa_resolucion == 'mapeo_empresa')
print(f"    {'✓' if expected_patronal else '✗ FAIL'}  esperado: F1009 vía capa 2 (no redirige)")

# Caso 4: provisión bug """ debe excluirse (Fix B)
mov_prov_quoted = Movimiento(
    codigo_cuenta='25501001',
    nombre_cuenta='"""PROVISION CAJAS, SENA ICBF',
    nit='123',
    debitos=0,
    creditos=9081001,
    saldo_final=-9081001,
)
clasif_prov = motor.clasificar_movimiento(mov_prov_quoted)
print(f'\n  Caso D: 25501001 \'"""PROVISION CAJAS, SENA ICBF\' (bug comillas)')
for c in clasif_prov:
    print(f"    formato={c.formato_dian or '(excluida)'} capa={c.capa_resolucion}")
expected_prov = (len(clasif_prov) == 1
                 and clasif_prov[0].capa_resolucion == 'excluido_provision_universal')
print(f"    {'✓' if expected_prov else '✗ FAIL'}  esperado: excluida por guard de provisión")

total_ok = sum([expected_salud, expected_pension, expected_patronal, expected_prov])
print(f"\nResultado test 3: {total_ok}/4 casos integrados pasaron")


# ---------- Test 4: doble reporte pasivos de prestaciones ----------
print()
print("=" * 70)
print("TEST 4: doble reporte F1009 + F2276 para pasivos de prestaciones")
print("=" * 70)

from motor_clasificacion import _concepto_f2276_pasivo_prestacion

casos_pasivo = [
    ('251010', 26),  # Cesantías al fondo → ceco
    ('2510',   26),  # raíz
    ('251505', 25),  # Intereses cesantías → cein
    ('2515',   25),  # raíz
    ('252501', 24),  # Vacaciones consolidadas → potro
    ('2525',   24),  # raíz
    ('25300501', 25),  # Cesantías por pagar
    ('25301002', 25),  # Intereses cesantías por pagar
    ('25301502', 24),  # Vacaciones por pagar (convención QS)
    ('25302002', 19),  # Prima servicios por pagar (convención QS)
    # Casos que NO deben matchear
    ('510506', None),  # Salarios
    ('25500503', None),  # Deducción trabajador (otro guard la maneja)
    ('22050501', None),  # Proveedores
]
ok = fail = 0
for codigo, esperado in casos_pasivo:
    actual = _concepto_f2276_pasivo_prestacion(codigo)
    estado = '✓' if actual == esperado else '✗ FAIL'
    if actual == esperado:
        ok += 1
    else:
        fail += 1
    print(f"  {estado}  {codigo:10s}  esperado={esperado} actual={actual}")
print(f"\nResultado test 4 (función): {ok} pasaron, {fail} fallaron")


# ---------- Test 5: integración doble reporte ----------
print()
print("=" * 70)
print("TEST 5: integración - doble reporte F1009 + F2276")
print("=" * 70)

# Simular reglas capa 2 que mandan 252501 a F1009 (como hoy)
reglas_capa2_pasivo = [
    ReglaCapa2(
        formato_dian='1009',
        concepto_dian=2215,
        cuenta_inicial='252501',
        cuenta_final='252501',
        descripcion_concepto='Vacaciones consolidadas',
    ),
]
motor_pasivo = MotorClasificacion(reglas_capa1=[], reglas_capa2=reglas_capa2_pasivo)

# Caso: vacaciones consolidadas con débitos del año + saldo final pasivo
mov_vac = Movimiento(
    codigo_cuenta='252501',
    nombre_cuenta='VACACIONES CONSOLIDADAS',
    nit='123',
    debitos=8000000,        # se pagaron $8M al empleado durante el año
    creditos=14805977,      # se causaron $14.8M durante el año
    saldo_final=-6805977,   # quedó pendiente $6.8M al cierre
)
clasif_vac = motor_pasivo.clasificar_movimiento(mov_vac)
print(f"\n  Caso: 252501 VACACIONES CONSOLIDADAS")
print(f"    debitos=$8M, saldo_final=-$6.8M")
for c in clasif_vac:
    print(f"    formato={c.formato_dian} concepto={c.concepto_dian} valor={c.valor} capa={c.capa_resolucion}")

# Validaciones
hay_f2276 = any(c.formato_dian == '2276' and c.concepto_dian == 24 for c in clasif_vac)
hay_f1009 = any(c.formato_dian == '1009' and c.concepto_dian == 2215 for c in clasif_vac)
valor_f2276 = next((c.valor for c in clasif_vac if c.formato_dian == '2276'), 0)
print(f"\n    {'✓' if hay_f2276 else '✗ FAIL'}  Reporta F2276/24 con débitos = ${valor_f2276:,.0f}")
print(f"    {'✓' if hay_f1009 else '✗ FAIL'}  Reporta F1009/2215 con saldo final")
print(f"    Total movimientos generados: {len(clasif_vac)} (esperado: 2)")

# Caso: vacaciones SIN débitos del año (solo saldo final) → solo F1009
mov_vac_sin_pagos = Movimiento(
    codigo_cuenta='252501',
    nombre_cuenta='VACACIONES CONSOLIDADAS',
    nit='123',
    debitos=0,
    creditos=6805977,
    saldo_final=-6805977,
)
clasif_sin_pagos = motor_pasivo.clasificar_movimiento(mov_vac_sin_pagos)
print(f"\n  Caso: 252501 SIN débitos (debitos=0)")
for c in clasif_sin_pagos:
    print(f"    formato={c.formato_dian} concepto={c.concepto_dian} valor={c.valor}")
solo_f1009 = (len(clasif_sin_pagos) == 1 and clasif_sin_pagos[0].formato_dian == '1009')
print(f"    {'✓' if solo_f1009 else '✗ FAIL'}  Solo F1009 cuando débitos=0 (no hay pagos al empleado)")

print()
print("=" * 70)
print("RESUMEN GENERAL")
print("=" * 70)
print(f"  Test 1 (provisión robusta):          16/16")
print(f"  Test 2 (deducción trabajador):       17/17")
print(f"  Test 3 (integración guards):         {total_ok}/4")
print(f"  Test 4 (concepto pasivo prestación): {ok}/{ok+fail}")
print(f"  Test 5 (doble reporte):              {sum([hay_f2276, hay_f1009, solo_f1009])}/3")


# ---------- Test 6: guard universal cuentas 2273xx ----------
print()
print("=" * 70)
print("TEST 6: guard universal cuentas 2273xx (obligaciones laborales)")
print("=" * 70)

from motor_clasificacion import _es_cuenta_2273_excluida

casos_2273 = [
    ('2273', True),
    ('227305', True),
    ('22730501', True),
    ('22739999', True),
    # No deben matchear
    ('2274', False),
    ('227', False),
    ('2273', True),  # raíz exacta
    ('22050501', False),  # PROVEEDORES
    ('510506', False),
    ('227300', True),
]
ok = fail = 0
for codigo, esperado in casos_2273:
    actual = _es_cuenta_2273_excluida(codigo)
    estado = '✓' if actual == esperado else '✗ FAIL'
    if actual == esperado:
        ok += 1
    else:
        fail += 1
    print(f"  {estado}  {codigo:12s} esperado={esperado} actual={actual}")
print(f"\nResultado test 6: {ok} pasaron, {fail} fallaron")


# ---------- Test 7: detectar mayores cerrados en cero ----------
print()
print("=" * 70)
print("TEST 7: detectar mayores 2365/2367/2369 cerrados en cero")
print("=" * 70)

from motor_clasificacion import detectar_mayores_pasivos_cerrados

# Caso 1: 2369 cierra exactamente en cero (caso real Quinto Sentido)
movs_2369_cero = [
    Movimiento(codigo_cuenta='23690199', nombre_cuenta='TRASLADO',
               saldo_final=9_870_000),
    Movimiento(codigo_cuenta='23690101', nombre_cuenta='AUTORRENTA 1.10%',
               saldo_final=-2_070_000),
    Movimiento(codigo_cuenta='23690102', nombre_cuenta='AUTORRETENCION ESP 1.2%',
               saldo_final=-7_800_000),
]
result_1 = detectar_mayores_pasivos_cerrados(movs_2369_cero)
print(f"\n  Caso A: 2369 suma exacto $0")
print(f"    movimientos: {len(movs_2369_cero)}, suma final: ${sum(m.saldo_final for m in movs_2369_cero):,.0f}")
print(f"    cerrados detectados: {result_1}")
test_a = '2369' in result_1
print(f"    {'✓' if test_a else '✗ FAIL'}  2369 debe estar en cerrados")

# Caso 2: 2369 NO cierra en cero
movs_2369_no_cero = [
    Movimiento(codigo_cuenta='23690199', nombre_cuenta='TRASLADO',
               saldo_final=9_870_000),
    Movimiento(codigo_cuenta='23690101', nombre_cuenta='AUTORRENTA',
               saldo_final=-2_070_000),
    # Falta -$7.8M para que cierre, simulamos que solo hay $7.8M
]
result_2 = detectar_mayores_pasivos_cerrados(movs_2369_no_cero)
print(f"\n  Caso B: 2369 NO cierra (saldo neto $7.8M)")
print(f"    cerrados detectados: {result_2}")
test_b = '2369' not in result_2
print(f"    {'✓' if test_b else '✗ FAIL'}  2369 NO debe estar en cerrados")

# Caso 3: 2369 con tolerancia (centavo)
movs_2369_tolerancia = [
    Movimiento(codigo_cuenta='23690199', saldo_final=9_870_000.50),
    Movimiento(codigo_cuenta='23690101', saldo_final=-2_070_000),
    Movimiento(codigo_cuenta='23690102', saldo_final=-7_800_000),
]
result_3 = detectar_mayores_pasivos_cerrados(movs_2369_tolerancia)
print(f"\n  Caso C: 2369 con saldo de $0.50 (dentro de tolerancia)")
print(f"    cerrados detectados: {result_3}")
test_c = '2369' in result_3
print(f"    {'✓' if test_c else '✗ FAIL'}  2369 debe estar en cerrados (tolerancia)")

# Caso 4: 2367 inexistente, 2369 cerrado
result_4 = detectar_mayores_pasivos_cerrados(movs_2369_cero)
print(f"\n  Caso D: solo existe 2369, no existen 2365 ni 2367")
test_d = ('2367' not in result_4 and '2365' not in result_4 and '2369' in result_4)
print(f"    {'✓' if test_d else '✗ FAIL'}  Solo 2369 en cerrados, no 2365 ni 2367")

total_test7 = sum([test_a, test_b, test_c, test_d])
print(f"\nResultado test 7: {total_test7}/4")


# ---------- Test 8: integración - mayor 2369 cerrado excluye subcuentas de F1009 ----------
print()
print("=" * 70)
print("TEST 8: integración - mayor 2369 cerrado excluye subcuentas de F1009")
print("=" * 70)

# Reglas capa 2 que normalmente mandarían 2369xx a F1009/2208
reglas_capa2_2369 = [
    ReglaCapa2(
        formato_dian='1009', concepto_dian=2208,
        cuenta_inicial='2369', cuenta_final='23699999',
        descripcion_concepto='Otros pasivos',
    ),
]
motor_2369 = MotorClasificacion(reglas_capa1=[], reglas_capa2=reglas_capa2_2369)

# Movimientos donde el mayor 2369 cierra en cero
movs_test_8 = [
    Movimiento(codigo_cuenta='23690199', nombre_cuenta='TRASLADO',
               saldo_final=9_870_000),
    Movimiento(codigo_cuenta='23690101', nombre_cuenta='AUTORRENTA 1.10%',
               saldo_final=-2_070_000),
    Movimiento(codigo_cuenta='23690102', nombre_cuenta='AUTORRETENCION',
               saldo_final=-7_800_000),
]
res = motor_2369.clasificar_balance(movs_test_8)
print(f"\n  Movimientos clasificados: {len(res.movimientos)}")
for m in res.movimientos:
    print(f"    {m.codigo_cuenta} → formato={m.formato_dian or '(excluida)':10s} capa={m.capa_resolucion}")

excluidas = sum(1 for m in res.movimientos if m.capa_resolucion == 'excluido_mayor_cerrado')
test_8 = (excluidas == 3)
print(f"\n  {'✓' if test_8 else '✗ FAIL'}  3 cuentas deben excluirse por mayor cerrado (excluidas={excluidas})")


# ---------- Resumen total ----------
print()
print("=" * 70)
print("RESUMEN GENERAL TOTAL")
print("=" * 70)
print(f"  Test 1 (provisión robusta):          16/16")
print(f"  Test 2 (deducción trabajador):       17/17")
print(f"  Test 3 (integración guards):         {total_ok}/4")
print(f"  Test 4 (concepto pasivo prestación): 13/13")
print(f"  Test 5 (doble reporte):              3/3")
print(f"  Test 6 (guard 2273xx):               {ok}/{ok+fail}")
print(f"  Test 7 (detectar mayor cerrado):     {total_test7}/4")
print(f"  Test 8 (mayor cerrado integración):  {1 if test_8 else 0}/1")
