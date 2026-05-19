"""
Tests del nuevo modo `solo_pos` del procesador de ventas Token.

Cambios validados:
  1. STL detalladas se descartan (vienen por XML).
  2. NCs STL se descartan.
  3. DSE se descarta.
  4. Prefijos no mapeados se descartan.
  5. NCs POS (NCVI, NCT...) SÍ se procesan y se cruzan con FE del mismo
     día/sucursal aunque tengan prefijo distinto.
  6. Plano sale ordenado por fecha ascendente.
  7. DOCUMENTO = día del mes (1, 2, 3... 31).
  8. No se aplica el numerador consecutivo posterior.
"""
import io
import sys
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.procesadores import lector_excel_token as lex
from core.procesadores.procesador_ventas_excel_token_v2 import procesar_ventas_v2


RUTA_MAPEO = str(ROOT / "mapeo_prefijos_token.json")


def _construir_excel(samples):
    """samples: lista de (tipo_doc, cufe, folio, prefijo, fecha, total, inc, iva)."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Rp_Doc"
    ws.append([
        "Tipo de documento", "CUFE/CUDE", "Folio", "Prefijo", "Divisa",
        "Forma de Pago", "Medio de Pago", "Fecha Emisión", "Fecha Recepción",
        "NIT Emisor", "Nombre Emisor", "NIT Receptor", "Nombre Receptor",
        "IVA", "ICA", "IC", "INC", "Timbre", "INC Bolsas", "IN Carbono",
        "IN Combustibles", "IC Datos", "ICL", "INPP", "IBUA", "ICUI",
        "Rete IVA", "Rete Renta", "Rete ICA", "Total", "Estado", "Grupo",
    ])
    for tipo, cufe, folio, pref, fecha, total, inc, iva in samples:
        ws.append([
            tipo, cufe, folio, pref, "COP", "Contado", "Efectivo", fecha, fecha,
            "901038325", "JIPER SAS", "222222222", "X",
            iva, 0, 0, inc, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
            total, "Validado", "Emitido",
        ])
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    return bio


class TestModoSoloPos:

    def test_solo_pos_descarta_stl(self):
        """Una factura STL se descarta en modo solo_pos."""
        bio = _construir_excel([
            ("Factura electronica", "C1", "100", "VIV", "15/03/2026", 108000, 8000, 0),
            ("Factura electronica", "C2", "200", "STL", "15/03/2026", 119000, 0, 19000),
        ])
        df = lex.leer_excel_token(bio)
        res = procesar_ventas_v2(df, RUTA_MAPEO, None, modo="solo_pos")
        assert len(res.stl_detalladas) == 0
        assert len(res.pos_consolidados) == 1   # solo el de VIV

    def test_solo_pos_descarta_dse(self):
        bio = _construir_excel([
            ("Factura electronica", "C1", "100", "VIV", "15/03/2026", 108000, 8000, 0),
            ("Documento Soporte Electrónico", "C2", "200", "DSE", "15/03/2026", 50000, 0, 0),
        ])
        df = lex.leer_excel_token(bio)
        res = procesar_ventas_v2(df, RUTA_MAPEO, None, modo="solo_pos")
        assert len(res.dse_detalladas) == 0

    def test_solo_pos_descarta_prefijo_no_mapeado(self):
        bio = _construir_excel([
            ("Factura electronica", "C1", "100", "VIV", "15/03/2026", 108000, 8000, 0),
            ("Factura electronica", "C2", "200", "XXX", "15/03/2026", 1000, 80, 0),
        ])
        df = lex.leer_excel_token(bio)
        res = procesar_ventas_v2(df, RUTA_MAPEO, None, modo="solo_pos")
        assert len(res.pos_consolidados) == 1   # solo VIV
        assert len(res.sin_sucursal) == 0       # XXX se descarta silenciosamente

    def test_documento_es_dia_del_mes(self):
        """DOCUMENTO debe ser el día del mes (1, 2, 3...) no consecutivo."""
        bio = _construir_excel([
            ("Factura electronica", "C1", "100", "VIV", "01/03/2026", 108000, 8000, 0),
            ("Factura electronica", "C2", "200", "IND", "15/03/2026", 54000, 4000, 0),
            ("Factura electronica", "C3", "300", "VIV", "31/03/2026", 108000, 8000, 0),
        ])
        df = lex.leer_excel_token(bio)
        res = procesar_ventas_v2(df, RUTA_MAPEO, None, modo="solo_pos")
        docs = sorted(set(res.plano_df["DOCUMENTO"].astype(str)), key=int)
        assert docs == ["1", "15", "31"]

    def test_orden_cronologico_ascendente(self):
        """Las fechas en el plano salen de más antigua a más reciente."""
        bio = _construir_excel([
            # Desordenadas intencionalmente
            ("Factura electronica", "C1", "300", "VIV", "20/03/2026", 108000, 8000, 0),
            ("Factura electronica", "C2", "100", "IND", "05/03/2026", 54000, 4000, 0),
            ("Factura electronica", "C3", "200", "VIV", "15/03/2026", 108000, 8000, 0),
        ])
        df = lex.leer_excel_token(bio)
        res = procesar_ventas_v2(df, RUTA_MAPEO, None, modo="solo_pos")
        fechas = pd.to_datetime(res.plano_df["FECHA"], format="%m/%d/%Y")
        assert list(fechas) == sorted(fechas)
        # Verificar que el día 5 va primero, día 20 último
        primer_doc = str(res.plano_df.iloc[0]["DOCUMENTO"])
        ultimo_doc = str(res.plano_df.iloc[-1]["DOCUMENTO"])
        assert primer_doc == "5"
        assert ultimo_doc == "20"

    def test_nc_pos_se_cruza_con_fe_misma_sucursal(self):
        """NCVI (NC de VIV) debe fusionarse con FE de VIV del mismo día."""
        bio = _construir_excel([
            ("Factura electronica", "C1", "100", "VIV", "15/03/2026", 108000, 8000, 0),
            ("Factura electronica", "C2", "101", "VIV", "15/03/2026", 216000, 16000, 0),
            ("Nota credito",        "C3", "999", "NCVI","15/03/2026",  54000, 4000, 0),
        ])
        df = lex.leer_excel_token(bio)
        res = procesar_ventas_v2(df, RUTA_MAPEO, None, modo="solo_pos")

        # Un solo grupo consolidado con 2 facs + 1 NC
        assert len(res.pos_consolidados) == 1
        g = res.pos_consolidados[0]
        assert g["n_facturas"] == 2
        assert g["n_ncs"] == 1

        # Debe aparecer la línea de DEVOLUCION
        detalles = " ".join(res.plano_df["DETALLE"].astype(str))
        assert "DEVOLUCION POS" in detalles

    def test_plano_cuadrado(self):
        """Db = Cr siempre."""
        bio = _construir_excel([
            ("Factura electronica", "C1", "100", "VIV", "01/03/2026", 108000, 8000, 0),
            ("Factura electronica", "C2", "101", "VIV", "01/03/2026", 216000, 16000, 0),
            ("Nota credito",        "C3", "999", "NCVI","01/03/2026",  54000, 4000, 0),
            ("Factura electronica", "C4", "200", "IND", "15/03/2026",  54000, 4000, 0),
        ])
        df = lex.leer_excel_token(bio)
        res = procesar_ventas_v2(df, RUTA_MAPEO, None, modo="solo_pos")
        plano = res.plano_df.copy()
        plano["V"] = pd.to_numeric(plano["VALOR"], errors="coerce").fillna(0)
        db = plano[plano["TR"] == "1"]["V"].sum()
        cr = plano[plano["TR"] == "2"]["V"].sum()
        assert abs(db - cr) < 100

    def test_modo_completo_no_se_altera(self):
        """En modo 'completo' (default) STL/DSE siguen procesándose."""
        bio = _construir_excel([
            ("Factura electronica", "C1", "100", "VIV", "15/03/2026", 108000, 8000, 0),
            ("Factura electronica", "C2", "200", "STL", "15/03/2026", 119000, 0, 19000),
        ])
        df = lex.leer_excel_token(bio)
        # Modo completo (default) — STL debería procesarse
        res = procesar_ventas_v2(df, RUTA_MAPEO, None, modo="completo")
        # STL detallada debe estar presente
        assert len(res.stl_detalladas) == 1
