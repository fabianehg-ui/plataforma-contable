"""Demo v0.2.2 con casos reales del plano del usuario:
- Postobón → debe ir a 143505 automáticamente (no 519095)
- D'Carnes → debe ir a 143505
- SIIGO → debe quedar en PENDIENTE (no es alimenticio)
- IVA 5% va a 24080203, IVA 19% va a 24080201
- INC, IBUA si vienen, separados
"""
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "core" / "procesadores"))
sys.path.insert(0, str(Path(__file__).parent))

from procesador_dian_xml import RegistryEmpresas, procesar_multiples_zips, ZipInput
from test_procesador_dian_xml import xml_invoice, empaquetar_zip_maestro
from test_v022_iva_e_impuestos import xml_invoice_con_impuestos

EMPRESAS_DIR = Path(__file__).parent.parent / "core" / "data" / "empresas"


def main():
    reg = RegistryEmpresas(EMPRESAS_DIR)

    xmls = [
        # 1. SIIGO (software, NO alimenticio) → debe quedar PENDIENTE
        ("siigo", xml_invoice(
            nit_emisor="830048145", nombre_emisor="SIIGO S.A.S",
            nit_receptor="900451388",
            prefijo="SS", numero="105204733", fecha="2026-04-03",
            cufe="a" * 96,
            items=[{"desc": "Licencia software contable abril 2026",
                    "cantidad": 1, "precio": 55385, "iva_pct": 19}],
        )),

        # 2. POSTOBÓN (bebidas) → debe detectarse como insumo y ir a 143505
        ("postobon", xml_invoice(
            nit_emisor="890903939", nombre_emisor="POSTOBON S.A.",
            nit_receptor="900451388",
            prefijo="NW", numero="30310411", fecha="2026-04-12",
            cufe="b" * 96,
            items=[{"desc": "Gaseosa Postobón Manzana 350ml x12",
                    "cantidad": 12, "precio": 4000, "iva_pct": 19}],
        )),

        # 3. D'CARNES (carnes, IVA 5%) → debe ir a 143505 + IVA en 24080203
        ("dcarnes", xml_invoice(
            nit_emisor="800176100", nombre_emisor="D' CARNES S.A",
            nit_receptor="900451388",
            prefijo="FIV", numero="115", fecha="2026-04-22",
            cufe="c" * 96,
            items=[{"desc": "Carne de res molida x kg",
                    "cantidad": 10, "precio": 21650, "iva_pct": 5}],
        )),

        # 4. POSTOBÓN con IBUA (bebidas azucaradas)
        ("postobon_ibua", xml_invoice_con_impuestos(
            nit_emisor="890903939", nombre_emisor="POSTOBON S.A.",
            nit_receptor="900451388",
            prefijo="JM", numero="07843547", fecha="2026-04-22",
            cufe="d" * 96,
            items=[{"desc": "Gaseosa azucarada x 24",
                    "cantidad": 1, "precio": 366512, "iva_pct": 19}],
            ibua_valor=15000,
        )),

        # 5. COLANTA (lácteos)
        ("colanta", xml_invoice(
            nit_emisor="890904478", nombre_emisor="COOPERATIVA COLANTA",
            nit_receptor="900451388",
            prefijo="417", numero="N113240", fecha="2026-04-22",
            cufe="e" * 96,
            items=[{"desc": "Leche entera UHT 1L x 12",
                    "cantidad": 12, "precio": 4200, "iva_pct": 0}],
        )),

        # 6. NUTRIENTES AVÍCOLAS (ya catalogado, debe ir a 143505 también)
        ("nutrientes", xml_invoice(
            nit_emisor="891301549", nombre_emisor="NUTRIENTES AVICOLAS S.A.S.",
            nit_receptor="900451388",
            prefijo="CL", numero="95089042", fecha="2026-04-16",
            cufe="f" * 96,
            items=[{"desc": "Concentrado pollos engorde 40kg",
                    "cantidad": 5, "precio": 95000, "iva_pct": 0}],
        )),
    ]

    zip_bytes = empaquetar_zip_maestro(xmls)
    zips = [ZipInput(nombre="DEMO_real.zip", contenido=zip_bytes, tipo_declarado="FE")]

    resultados, resumen = procesar_multiples_zips(
        zips, reg, "202604",
        modo_filtro_fecha="ninguno",
    )

    r = resultados[0]
    print(f"\n{'=' * 90}")
    print(f"📊 DEMO v0.2.2 — Casos reales de Silla Tres SAS")
    print(f"{'=' * 90}")
    print(f"\n   Documentos:     {len(r.documentos)}")
    print(f"   Líneas plano:   {len(r.lineas_plano)}")
    print(f"   Cuadre:         Db ${r.cuadre_db:>15,.0f}  Cr ${r.cuadre_cr:>15,.0f}  "
          f"{'✅' if r.cuadrado else '❌'}")
    print(f"   Pendientes:     {len(r.nits_pendientes)}")

    print(f"\n📋 Plano contable resultante:")
    print(f"   {'Doc':<12} {'Cuenta':<10} {'CC':<6} {'Concepto':<35} {'Db':>12} {'Cr':>12}")
    print(f"   {'-' * 12} {'-' * 10} {'-' * 6} {'-' * 35} {'-' * 12} {'-' * 12}")
    for l in r.lineas_plano:
        print(f"   {l.documento_referencia:<12} {l.cuenta:<10} {l.centro_costo:<6} "
              f"{l.descripcion[:35]:<35} ${l.debito:>11,.0f} ${l.credito:>11,.0f}")

    # Validar específicamente
    print(f"\n✅ VALIDACIONES:")
    cuentas = {(l.documento_referencia, l.cuenta): l.descripcion for l in r.lineas_plano}

    # SIIGO debe ir a 519095 (PENDIENTE)
    siigo_cuentas = [c for (d, c) in cuentas if d == "SS105204733"]
    print(f"   SIIGO → cuentas usadas: {siigo_cuentas}")
    assert "519095" in siigo_cuentas, "SIIGO debería estar PENDIENTE"
    print(f"   ✓ SIIGO correctamente en PENDIENTE (519095)")

    # POSTOBON sin IBUA → 143505 (auto-detectado)
    posto_cuentas = [c for (d, c) in cuentas if d == "NW30310411"]
    print(f"   POSTOBON → cuentas usadas: {posto_cuentas}")
    assert "143505" in posto_cuentas, "POSTOBON debería ir a 143505 (auto-insumo)"
    print(f"   ✓ POSTOBON auto-detectado como insumo → 143505")

    # D'CARNES con IVA 5% → debe usar 24080203
    dcarnes_cuentas = [c for (d, c) in cuentas if d == "FIV115"]
    print(f"   D'CARNES (IVA 5%) → cuentas: {dcarnes_cuentas}")
    assert "143505" in dcarnes_cuentas
    assert "24080203" in dcarnes_cuentas, "D'CARNES con IVA 5% debe ir a 24080203"
    print(f"   ✓ D'CARNES → 143505 + IVA 5% en 24080203 (no 24080201)")

    # POSTOBON con IBUA → debe tener línea de 24080540
    posto_ibua_cuentas = [c for (d, c) in cuentas if d == "JM07843547"]
    print(f"   POSTOBON+IBUA → cuentas: {posto_ibua_cuentas}")
    assert "24080540" in posto_ibua_cuentas, "Debe haber línea IBUA"
    print(f"   ✓ POSTOBON con IBUA → 24080540 separado")

    # COLANTA → 143505 auto
    colanta_cuentas = [c for (d, c) in cuentas if d == "417N113240"]
    assert "143505" in colanta_cuentas
    print(f"   ✓ COLANTA auto-detectado como lácteo → 143505")

    print(f"\n🎉 TODAS las validaciones pasaron. v0.2.2 funcionando como se esperaba.")


if __name__ == "__main__":
    main()
