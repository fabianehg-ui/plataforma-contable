"""Tests del exportador Silla Tres v2."""
import sys
from decimal import Decimal
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.procesadores.exportador_silla_tres import (
    construir_dataframe_silla_tres,
    exportar_txt_silla_tres,
    exportar_csv_silla_tres,
    exportar_xlsx_silla_tres,
    _fecha_americana,
    _formato_cc,
    _cuenta_lleva_base,
    _agrupar_lineas_por_asiento,
    CABECERAS,
)


class LineaMock:
    def __init__(self, **kwargs):
        defaults = {
            'fecha': '', 'comprobante': '', 'consecutivo': '',
            'cuenta': '', 'centro_costo': '', 'nit_tercero': '',
            'descripcion': '', 'documento_referencia': '',
            'debito': Decimal(0), 'credito': Decimal(0),
            'base': Decimal(0)
        }
        defaults.update(kwargs)
        for k, v in defaults.items():
            setattr(self, k, v)


# ─── Helpers ─────────────────────────────────────────

def test_fecha_americana():
    assert _fecha_americana('2026-04-24') == '04/24/2026'
    assert _fecha_americana('2026/04/24') == '04/24/2026'
    assert _fecha_americana('2026-4-24') == '04/24/2026'
    assert _fecha_americana('') == ''
    assert _fecha_americana('24-04-2026') == '04/24/2026'
    print("✓ test_fecha_americana")


def test_formato_cc():
    assert _formato_cc('10-04', 'sin_guion') == '1004'
    assert _formato_cc('10-19', 'sin_guion') == '1019'
    assert _formato_cc('10-04', 'con_guion') == '10-04'
    assert _formato_cc('10-04', 'primer_grupo') == '10'
    assert _formato_cc('') == ''
    print("✓ test_formato_cc")


# ─── BASE solo en cuentas tributarias ────────────────

def test_cuenta_lleva_base():
    # IVA y retenciones SÍ
    assert _cuenta_lleva_base('24080201') is True   # IVA descontable
    assert _cuenta_lleva_base('24080308') is True   # IVA servicios
    assert _cuenta_lleva_base('23654020') is True   # Retefuente compras
    assert _cuenta_lleva_base('23652505') is True   # Retefuente servicios
    assert _cuenta_lleva_base('23670505') is True   # ReteIVA
    assert _cuenta_lleva_base('23682002') is True   # ReteICA
    # Inventario, proveedor, gastos, ingresos NO
    assert _cuenta_lleva_base('14350503') is False  # Inventario alimentos
    assert _cuenta_lleva_base('22050501') is False  # Proveedor
    assert _cuenta_lleva_base('51950501') is False  # Gasto
    assert _cuenta_lleva_base('41xxxxx') is False   # Ingreso
    assert _cuenta_lleva_base('') is False
    print("✓ test_cuenta_lleva_base")


def test_base_solo_en_iva_y_retenciones():
    """Una factura: inventario + IVA + retefuente + proveedor.
    Solo IVA y retefuente deben tener base. Inventario y proveedor vacíos."""
    lineas = [
        LineaMock(  # Inventario - SIN base
            cuenta='14350503', debito=Decimal('100000'),
            base=Decimal('100000'),  # aunque venga la base, no se debe mostrar
            consecutivo='X1', documento_referencia='F1', nit_tercero='900', fecha='2026-04-24'
        ),
        LineaMock(  # IVA - CON base
            cuenta='24080201', debito=Decimal('19000'),
            base=Decimal('100000'),
            consecutivo='X1', documento_referencia='F1', nit_tercero='900', fecha='2026-04-24'
        ),
        LineaMock(  # Retefuente - CON base
            cuenta='23654020', credito=Decimal('2500'),
            base=Decimal('100000'),
            consecutivo='X1', documento_referencia='F1', nit_tercero='900', fecha='2026-04-24'
        ),
        LineaMock(  # Proveedor - SIN base
            cuenta='22050501', credito=Decimal('116500'),
            base=Decimal('0'),
            consecutivo='X1', documento_referencia='F1', nit_tercero='900', fecha='2026-04-24'
        ),
    ]
    df = construir_dataframe_silla_tres(lineas)

    bases = df['Base'].tolist()
    cuentas = df['CUENTA'].tolist()
    print(f"\n  Cuentas: {cuentas}")
    print(f"  Bases:   {bases}")

    # Inventario y proveedor → vacío
    assert bases[0] == ''   # 14350503 inventario
    assert bases[3] == ''   # 22050501 proveedor
    # IVA y retefuente → con valor
    assert bases[1] == '100000'  # 24080201 IVA
    assert bases[2] == '100000'  # 23654020 retefuente
    print("✓ test_base_solo_en_iva_y_retenciones")


# ─── Consecutivo configurable ────────────────────────

