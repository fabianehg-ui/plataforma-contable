"""
Tests del flujo de filtros del descargador unificado (paso 2):
  - Detección de tipos disponibles para RECIBIDOS
  - Detección de prefijos disponibles para EMITIDOS
  - Defaults correctos (excluir Application response, Nomina Individual)
  - Selección y conteo de CUFEs a descargar
"""
import io
import sys
from datetime import date
from pathlib import Path

import pytest
from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.procesadores import lector_excel_token as lex


# ============================================================
# Helper
# ============================================================

def _construir_excel_token(samples: list[tuple]) -> io.BytesIO:
    """Construye un Excel del Token con la estructura DIAN real.

    samples: lista de (tipo_documento, prefijo, n, grupo).
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Rp_Doc"
    encabezados = [
        "Tipo de documento", "CUFE/CUDE", "Folio", "Prefijo", "Divisa",
        "Forma de Pago", "Medio de Pago", "Fecha Emisión", "Fecha Recepción",
        "NIT Emisor", "Nombre Emisor", "NIT Receptor", "Nombre Receptor",
        "IVA", "ICA", "IC", "INC", "Timbre", "INC Bolsas", "IN Carbono",
        "IN Combustibles", "IC Datos", "ICL", "INPP", "IBUA", "ICUI",
        "Rete IVA", "Rete Renta", "Rete ICA", "Total", "Estado", "Grupo",
    ]
    ws.append(encabezados)
    i = 0
    for tipo, pref, n, grupo in samples:
        for _ in range(n):
            i += 1
            ws.append([
                tipo, f"CUFE_{i:04d}", str(i), pref, "COP",
                "Contado", "Efectivo", "15/03/2026", "15/03/2026",
                f"800{i:06d}" if grupo == "Recibido" else "901038325",
                f"EMISOR {i}",
                "901038325" if grupo == "Recibido" else f"900{i:06d}",
                "JIPER" if grupo == "Recibido" else f"CLIENTE {i}",
                0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                100000, "Validado", grupo,
            ])
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    return bio


# ============================================================
# Tests
# ============================================================

class TestFiltrosDescargadorUnificado:

    def test_deteccion_tipos_recibidos(self):
        """El paso 2 detecta todos los tipos de documento recibidos."""
        bio = _construir_excel_token([
            ("Factura electronica", "FEPRV", 60, "Recibido"),
            ("Nota credito", "NCFE", 5, "Recibido"),
            ("Documento Soporte Electrónico", "DSEREC", 20, "Recibido"),
        ])
        df = lex.leer_excel_token(bio)
        df_recb = df[df["grupo"].str.lower() == "recibido"]
        tipos = df_recb["tipo_documento"].value_counts().to_dict()

        assert "Factura electronica" in tipos
        assert tipos["Factura electronica"] == 60
        assert tipos["Nota credito"] == 5
        assert tipos["Documento Soporte Electrónico"] == 20

    def test_application_response_y_nomina_son_excluibles(self):
        """Application response y Nomina Individual están en TIPOS_EXCLUIBLES."""
        assert "Application response" in lex.TIPOS_EXCLUIBLES
        assert "Nomina Individual" in lex.TIPOS_EXCLUIBLES

    def test_filtrar_recibidos_por_seleccion(self):
        """Solo se descargan los tipos seleccionados."""
        bio = _construir_excel_token([
            ("Factura electronica", "FEPRV", 60, "Recibido"),
            ("Application response", "AR", 10, "Recibido"),
            ("Nota credito", "NCFE", 5, "Recibido"),
        ])
        df = lex.leer_excel_token(bio)
        df_recb = df[df["grupo"].str.lower() == "recibido"]

        # Selección: solo FE (no marcar AR ni NC)
        seleccion = ["Factura electronica"]
        df_sel = df_recb[df_recb["tipo_documento"].isin(seleccion)]
        assert len(df_sel) == 60

    def test_deteccion_prefijos_emitidos(self):
        """El paso 2 lista todos los prefijos de emitidos."""
        bio = _construir_excel_token([
            ("Factura electronica", "STL", 15, "Emitido"),
            ("Documento Soporte Electrónico", "DSE", 8, "Emitido"),
            ("Factura electronica", "VIV", 50, "Emitido"),
            ("Factura electronica", "IND", 30, "Emitido"),
        ])
        df = lex.leer_excel_token(bio)
        df_emit = df[df["grupo"].str.lower() == "emitido"]
        df_emit_util = df_emit[~df_emit["tipo_documento"].isin(lex.TIPOS_EXCLUIBLES)]

        prefijos = (
            df_emit_util["prefijo"]
            .astype(str).str.strip().str.upper()
            .value_counts().to_dict()
        )

        # Los 4 prefijos deben aparecer
        assert set(prefijos.keys()) == {"STL", "DSE", "VIV", "IND"}
        assert prefijos["VIV"] == 50  # el más numeroso
        assert prefijos["STL"] == 15

    def test_filtrar_emitidos_por_prefijos(self):
        """Solo se descargan los prefijos marcados."""
        bio = _construir_excel_token([
            ("Factura electronica", "STL", 15, "Emitido"),
            ("Documento Soporte Electrónico", "DSE", 8, "Emitido"),
            ("Factura electronica", "VIV", 50, "Emitido"),
            ("Factura electronica", "IND", 30, "Emitido"),
        ])
        df = lex.leer_excel_token(bio)
        df_emit = df[df["grupo"].str.lower() == "emitido"]

        # Selección: STL + DSE (default sugerido)
        seleccion = ["STL", "DSE"]
        mascara = (
            df_emit["prefijo"]
            .astype(str).str.strip().str.upper()
            .isin(seleccion)
        )
        df_sel = df_emit[mascara]
        assert len(df_sel) == 15 + 8  # 23

    def test_consolidado_recibidos_mas_emitidos(self):
        """El total a descargar = recibidos seleccionados + emitidos seleccionados."""
        bio = _construir_excel_token([
            ("Factura electronica", "STL", 15, "Emitido"),
            ("Documento Soporte Electrónico", "DSE", 8, "Emitido"),
            ("Factura electronica", "VIV", 50, "Emitido"),
            ("Factura electronica", "FEPRV", 60, "Recibido"),
            ("Application response", "AR", 10, "Recibido"),
            ("Nomina Individual", "NI", 4, "Recibido"),
        ])
        df = lex.leer_excel_token(bio)
        df_recb = df[df["grupo"].str.lower() == "recibido"]
        df_emit = df[df["grupo"].str.lower() == "emitido"]

        # Usuario marca: FE (recibidos), STL+DSE (emitidos)
        tipos_recb_sel = ["Factura electronica"]
        prefijos_emit_sel = ["STL", "DSE"]

        df_recb_sel = df_recb[df_recb["tipo_documento"].isin(tipos_recb_sel)]
        df_emit_sel = df_emit[
            df_emit["prefijo"].astype(str).str.strip().str.upper().isin(prefijos_emit_sel)
        ]

        total = len(df_recb_sel) + len(df_emit_sel)
        assert total == 60 + 15 + 8  # 83

        # Lista final de CUFEs a descargar
        cufes_total = df_recb_sel["cufe"].tolist() + df_emit_sel["cufe"].tolist()
        assert len(cufes_total) == 83
        assert len(set(cufes_total)) == 83  # todos únicos

    def test_filtro_por_fecha_funciona(self):
        """El filtro de fechas reduce correctamente el rango."""
        bio = _construir_excel_token([
            ("Factura electronica", "STL", 10, "Emitido"),
        ])
        df = lex.leer_excel_token(bio)

        # Filtro fuera de rango
        df_fuera = lex.filtrar_por_rango(df, date(2026, 4, 1), date(2026, 4, 30))
        assert len(df_fuera) == 0

        # Filtro dentro de rango
        df_dentro = lex.filtrar_por_rango(df, date(2026, 3, 1), date(2026, 3, 31))
        assert len(df_dentro) == 10
