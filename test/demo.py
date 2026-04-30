"""Demo manual: simula un mes con varias facturas y muestra el plano generado."""
import sys
from pathlib import Path
from decimal import Decimal

sys.path.insert(0, str(Path(__file__).parent.parent / "core" / "procesadores"))
sys.path.insert(0, str(Path(__file__).parent))

from procesador_dian_xml import RegistryEmpresas, procesar_zip, exportar_plano_txt
from test_procesador_dian_xml import xml_invoice, empaquetar_zip_maestro

EMPRESAS_DIR = Path(__file__).parent.parent / "core" / "data" / "empresas"


def main():
    reg = RegistryEmpresas(EMPRESAS_DIR)

    # Simular un mes con varias facturas mezcladas
    xmls = [
        # Factura grande: alimento avícola (Nutrientes)
        ("01_nutrientes", xml_invoice(
            nit_emisor="891301549", nombre_emisor="NUTRIENTES AVICOLAS S.A.S.",
            nit_receptor="900451388",
            prefijo="CL", numero="15443073", fecha="2026-03-28",
            cufe="a" * 96,
            items=[
                {"desc": "Alimento concentrado pollos engorde 40kg", "cantidad": 50,
                 "precio": 95000, "iva_pct": 0},
            ],
        )),
        # Estra: papelería (matchea regla)
        ("02_estra_papel", xml_invoice(
            nit_emisor="890900099", nombre_emisor="Industrias Estra S.A",
            nit_receptor="900451388",
            prefijo="605T", numero="30865", fecha="2026-03-28",
            cufe="b" * 96,
            items=[
                {"desc": "Resma papel bond carta x500", "cantidad": 10,
                 "precio": 18000, "iva_pct": 19},
            ],
        )),
        # Estra: cafetería (matchea otra regla)
        ("03_estra_cafe", xml_invoice(
            nit_emisor="890900099", nombre_emisor="Industrias Estra S.A",
            nit_receptor="900451388",
            prefijo="605T", numero="30864", fecha="2026-03-28",
            cufe="c" * 96,
            items=[
                {"desc": "Café tostado molido 1kg", "cantidad": 5,
                 "precio": 30000, "iva_pct": 19},
            ],
        )),
        # Ecolimpiadores: servicio
        ("04_ecolimp", xml_invoice(
            nit_emisor="900410852", nombre_emisor="ECOLIMPIADORES S.A.S.",
            nit_receptor="900451388",
            prefijo="E", numero="99574", fecha="2026-03-28",
            cufe="d" * 96,
            items=[
                {"desc": "Servicio de aseo mensual marzo 2026", "cantidad": 1,
                 "precio": 200000, "iva_pct": 19},
            ],
            rete_fuente=8000,  # 4% sobre servicios
        )),
        # NIT no catalogado (debe quedar pendiente)
        ("05_desconocido", xml_invoice(
            nit_emisor="800123456", nombre_emisor="Proveedor Misterioso SAS",
            nit_receptor="900451388",
            prefijo="MS", numero="100", fecha="2026-03-30",
            cufe="e" * 96,
            items=[
                {"desc": "Producto X", "cantidad": 1,
                 "precio": 50000, "iva_pct": 19},
            ],
        )),
        # NC de la primera factura
        ("06_nc_nutrientes", xml_invoice(
            tipo="CreditNote",
            nit_emisor="891301549", nombre_emisor="NUTRIENTES AVICOLAS S.A.S.",
            nit_receptor="900451388",
            prefijo="NC", numero="500", fecha="2026-03-30",
            cufe="f" * 96,
            items=[
                {"desc": "Devolución alimento concentrado", "cantidad": 5,
                 "precio": 95000, "iva_pct": 0},
            ],
        )),
    ]

    zip_bytes = empaquetar_zip_maestro(xmls)
    print(f"📦 ZIP simulado: {len(zip_bytes)} bytes con {len(xmls)} documentos\n")

    resultados = procesar_zip(zip_bytes, reg, "202603")

    for r in resultados:
        print("=" * 80)
        print(f"📊 EMPRESA: {r.empresa_razon_social} (NIT {r.empresa_nit})")
        print("=" * 80)
        print(f"   Documentos procesados: {len(r.documentos)}")
        print(f"   Líneas de plano:       {len(r.lineas_plano)}")
        print(f"   Cuadre:                Db ${r.cuadre_db:>15,.0f}  Cr ${r.cuadre_cr:>15,.0f}  "
              f"{'✅ CUADRA' if r.cuadrado else '❌ NO CUADRA'}")

        if r.nits_pendientes:
            print(f"\n   ⚠️ NITs pendientes de mapeo:")
            for p in r.nits_pendientes:
                print(f"      • {p['nit']} {p['nombre']}: {p['documentos']} doc(s), ${p['valor_total']:,.0f}")

        if r.advertencias:
            print(f"\n   ⚠️ Advertencias:")
            for a in r.advertencias:
                print(f"      • {a}")

        # Mostrar primeras líneas del plano
        if r.lineas_plano:
            print(f"\n   📋 Plano contable (primeras 20 líneas):")
            print(f"   {'FECHA':<11} {'COMP':<8} {'CONSEC':<11} {'CTA':<10} {'CC':<6} "
                  f"{'NIT':<12} {'DEBITO':>14} {'CREDITO':>14}  DESCRIPCION")
            print(f"   {'-'*11} {'-'*8} {'-'*11} {'-'*10} {'-'*6} {'-'*12} "
                  f"{'-'*14} {'-'*14}  {'-'*40}")
            for l in r.lineas_plano[:20]:
                print(f"   {l.fecha:<11} {l.comprobante:<8} {l.consecutivo:<11} "
                      f"{l.cuenta:<10} {l.centro_costo:<6} {l.nit_tercero:<12} "
                      f"${l.debito:>13,.0f} ${l.credito:>13,.0f}  {l.descripcion[:40]}")
            if len(r.lineas_plano) > 20:
                print(f"   ... ({len(r.lineas_plano) - 20} líneas más)")
        print()


if __name__ == "__main__":
    main()