def test_consecutivo_inicial_default_1():
    """Sin parámetro, empieza en 1."""
    lineas = [
        LineaMock(cuenta='14350503', debito=Decimal('100'),
                  consecutivo='X1', documento_referencia='F1'),
        LineaMock(cuenta='22050501', credito=Decimal('100'),
                  consecutivo='X1', documento_referencia='F1'),
    ]
    df = construir_dataframe_silla_tres(lineas)
    assert df['DOCUMENTO'].tolist() == ['1', '1']  # ambas líneas mismo asiento
    print("✓ test_consecutivo_inicial_default_1")


def test_consecutivo_inicial_personalizado():
    """Si se pasa consecutivo_inicial=1500, empieza ahí."""
    lineas = [
        LineaMock(cuenta='14350503', debito=Decimal('100'),
                  consecutivo='X1', documento_referencia='F1'),
        LineaMock(cuenta='22050501', credito=Decimal('100'),
                  consecutivo='X1', documento_referencia='F1'),
    ]
    df = construir_dataframe_silla_tres(lineas, consecutivo_inicial=1500)
    assert df['DOCUMENTO'].tolist() == ['1500', '1500']
    print("✓ test_consecutivo_inicial_personalizado")


def test_consecutivo_se_incrementa_por_asiento():
    """Dos facturas distintas → 2 consecutivos diferentes."""
    lineas = [
        # Asiento 1 (factura X1)
        LineaMock(cuenta='14350503', debito=Decimal('100'),
                  consecutivo='X1', documento_referencia='F1', nit_tercero='900', fecha='2026-04-01'),
        LineaMock(cuenta='22050501', credito=Decimal('100'),
                  consecutivo='X1', documento_referencia='F1', nit_tercero='900', fecha='2026-04-01'),
        # Asiento 2 (factura X2)
        LineaMock(cuenta='14350503', debito=Decimal('200'),
                  consecutivo='X2', documento_referencia='F2', nit_tercero='800', fecha='2026-04-02'),
        LineaMock(cuenta='22050501', credito=Decimal('200'),
                  consecutivo='X2', documento_referencia='F2', nit_tercero='800', fecha='2026-04-02'),
    ]
    df = construir_dataframe_silla_tres(lineas, consecutivo_inicial=100)
    docs = df['DOCUMENTO'].tolist()
    assert docs == ['100', '100', '101', '101']
    print(f"✓ test_consecutivo_se_incrementa_por_asiento: {docs}")


def test_agrupacion_por_asiento():
    """3 facturas, cada una con 3 líneas → 3 asientos."""
    lineas = []
    for i in range(3):
        lineas.append(LineaMock(consecutivo=f'X{i}', documento_referencia=f'F{i}',
                                  nit_tercero=str(900 + i), fecha=f'2026-04-{i+1:02d}',
                                  cuenta='14350503', debito=Decimal('100')))
        lineas.append(LineaMock(consecutivo=f'X{i}', documento_referencia=f'F{i}',
                                  nit_tercero=str(900 + i), fecha=f'2026-04-{i+1:02d}',
                                  cuenta='24080201', debito=Decimal('19'), base=Decimal('100')))
        lineas.append(LineaMock(consecutivo=f'X{i}', documento_referencia=f'F{i}',
                                  nit_tercero=str(900 + i), fecha=f'2026-04-{i+1:02d}',
                                  cuenta='22050501', credito=Decimal('119')))
    asientos = _agrupar_lineas_por_asiento(lineas)
    assert len(asientos) == 3
    assert all(len(a) == 3 for a in asientos)
    print(f"✓ test_agrupacion_por_asiento: 3 asientos × 3 líneas")


# ─── Tipo y Valor ─────────────────────────────────────

def test_debito_tipo_1():
    df = construir_dataframe_silla_tres([LineaMock(debito=Decimal('100000'))])
    assert df.iloc[0]['Tipo'] == 1
    assert df.iloc[0]['Valor'] == 100000
    print("✓ test_debito_tipo_1")


def test_credito_tipo_2():
    df = construir_dataframe_silla_tres([LineaMock(credito=Decimal('220642'))])
    assert df.iloc[0]['Tipo'] == 2
    assert df.iloc[0]['Valor'] == 220642
    print("✓ test_credito_tipo_2")


def test_valor_siempre_positivo():
    df_db = construir_dataframe_silla_tres([LineaMock(debito=Decimal('100000'))])
    df_cr = construir_dataframe_silla_tres([LineaMock(credito=Decimal('100000'))])
    assert df_db.iloc[0]['Valor'] == 100000
    assert df_cr.iloc[0]['Valor'] == 100000
    print("✓ test_valor_siempre_positivo")


# ─── Exportación ──────────────────────────────────────

def test_dataframe_columnas_correctas():
    df = construir_dataframe_silla_tres([LineaMock(debito=Decimal('100'))])
    assert list(df.columns) == CABECERAS
    print(f"✓ test_dataframe_columnas_correctas: {list(df.columns)}")


