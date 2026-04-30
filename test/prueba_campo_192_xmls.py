"""
Prueba de campo: procesa los 192 XMLs reales de Silla Tres marzo 2026
y muestra cómo el motor v0.3 los clasifica.
"""
import json
import sys
import xml.etree.ElementTree as ET
import glob
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.procesadores.motor_mapeo_v03 import (
    CatalogoEmpresa, resolver_mapeo, normalizar_nit, formato_cc_salida,
    calcular_retencion_renta, calcular_reteiva, calcular_reteica
)
from core.procesadores.detector_tipo_doc import (
    detectar_tipo_documento, mapear_a_comprobante
)


NS = {
    'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
    'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
}


def get_inner(root):
    tag = root.tag.split('}')[-1]
    if tag == 'AttachedDocument':
        for desc in root.iter('{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}Description'):
            if desc.text and ('<Invoice' in desc.text or '<CreditNote' in desc.text or '<DebitNote' in desc.text):
                try:
                    return ET.fromstring(desc.text)
                except Exception:
                    pass
    return root


def extraer_doc(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            c = f.read()
        root = ET.fromstring(c)
    except Exception:
        return None
    inner = get_inner(root)

    sup = inner.find('.//cac:AccountingSupplierParty', NS)
    nit_emi = (sup.find('.//cbc:CompanyID', NS).text
               if sup is not None and sup.find('.//cbc:CompanyID', NS) is not None else '')
    nombre_emi = (sup.find('.//cbc:RegistrationName', NS).text
                  if sup is not None and sup.find('.//cbc:RegistrationName', NS) is not None else '')

    delivery_line = ''
    for d in inner.findall('.//cac:Delivery', NS):
        line = d.find('.//cbc:Line', NS)
        if line is not None and line.text:
            delivery_line = line.text.strip()
            break

    total = inner.find('.//cac:LegalMonetaryTotal/cbc:PayableAmount', NS)
    total_val = float(total.text) if total is not None and total.text else 0.0

    base_imponible_total = 0.0
    iva_total = 0.0
    for tt in inner.findall('.//cac:TaxTotal', NS):
        for ts in tt.findall('.//cac:TaxSubtotal', NS):
            cat = ts.find('.//cac:TaxCategory/cac:TaxScheme/cbc:ID', NS)
            tax_amount = ts.find('.//cbc:TaxAmount', NS)
            taxable = ts.find('.//cbc:TaxableAmount', NS)
            if cat is not None and cat.text == '01' and tax_amount is not None:
                try:
                    iva_total += float(tax_amount.text or 0)
                    base_imponible_total += float(taxable.text or 0) if taxable is not None else 0
                except Exception:
                    pass

    descripciones = []
    for line in inner.findall('.//cac:InvoiceLine', NS) + inner.findall('.//cac:CreditNoteLine', NS) + inner.findall('.//cac:DebitNoteLine', NS):
        for desc in line.findall('.//cac:Item/cbc:Description', NS):
            if desc.text:
                descripciones.append(desc.text)

    # Notas a nivel documento (cbc:Note) - clave para detectar pistas tipo "CTS1.=..."
    notas = []
    for note in inner.findall('.//cbc:Note', NS):
        if note.text:
            notas.append(note.text)

    return {
        'archivo': Path(path).name,
        'nit_emisor': nit_emi,
        'nombre_emisor': nombre_emi,
        'direccion_entrega': delivery_line,
        'total': total_val,
        'iva': iva_total,
        'base_imponible': base_imponible_total or (total_val - iva_total if iva_total else total_val),
        'items_descripcion': ' || '.join(descripciones[:20]),
        'items_descripciones_lista': descripciones,
        'notas': notas,
        'xml_root': root  # para detector de tipo
    }


def main():
    cat = CatalogoEmpresa.cargar(
        Path(__file__).parent.parent / 'core' / 'data' / 'empresas' / '900451388_silla_tres'
    )

    base_xmls = '/home/claude/analisis/all_xmls'
    docs = []
    for tipo in ['FE', 'NC', 'ND', 'DS']:
        for x in sorted(glob.glob(f'{base_xmls}/{tipo}/*.xml')):
            d = extraer_doc(x)
            if d:
                d['tipo'] = tipo
                docs.append(d)

    print(f"Procesando {len(docs)} XMLs reales de Silla Tres marzo 2026...")
    print()

    catalogo_comprobantes = cat.empresa_json.get('comprobantes_por_tipo_dian', None)

    resultados = []
    for d in docs:
        # ── DETECTOR DE TIPO ─────────────────────────────────
        tipo_real, fuente_tipo = detectar_tipo_documento(
            xml_root=d.get('xml_root'),
            nombre_archivo=d['archivo']
        )
        comp_info = mapear_a_comprobante(tipo_real, catalogo_comprobantes)
        d['tipo_dian_real'] = tipo_real
        d['fuente_tipo'] = fuente_tipo
        d['comprobante'] = comp_info.get('comprobante', '')
        d['comprobante_desc'] = comp_info.get('descripcion', '')

        # Saltar acuses de recibo (no contables)
        if tipo_real == 'ACUSE':
            resultados.append({
                'doc': d, 'res': None, 'ret_renta': None, 'ret_iva': None,
                'es_acuse': True
            })
            continue

        r = resolver_mapeo(
            cat,
            nit_emisor=d['nit_emisor'],
            nombre_emisor=d['nombre_emisor'],
            direccion_entrega=d['direccion_entrega'],
            items_descripcion=d['items_descripcion'],
            notas_xml=d.get('notas', []),
            items_descripciones_lista=d.get('items_descripciones_lista', [])
        )

        ret_renta = calcular_retencion_renta(
            cat, r.concepto_retencion, d['base_imponible'],
            r.regimen_emisor, r.autorretenedor_renta
        )
        ret_iva = calcular_reteiva(cat, d['iva'], r.regimen_emisor, d['base_imponible'])
        # ReteICA deshabilitado para Silla Tres

        resultados.append({
            'doc': d,
            'res': r,
            'ret_renta': ret_renta,
            'ret_iva': ret_iva
        })

    # Estadísticas
    print("═" * 75)
    print("RESULTADOS")
    print("═" * 75)

    # Conteo por TIPO REAL detectado
    tipos_reales = Counter(r['doc']['tipo_dian_real'] for r in resultados)
    print("\nTIPO DIAN detectado (desde XML):")
    for t, n in tipos_reales.most_common():
        comp_map = catalogo_comprobantes.get(t, {}) if catalogo_comprobantes else {}
        comp = comp_map.get('comprobante', '?')
        desc = comp_map.get('descripcion', '?')
        print(f"  {t:12s} ×{n:4d}  →  Comprobante {comp:3s} ({desc})")

    fuentes_cuenta = Counter(r['res'].fuente_cuenta for r in resultados if r.get('res'))
    fuentes_cc = Counter(r['res'].fuente_cc for r in resultados if r.get('res'))
    print("\nFuente de la CUENTA asignada:")
    for f, n in fuentes_cuenta.most_common():
        pct = n / len(resultados) * 100
        print(f"  {f:30s} {n:4d}  ({pct:.1f}%)")

    print("\nFuente del CC asignado:")
    for f, n in fuentes_cc.most_common():
        pct = n / len(resultados) * 100
        print(f"  {f:30s} {n:4d}  ({pct:.1f}%)")

    pendientes = [r for r in resultados if r.get('res') and r['res'].es_pendiente_revision]
    print(f"\n⚠️  XMLs pendientes de catalogación: {len(pendientes)} de {len(resultados)}")
    nits_pend = Counter((r['doc']['nit_emisor'], r['doc']['nombre_emisor']) for r in pendientes)
    for (nit, nom), n in nits_pend.most_common():
        print(f"   {n:3d}x  {nit:12s}  {nom[:50]}")

    # Formato CC empresa
    cc_formato = cat.empresa_json.get('formato_salida', {}).get('cc_formato', 'sin_guion')

    print("\n" + "═" * 75)
    print(f"MUESTRA: 10 XMLs procesados (CCs en formato '{cc_formato}')")
    print("═" * 75)
    contables = [r for r in resultados if r.get('res')]
    for r in contables[:10]:
        d, res = r['doc'], r['res']
        cc_out = formato_cc_salida(res.cc, cc_formato)
        print(f"\n📄 {d['archivo'][:30]} | Tipo:{d['tipo_dian_real']:3s} → Comprob {d['comprobante']:3s} | {d['nombre_emisor'][:25]:25s} | ${d['total']:>14,.0f}")
        print(f"   Cuenta: {res.cuenta:8s} | CC: {cc_out:6s} | Concepto ret: {res.concepto_retencion}")
        print(f"   Fuente cuenta: {res.fuente_cuenta:15s} | Fuente CC: {res.fuente_cc}")
        if res.pista_palabra_clave:
            print(f"   Pista usada: '{res.pista_palabra_clave[:80]}'")
        elif d['direccion_entrega']:
            print(f"   Dir XML: '{d['direccion_entrega']}'")
        if r['ret_renta'] and r['ret_renta'].aplicada:
            print(f"   ↳ Retefuente: ${r['ret_renta'].valor:,.0f} ({r['ret_renta'].tarifa:.1%}) → cuenta {r['ret_renta'].cuenta}")
        elif r['ret_renta'] and not r['ret_renta'].aplicada and r['ret_renta'].motivo_no_aplicada:
            print(f"   ↳ Retefuente NO aplica: {r['ret_renta'].motivo_no_aplicada}")
        if r['ret_iva'] and r['ret_iva'].aplicada:
            print(f"   ↳ ReteIVA: ${r['ret_iva'].valor:,.0f} (a régimen RST)")

    # Totales
    total_retfuente = sum(r['ret_renta'].valor for r in resultados if r.get('ret_renta') and r['ret_renta'].aplicada)
    total_reteiva = sum(r['ret_iva'].valor for r in resultados if r.get('ret_iva') and r['ret_iva'].aplicada)
    total_compras = sum(r['doc']['total'] for r in resultados if not r.get('es_acuse'))
    total_acuses = sum(1 for r in resultados if r.get('es_acuse'))

    print("\n" + "═" * 75)
    print("TOTALES MES")
    print("═" * 75)
    print(f"Total compras (con IVA):           ${total_compras:>15,.0f}")
    print(f"Retefuente practicada:             ${total_retfuente:>15,.0f}")
    print(f"ReteIVA practicada (solo a RST):   ${total_reteiva:>15,.0f}")
    print(f"ReteICA: NO se practica (empresa no obligada)")
    if total_acuses > 0:
        print(f"Acuses de recibo descartados:      {total_acuses}")


if __name__ == '__main__':
    main()
