"""
Test integral FINAL: los 11 formatos para Quinto Sentido SAS con sistema
de consecutivos automáticos.

Simula el flujo completo de la UI:
   1. Sugerir consecutivos para los 11 formatos
   2. Generar XMLs (con consecutivos auto o elegidos por el contador)
   3. Registrar todo en histórico
"""
import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'core/exogena')

from datetime import datetime, date
from pathlib import Path
from lxml import etree

from generador_xml_v2 import (
    Tercero, TerceroDestino,
    TIPO_DOC_NIT, TIPO_DOC_CC, TIPO_DOC_NEX,
    RegistroF1001, RegistroF1003, RegistroF1005, RegistroF1006, RegistroF1007,
    RegistroF1008, RegistroF1009, RegistroF1011, RegistroF1012,
    RegistroF1647, RegistroF2276,
)
from gestor_consecutivos import GestorConsecutivos, TIPO_ENVIO_INICIAL
from generar_xml_exogena import (
    sugerir_consecutivos_lote,
    generar_lote_xmls,
)


# Mock Supabase (mismo de test_consecutivos.py)
class MockSupabase:
    def __init__(self):
        self.consecutivos = {}
        self.envios = []
        self._next_id = 1
    
    def rpc(self, function_name, params):
        if function_name == 'exogena_siguiente_consecutivo':
            key = (params['p_empresa_id'], params['p_ano_gravable'],
                   params['p_formato'], params['p_tipo_envio'])
            ultimo = self.consecutivos.get(key, 0)
            return _MockResp([{'ultimo_usado': ultimo, 'siguiente': ultimo + 1}])
        
        elif function_name == 'exogena_registrar_envio':
            for env in self.envios:
                if (env['empresa_id'] == params['p_empresa_id'] and
                    env['formato'] == params['p_formato'] and
                    env['tipo_envio'] == params['p_tipo_envio'] and
                    env['consecutivo'] == params['p_consecutivo']):
                    raise Exception(f"Consecutivo {params['p_consecutivo']} ya fue usado")
            envio_id = self._next_id
            self._next_id += 1
            self.envios.append({'id': envio_id, **{k.replace('p_',''): v for k,v in params.items()}})
            key = (params['p_empresa_id'], params['p_ano_gravable'],
                   params['p_formato'], params['p_tipo_envio'])
            self.consecutivos[key] = max(self.consecutivos.get(key, 0), params['p_consecutivo'])
            return _MockResp(envio_id)
        raise NotImplementedError(function_name)


class _MockResp:
    def __init__(self, data): self.data = data
    def execute(self): return self


def validar_xml(xml, fmt):
    xsd = etree.XMLSchema(etree.parse(f'core/exogena/xsd/{fmt}.xsd'))
    doc = etree.fromstring(xml.encode('ISO-8859-1'))
    return xsd.validate(doc)


def t_juridico(nit, raz):
    return Tercero(nit=nit, tipo_documento=TIPO_DOC_NIT, razon_social=raz,
                   codigo_pais='169', codigo_departamento='05', codigo_municipio='001',
                   direccion='CALLE 100 # 10-20 MEDELLIN')


# ============================================================
# Datos de Quinto Sentido
# ============================================================
EMPRESA_QS = '550e8400-e29b-41d4-a716-446655440000'
ANO = 2025

