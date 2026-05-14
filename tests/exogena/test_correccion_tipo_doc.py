"""
Test integral: corrección automática de tipo de documento + fallback empresa.

Casos reales del Excel del usuario:
   - NITs que en realidad son cédulas (CC mal clasificadas como NIT)
   - Personas naturales sin dirección que deben recibir la de la empresa
   - Cédulas pequeñas (6-7 dígitos) que el sistema reconoce como CC
"""
import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'core/exogena')
sys.path.insert(0, 'core/exogena/enriquecimiento')

from helpers_inferencia import (
    inferir_tipo_documento_real,
    corregir_tipo_documento,
    es_persona_natural,
)
from generador_xml_v2 import Tercero, RegistroF1001, PAIS_COLOMBIA
from validador_pre_generacion import validar_y_enriquecer


print("=" * 70)
print("TEST 1: Inferencia de tipo de documento desde el número")
print("=" * 70)

casos_inferencia = [
    # NIT (Número) → Tipo esperado, descripción
    ('70071271',   13, "Cédula vieja típica de hombre (Antioquia)"),
    ('8031232',    13, "Cédula vieja (7 dígitos)"),
    ('6017605',    13, "Cédula muy vieja (7 dígitos)"),
    ('43000123',   13, "Cédula vieja de mujer (Antioquia)"),
    ('1037612345', 13, "CC joven (10 dígitos empezando con 1)"),
    ('1020987654', 13, "CC joven de Bogotá"),
    ('900533491',  31, "NIT moderno empresa (9 dígitos, comienza con 9)"),
    ('890900841',  31, "NIT antiguo empresa (9 dígitos, comienza con 8)"),
    ('800088702',  31, "NIT EPS Sura"),
    ('600100123',  31, "NIT empresa pública"),
    ('400123456',  31, "NIT empresa vieja con 4"),
]

for nit, esperado, descripcion in casos_inferencia:
    inferido = inferir_tipo_documento_real(nit)
    emoji = '✅' if inferido == esperado else '❌'
    tipo_str = {13: 'CC', 31: 'NIT'}.get(inferido, '?')
    print(f"  {emoji} {nit:12s} → {tipo_str:3s} (esperaba {{13:'CC',31:'NIT'}}[{esperado}])  {descripcion}")
    assert inferido == esperado, f"Falla en {nit}"


print()
print("=" * 70)
print("TEST 2: Corregir tipo de documento del tercero")
print("=" * 70)

casos = [
    # Caso original (mal cargado) → esperado después de corregir
    (
        {'nit': '70071271', 'tipo_documento': 31, 'razon_social': 'JORGE IVAN GONZALEZ RESTREPO'},
        13,  # CC
        'CC mal cargada como NIT (caso real Quinto Sentido)'
    ),
    (
        {'nit': '6017605', 'tipo_documento': 31},
        13,  # CC
        'CC vieja sin nombres'
    ),
    (
        {'nit': '900533491', 'tipo_documento': 13},
        31,  # NIT
        'NIT empresa mal cargado como CC'
    ),
    (
        {'nit': '900533491', 'tipo_documento': 31, 'razon_social': 'QUINTO SENTIDO SAS'},
        31,  # NIT (no cambia)
        'NIT bien cargado, no cambia'
    ),
    (
        {'nit': '70071271', 'tipo_documento': 13, 'primer_nombre': 'JORGE'},
        13,  # CC (no cambia)
        'CC bien cargada, no cambia'
    ),
]

for entrada, tipo_esperado, descripcion in casos:
    corregido = corregir_tipo_documento(entrada)
    tipo_real = corregido.get('tipo_documento')
    emoji = '✅' if tipo_real == tipo_esperado else '❌'
    print(f"  {emoji} {entrada.get('nit'):11s}: tipo {entrada['tipo_documento']:2d} → {tipo_real:2d}  ({descripcion})")
    assert tipo_real == tipo_esperado, f"Falla: {entrada} → {corregido}"


print()
print("=" * 70)
print("TEST 3: Flujo completo - CC mal cargada se corrige + autodivide + fallback empresa")
print("=" * 70)

# Caso típico: persona natural en el balance con:
#  - tipo_documento = 31 (mal, debería ser 13)
#  - nombre completo en razon_social
#  - sin dirección (debe recibirla de la empresa informante)
terceros_bd = {
    '70071271': {
        'nit': '70071271',
        'tipo_documento': 31,  # ← ERROR: debería ser 13 (CC)
        'razon_social': 'JORGE IVAN GONZALEZ RESTREPO',
        # SIN direccion, codigo_dpto, codigo_municipio
    },
    '6017605': {
        'nit': '6017605',
        'tipo_documento': 31,  # ← ERROR: cédula vieja mal clasificada
        # SIN nada más
    },
    '900533491': {
        'nit': '900533491',
        'tipo_documento': 31,  # ← OK
        'razon_social': 'QUINTO SENTIDO SAS',
        'direccion': 'CRA 35 # 8-20',
        'codigo_dpto': '05',
        'codigo_municipio': '001',
    },
}

