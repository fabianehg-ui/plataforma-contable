"""
Test del sistema de consecutivos:
   - Sugerencia automática del siguiente
   - Permitir al usuario sobreescribir
   - Detectar consecutivo ya usado
   - Registrar envío en histórico
"""
import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'core/exogena')

from datetime import datetime, date
from pathlib import Path

from generador_xml_v2 import (
    Tercero, TIPO_DOC_NIT,
    RegistroF1001, RegistroF1005,
)
from gestor_consecutivos import (
    GestorConsecutivos, SugerenciaConsecutivo, EnvioRegistrado,
    TIPO_ENVIO_INICIAL, TIPO_ENVIO_CORRECCION,
)
from generar_xml_exogena import (
    sugerir_consecutivo, sugerir_consecutivos_lote,
    generar_xml_con_consecutivo, generar_lote_xmls,
)


# ============================================================
# Mock Supabase — guarda en memoria
# ============================================================

class MockSupabase:
    """Cliente Supabase mock que mantiene un dict en memoria con los consecutivos."""
    
    def __init__(self):
        # estructura: {(empresa, año, formato, tipo): ultimo_consecutivo}
        self.consecutivos = {}
        # histórico de envíos: lista de dicts
        self.envios = []
        self._next_id = 1
    
    def rpc(self, function_name, params):
        if function_name == 'exogena_siguiente_consecutivo':
            key = (
                params['p_empresa_id'],
                params['p_ano_gravable'],
                params['p_formato'],
                params['p_tipo_envio'],
            )
            ultimo = self.consecutivos.get(key, 0)
            return MockResponse(data=[{'ultimo_usado': ultimo, 'siguiente': ultimo + 1}])
        
        elif function_name == 'exogena_registrar_envio':
            key = (
                params['p_empresa_id'],
                params['p_ano_gravable'],
                params['p_formato'],
                params['p_tipo_envio'],
            )
            
            # Validar duplicado
            for env in self.envios:
                if (env['empresa_id'] == params['p_empresa_id'] and
                    env['ano_gravable'] == params['p_ano_gravable'] and
                    env['formato'] == params['p_formato'] and
                    env['tipo_envio'] == params['p_tipo_envio'] and
                    env['consecutivo'] == params['p_consecutivo']):
                    raise Exception(
                        f"Consecutivo {params['p_consecutivo']} ya fue usado"
                    )
            
            envio_id = self._next_id
            self._next_id += 1
            self.envios.append({
                'id': envio_id,
                'empresa_id': params['p_empresa_id'],
                'ano_gravable': params['p_ano_gravable'],
                'formato': params['p_formato'],
                'version': params['p_version'],
                'tipo_envio': params['p_tipo_envio'],
                'consecutivo': params['p_consecutivo'],
                'nombre_archivo': params['p_nombre_archivo'],
                'cantidad_registros': params['p_cantidad_registros'],
                'valor_total': params['p_valor_total'],
                'fecha_generacion': datetime.now(),
            })
            
            # Actualizar contador (max del actual vs el nuevo)
            actual = self.consecutivos.get(key, 0)
            self.consecutivos[key] = max(actual, params['p_consecutivo'])
            
            return MockResponse(data=envio_id)
        
        raise NotImplementedError(f"RPC {function_name} no implementada en mock")


class MockResponse:
    def __init__(self, data):
        self.data = data
    
    def execute(self):
        return self


# ============================================================
# Datos de prueba
# ============================================================

EMPRESA_QS = '550e8400-e29b-41d4-a716-446655440000'  # UUID fake

def t(nit, raz):
    return Tercero(nit=nit, tipo_documento=TIPO_DOC_NIT, razon_social=raz,
                   codigo_pais='169', codigo_departamento='05', codigo_municipio='001',
                   direccion='CALLE 100 # 10-20')

regs_f1001 = [
    RegistroF1001(tercero=t('900380500','GRUPO ATOCHA SAS'), concepto=5004,
                  pago_deducible=263_157_894, retencion_renta_practicada=10_526_316),
]
regs_f1005 = [
    RegistroF1005(tercero=t('811000000','NOVAVENTA'), iva_descontable=4_510_408),
    RegistroF1005(tercero=t('900380500','GRUPO ATOCHA'), iva_descontable=50_000_000),
]


# ============================================================
# Tests
# ============================================================

mock_sb = MockSupabase()
gestor = GestorConsecutivos(mock_sb)

print("="*70)
print("TEST 1: Primera vez — debe sugerir consecutivo 1")
print("="*70)
sug = sugerir_consecutivo(gestor, EMPRESA_QS, 2025, '1001', '01')
print(f"  Sugerencia: ultimo_usado={sug.ultimo_usado}, siguiente={sug.siguiente}")
print(f"  ¿Es primer envío? {sug.es_primer_envio}")
assert sug.ultimo_usado == 0
assert sug.siguiente == 1
assert sug.es_primer_envio is True
print("  ✅ OK")


print()
print("="*70)
print("TEST 2: Generar XML con consecutivo automático (debe usar 1)")
print("="*70)
res = generar_xml_con_consecutivo(
    gestor=gestor,
    empresa_id=EMPRESA_QS,
    ano_gravable=2025,
    formato='1001',
    registros=regs_f1001,
    consecutivo=None,  # auto
    tipo_envio='01',
)
print(f"  Consecutivo usado: {res.consecutivo_usado}")
print(f"  Nombre archivo:    {res.nombre_archivo}")
print(f"  Envío ID en BD:    {res.envio_id}")
print(f"  Valor total:       ${res.valor_total:,.0f}")
print(f"  Registros:         {res.cantidad_registros}")
assert res.consecutivo_usado == 1
assert res.envio_id == 1
print("  ✅ OK")


