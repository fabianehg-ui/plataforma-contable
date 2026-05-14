"""
Test del validador y auto-enriquecedor pre-generación.

Escenarios:
   1. Tercero completo → pasa directo
   2. Tercero incompleto + se enriquece desde mock RUES → pasa
   3. Persona natural sin datos → aplica fallback empresa
   4. Tercero sin nada y sin enriquecer → queda pendiente
   5. F1012 cuenta bancaria → infiere NIT del banco
"""
import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'core/exogena')
sys.path.insert(0, 'core/exogena/enriquecimiento')

from typing import Optional
from generador_xml_v2 import (
    Tercero, TIPO_DOC_NIT, TIPO_DOC_CC, PAIS_COLOMBIA,
    RegistroF1001, RegistroF1003, RegistroF1009, RegistroF1012, RegistroF2276,
)
from enriquecimiento.base import Enriquecedor, DatosEnriquecidos
from validador_pre_generacion import (
    validar_y_enriquecer,
    aplicar_terceros_a_registros,
    TerceroPendiente,
)


# Mock de enriquecedor: simula RUES con datos pre-cargados
class MockEnriquecedor(Enriquecedor):
    def __init__(self, datos_por_nit: dict):
        self.datos = datos_por_nit
        self.llamadas = []

    @property
    def nombre(self) -> str:
        return 'mock'

    def disponible(self) -> bool:
        return True

    def enriquecer(self, nit: str) -> Optional[DatosEnriquecidos]:
        self.llamadas.append(nit)
        return self.datos.get(nit)


# ============================================================
# Datos de prueba
# ============================================================

# Maestro actual: algunos completos, otros incompletos
TERCEROS_BD = {
    '900380500': {  # COMPLETO
        'tipo_documento': 31,
        'razon_social': 'GRUPO ATOCHA SAS',
        'direccion': 'CALLE 33 # 65-100',
        'codigo_dpto': '05',
        'codigo_municipio': '001',
        'codigo_pais': '169',
    },
    '800067065': {  # SIN dirección/dpto/mun → debe enriquecer
        'tipo_documento': 31,
        'razon_social': 'PROMOTORA MEDICA',
        'codigo_pais': '169',
    },
    '900111111': {  # SIN nada → debe quedar pendiente
        'tipo_documento': 31,
        'razon_social': 'EMPRESA SIN DATOS SA',
    },
    '1037612345': {  # PERSONA NATURAL sin dirección → fallback empresa
        'tipo_documento': 13,
        'primer_nombre': 'LAURA',
        'primer_apellido': 'RODRIGUEZ',
    },
    '860001234': {  # cuenta bancaria — sin tercero útil
        # Vacío a propósito, F1012 inferirá NIT desde el nombre
    },
}

# Mock de enriquecedor: tiene datos para 800067065
mock_rues_data = {
    '800067065': DatosEnriquecidos(
        nit='800067065',
        fuente='mock_rues',
        razon_social='PROMOTORA MEDICA LAS AMERICAS S.A.',
        direccion='CALLE 78B # 69-240',
        codigo_dpto='05',
        codigo_municipio='001',
    ),
}
mock_enriquecedor = MockEnriquecedor(mock_rues_data)


# Empresa informante (Quinto Sentido SAS)
INFO_EMPRESA = {
    'direccion': 'CARRERA 35 # 8-20 OF 1002',
    'codigo_dpto': '05',
    'codigo_municipio': '001',
    'codigo_pais': '169',
}


# ============================================================
# Registros simulados (output del adaptador)
# ============================================================

def t(nit):
    """Construye Tercero desde el dict de BD."""
    d = TERCEROS_BD.get(nit, {'nit': nit})
    return Tercero(
        nit=nit,
        tipo_documento=str(d.get('tipo_documento') or 31).zfill(2),
        razon_social=d.get('razon_social'),
        primer_nombre=d.get('primer_nombre'),
        primer_apellido=d.get('primer_apellido'),
        direccion=d.get('direccion'),
        codigo_departamento=d.get('codigo_dpto'),
        codigo_municipio=d.get('codigo_municipio'),
        codigo_pais=d.get('codigo_pais') or PAIS_COLOMBIA,
    )


registros = {
    '1001': [
        RegistroF1001(tercero=t('900380500'), concepto=5004, pago_deducible=100_000_000),
        RegistroF1001(tercero=t('800067065'), concepto=5002, pago_deducible=80_000_000),
        RegistroF1001(tercero=t('900111111'), concepto=5004, pago_deducible=10_000_000),
    ],
    '1009': [
        RegistroF1009(tercero=t('800067065'), concepto=2201, saldo=5_000_000),
    ],
    '1012': [
        # Cuenta bancaria con nombre indicativo del banco
        RegistroF1012(tercero=t('860001234'), concepto=1110, valor=185_000_000,
                       nota='BANCOLOMBIA AHORROS 12345'),
        # Otra cuenta sin info útil
        RegistroF1012(tercero=Tercero(nit='', tipo_documento='43',
                                       razon_social=None, codigo_pais=PAIS_COLOMBIA),
                       concepto=1120, valor=42_000_000,
                       nota='DAVIVIENDA Cta Cte'),
    ],
    '2276': [
        # Persona natural sin dirección
        RegistroF2276(
            entidad_informante=11,
            tipo_doc_beneficiario=TIPO_DOC_CC,
            nit_beneficiario='1037612345',
            primer_apellido='RODRIGUEZ',
            primer_nombre='LAURA',
            codigo_pais=PAIS_COLOMBIA,
            pagos_salarios=72_000_000,
            total_ingresos_brutos=72_000_000,
        ),
    ],
}


