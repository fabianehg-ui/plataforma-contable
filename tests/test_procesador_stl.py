"""
tests/test_procesador_stl.py

Valida que el procesador STL produce el resultado esperado contra
los datos reales de marzo 2026 (88 facturas + 5 NC).

Ejecutar con:
    cd /home/claude/proyecto/plataforma-contable-main
    python3 -m pytest tests/test_procesador_stl.py -v

Si no hay pytest:
    python3 tests/test_procesador_stl.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
from core.procesadores.procesador_stl import (
    procesar_stl, cargar_config_stl,
    plano_a_tsv_bytes, plano_a_csv_bytes, plano_a_xlsx_bytes,
)


# Path al Token de marzo (ajustar si está en otro lugar)
TOKEN_PATH = "/tmp/token_extract/57636773-f2b9-4688-a609-3fa386d919c6.xlsx"


def test_config_carga_correcto():
    cfg = cargar_config_stl()
    assert cfg["nit_empresa"] == "901038325"
    assert cfg["comprobante_stl"] == "426"
    assert cfg["comprobante_nc_stl"] == "5"
    assert cfg["cc_default"] == "001101"
    assert "19" in cfg["cuentas_por_tarifa_iva"]
    assert "5" in cfg["cuentas_por_tarifa_iva"]
    assert "0" in cfg["cuentas_por_tarifa_iva"]
    print("✅ test_config_carga_correcto")


def test_procesar_marzo_2026():
    """Validación principal contra los datos reales de marzo 2026."""
    if not Path(TOKEN_PATH).exists():
        print(f"⏭️  test_procesar_marzo_2026 OMITIDO (no existe {TOKEN_PATH})")
        return

    r = procesar_stl(TOKEN_PATH, anio=2026, mes=3)

    # Conteos esperados
    assert r["metadatos"]["facturas_procesadas"] == 88, \
        f"Esperaba 88 facturas, obtuve {r['metadatos']['facturas_procesadas']}"
    assert r["metadatos"]["ncs_procesadas"] == 5, \
        f"Esperaba 5 NCs, obtuve {r['metadatos']['ncs_procesadas']}"
    assert r["metadatos"]["lineas_plano"] == 215, \
        f"Esperaba 215 líneas, obtuve {r['metadatos']['lineas_plano']}"

    # Cuadre exacto
    assert r["cuadre"]["cuadra"], \
        f"No cuadra. Diferencia: ${r['cuadre']['diferencia']:,.2f}"
    assert abs(r["cuadre"]["diferencia"]) < 1, \
        f"Diferencia > $1: ${r['cuadre']['diferencia']:,.2f}"

    # Totales esperados (validados manualmente)
    debitos_esperados = 1_196_261_678.99  # 1.057M (facts) + 138.6M (NCs)
    assert abs(r["cuadre"]["debitos"] - debitos_esperados) < 1, \
        f"Débitos: esperaba ${debitos_esperados:,.2f}, obtuve ${r['cuadre']['debitos']:,.2f}"

    # Distribución por tarifa
    rt = r["resumen_por_tarifa"]
    assert rt["sin_iva"]["facs"] == 69, f"Sin IVA: esperaba 69, obtuve {rt['sin_iva']['facs']}"
    assert rt["iva_19"]["facs"] == 9,   f"IVA 19% puro: esperaba 9, obtuve {rt['iva_19']['facs']}"
    assert rt["iva_5"]["facs"]  == 0,   f"IVA 5%: esperaba 0, obtuve {rt['iva_5']['facs']}"
    assert rt["mixto"]["facs"]  == 10,  f"Mixto: esperaba 10, obtuve {rt['mixto']['facs']}"

    # NC STL
    assert r["resumen_nc"]["facs"] == 5
    assert abs(r["resumen_nc"]["total"] - 138_631_840.00) < 1
    assert r["resumen_nc"]["iva"] == 0  # todas sin IVA

    # IVA total
    iva_19 = rt["iva_19"]["iva"]
    assert abs(iva_19 - 3_363_827.99) < 1, f"IVA 19% total: esperaba 3,363,827.99, obtuve {iva_19:,.2f}"

    # Sin alertas
    assert len(r["alertas"]) == 0, f"Alertas inesperadas: {r['alertas']}"

    print(f"✅ test_procesar_marzo_2026")
    print(f"   - 88 facturas, 5 NCs, 215 líneas")
    print(f"   - Débitos = Créditos = ${r['cuadre']['debitos']:,.2f}")
    print(f"   - 69 sin IVA + 9 (19% puro) + 10 mixtas")


def test_doc_y_doc_referencia_son_iguales():
    """En las facturas STL, DOCUMENTO y DOC REFERENCIA deben ser iguales."""
    if not Path(TOKEN_PATH).exists():
        print(f"⏭️  test_doc_y_doc_referencia OMITIDO")
        return

    r = procesar_stl(TOKEN_PATH, anio=2026, mes=3)
    facturas = r["lineas_stl_facturas"]
    iguales = (facturas["DOCUMENTO"].astype(str) == facturas["DOC REFERENCIA"].astype(str)).all()
    assert iguales, "DOCUMENTO debe coincidir con DOC REFERENCIA en facturas"
    print(f"✅ test_doc_y_doc_referencia_son_iguales")


def test_nc_reversa_cuenta_venta():
    """Las NC STL deben usar la misma cuenta de venta (no una cuenta de devolución)."""
    if not Path(TOKEN_PATH).exists():
        print(f"⏭️  test_nc_reversa_cuenta_venta OMITIDO")
        return

    r = procesar_stl(TOKEN_PATH, anio=2026, mes=3)
    ncs = r["lineas_nc_stl"]
    # Las NC SIN IVA deben tener 41200902 al débito (reversa la venta sin IVA)
    cuentas_db_nc = ncs[ncs["TR"] == "1"]["CUENTA"].unique()
    assert "41200902" in cuentas_db_nc, \
        f"NC sin IVA debe reversar 41200902, encontradas: {cuentas_db_nc}"
    # NO debe aparecer 41752002 ni 41754001 (cuentas de devolución)
    assert "41752002" not in cuentas_db_nc, "No debe usar 41752002 (lo confirmaste así)"
    assert "41754001" not in cuentas_db_nc, "No debe usar 41754001"
    print(f"✅ test_nc_reversa_cuenta_venta")


def test_comprobantes_correctos():
    """Los comprobantes deben ser 426 (STL) y 5 (NC STL)."""
    if not Path(TOKEN_PATH).exists():
        print(f"⏭️  test_comprobantes_correctos OMITIDO")
        return

    r = procesar_stl(TOKEN_PATH, anio=2026, mes=3)
    facturas = r["lineas_stl_facturas"]
    ncs = r["lineas_nc_stl"]

    assert (facturas["COMPROBANTE"] == "426").all(), "Facturas STL deben tener comprobante 426"
    assert (ncs["COMPROBANTE"] == "5").all(), "NC STL deben tener comprobante 5"
    print(f"✅ test_comprobantes_correctos")


def test_cc_001101_en_todas_las_lineas():
    """Todas las líneas STL deben tener CC = 001101."""
    if not Path(TOKEN_PATH).exists():
        print(f"⏭️  test_cc_001101 OMITIDO")
        return

    r = procesar_stl(TOKEN_PATH, anio=2026, mes=3)
    assert (r["plano"]["CENTRO DE COSTO"] == "001101").all(), "Todas las líneas deben tener CC 001101"
    print(f"✅ test_cc_001101_en_todas_las_lineas")


def test_exportadores_funcionan():
    """TSV, CSV, XLSX deben generar bytes válidos."""
    if not Path(TOKEN_PATH).exists():
        print(f"⏭️  test_exportadores OMITIDO")
        return

    r = procesar_stl(TOKEN_PATH, anio=2026, mes=3)
    tsv = plano_a_tsv_bytes(r["plano"])
    csv = plano_a_csv_bytes(r["plano"])
    xlsx = plano_a_xlsx_bytes(r["plano"], resumen=r)
    assert len(tsv) > 1000
    assert len(csv) > 1000
    assert len(xlsx) > 1000
    print(f"✅ test_exportadores_funcionan (TSV={len(tsv)}b, CSV={len(csv)}b, XLSX={len(xlsx)}b)")


def test_mes_vacio_no_falla():
    """Procesar un mes sin datos debe devolver plano vacío sin crash."""
    if not Path(TOKEN_PATH).exists():
        print(f"⏭️  test_mes_vacio OMITIDO")
        return

    r = procesar_stl(TOKEN_PATH, anio=2020, mes=1)  # mes inexistente
    assert r["metadatos"]["facturas_procesadas"] == 0
    assert r["metadatos"]["ncs_procesadas"] == 0
    assert r["cuadre"]["cuadra"]  # 0 == 0
    print(f"✅ test_mes_vacio_no_falla")


if __name__ == "__main__":
    print("=" * 60)
    print("Tests del procesador STL")
    print("=" * 60)
    test_config_carga_correcto()
    test_procesar_marzo_2026()
    test_doc_y_doc_referencia_son_iguales()
    test_nc_reversa_cuenta_venta()
    test_comprobantes_correctos()
    test_cc_001101_en_todas_las_lineas()
    test_exportadores_funcionan()
    test_mes_vacio_no_falla()
    print("\n🎉 Todos los tests pasaron")
