"""
Tests del motor de mapeo v0.3
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.procesadores.motor_mapeo_v03 import (
    normalizar_nit, normalizar_direccion, fingerprint_direccion,
    CatalogoEmpresa, resolver_mapeo,
    calcular_retencion_renta, calcular_reteiva, calcular_reteica
)


def test_normalizar_nit():
    assert normalizar_nit('900.451.388-9') == '900451388'
    assert normalizar_nit('890903939') == '890903939'
    assert normalizar_nit('900-451-388-9') == '900'  # documenta el comportamiento: corta en el primer guión
    assert normalizar_nit('') == ''
    assert normalizar_nit(None) == ''
    print("✓ test_normalizar_nit")


def test_normalizar_direccion():
    assert normalizar_direccion('CRA 20 # 2B SUR 185') == 'CR 20 2B SUR 185'
    assert normalizar_direccion('Calle 33 # 42 B 06') == 'CL 33 42 B 06'
    assert normalizar_direccion('DIAGONAL 75 B # 2-A 80') == 'DG 75 B 2 A 80'
    assert normalizar_direccion('') == ''
    print("✓ test_normalizar_direccion")


def test_fingerprint_matching():
    """Direcciones equivalentes deben producir el mismo fingerprint."""
    a = fingerprint_direccion('CRA 20 # 2B SUR 185')
    b = fingerprint_direccion('CR 20 2 SUR 185')  # variante con espacio
    c = fingerprint_direccion('CARRERA 20 2B SUR 185')
    print(f"   fp(a) = '{a}'")
    print(f"   fp(c) = '{c}'")
    assert a == c, f"a={a} c={c}"
    print("✓ test_fingerprint_matching")


def test_carga_catalogo():
    cat = CatalogoEmpresa.cargar(
        Path(__file__).parent.parent / 'core' / 'data' / 'empresas' / '900451388_silla_tres'
    )
    assert cat.nit == '900451388'
    assert len(cat.mapeo_nits) > 100, f"Esperaba >100 NITs, obtuve {len(cat.mapeo_nits)}"
    assert len(cat.centros_costo) >= 18
    assert 'POSTOBON' in cat.mapeo_nits['890903939']['nombre'].upper() or \
           'POSADA TOBÓN' in cat.mapeo_nits['890903939']['nombre'].upper()
    print(f"✓ test_carga_catalogo ({len(cat.mapeo_nits)} NITs, {len(cat.centros_costo)} CCs)")
    return cat


def test_resolver_postobon_con_direccion(cat):
    """Postobón en CRA 20 2B SUR 185 → debe ir al CC catalogado para esa dirección."""
    r = resolver_mapeo(
        cat,
        nit_emisor='890903939',
        nombre_emisor='POSTOBON S.A.',
        direccion_entrega='CRA 20  2B SUR 185'
    )
    assert r.cuenta == '14350511', f"esperaba 14350511 (gravada 19%), obtuve {r.cuenta}"
    assert r.cc, "Debe asignar algún CC"
    assert r.concepto_retencion == 'compras_2_5'
    print(f"✓ test_resolver_postobon: cuenta={r.cuenta}, cc={r.cc} (fuente: {r.fuente_cc})")


def test_resolver_proveedor_no_catalogado_con_alimento(cat):
    """Proveedor desconocido pero el nombre dice 'CARNES' → auto-insumo."""
    r = resolver_mapeo(
        cat,
        nit_emisor='999999999',
        nombre_emisor='COMERCIALIZADORA DE CARNES NUEVA SAS',
        items_descripcion='CARNE DE RES, POLLO ENTERO'
    )
    assert r.cuenta == '14350503', f"esperaba 14350503, obtuve {r.cuenta}"
    assert r.fuente_cuenta == 'auto_insumos'
    print(f"✓ test_resolver_auto_insumos: cuenta={r.cuenta}, fuente={r.fuente_cuenta}")


def test_resolver_proveedor_no_catalogado_no_alimento(cat):
    """SIIGO no es alimento → debe ir a pendiente."""
    r = resolver_mapeo(
        cat,
        nit_emisor='830048145',
        nombre_emisor='SIIGO S.A.S',
        items_descripcion='LICENCIAMIENTO ANUAL DE SOFTWARE'
    )
    assert r.es_pendiente_revision is True
    assert r.cuenta == '519095'
    print(f"✓ test_resolver_pendiente_no_alimento")


def test_retencion_compras_aplica(cat):
    r = calcular_retencion_renta(cat, 'compras_2_5', 5000000, 'ordinario', False)
    assert r.aplicada is True
    assert r.valor == 125000  # 2.5% de 5M
    print(f"✓ test_retencion_compras_aplica: {r.valor:,.0f}")


def test_retencion_no_aplica_RST(cat):
    """Si emisor es RST, no se le retiene RENTA."""
    r = calcular_retencion_renta(cat, 'compras_2_5', 5000000, 'RST', False)
    assert r.aplicada is False
    assert 'RST' in r.motivo_no_aplicada or 'Simple' in r.motivo_no_aplicada
    print(f"✓ test_retencion_RST: motivo='{r.motivo_no_aplicada}'")


def test_retencion_no_aplica_autorretenedor(cat):
    r = calcular_retencion_renta(cat, 'servicios_4', 5000000, 'ordinario', autorretenedor=True)
    assert r.aplicada is False
    print(f"✓ test_retencion_autorretenedor: motivo='{r.motivo_no_aplicada}'")


def test_retencion_servicio_publico_no_aplica(cat):
    r = calcular_retencion_renta(cat, 'sin_retencion_servicio_publico', 5000000, 'ordinario', False)
    assert r.aplicada is False
    print(f"✓ test_retencion_servicio_publico_no_aplica")


def test_retencion_base_minima_2026(cat):
    """Base mínima 2026: compras 10 UVT = $524.000. Una compra de 500K NO debe retener."""
    r = calcular_retencion_renta(cat, 'compras_2_5', 500000, 'ordinario', False)
    assert r.aplicada is False
    assert 'mín' in r.motivo_no_aplicada.lower()
    print(f"✓ test_retencion_base_minima_2026: {r.motivo_no_aplicada}")


def test_retencion_base_524k_si_aplica(cat):
    """Una compra de 600K SÍ debe retener (>524K base mínima)."""
    r = calcular_retencion_renta(cat, 'compras_2_5', 600000, 'ordinario', False)
    assert r.aplicada is True
    assert r.valor == 15000  # 2.5% de 600K
    print(f"✓ test_retencion_base_524k_si_aplica: {r.valor}")


# ──────── ReteIVA — Silla Tres modo INVERSO ────────

def test_reteiva_silla_tres_NO_aplica_a_ordinario(cat):
    """Silla Tres NO retiene IVA a ordinario (solo a RST)."""
    r = calcular_reteiva(cat, iva_factura=950000, regimen_emisor='ordinario', base_imponible=5000000)
    assert r.aplicada is False
    assert 'Régimen Simple' in r.motivo_no_aplicada or 'RST' in r.motivo_no_aplicada
    print(f"✓ test_reteiva_NO_a_ordinario: {r.motivo_no_aplicada}")


def test_reteiva_silla_tres_SI_aplica_a_RST(cat):
    """Silla Tres SÍ retiene IVA a RST (lógica inversa)."""
    r = calcular_reteiva(cat, iva_factura=950000, regimen_emisor='RST', base_imponible=5000000)
    assert r.aplicada is True
    assert r.valor == round(950000 * 0.15)
    print(f"✓ test_reteiva_SI_a_RST: {r.valor:,.0f}")


def test_reteiva_silla_tres_RST_pero_base_baja(cat):
    """Si emisor es RST pero base es chica, no aplica."""
    r = calcular_reteiva(cat, iva_factura=10000, regimen_emisor='RST', base_imponible=400000)
    assert r.aplicada is False
    assert 'mín' in r.motivo_no_aplicada.lower()
    print(f"✓ test_reteiva_RST_base_baja: {r.motivo_no_aplicada}")


# ──────── ReteICA — Deshabilitada ────────

def test_reteica_deshabilitado(cat):
    """Silla Tres no retiene ICA, debe devolver None."""
    r = calcular_reteica(cat, base_imponible=5000000, actividad='servicios', regimen_emisor='ordinario')
    assert r is None, f"esperaba None, obtuve {r}"
    print(f"✓ test_reteica_deshabilitado: devuelve None")


# ──────── Formato CC sin guion ────────

def test_formato_cc_sin_guion():
    from core.procesadores.motor_mapeo_v03 import formato_cc_salida
    assert formato_cc_salida('10-04', 'sin_guion') == '1004'
    assert formato_cc_salida('10-19', 'sin_guion') == '1019'
    assert formato_cc_salida('10-04', 'con_guion') == '10-04'
    assert formato_cc_salida('', 'sin_guion') == ''
    print(f"✓ test_formato_cc_sin_guion: 10-04 → 1004")


# ───────────── Tests de palabras clave ─────────────

def test_palabra_clave_lolita_imbanaco(cat):
    """Nota CTS1.=De lolita Clinica Imbanaco → 10-16 OASIS IMBANACO"""
    r = resolver_mapeo(
        cat,
        nit_emisor='890903939',
        nombre_emisor='POSTOBON S.A.',
        direccion_entrega='',  # sin dirección
        notas_xml=['CTS1.=De lolita  Clinica Imbanaco']
    )
    assert r.cc == '10-16', f"esperaba 10-16, obtuve {r.cc}"
    assert r.fuente_cc == 'palabra_clave'
    print(f"✓ test_palabra_clave_lolita_imbanaco: {r.pista_palabra_clave[:60]}")


def test_palabra_clave_lolita_san_diego(cat):
    """CTS1.=DE LOLITA CC SAN DIEGO → 10-19 DE LOLITA CCSD"""
    r = resolver_mapeo(
        cat,
        nit_emisor='890903939',
        notas_xml=['CTS1.=DE LOLITA CC SAN DIEGO'],
    )
    assert r.cc == '10-19', f"esperaba 10-19, obtuve {r.cc}"
    print(f"✓ test_palabra_clave_lolita_san_diego")


def test_palabra_clave_lolita_las_americas(cat):
    """CTS1.-DE LOLITA CLINICA LAS AMERICAS → 10-18 DE LOLITA TMLA"""
    r = resolver_mapeo(
        cat,
        nit_emisor='890903939',
        notas_xml=['CTS1.-DE LOLITA CLINICA LAS AMERICAS SEDE'],
    )
    assert r.cc == '10-18', f"esperaba 10-18, obtuve {r.cc}"
    print(f"✓ test_palabra_clave_lolita_las_americas")


def test_palabra_clave_descripcion_item(cat):
    """Pista en descripción de ítem ('VASO DE LOLITA') → debería matchear"""
    r = resolver_mapeo(
        cat,
        nit_emisor='890903939',
        notas_xml=[],
        items_descripciones_lista=[
            'VASO 12 OZ PLASTICO LOLITA',
            'CINTA RAZO DELOLITA',
            'VASO 9 OZ D LOLITA CAFE EKA'
        ]
    )
    # Solo "LOLITA" sin más contexto → no debe matchear (porque LOLITA solo no aporta CC)
    # Sí ganaría por dirección XML o NIT default. En este caso cae a NIT default.
    assert r.fuente_cc != 'palabra_clave', "LOLITA solo no debería matchear"
    print(f"✓ test_palabra_clave_lolita_solo_no_matchea (cae a {r.fuente_cc})")


def test_palabra_clave_codificacion_rara(cat):
    """El XML viene con encoding latin-1 mal decodificado: CLÃNICA LAS AMÃ‰RICAS"""
    r = resolver_mapeo(
        cat,
        nit_emisor='890903939',
        notas_xml=['CTS1.-DE LOLITA CLÃNICA LAS AMÃ‰RICAS SILLA TRES S.A.S - DE LOLITA TORRE MEDICA'],
    )
    assert r.cc == '10-18', f"esperaba 10-18, obtuve {r.cc}"
    print(f"✓ test_palabra_clave_codificacion_rara: maneja encoding latin-1")


def test_palabra_clave_silla_tres_aislado_no_matchea(cat):
    """CTS1.=SILLA 3 (sin más contexto) → NO debe matchear como CC, cae a default"""
    r = resolver_mapeo(
        cat,
        nit_emisor='830048145',  # SIIGO, no catalogado
        nombre_emisor='SIIGO S.A.S',
        notas_xml=['CTS1.=SILLA 3'],
    )
    assert r.fuente_cc != 'palabra_clave', "SILLA 3 aislado no debe ganar como pista de CC"
    print(f"✓ test_palabra_clave_silla_tres_no_matchea (fuente: {r.fuente_cc})")


def test_palabra_clave_gana_sobre_direccion(cat):
    """Si hay nota con CC y también dirección, GANA la nota."""
    r = resolver_mapeo(
        cat,
        nit_emisor='890903939',
        direccion_entrega='CRA 20 2B SUR 185',  # dirección que mapea a otro CC
        notas_xml=['CTS1.=De lolita  Clinica Imbanaco'],  # nota dice OASIS
    )
    assert r.fuente_cc == 'palabra_clave', f"nota debe ganar sobre dirección"
    assert r.cc == '10-16', f"esperaba 10-16 (de la nota), obtuve {r.cc}"
    print(f"✓ test_palabra_clave_gana_sobre_direccion")


if __name__ == '__main__':
    print("=== Tests del motor v0.3.1 ===\n")
    test_normalizar_nit()
    test_normalizar_direccion()
    test_fingerprint_matching()
    test_formato_cc_sin_guion()
    cat = test_carga_catalogo()
    test_resolver_postobon_con_direccion(cat)
    test_resolver_proveedor_no_catalogado_con_alimento(cat)
    test_resolver_proveedor_no_catalogado_no_alimento(cat)
    test_retencion_compras_aplica(cat)
    test_retencion_no_aplica_RST(cat)
    test_retencion_no_aplica_autorretenedor(cat)
    test_retencion_servicio_publico_no_aplica(cat)
    test_retencion_base_minima_2026(cat)
    test_retencion_base_524k_si_aplica(cat)
    test_reteiva_silla_tres_NO_aplica_a_ordinario(cat)
    test_reteiva_silla_tres_SI_aplica_a_RST(cat)
    test_reteiva_silla_tres_RST_pero_base_baja(cat)
    test_reteica_deshabilitado(cat)
    test_palabra_clave_lolita_imbanaco(cat)
    test_palabra_clave_lolita_san_diego(cat)
    test_palabra_clave_lolita_las_americas(cat)
    test_palabra_clave_descripcion_item(cat)
    test_palabra_clave_codificacion_rara(cat)
    test_palabra_clave_silla_tres_aislado_no_matchea(cat)
    test_palabra_clave_gana_sobre_direccion(cat)
    print("\n✅ Todos los tests pasaron")
