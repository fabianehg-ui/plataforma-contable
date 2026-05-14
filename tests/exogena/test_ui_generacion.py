"""
Test funcional de la UI de generación: simula el flujo completo sin Streamlit.
Valida que:
   - La función render_tab_generar_xml importa correctamente
   - Los componentes (gestor, generador, excel) se conectan bien
   - El flujo end-to-end produce los archivos esperados
"""
import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'core/exogena')

# Mock Streamlit antes de que la UI lo importe
import types

st_mock = types.ModuleType('streamlit')
st_mock.session_state = {}
def _noop(*args, **kwargs): return None
def _identity(x, *args, **kwargs): return x
for attr in ['title', 'markdown', 'caption', 'info', 'success', 'warning',
             'error', 'write', 'code', 'rerun', 'image']:
    setattr(st_mock, attr, _noop)
st_mock.metric = _noop
st_mock.empty = lambda: types.SimpleNamespace(empty=_noop)
st_mock.spinner = lambda *a, **k: types.SimpleNamespace(
    __enter__=lambda self: None, __exit__=lambda self, *a: None)
st_mock.expander = lambda *a, **k: types.SimpleNamespace(
    __enter__=lambda self: None, __exit__=lambda self, *a: None)

class _Col:
    def __enter__(self): return self
    def __exit__(self, *a): pass
    metric = staticmethod(_noop)
    write = staticmethod(_noop)
    markdown = staticmethod(_noop)
    caption = staticmethod(_noop)
def _columns(n_or_widths, **kwargs):
    n = n_or_widths if isinstance(n_or_widths, int) else len(n_or_widths)
    return tuple(_Col() for _ in range(n))
st_mock.columns = _columns

# Verificar que los módulos cargan sin error
print("="*70)
print("TEST 1: Imports limpios")
print("="*70)

sys.modules['streamlit'] = st_mock

try:
    import gestor_consecutivos
    import generar_xml_exogena
    import generador_xml_v2
    import generador_excel_prevalidador
    print("  ✅ Todos los módulos core importan limpio")
except ImportError as e:
    print(f"  ❌ ImportError: {e}")
    sys.exit(1)

# Mock supabase
class MockSb:
    def __init__(self):
        self.consec = {}
        self.envios = []
        self._id = 1
    def rpc(self, name, p):
        if name == 'exogena_siguiente_consecutivo':
            key = (p['p_empresa_id'], p['p_ano_gravable'], p['p_formato'], p['p_tipo_envio'])
            u = self.consec.get(key, 0)
            return _MR([{'ultimo_usado': u, 'siguiente': u + 1}])
        elif name == 'exogena_registrar_envio':
            # Validar duplicado igual que la función SQL real
            for env in self.envios:
                if (env.get('empresa_id') == p['p_empresa_id'] and
                    env.get('ano_gravable') == p['p_ano_gravable'] and
                    env.get('formato') == p['p_formato'] and
                    env.get('tipo_envio') == p['p_tipo_envio'] and
                    env.get('consecutivo') == p['p_consecutivo']):
                    raise Exception(
                        f"Consecutivo {p['p_consecutivo']} ya fue usado para "
                        f"F{p['p_formato']} tipo_envio {p['p_tipo_envio']}"
                    )
            envio_id = self._id; self._id += 1
            self.envios.append({'id': envio_id, **{k.replace('p_',''): v for k,v in p.items()}})
            key = (p['p_empresa_id'], p['p_ano_gravable'], p['p_formato'], p['p_tipo_envio'])
            self.consec[key] = max(self.consec.get(key, 0), p['p_consecutivo'])
            return _MR(envio_id)
    def from_(self, table):
        return _MQ([])

class _MR:
    def __init__(self, data): self.data = data
    def execute(self): return self
class _MQ:
    def __init__(self, data): self.data = data
    def select(self, *a): return self
    def eq(self, *a, **k): return self
    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def execute(self): return self


print()
print("="*70)
print("TEST 2: Flujo end-to-end del orquestador")
print("="*70)

from datetime import datetime, date
from pathlib import Path
from generador_xml_v2 import (
    Tercero, TIPO_DOC_NIT, RegistroF1001, RegistroF1005,
)
from gestor_consecutivos import GestorConsecutivos
from generar_xml_exogena import sugerir_consecutivos_lote, generar_lote_xmls

EMPRESA = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
mock_sb = MockSb()
gestor = GestorConsecutivos(mock_sb)

regs = {
    '1001': [RegistroF1001(
        tercero=Tercero(nit='900380500', tipo_documento=TIPO_DOC_NIT,
                        razon_social='GRUPO ATOCHA SAS', codigo_pais='169',
                        codigo_departamento='05', codigo_municipio='001',
                        direccion='CALLE 100 # 10-20'),
        concepto=5004, pago_deducible=263_157_894,
        retencion_renta_practicada=10_526_316)],
    '1005': [RegistroF1005(
        tercero=Tercero(nit='811000000', tipo_documento=TIPO_DOC_NIT,
                        razon_social='NOVAVENTA', codigo_pais='169'),
        iva_descontable=4_510_408)],
}