regs_por_formato = {
    '1001': [
        RegistroF1001(tercero=t_juridico('900380500', 'GRUPO ATOCHA SAS'),
                      concepto=5004, pago_deducible=263_157_894,
                      retencion_renta_practicada=10_526_316,
                      retencion_iva_responsables=5_000_000),
        RegistroF1001(tercero=t_juridico('800067065', 'PROMOTORA MEDICA'),
                      concepto=5002, pago_deducible=248_566_858,
                      retencion_renta_practicada=24_856_686),
    ],
    '1003': [
        RegistroF1003(tercero=t_juridico('800067065', 'PROMOTORA MEDICA'),
                      concepto=1301, valor_base=100_000_000, retencion=3_500_000),
    ],
    '1005': [
        RegistroF1005(tercero=t_juridico('811000000', 'NOVAVENTA'), iva_descontable=4_510_408),
        RegistroF1005(tercero=t_juridico('900380500', 'GRUPO ATOCHA SAS'), iva_descontable=50_000_000),
    ],
    '1006': [
        RegistroF1006(tercero=t_juridico('800067065', 'PROMOTORA MEDICA'), iva_generado=53_628_800),
        RegistroF1006(tercero=t_juridico('900380500', 'SILLA TRES SAS'),
                      iva_generado=64_941_240, iva_dev_compras=27_528_172),
    ],
    '1007': [
        RegistroF1007(tercero=t_juridico('800067065', 'PROMOTORA MEDICA'),
                      concepto=4001, ingresos_brutos=282_257_894),
        RegistroF1007(tercero=t_juridico('900380500', 'SILLA TRES SAS'),
                      concepto=4001, ingresos_brutos=341_796_000),
    ],
    '1008': [
        RegistroF1008(tercero=t_juridico('900380500', 'GRUPO ATOCHA'),
                      concepto=1315, saldo=85_000_000),
    ],
    '1009': [
        RegistroF1009(tercero=t_juridico('900380500', 'GRUPO ATOCHA'),
                      concepto=2201, saldo=120_000_000),
        RegistroF1009(tercero=t_juridico('800173052', 'EPS SURA'),
                      concepto=2214, saldo=2_500_000),
    ],
    '1011': [
        RegistroF1011(concepto=8001, saldo=2_500_000_000),
        RegistroF1011(concepto=8002, saldo=1_200_000_000),
    ],
    '1012': [
        RegistroF1012(tercero=t_juridico('860001234', 'BANCOLOMBIA SA'),
                      concepto=1110, valor=185_000_000),
    ],
    '1647': [
        RegistroF1647(
            tercero=t_juridico('800067065', 'PROMOTORA MEDICA'),
            tercero_destino=TerceroDestino(
                nit='900380500', tipo_documento=TIPO_DOC_NIT,
                razon_social='SILLA TRES SAS', codigo_pais='169',
                codigo_departamento='05', codigo_municipio='001',
                direccion='CALLE 33 # 65-100',
            ),
            concepto=4040,
            valor_total=50_000_000,
            valor_ingreso_transferido=25_000_000,
            valor_retencion_transferida=1_250_000,
        ),
    ],
    '2276': [
        RegistroF2276(
            entidad_informante=11,
            tipo_doc_beneficiario=TIPO_DOC_CC,
            nit_beneficiario='1037612345',
            primer_apellido='RODRIGUEZ',
            primer_nombre='LAURA',
            codigo_pais='169',
            pagos_salarios=72_000_000,
            cesantias_consignadas=6_000_000,
            total_ingresos_brutos=78_000_000,
            aportes_obligatorios_salud=2_880_000,
            aportes_obligatorios_pension=2_880_000,
            retencion_fuente=3_240_000,
            ingreso_laboral_promedio_6m=6_000_000,
        ),
    ],
}


# ============================================================
# Setup gestor con BD mock
# ============================================================
mock_sb = MockSupabase()
gestor = GestorConsecutivos(mock_sb)


# ============================================================
# ESCENARIO 1: Primera vez generando exógena para Quinto Sentido
# ============================================================
print("="*70)
print("ESCENARIO 1: Primera vez — sugerencias para los 11 formatos")
print("="*70)
formatos = list(regs_por_formato.keys())
sugs = sugerir_consecutivos_lote(gestor, EMPRESA_QS, ANO, formatos, '01')

print(f"\n{'Formato':10s} {'Último':>8s}  {'Siguiente':>10s}  Estado")
print("-" * 60)
for fmt in formatos:
    s = sugs[fmt]
    estado = '🆕 Primer envío' if s.es_primer_envio else f'Continúa desde {s.ultimo_usado}'
    print(f"F{fmt:9s} {s.ultimo_usado:>8d}  {s.siguiente:>10d}  {estado}")


# ============================================================
# ESCENARIO 2: Contador acepta los consecutivos sugeridos
# ============================================================
print()
print("="*70)
print("ESCENARIO 2: Contador acepta sugerencias y genera todo")
print("="*70)