def test_exportar_txt():
    linea = LineaMock(fecha='2026-04-24', comprobante='3', cuenta='14350503',
                       debito=Decimal('216416'))
    df = construir_dataframe_silla_tres([linea])
    txt = exportar_txt_silla_tres(df)
    assert isinstance(txt, bytes)
    s = txt.decode('utf-8')
    assert 'CUENTA\tComprobante' in s
    assert '14350503' in s
    assert '04/24/2026' in s
    print("✓ test_exportar_txt")


def test_exportar_csv():
    df = construir_dataframe_silla_tres([LineaMock(cuenta='14350503', debito=Decimal('1000'))])
    csv = exportar_csv_silla_tres(df)
    s = csv.decode('utf-8')
    assert 'CUENTA,Comprobante' in s
    print("✓ test_exportar_csv")


def test_exportar_xlsx():
    df = construir_dataframe_silla_tres([LineaMock(cuenta='14350503', debito=Decimal('1000'))])
    xlsx = exportar_xlsx_silla_tres(df)
    assert isinstance(xlsx, bytes)
    assert xlsx[:2] == b'PK'
    print(f"✓ test_exportar_xlsx ({len(xlsx)} bytes)")


def test_descripcion_sanitiza_tabs():
    df = construir_dataframe_silla_tres([
        LineaMock(descripcion='LINEA1\tCON_TAB\nY_NEWLINE', debito=Decimal('1000'))
    ])
    detalle = df.iloc[0]['DETALLE']
    assert '\t' not in detalle and '\n' not in detalle
    print(f"✓ test_descripcion_sanitiza_tabs")


# ─── Test integración: asiento completo realista ─────

def test_asiento_completo_realista():
    """Factura Atlantic FS por $220.642 con CC ROSARIO POBLADO."""
    lineas = [
        LineaMock(  # Inventario alimentos
            fecha='2026-04-24', comprobante='3', consecutivo='X1',
            cuenta='14350503', centro_costo='10-02', nit_tercero='900040299',
            descripcion='INVENTARIO ALIMENTOS', documento_referencia='FAT1110734925',
            debito=Decimal('216416'), base=Decimal('216416')  # base se ignora
        ),
        LineaMock(  # IVA descontable 19%
            fecha='2026-04-24', comprobante='3', consecutivo='X1',
            cuenta='24080201', centro_costo='10-02', nit_tercero='900040299',
            descripcion='IVA DESCONTABLE 19%', documento_referencia='FAT1110734925',
            debito=Decimal('4226'), base=Decimal('22244')  # base sí se muestra
        ),
        LineaMock(  # Retefuente 2.5%
            fecha='2026-04-24', comprobante='3', consecutivo='X1',
            cuenta='23654020', centro_costo='10-02', nit_tercero='900040299',
            descripcion='RETEFUENTE COMPRAS 2.5%', documento_referencia='FAT1110734925',
            credito=Decimal('5410'), base=Decimal('216416')  # base sí se muestra
        ),
        LineaMock(  # Proveedor (cuenta x pagar)
            fecha='2026-04-24', comprobante='3', consecutivo='X1',
            cuenta='22050501', centro_costo='10-02', nit_tercero='900040299',
            descripcion='ATLANTIC FS S.A.S', documento_referencia='FAT1110734925',
            credito=Decimal('215232'),
        ),
    ]
    df = construir_dataframe_silla_tres(lineas, cc_formato='sin_guion',
                                          consecutivo_inicial=1500)

    print("\n  ─── Asiento completo ───")
    print(df.to_string(index=False))

    # Verificaciones
    assert df['DOCUMENTO'].tolist() == ['1500'] * 4  # mismo número en todas
    assert df['Tipo'].tolist() == [1, 1, 2, 2]
    assert df['Valor'].tolist() == [216416, 4226, 5410, 215232]
    # BASE: solo en IVA y retefuente
    assert df['Base'].tolist() == ['', '22244', '216416', '']
    assert df['Centro de Costo'].tolist() == ['1002'] * 4
    assert df['Fecha(mm/dd/yyyy)'].tolist() == ['04/24/2026'] * 4

    # Cuadre DB = CR
    db_total = df[df['Tipo'] == 1]['Valor'].sum()
    cr_total = df[df['Tipo'] == 2]['Valor'].sum()
    assert db_total == cr_total == 220642
    print(f"\n  Cuadre OK: DB={db_total} = CR={cr_total}")
    print("✓ test_asiento_completo_realista")


if __name__ == '__main__':
    print("=== Tests del exportador Silla Tres v2 ===\n")
    test_fecha_americana()
    test_formato_cc()
    test_cuenta_lleva_base()
    test_base_solo_en_iva_y_retenciones()
    test_consecutivo_inicial_default_1()
    test_consecutivo_inicial_personalizado()
    test_consecutivo_se_incrementa_por_asiento()
    test_agrupacion_por_asiento()
    test_debito_tipo_1()
    test_credito_tipo_2()
    test_valor_siempre_positivo()
    test_dataframe_columnas_correctas()
    test_exportar_txt()
    test_exportar_csv()
    test_exportar_xlsx()
    test_descripcion_sanitiza_tabs()
    test_asiento_completo_realista()
    print("\n✅ Todos los tests pasaron")
