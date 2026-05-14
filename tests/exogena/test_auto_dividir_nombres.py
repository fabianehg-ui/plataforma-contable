"""
Test de validación de identidad y auto-división de nombres.

Casos reales del Excel descargado por el usuario:
   - Persona natural con todo el nombre en razón social:
     "JORGE IVAN GONZALEZ RESTREPO" → debe dividirse en
       primer_nombre='JORGE', otros_nombres='IVAN',
       primer_apellido='GONZALEZ', segundo_apellido='RESTREPO'
   - Persona jurídica sin razón social → debe quedar pendiente
   - Persona natural sin nombre → debe quedar pendiente
"""
import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'core/exogena')
sys.path.insert(0, 'core/exogena/enriquecimiento')

from helpers_inferencia import (
    validar_tercero_completo,
    auto_dividir_nombre_natural,
    es_persona_natural,
)


print("=" * 70)
print("TEST 1: Auto-división de nombre natural")
print("=" * 70)

# Caso del Excel del usuario
casos = [
    {
        'descripcion': '4 palabras (2 nombres + 2 apellidos)',
        'entrada': {
            'nit': '70071271', 'tipo_documento': 13,
            'razon_social': 'JORGE IVAN GONZALEZ RESTREPO',
        },
        'esperado': {
            'primer_nombre': 'JORGE', 'otros_nombres': 'IVAN',
            'primer_apellido': 'GONZALEZ', 'segundo_apellido': 'RESTREPO',
            'razon_social': None,
        }
    },
    {
        'descripcion': '3 palabras (1 nombre + 2 apellidos)',
        'entrada': {
            'nit': '8001234', 'tipo_documento': 13,
            'razon_social': 'MARIA RODRIGUEZ PEREZ',
        },
        'esperado': {
            'primer_nombre': 'MARIA', 'otros_nombres': None,
            'primer_apellido': 'RODRIGUEZ', 'segundo_apellido': 'PEREZ',
        }
    },
    {
        'descripcion': '5 palabras (1 nombre + nombres + 2 apellidos)',
        'entrada': {
            'nit': '1234567', 'tipo_documento': 13,
            'razon_social': 'ANA MARIA DEL CARMEN GOMEZ TORRES',
        },
        'esperado': {
            'primer_nombre': 'ANA',
            'otros_nombres': 'MARIA DEL CARMEN',
            'primer_apellido': 'GOMEZ', 'segundo_apellido': 'TORRES',
        }
    },
    {
        'descripcion': '2 palabras (1 nombre + 1 apellido)',
        'entrada': {
            'nit': '5555', 'tipo_documento': 13,
            'razon_social': 'JUAN PEREZ',
        },
        'esperado': {
            'primer_nombre': 'JUAN', 'primer_apellido': 'PEREZ',
            'segundo_apellido': None, 'otros_nombres': None,
        }
    },
    {
        'descripcion': 'Persona jurídica (NIT) NO se debe dividir',
        'entrada': {
            'nit': '900304275', 'tipo_documento': 31,
            'razon_social': 'DARCONTER S.A.S',
        },
        'esperado': {
            'razon_social': 'DARCONTER S.A.S',  # se mantiene
        }
    },
]

for caso in casos:
    print(f"\n  {caso['descripcion']}:")
    print(f"    Entrada: {caso['entrada'].get('razon_social')}")
    resultado = auto_dividir_nombre_natural(caso['entrada'])
    for campo, val_esperado in caso['esperado'].items():
        val_real = resultado.get(campo)
        ok = '✅' if val_real == val_esperado else '❌'
        print(f"    {ok} {campo}: {val_real!r} (esperaba {val_esperado!r})")
        assert val_real == val_esperado, f"Falla en {campo}"


print()
print("=" * 70)
print("TEST 2: validar_tercero_completo detecta inconsistencias")
print("=" * 70)

# Caso 1: persona natural con nombre en razón social (caso típico)
t = {
    'nit': '70071271', 'tipo_documento': 13,
    'razon_social': 'JORGE IVAN GONZALEZ RESTREPO',
    'direccion': 'CR 49', 'codigo_dpto': '05', 'codigo_municipio': '001',
}
errs = validar_tercero_completo(t, '1001')
print(f"\nNatural con razón social: {errs}")
assert any('Razón social' in e for e in errs), "Debería detectar inconsistencia"
print("✅ Detectado: razón social en persona natural")

# Caso 2: persona jurídica sin razón social
t = {
    'nit': '900304275', 'tipo_documento': 31,
    'razon_social': '',
    'direccion': 'CALLE 15', 'codigo_dpto': '05', 'codigo_municipio': '001',
}
errs = validar_tercero_completo(t, '1001')
print(f"\nJurídica sin razón social: {errs}")
assert any('sin razón social' in e.lower() for e in errs)
print("✅ Detectado: jurídica sin razón social")

# Caso 3: natural sin apellido ni nombre (vacío completo)
t = {
    'nit': '12345', 'tipo_documento': 13,
    'direccion': 'CR 1', 'codigo_dpto': '05', 'codigo_municipio': '001',
}
errs = validar_tercero_completo(t, '1001')
print(f"\nNatural vacío: {errs}")
assert any('apellido' in e.lower() for e in errs)
assert any('nombre' in e.lower() for e in errs)
print("✅ Detectado: natural sin apellido ni nombre")