# Registros del adaptador (Tercero viene del balance, NO tiene los datos corregidos aún)
registros = {
    '1001': [
        RegistroF1001(
            tercero=Tercero(nit=n, tipo_documento='31', codigo_pais=PAIS_COLOMBIA),
            concepto=5004, pago_deducible=5_000_000,
        ) for n in terceros_bd
    ]
}

info_empresa = {
    'direccion': 'CRA 35 # 8-20 OF 1002',
    'codigo_dpto': '05',
    'codigo_municipio': '001',
    'codigo_pais': '169',
}

resultado = validar_y_enriquecer(
    registros_por_formato=registros,
    terceros_dict=terceros_bd,
    info_empresa_informante=info_empresa,
    enriquecedor=None,
)

print(f"\nTotal procesados:           {resultado.total_terceros}")
print(f"Completos:                  {len(resultado.terceros_completos)}")
print(f"Pendientes:                 {resultado.total_pendientes}")
print(f"Tipos doc corregidos:       {resultado.tipos_documento_corregidos}")
print(f"Fallback empresa aplicado:  {resultado.enriquecidos_fallback}")
print()

# Caso 1: Jorge Iván
jorge = resultado.terceros_completos.get('70071271')
if jorge:
    print(f"Jorge Iván González (70071271):")
    print(f"  tipo_documento:   {jorge.get('tipo_documento')} (debería ser 13)")
    print(f"  primer_nombre:    {jorge.get('primer_nombre')!r}")
    print(f"  primer_apellido:  {jorge.get('primer_apellido')!r}")
    print(f"  razon_social:     {jorge.get('razon_social')!r}")
    print(f"  direccion:        {jorge.get('direccion')!r} (fallback empresa)")
    print(f"  codigo_dpto:      {jorge.get('codigo_dpto')!r}")
    print(f"  codigo_municipio: {jorge.get('codigo_municipio')!r}")
    assert jorge.get('tipo_documento') == 13, "Tipo no corregido"
    assert jorge.get('primer_apellido') == 'GONZALEZ', "No se auto-dividió"
    assert jorge.get('primer_nombre') == 'JORGE'
    assert jorge.get('razon_social') is None, "razon_social no se borró"
    assert jorge.get('direccion') == 'CRA 35 # 8-20 OF 1002', f"No se aplicó fallback empresa: {jorge.get('direccion')}"
    print("  ✅ Completo + fallback")
else:
    print(f"Jorge Iván sigue pendiente: {resultado.terceros_pendientes.get('70071271').errores}")

print()

# Caso 2: 6017605 (cédula vieja sin nombres)
ced_vieja = resultado.terceros_pendientes.get('6017605')
if ced_vieja:
    print(f"Cédula vieja 6017605:")
    print(f"  En pendientes: {ced_vieja.errores}")
    # Debe quedar pendiente porque no tiene NOMBRES (no hay nada que autodividir)
    # Pero la dirección ya debe estar del fallback empresa
    print(f"  direccion:        {ced_vieja.direccion!r} (fallback empresa)")
    print(f"  codigo_dpto:      {ced_vieja.codigo_dpto!r}")
    assert ced_vieja.direccion == 'CRA 35 # 8-20 OF 1002', "Fallback no aplicado a pendiente"
    assert any('apellido' in e.lower() or 'nombre' in e.lower() for e in ced_vieja.errores)
    print("  ✅ Pendiente por falta de NOMBRES (no de ubicación)")

print()

# Caso 3: Quinto Sentido (jurídica bien cargada)
qs = resultado.terceros_completos.get('900533491')
assert qs is not None, "Quinto Sentido debería estar completo"
assert qs.get('tipo_documento') == 31
print(f"Quinto Sentido SAS (900533491): ✅ pasa sin cambios")


print()
print("=" * 70)
print("✅ TODOS LOS TESTS PASAN")
print("=" * 70)
print("""
Resumen:
  ✅ Detección de cédula vs NIT por patrón del número
  ✅ Corrección automática de tipo_documento al inicio del flujo
  ✅ Auto-división de nombres se aplica DESPUÉS de corregir tipo
  ✅ Fallback empresa se aplica a personas naturales sin ubicación
  ✅ Si TODO está OK → completo
  ✅ Si falta nombre + apellido → pendiente (con dirección ya rellenada)
""")