print()
print("="*70)
print("TEST 3: Generar otra vez — debe sugerir 2")
print("="*70)
sug = sugerir_consecutivo(gestor, EMPRESA_QS, 2025, '1001', '01')
print(f"  Sugerencia: ultimo_usado={sug.ultimo_usado}, siguiente={sug.siguiente}")
assert sug.ultimo_usado == 1
assert sug.siguiente == 2
print("  ✅ OK")


print()
print("="*70)
print("TEST 4: Usuario decide sobrescribir y usar consecutivo 100")
print("="*70)
res = generar_xml_con_consecutivo(
    gestor=gestor,
    empresa_id=EMPRESA_QS,
    ano_gravable=2025,
    formato='1001',
    registros=regs_f1001,
    consecutivo=100,  # sobrescribe
    tipo_envio='01',
)
print(f"  Consecutivo usado: {res.consecutivo_usado}")
print(f"  Nombre archivo:    {res.nombre_archivo}")
assert res.consecutivo_usado == 100
print("  ✅ OK")


print()
print("="*70)
print("TEST 5: Después de usar 100, debe sugerir 101")
print("="*70)
sug = sugerir_consecutivo(gestor, EMPRESA_QS, 2025, '1001', '01')
print(f"  Sugerencia: siguiente={sug.siguiente}")
assert sug.siguiente == 101
print("  ✅ OK")


print()
print("="*70)
print("TEST 6: Intentar usar consecutivo 1 OTRA VEZ — debe fallar")
print("="*70)
try:
    res = generar_xml_con_consecutivo(
        gestor=gestor, empresa_id=EMPRESA_QS, ano_gravable=2025,
        formato='1001', registros=regs_f1001,
        consecutivo=1,  # ya usado!
        tipo_envio='01',
    )
    print("  ❌ Debió fallar pero no falló")
    raise AssertionError("Test 6 falló")
except ValueError as e:
    print(f"  Error esperado: {e}")
    assert 'ya fue usado' in str(e).lower()
    print("  ✅ OK — detectó duplicado")


print()
print("="*70)
print("TEST 7: Consecutivo INDEPENDIENTE por formato")
print("="*70)
# F1005 nunca se ha generado, debe sugerir 1 aunque F1001 ya tenga consecutivos
sug = sugerir_consecutivo(gestor, EMPRESA_QS, 2025, '1005', '01')
print(f"  F1005 (nunca generado): siguiente={sug.siguiente}")
assert sug.siguiente == 1

res = generar_xml_con_consecutivo(
    gestor=gestor, empresa_id=EMPRESA_QS, ano_gravable=2025,
    formato='1005', registros=regs_f1005,
)
print(f"  F1005 generado con consecutivo {res.consecutivo_usado}")
assert res.consecutivo_usado == 1
print("  ✅ OK — F1001 va en 101 y F1005 en 1, son independientes")


print()
print("="*70)
print("TEST 8: Consecutivo INDEPENDIENTE por tipo_envio")
print("="*70)
# Corrección de F1001 (tipo_envio '04') debe sugerir 1, no continuar el contador de '01'
sug = sugerir_consecutivo(gestor, EMPRESA_QS, 2025, '1001', '04')
print(f"  F1001 corrección (tipo 04, primera vez): siguiente={sug.siguiente}")
assert sug.siguiente == 1
print("  ✅ OK — contadores separados por tipo de envío")


print()
print("="*70)
print("TEST 9: Sugerencias en lote para los 11 formatos")
print("="*70)
formatos = ['1001', '1003', '1005', '1006', '1007', '1008', '1009', '1011', '1012', '1647', '2276']
sugerencias = sugerir_consecutivos_lote(gestor, EMPRESA_QS, 2025, formatos, '01')
print(f"  Sugerencias por formato:")
for fmt, sug in sugerencias.items():
    print(f"    F{fmt}: último={sug.ultimo_usado}, siguiente={sug.siguiente}")
assert sugerencias['1001'].siguiente == 101  # ya tenemos consecutivos
assert sugerencias['1005'].siguiente == 2    # ya generamos 1
assert sugerencias['2276'].siguiente == 1    # nunca generado
print("  ✅ OK")


print()
print("="*70)
print("TEST 10: Histórico en BD")
print("="*70)
print(f"  Total envíos en BD mock: {len(mock_sb.envios)}")
for e in mock_sb.envios:
    print(f"    #{e['id']}: F{e['formato']} tipo {e['tipo_envio']} consec {e['consecutivo']} → {e['nombre_archivo']}")
# Esperamos 3: test 2 (F1001 consec 1), test 4 (F1001 consec 100), test 7 (F1005 consec 1)
# Test 6 fue rechazado correctamente y NO se registró
assert len(mock_sb.envios) == 3, f"Esperaba 3 envíos exitosos, hay {len(mock_sb.envios)}"
print("  ✅ OK (3 envíos exitosos, test 6 fue rechazado correctamente)")


print()
print("="*70)
print("RESUMEN")
print("="*70)
print("✅ 10/10 tests pasan — sistema de consecutivos listo")
print()
print("Estado final del mock:")
print(f"  Consecutivos usados:")
for key, ultimo in sorted(mock_sb.consecutivos.items()):
    print(f"    F{key[2]} tipo {key[3]} → último usado: {ultimo}")
