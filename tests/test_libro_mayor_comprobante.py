"""
Tests de LIBRO MAYOR y COMPROBANTE DE DIARIO — lógica pura (no toca Supabase).

Cubre las funciones _calc_* de core/contable/servicio_contable.py y la
generación del PDF del comprobante (sanity check).

Ejecutar: pytest tests/test_libro_mayor_comprobante.py -v
"""
import pandas as pd
import pytest

from core.contable import servicio_contable as cont
from core.contable.pdf_comprobante import generar_pdf_comprobante, _fmt, _fecha_larga


# Movimiento de prueba: dos períodos, dos comprobantes.
# 202605: comprobante 1 doc 100 (Db 111005 1.000.000 / Cr 111005? no) -> asiento cuadrado
# Usamos un asiento simple: Db 5195 (gasto) 100.000 / Cr 1110 (banco) 100.000 en 202606,
# y un saldo anterior en 202605 para 1110.
MOVS = [
    # período anterior (202605): banco recibe 500.000 (Db 111005), capital 500.000 (Cr 311505)
    {"cuenta": "111005", "periodo": "202605", "comprobante": "5", "documento": "1",
     "fecha": "2026-05-01", "nit": "900", "detalle": "Aporte", "tr": "1", "valor": 500000, "centro_costo": ""},
    {"cuenta": "311505", "periodo": "202605", "comprobante": "5", "documento": "1",
     "fecha": "2026-05-01", "nit": "900", "detalle": "Aporte", "tr": "2", "valor": 500000, "centro_costo": ""},
    # período en rango (202606): gasto 100.000 contra banco
    {"cuenta": "519595", "periodo": "202606", "comprobante": "1", "documento": "100",
     "fecha": "2026-06-15", "nit": "800", "detalle": "Papelería", "tr": "1", "valor": 100000, "centro_costo": "01"},
    {"cuenta": "111005", "periodo": "202606", "comprobante": "1", "documento": "100",
     "fecha": "2026-06-15", "nit": "800", "detalle": "Papelería", "tr": "2", "valor": 100000, "centro_costo": "01"},
]

NOMBRES = {"111005": "Banco", "311505": "Capital", "519595": "Diversos"}


class TestLibroMayor:
    def test_saldo_anterior_y_final_por_cuenta_completa(self):
        df = cont._calc_libro_mayor(MOVS, "202606", "202606", nivel=None, nombres=NOMBRES)
        banco = df[df["Cuenta"] == "111005"].iloc[0]
        # saldo anterior de banco = 500.000 (Db en 202605)
        assert banco["Saldo anterior"] == 500000
        # en 202606 el banco tuvo crédito 100.000
        assert banco["Débitos"] == 0
        assert banco["Créditos"] == 100000
        assert banco["Saldo final"] == 400000  # 500.000 - 100.000

    def test_gasto_solo_movimiento_del_rango(self):
        df = cont._calc_libro_mayor(MOVS, "202606", "202606", nivel=None, nombres=NOMBRES)
        gasto = df[df["Cuenta"] == "519595"].iloc[0]
        assert gasto["Saldo anterior"] == 0
        assert gasto["Débitos"] == 100000
        assert gasto["Saldo final"] == 100000

    def test_agrega_por_nivel_clase(self):
        # A nivel de 1 dígito (clase): banco(1) trae 500.000 anterior,
        # capital(3) trae -500.000 (crédito).
        df = cont._calc_libro_mayor(MOVS, "202606", "202606", nivel=1, nombres={})
        clases = dict(zip(df["Cuenta"], df["Saldo anterior"]))
        assert clases["1"] == 500000      # activo
        assert clases["3"] == -500000     # patrimonio (crédito -> negativo en Db-Cr)

    def test_agrega_por_nivel_grupo(self):
        # nivel 2: 11 (disponible), 31 (capital), 51 (gastos operac.)
        df = cont._calc_libro_mayor(MOVS, "202606", "202606", nivel=2, nombres={})
        assert set(df["Cuenta"]) == {"11", "31", "51"}

    def test_omite_cuentas_totalmente_en_cero(self):
        movs = [
            {"cuenta": "111005", "periodo": "202606", "tr": "1", "valor": 0},
        ]
        df = cont._calc_libro_mayor(movs, "202606", "202606")
        assert len(df) == 0

    def test_movimiento_del_rango_cuadra(self):
        df = cont._calc_libro_mayor(MOVS, "202606", "202606", nivel=None, nombres=NOMBRES)
        assert int(df["Débitos"].sum()) == int(df["Créditos"].sum())


