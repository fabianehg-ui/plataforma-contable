"""
Tests del procesador POS desde Token (procesador_ventas_excel_token_v2)
con la lógica de propinas activada.

Casos clave:
  1. Asiento POS con propina genera la línea Cr 28150505.
  2. Cuadre Db=Cr garantizado (Db Caja incluye propina).
  3. Sin propina → asiento clásico (sin línea de propinas).
  4. Tolerancia de redondeo (propina ≤ $5 no se asienta).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.procesadores.procesador_ventas_excel_token_v2 import (
    _generar_lineas_pos_consolidado,
    CUENTA_PROPINAS_POS,
    TR_DEBITO,
    TR_CREDITO,
    TOLERANCIA,
)


def _check_cuadre(lineas):
    db = sum(l["VALOR"] for l in lineas if l["TR"] == TR_DEBITO)
    cr = sum(l["VALOR"] for l in lineas if l["TR"] == TR_CREDITO)
    return db, cr


def _grupo_base(propina=0):
    """Helper para construir un dict de grupo POS realista."""
    from datetime import date
    return {
        "fecha": date(2026, 3, 15),
        "prefijo": "VIV",
        "cc": "001106",
        "nombre_sucursal": "Viva Envigado",
        "cuenta_caja": "11050515",
        "cta_base_v": "41401501",
        "cta_ico": "24800505",
        "comprobante": "406",
        "clase": "SANTA LEÑA",
        "n_facturas": 10,
        "base": 100000,
        "inc": 8000,
        "iva": 0,
        "otros": 0,
        "propina": propina,
        "total_bruto": 108000 + propina,
        "n_ncs": 0,
        "nc_base": 0, "nc_inc": 0, "nc_iva": 0, "nc_total": 0,
    }


class TestPropinasEnTokenPOS:

    def test_sin_propina_3_lineas_clasicas(self):
        """Sin propina → Db caja + Cr base + Cr INC."""
        g = _grupo_base(propina=0)
        lineas = _generar_lineas_pos_consolidado(g)

        assert len(lineas) == 3
        propinas = [l for l in lineas if l["CUENTA"] == CUENTA_PROPINAS_POS]
        assert len(propinas) == 0

        db, cr = _check_cuadre(lineas)
        assert db == cr == 108000

    def test_con_propina_4_lineas_cuadrado(self):
        """Con propina de $12.000:
           Db Caja  = 100k + 8k + 12k = 120.000
           Cr Base  = 100.000
           Cr INC   = 8.000
           Cr Prop  = 12.000
        Total Db = Total Cr = 120.000.
        """
        g = _grupo_base(propina=12000)
        lineas = _generar_lineas_pos_consolidado(g)

        assert len(lineas) == 4
        propinas = [l for l in lineas if l["CUENTA"] == CUENTA_PROPINAS_POS]
        assert len(propinas) == 1
        assert propinas[0]["VALOR"] == 12000
        assert propinas[0]["TR"] == TR_CREDITO
        assert propinas[0]["CENTRO DE COSTO"] == "001106"

        # Db Caja incluye propina
        caja = [l for l in lineas if l["CUENTA"] == "11050515"]
        assert caja[0]["VALOR"] == 120000
        assert caja[0]["TR"] == TR_DEBITO

        # Cuadre
        db, cr = _check_cuadre(lineas)
        assert db == cr == 120000

    def test_tolerancia_propina_pequena(self):
        """Propina ≤ TOLERANCIA ($5) → tratada como redondeo, no se asienta."""
        g = _grupo_base(propina=TOLERANCIA)  # = 5
        lineas = _generar_lineas_pos_consolidado(g)

        propinas = [l for l in lineas if l["CUENTA"] == CUENTA_PROPINAS_POS]
        assert len(propinas) == 0

        # Pero el cuadre debe seguir siendo Db=Cr (la propina pequeña se ignora
        # del Db caja también, así no descuadra)
        db, cr = _check_cuadre(lineas)
        assert db == cr

    def test_cc_propina_es_del_prefijo(self):
        """La línea de propina lleva el CC del prefijo (sucursal)."""
        g = _grupo_base(propina=5000)
        g["cc"] = "001207"   # ej. Milagros Milla de Oro
        g["nombre_sucursal"] = "Milagros Milla de Oro"
        g["prefijo"] = "MMI"

        lineas = _generar_lineas_pos_consolidado(g)
        propinas = [l for l in lineas if l["CUENTA"] == CUENTA_PROPINAS_POS]
        assert len(propinas) == 1
        assert propinas[0]["CENTRO DE COSTO"] == "001207"
        assert "MMI" in propinas[0]["DETALLE"]
        assert "PROPINA VENTAS" in propinas[0]["DETALLE"]

    def test_cuadre_con_iva_y_propina(self):
        """Caso con IVA + propina: cuadre se mantiene."""
        g = _grupo_base(propina=20000)
        g["iva"] = 9500       # IVA 19% sobre base = ej. 50k IVA → base ≈ 50k
        g["base"] = 100000    # base de INC (es el cálculo del Token)
        g["inc"] = 8000

        lineas = _generar_lineas_pos_consolidado(g)
        # Esperamos 5 líneas: Db Caja + Cr Base + Cr INC + Cr IVA + Cr Propina
        assert len(lineas) == 5

        db, cr = _check_cuadre(lineas)
        assert db == cr
        # Total = 100k + 8k + 9.5k + 20k = 137.500
        assert db == 137500