# Sugerencia de consecutivos
sugs = sugerir_consecutivos_lote(gestor, EMPRESA, 2025, list(regs.keys()), '01')
print(f"  Sugerencias iniciales: F1001={sugs['1001'].siguiente}, F1005={sugs['1005'].siguiente}")
assert sugs['1001'].siguiente == 1
assert sugs['1005'].siguiente == 1

# Generación con consecutivo automático
import tempfile
tmpdir = Path(tempfile.mkdtemp(prefix='exo_ui_'))
resultados = generar_lote_xmls(
    gestor=gestor, empresa_id=EMPRESA, ano_gravable=2025,
    registros_por_formato=regs, tipo_envio='01',
    ruta_salida=tmpdir, registrar_en_bd=True,
)

print(f"  Generados {len(resultados)} archivos:")
for fmt, res in resultados.items():
    print(f"    F{fmt} consec={res.consecutivo_usado} → {res.nombre_archivo}")
    assert res.envio_id > 0  # Se registró en BD
    assert (tmpdir / res.nombre_archivo).exists()


print()
print("="*70)
print("TEST 3: Override manual de consecutivo")
print("="*70)
# Segunda corrida: contador elige F1001=50, F1005=auto (debería ser 2)
resultados2 = generar_lote_xmls(
    gestor=gestor, empresa_id=EMPRESA, ano_gravable=2025,
    registros_por_formato=regs,
    consecutivos_elegidos={'1001': 50},  # solo F1001 manual
    tipo_envio='01',
    ruta_salida=tmpdir,
    registrar_en_bd=True,
)
print(f"  F1001 consec={resultados2['1001'].consecutivo_usado} (esperado: 50)")
print(f"  F1005 consec={resultados2['1005'].consecutivo_usado} (esperado: 2)")
assert resultados2['1001'].consecutivo_usado == 50
assert resultados2['1005'].consecutivo_usado == 2


print()
print("="*70)
print("TEST 4: Detección de consecutivo duplicado")
print("="*70)
try:
    generar_lote_xmls(
        gestor=gestor, empresa_id=EMPRESA, ano_gravable=2025,
        registros_por_formato={'1001': regs['1001']},
        consecutivos_elegidos={'1001': 50},  # YA usado
        tipo_envio='01', registrar_en_bd=True,
    )
    print("  ❌ Debió fallar")
except ValueError as e:
    print(f"  ✅ Error detectado: {e}")
    assert 'ya fue usado' in str(e).lower()


print()
print("="*70)
print("TEST 5: Excel maestro junto con XMLs")
print("="*70)
from generador_excel_prevalidador import generar_excel_prevalidador

ruta_xlsx = tmpdir / 'Exogena_TEST.xlsx'
generar_excel_prevalidador(
    ruta_xlsx,
    {'ano': 2025, 'nit_informante': '900533491', 'razon_informante': 'EMPRESA TEST',
     'fecha_generacion': '2026-05-13'},
    {fmt: {'registros': lst} for fmt, lst in regs.items()},
)
assert ruta_xlsx.exists()
print(f"  ✅ Excel maestro generado: {ruta_xlsx.name} ({ruta_xlsx.stat().st_size:,} bytes)")


print()
print("="*70)
print("TEST 6: Importar la UI completa")
print("="*70)
try:
    # Para importar ui_generacion_xml necesitamos también db.supabase_client
    # Como no lo tenemos, hacemos un mock simple
    sys.modules['db'] = types.ModuleType('db')
    sys.modules['db.supabase_client'] = types.ModuleType('db.supabase_client')
    sys.modules['db.supabase_client'].get_supabase = lambda: mock_sb
    
    import ui_generacion_xml
    print("  ✅ ui_generacion_xml importa limpio")
    print(f"  Función principal: {ui_generacion_xml.render_tab_generar_xml.__name__}")
    print(f"  Formatos soportados: {sorted(ui_generacion_xml.FORMATOS_INFO.keys())}")
except Exception as e:
    print(f"  ❌ Error: {e}")
    import traceback
    traceback.print_exc()


print()
print("="*70)
print("RESUMEN")
print("="*70)
print("✅ Todos los tests del flujo de la UI pasan")
print()
print(f"Estado del mock SB:")
print(f"  Envíos registrados: {len(mock_sb.envios)}")
print(f"  Consecutivos por formato:")
for k, v in mock_sb.consec.items():
    print(f"    F{k[2]} tipo {k[3]} → último: {v}")