out_dir = Path('/tmp/qs_consecutivos/xml')
out_dir.mkdir(parents=True, exist_ok=True)

resultados = generar_lote_xmls(
    gestor=gestor,
    empresa_id=EMPRESA_QS,
    ano_gravable=ANO,
    registros_por_formato=regs_por_formato,
    consecutivos_elegidos=None,    # usa los sugeridos
    tipo_envio='01',
    ruta_salida=out_dir,
    registrar_en_bd=True,
)

print(f"\n{'Formato':8s} {'Consec':>6s}  {'Archivo':45s}  {'Valor':>15s}  XSD")
print("-" * 95)
todos_ok = True
for fmt, res in resultados.items():
    xml_ok = validar_xml(res.xml, fmt)
    if not xml_ok: todos_ok = False
    print(f"F{fmt:7s} {res.consecutivo_usado:>6d}  {res.nombre_archivo:45s}  ${res.valor_total:>13,.0f}  {'✅' if xml_ok else '❌'}")


# ============================================================
# ESCENARIO 3: Segunda generación (correcciones) — sugiere siguientes
# ============================================================
print()
print("="*70)
print("ESCENARIO 3: Segunda corrida — debe sugerir consecutivos +1")
print("="*70)

sugs2 = sugerir_consecutivos_lote(gestor, EMPRESA_QS, ANO, formatos, '01')
print(f"\n{'Formato':10s} {'Último':>8s}  {'Siguiente':>10s}")
print("-" * 40)
for fmt in formatos:
    s = sugs2[fmt]
    print(f"F{fmt:9s} {s.ultimo_usado:>8d}  {s.siguiente:>10d}")


# ============================================================
# ESCENARIO 4: Contador sobrescribe el consecutivo de F1001 a 100
# ============================================================
print()
print("="*70)
print("ESCENARIO 4: Contador elige consecutivo manual para F1001 (= 100)")
print("="*70)

consec_elegidos = {'1001': 100}  # solo F1001 manual, resto auto
res = generar_lote_xmls(
    gestor=gestor,
    empresa_id=EMPRESA_QS,
    ano_gravable=ANO,
    registros_por_formato={'1001': regs_por_formato['1001'],
                            '1003': regs_por_formato['1003']},  # solo 2 formatos
    consecutivos_elegidos=consec_elegidos,
    tipo_envio='01',
    ruta_salida=out_dir,
    registrar_en_bd=True,
)
print(f"  F1001 generado con consecutivo: {res['1001'].consecutivo_usado} (manual)")
print(f"  F1003 generado con consecutivo: {res['1003'].consecutivo_usado} (auto)")
assert res['1001'].consecutivo_usado == 100
assert res['1003'].consecutivo_usado == 2


# ============================================================
# ESCENARIO 5: Después de usar 100, debe sugerir 101
# ============================================================
print()
print("="*70)
print("ESCENARIO 5: Después de F1001 consec 100, siguiente es 101")
print("="*70)
sug_post = gestor.siguiente_consecutivo(EMPRESA_QS, ANO, '1001', '01')
print(f"  F1001 último={sug_post.ultimo_usado}, siguiente={sug_post.siguiente}")
assert sug_post.siguiente == 101


# ============================================================
# RESUMEN FINAL
# ============================================================
print()
print("="*70)
print("RESUMEN FINAL")
print("="*70)

print(f"\n📊 Total envíos generados en esta sesión: {len(mock_sb.envios)}")
print(f"\n📁 XMLs guardados en: {out_dir}")
xmls = sorted(out_dir.glob('*.xml'))
for x in xmls:
    print(f"   - {x.name}")

print(f"\n🔢 Consecutivos finales:")
for key, ultimo in sorted(mock_sb.consecutivos.items()):
    print(f"   F{key[2]} tipo {key[3]} → último usado: {ultimo}")

print()
print(f"Estado XSD: {'✅ TODOS PASAN' if todos_ok else '❌ HAY ERRORES'}")
print()
print("✅ Sistema de consecutivos integrado y funcionando")