# Caso 4: natural BIEN llenado
t = {
    'nit': '70071271', 'tipo_documento': 13,
    'primer_apellido': 'GONZALEZ', 'segundo_apellido': 'RESTREPO',
    'primer_nombre': 'JORGE', 'otros_nombres': 'IVAN',
    'direccion': 'CR 49', 'codigo_dpto': '05', 'codigo_municipio': '001',
}
errs = validar_tercero_completo(t, '1001')
print(f"\nNatural bien llenado: {errs}")
assert errs == [], f"No debería tener errores: {errs}"
print("✅ Natural correcto pasa validación")

# Caso 5: jurídica BIEN llenada
t = {
    'nit': '900304275', 'tipo_documento': 31,
    'razon_social': 'DARCONTER S.A.S',
    'direccion': 'CALLE 15', 'codigo_dpto': '05', 'codigo_municipio': '001',
}
errs = validar_tercero_completo(t, '1001')
print(f"\nJurídica bien llenada: {errs}")
assert errs == []
print("✅ Jurídica correcta pasa validación")


print()
print("=" * 70)
print("TEST 3: Flujo integral con validador pre-generación")
print("=" * 70)

from validador_pre_generacion import validar_y_enriquecer
from generador_xml_v2 import (
    Tercero, RegistroF1001, PAIS_COLOMBIA,
    TIPO_DOC_CC, TIPO_DOC_NIT,
)

# Maestro real con casos problemáticos del Excel del usuario
terceros_bd = {
    # ❌ Persona natural con nombre en razón social (debe dividirse auto)
    '70071271': {
        'nit': '70071271', 'tipo_documento': 13,
        'razon_social': 'JORGE IVAN GONZALEZ RESTREPO',
        'direccion': 'CR 49 61 SUR 540 BG 146',
        'codigo_dpto': '05', 'codigo_municipio': '001',
    },
    # ❌ Persona jurídica SIN razón social → debe quedar pendiente
    '900322985': {
        'nit': '900322985', 'tipo_documento': 31,
        'direccion': 'CALLE 1', 'codigo_dpto': '05', 'codigo_municipio': '001',
    },
    # ✅ Jurídica bien llenada
    '900304275': {
        'nit': '900304275', 'tipo_documento': 31,
        'razon_social': 'DARCONTER S.A.S',
        'direccion': 'CLL 15 No 70 - 27',
        'codigo_dpto': '05', 'codigo_municipio': '001',
    },
}

# Construir registros simulados
def t(nit):
    d = terceros_bd.get(nit, {'nit': nit})
    return Tercero(
        nit=nit,
        tipo_documento=str(d.get('tipo_documento', 31)).zfill(2),
        razon_social=d.get('razon_social'),
        codigo_pais=PAIS_COLOMBIA,
    )

registros = {
    '1001': [
        RegistroF1001(tercero=t('70071271'), concepto=5004, pago_deducible=50_000_000),
        RegistroF1001(tercero=t('900322985'), concepto=5004, pago_deducible=20_000_000),
        RegistroF1001(tercero=t('900304275'), concepto=5004, pago_deducible=15_000_000),
    ],
}

resultado = validar_y_enriquecer(
    registros_por_formato=registros,
    terceros_dict=terceros_bd,
    info_empresa_informante={
        'direccion': 'CRA 35 # 8-20', 'codigo_dpto': '05',
        'codigo_municipio': '001', 'codigo_pais': '169',
    },
    enriquecedor=None,  # sin enriquecedor externo
)

print(f"\nResultados:")
print(f"  Total procesados: {resultado.total_terceros}")
print(f"  Completos:        {len(resultado.terceros_completos)}")
print(f"  Pendientes:       {resultado.total_pendientes}")

# Inspeccionar el caso de Jorge Iván (debe haber auto-dividido)
jorge = resultado.terceros_completos.get('70071271')
if jorge:
    print(f"\n  Jorge Iván (auto-dividido):")
    print(f"    primer_nombre:    {jorge.get('primer_nombre')!r}")
    print(f"    otros_nombres:    {jorge.get('otros_nombres')!r}")
    print(f"    primer_apellido:  {jorge.get('primer_apellido')!r}")
    print(f"    segundo_apellido: {jorge.get('segundo_apellido')!r}")
    print(f"    razon_social:     {jorge.get('razon_social')!r}")
    assert jorge.get('primer_apellido') == 'GONZALEZ'
    assert jorge.get('primer_nombre') == 'JORGE'
    assert jorge.get('razon_social') is None
    print("  ✅ Auto-dividido correctamente")

# Inspeccionar el caso de jurídica sin razón social
problemático = resultado.terceros_pendientes.get('900322985')
assert problemático is not None, "Jurídica sin razón social debería estar pendiente"
print(f"\n  900322985 (jurídica sin razón social):")
print(f"    Errores: {problemático.errores}")
print("  ✅ Quedó pendiente para input manual")

# Darconter debe estar OK
darconter = resultado.terceros_completos.get('900304275')
assert darconter is not None
print(f"\n  ✅ DARCONTER S.A.S pasó validación sin problemas")

print()
print("=" * 70)
print("✅ TODOS LOS TESTS PASAN")
print("=" * 70)
