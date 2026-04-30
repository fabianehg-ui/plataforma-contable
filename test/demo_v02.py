"""
Demo v0.2 — flujo multi-ZIP con 4 tipos de documentos.

Simula el caso real: usuario descarga 4 ZIPs del bookmarklet (uno por tipo)
y los sube todos juntos.
"""
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "core" / "procesadores"))
sys.path.insert(0, str(Path(__file__).parent))

from procesador_dian_xml import (
    RegistryEmpresas,
    procesar_multiples_zips,
    separar_lineas_por_comprobante,
    generar_reporte_ejecutivo,
    exportar_plano_txt,
    ZipInput,
)
from test_procesador_dian_xml import xml_invoice, empaquetar_zip_maestro

EMPRESAS_DIR = Path(__file__).parent.parent / "core" / "data" / "empresas"


def main():
    reg = RegistryEmpresas(EMPRESAS_DIR)

    # ========== ZIP 1: FACTURAS ELECTRÓNICAS ==========
    zip_fe = empaquetar_zip_maestro([
        ("nutrientes_1", xml_invoice(
            nit_emisor="891301549", nombre_emisor="NUTRIENTES AVICOLAS S.A.S.",
            nit_receptor="900451388",
            prefijo="CL", numero="15443073", fecha="2026-03-05",
            cufe="a1" * 48,
            items=[{"desc": "Alimento concentrado pollos engorde", "cantidad": 100,
                   "precio": 95000, "iva_pct": 0}],
        )),
        ("estra_papel", xml_invoice(
            nit_emisor="890900099", nombre_emisor="Industrias Estra S.A",
            nit_receptor="900451388",
            prefijo="605T", numero="30865", fecha="2026-03-12",
            cufe="b1" * 48,
            items=[{"desc": "Resma papel bond carta x500", "cantidad": 10,
                   "precio": 18000, "iva_pct": 19}],
        )),
        ("estra_cafe", xml_invoice(
            nit_emisor="890900099", nombre_emisor="Industrias Estra S.A",
            nit_receptor="900451388",
            prefijo="605T", numero="30864", fecha="2026-03-15",
            cufe="c1" * 48,
            items=[{"desc": "Café tostado molido 1kg", "cantidad": 5,
                   "precio": 30000, "iva_pct": 19}],
        )),
        ("ecolimp", xml_invoice(
            nit_emisor="900410852", nombre_emisor="ECOLIMPIADORES S.A.S.",
            nit_receptor="900451388",
            prefijo="E", numero="99574", fecha="2026-03-20",
            cufe="d1" * 48,
            items=[{"desc": "Servicio de aseo mensual marzo 2026", "cantidad": 1,
                   "precio": 200000, "iva_pct": 19}],
            rete_fuente=8000,
        )),
    ])

    # ========== ZIP 2: NOTAS CRÉDITO ==========
    zip_nc = empaquetar_zip_maestro([
        ("nc_nutrientes", xml_invoice(
            tipo="CreditNote",
            nit_emisor="891301549", nombre_emisor="NUTRIENTES AVICOLAS S.A.S.",
            nit_receptor="900451388",
            prefijo="NC", numero="500", fecha="2026-03-25",
            cufe="e1" * 48,
            items=[{"desc": "Devolución alimento concentrado", "cantidad": 5,
                   "precio": 95000, "iva_pct": 0}],
        )),
    ])

    # ========== ZIP 3: NOTAS DÉBITO ==========
    zip_nd = empaquetar_zip_maestro([
        ("nd_estra", xml_invoice(
            tipo="DebitNote",
            nit_emisor="890900099", nombre_emisor="Industrias Estra S.A",
            nit_receptor="900451388",
            prefijo="ND", numero="100", fecha="2026-03-28",
            cufe="f1" * 48,
            items=[{"desc": "Cargo por mora", "cantidad": 1,
                   "precio": 25000, "iva_pct": 0}],
        )),
    ])

    # ========== ZIP 4: SERVICIOS PÚBLICOS ==========
    zip_sp = empaquetar_zip_maestro([
        ("epm_energia", xml_invoice(
            nit_emisor="830037946", nombre_emisor="Empresas Públicas de Medellín ESP",
            nit_receptor="900451388",
            prefijo="EPM", numero="78901234", fecha="2026-03-08",
            cufe="g1" * 48,
            items=[{"desc": "Energía eléctrica residencial 380 kWh marzo 2026",
                   "cantidad": 1, "precio": 235000, "iva_pct": 0}],
        )),
        ("vanti_gas", xml_invoice(
            nit_emisor="800007813", nombre_emisor="Vanti SA ESP",
            nit_receptor="900451388",
            prefijo="VANTI", numero="445566", fecha="2026-03-10",
            cufe="h1" * 48,
            items=[{"desc": "Gas natural domiciliario 45 m3", "cantidad": 1,
                   "precio": 85000, "iva_pct": 0}],
        )),
        ("claro_internet", xml_invoice(
            nit_emisor="800153993", nombre_emisor="COMUNICACIÓN CELULAR S.A.",
            nit_receptor="900451388",
            prefijo="CLR", numero="998877", fecha="2026-03-15",
            cufe="i1" * 48,
            items=[{"desc": "Plan internet hogar fibra óptica 200 megas",
                   "cantidad": 1, "precio": 95000, "iva_pct": 19}],
        )),
    ])

    # ========== SUBIR TODO ==========
    zips = [
        ZipInput(nombre="DIAN_FE_2026-03.zip", contenido=zip_fe, tipo_declarado="FE"),
        ZipInput(nombre="DIAN_NC_2026-03.zip", contenido=zip_nc, tipo_declarado="NC"),
        ZipInput(nombre="DIAN_ND_2026-03.zip", contenido=zip_nd, tipo_declarado="ND"),
        ZipInput(nombre="DIAN_SP_2026-03.zip", contenido=zip_sp, tipo_declarado="DS"),
    ]

    print("=" * 100)
    print("📥 DEMO v0.2 — Procesamiento multi-ZIP")
    print("=" * 100)
    print(f"\n📦 ZIPs a procesar: {len(zips)}")
    for z in zips:
        print(f"   • {z.nombre} ({z.tipo_declarado}) — {len(z.contenido):,} bytes")

    resultados, resumen = procesar_multiples_zips(
        zips, reg, "202603",
        fecha_desde="2026-03-01", fecha_hasta="2026-03-31",
    )

    print(f"\n{'='*100}")
    print("📊 RESUMEN DE INGESTA")
    print(f"{'='*100}")
    print(f"   XMLs extraídos:           {resumen.total_xmls_extraidos}")
    print(f"   Duplicados descartados:   {resumen.duplicados_descartados}")
    print(f"   Fuera de rango fechas:    {resumen.fuera_de_rango_fecha}")
    print(f"   Errores parseo:           {resumen.errores_parseo}")
    print(f"   Inconsistencias tipo:     {len(resumen.inconsistencias_tipo)}")
    print(f"\n   Distribución por tipo:")
    for tipo, n in resumen.por_tipo.items():
        print(f"      • {tipo:35s} {n}")
    print(f"\n   Distribución por ZIP:")
    for zip_name, n in resumen.por_zip.items():
        print(f"      • {zip_name:35s} {n}")
    print(f"\n   Empresas detectadas:")
    for emp_id, n in resumen.por_empresa.items():
        print(f"      • {emp_id:35s} {n} doc(s)")

    for r in resultados:
        print(f"\n{'='*100}")
        print(f"🏢 {r.empresa_razon_social} (NIT {r.empresa_nit})")
        print(f"{'='*100}")
        print(f"   Documentos:     {len(r.documentos)}")
        print(f"   Líneas plano:   {len(r.lineas_plano)}")
        print(f"   Db total:       ${r.cuadre_db:>15,.0f}")
        print(f"   Cr total:       ${r.cuadre_cr:>15,.0f}")
        print(f"   Cuadre:         {'✅ CUADRA' if r.cuadrado else '❌ NO CUADRA'}")

        # Reporte ejecutivo
        rep = generar_reporte_ejecutivo(r)
        print(f"\n   📊 KPIs:")
        print(f"      Compras netas:           ${rep['total_compras_netas']:>15,.0f}")
        print(f"      IVA descontable:         ${rep['total_iva_descontable']:>15,.0f}")
        print(f"      Retenciones practicadas: ${rep['total_retenciones_practicadas']:>15,.0f}")

        if r.nits_pendientes:
            print(f"\n   ⚠️  NITs pendientes de mapeo: {len(r.nits_pendientes)}")
            for p in r.nits_pendientes:
                print(f"      • {p['nit']} {p['nombre']}: {p['documentos']} doc(s), ${p['valor_total']:,.0f}")

        # Separación por comprobante
        if r.lineas_plano:
            separado = separar_lineas_por_comprobante(r.lineas_plano)
            print(f"\n   📋 Distribución por comprobante:")
            for comp, lineas in separado.items():
                db = sum((l.debito for l in lineas), Decimal(0))
                cr = sum((l.credito for l in lineas), Decimal(0))
                cuadra = "✅" if db == cr else "❌"
                print(f"      • {comp:10s} → {len(lineas):3d} líneas, "
                      f"Db=${db:,.0f}  Cr=${cr:,.0f}  {cuadra}")


if __name__ == "__main__":
    main()