# ============================================================
# TEST PRINCIPAL
# ============================================================

print("=" * 70)
print("TEST DEL VALIDADOR PRE-GENERACIÓN")
print("=" * 70)

resultado = validar_y_enriquecer(
    registros_por_formato=registros,
    terceros_dict=TERCEROS_BD,
    info_empresa_informante=INFO_EMPRESA,
    enriquecedor=mock_enriquecedor,
)

print(f"\nTotal terceros procesados: {resultado.total_terceros}")
print(f"Completos:                 {len(resultado.terceros_completos)}")
print(f"Pendientes:                {resultado.total_pendientes}")
print(f"Enriquecidos auto:         {resultado.enriquecidos_auto}")
print(f"Fallback empresa:          {resultado.enriquecidos_fallback}")
print(f"Bancos inferidos (F1012):  {resultado.bancos_inferidos}")
print(f"Fuentes usadas:            {resultado.fuentes_usadas}")
print(f"NITs consultados al mock:  {mock_enriquecedor.llamadas}")

print()
print("=" * 70)
print("TERCEROS COMPLETOS DESPUÉS DE VALIDAR")
print("=" * 70)
for nit, datos in resultado.terceros_completos.items():
    rs = datos.get('razon_social') or f"{datos.get('primer_nombre','')} {datos.get('primer_apellido','')}".strip()
    fuente = datos.get('enriquecido_desde', '—')
    print(f"  {nit} ({rs[:30]:30s}) → {datos.get('direccion','—')[:30]} | "
          f"{datos.get('codigo_dpto','—')}/{datos.get('codigo_municipio','—')} "
          f"[fuente: {fuente}]")

print()
print("=" * 70)
print("TERCEROS PENDIENTES (REQUIEREN INPUT MANUAL)")
print("=" * 70)
for nit, p in resultado.terceros_pendientes.items():
    print(f"\n  NIT: {nit}")
    print(f"  Razón: {p.razon_social or '—'}")
    print(f"  Aparece en formatos: {p.formatos_afectados}")
    print(f"  Errores: {p.errores}")

# ============================================================
# Verificaciones
# ============================================================

print()
print("=" * 70)
print("VERIFICACIONES")
print("=" * 70)

# 1. 900380500 ya estaba completo → en completos
assert '900380500' in resultado.terceros_completos
print("✅ Tercero ya completo (900380500) pasa directo")

# 2. 800067065 se enriqueció con mock → en completos
assert '800067065' in resultado.terceros_completos
assert resultado.terceros_completos['800067065']['direccion'] == 'CALLE 78B # 69-240'
print("✅ Tercero incompleto enriquecido desde mock RUES")

# 3. 900111111 sin datos y sin enriquecer → pendiente
assert '900111111' in resultado.terceros_pendientes
print("✅ Tercero sin datos queda pendiente")

# 4. 1037612345 persona natural → fallback empresa aplicado
assert '1037612345' in resultado.terceros_completos
fb = resultado.terceros_completos['1037612345']
assert fb['direccion'] == INFO_EMPRESA['direccion']
print(f"✅ Persona natural con fallback empresa: dir='{fb['direccion'][:30]}...'")

# 5. F1012 NIT bancos inferidos
assert resultado.bancos_inferidos == 2
print(f"✅ F1012: {resultado.bancos_inferidos} bancos inferidos por nombre cuenta")

# Inspeccionar los registros F1012 después del enriquecimiento
print()
print("Estado de los registros F1012 después de inferir bancos:")
for reg in registros['1012']:
    print(f"  Concepto {reg.concepto}, NIT={reg.tercero.nit} "
          f"({reg.tercero.razon_social}), nota='{reg.nota}'")


# ============================================================
# TEST 2: aplicar_terceros_a_registros
# ============================================================
print()
print("=" * 70)
print("APLICAR ACTUALIZACIONES A REGISTROS")
print("=" * 70)

aplicar_terceros_a_registros(registros, resultado.terceros_completos)

# Verificar que el F1001 de 800067065 ahora tiene dirección
r_promotora = next(r for r in registros['1001'] if r.tercero.nit == '800067065')
print(f"F1001 800067065:")
print(f"  Razón: {r_promotora.tercero.razon_social}")
print(f"  Dirección: {r_promotora.tercero.direccion}")
print(f"  Dpto/Mun: {r_promotora.tercero.codigo_departamento}/{r_promotora.tercero.codigo_municipio}")
assert r_promotora.tercero.direccion == 'CALLE 78B # 69-240'
print("✅ Tercero enriquecido aplicado al registro F1001")

# Verificar F2276 con persona natural
r_laura = registros['2276'][0]
print(f"\nF2276 Laura Rodriguez:")
print(f"  Dirección: {r_laura.direccion}")
print(f"  Dpto/Mun: {r_laura.codigo_departamento}/{r_laura.codigo_municipio}")
assert r_laura.direccion == INFO_EMPRESA['direccion']
print("✅ F2276 actualizado con fallback empresa")

print()
print("=" * 70)
print("✅ TODOS LOS TESTS PASAN")
print("=" * 70)