class TestAgruparComprobantes:
    def test_agrupa_por_comprobante_documento(self):
        grupos = cont._agrupar_comprobantes(MOVS)
        assert len(grupos) == 2  # (5,1) y (1,100)
        claves = {(g["comprobante"], g["documento"]) for g in grupos}
        assert claves == {("5", "1"), ("1", "100")}

    def test_totales_y_cuadre_por_asiento(self):
        grupos = {(g["comprobante"], g["documento"]): g
                  for g in cont._agrupar_comprobantes(MOVS)}
        g = grupos[("1", "100")]
        assert g["debitos"] == 100000
        assert g["creditos"] == 100000
        assert g["cuadra"] is True
        assert g["lineas"] == 2

    def test_orden_cronologico(self):
        grupos = cont._agrupar_comprobantes(MOVS)
        fechas = [g["fecha"] for g in grupos]
        assert fechas == sorted(fechas)

    def test_detecta_descuadre(self):
        movs = [
            {"cuenta": "1", "comprobante": "9", "documento": "1", "fecha": "2026-06-01",
             "tr": "1", "valor": 100},
            {"cuenta": "2", "comprobante": "9", "documento": "1", "fecha": "2026-06-01",
             "tr": "2", "valor": 90},
        ]
        g = cont._agrupar_comprobantes(movs)[0]
        assert g["cuadra"] is False
        assert g["diferencia"] == 10


class TestCalcComprobante:
    def test_header_detalle_y_totales(self):
        header, det, tot = cont._calc_comprobante(MOVS, "1", "100", nombres=NOMBRES)
        assert header["comprobante"] == "1"
        assert header["documento"] == "100"
        assert header["fecha"] == "2026-06-15"
        assert header["periodo"] == "202606"
        assert tot["debitos"] == 100000
        assert tot["creditos"] == 100000
        assert tot["cuadra"] is True
        assert len(det) == 2

    def test_debitos_primero(self):
        _, det, _ = cont._calc_comprobante(MOVS, "1", "100", nombres=NOMBRES)
        # la primera fila debe ser el débito (tr=1 -> gasto 519595)
        assert det.iloc[0]["Débito"] == 100000
        assert det.iloc[0]["Crédito"] == 0

    def test_nombre_de_cuenta_resuelto(self):
        _, det, _ = cont._calc_comprobante(MOVS, "1", "100", nombres=NOMBRES)
        nombres = set(det["Nombre"])
        assert "Diversos" in nombres and "Banco" in nombres

    def test_comprobante_inexistente_da_vacio(self):
        header, det, tot = cont._calc_comprobante(MOVS, "99", "0")
        assert len(det) == 0
        assert tot["debitos"] == 0 and tot["creditos"] == 0
        assert header["fecha"] is None


class TestPdfComprobante:
    def test_formato_numero(self):
        assert _fmt(1234567) == "1.234.567"
        assert _fmt(0) == ""
        assert _fmt(None) == ""

    def test_fecha_larga(self):
        assert _fecha_larga("2026-06-15") == "15 de junio de 2026"
        assert _fecha_larga("") == ""

    def test_genera_pdf_valido(self):
        _, det, tot = cont._calc_comprobante(MOVS, "1", "100", nombres=NOMBRES)
        datos = {
            "empresa": "JIPER SAS", "nit_empresa": "901038325",
            "comprobante_cod": "1", "comprobante_nombre": "Egreso",
            "documento": "100", "fecha": "2026-06-15", "periodo": "202606",
            "detalle": "Papelería",
            "lineas": [
                {"cuenta": r["Cuenta"], "nombre": r["Nombre"], "nit": r["NIT"],
                 "detalle": r["Detalle"], "cc": r["C. Costo"],
                 "debito": r["Débito"], "credito": r["Crédito"]}
                for r in det.to_dict("records")
            ],
            "total_debito": tot["debitos"], "total_credito": tot["creditos"],
        }
        pdf = generar_pdf_comprobante(datos)
        assert isinstance(pdf, (bytes, bytearray))
        assert pdf[:4] == b"%PDF"
        assert len(pdf) > 1000
