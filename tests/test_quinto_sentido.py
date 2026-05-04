"""
Test de validación end-to-end: reproducir el Form 110 AG 2025 de
QUINTO SENTIDOS S.A.S. al peso contra el Excel modelo del contador.

VALORES ESPERADOS (Excel modelo del contador):
    Casilla 44 (Patrimonio bruto):       1.783.409.000
    Casilla 46 (Patrimonio líquido):       249.369.000
    Casilla 58 (Ingresos brutos):        1.098.144.000
    Casilla 67 (Total costos y gastos):    974.817.000
    Casilla 72 (Renta líq. ordinaria):     123.327.000
    Casilla 84 (Impuesto 35%):              43.164.000
    Casilla 99 (Total impuesto a cargo):    43.164.000
    Casilla 107 (Total retenciones):        33.169.000
    Casilla 114 (SALDO A FAVOR):            27.911.000

Tolerancia: $1.000 por casilla (las casillas DIAN se presentan en miles,
así que diferencias < $1.000 son ruido de redondeo).
"""
from __future__ import annotations
import sys
from pathlib import Path

# Soporte para ejecución directa fuera de pytest
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from core.procesadores.renta import (
    LiquidadorRenta,
    ParametrosLiquidacion,
)


# ============================================================
# DATOS DEL CONTRIBUYENTE
# ============================================================
NIT = "900533491"
RAZON_SOCIAL = "QUINTO SENTIDOS S.A.S."
ACTIVIDAD_PRINCIPAL = "4781"  # Comercio al por menor
COD_SECCIONAL = "11"           # Bogotá
ANO_GRAVABLE = 2025

# Tolerancia: las casillas DIAN se presentan en miles
TOLERANCIA_PESOS = 1000


# ============================================================
# FIXTURE: liquidación reproducible
# ============================================================
@pytest.fixture
def liq() -> LiquidadorRenta:
    """Construye y ejecuta la liquidación de QUINTO SENTIDOS para AG 2025."""
    parametros = ParametrosLiquidacion(
        ano_gravable=ANO_GRAVABLE,
        es_gran_contribuyente=False,
        patrimonio_liquido_ano_anterior=170_219_000,
        saldo_a_favor_ano_anterior=37_906_000,
        impuesto_neto_renta_ano_anterior=31_507_000,
        ano_actual_de_declaracion=3,
    )

    liq = LiquidadorRenta(
        nit=NIT,
        razon_social=RAZON_SOCIAL,
        actividad_principal=ACTIVIDAD_PRINCIPAL,
        cod_seccional=COD_SECCIONAL,
        parametros=parametros,
    )

    # Patrimonio (a 31-DIC-2025, valor fiscal)
    liq.cargar_patrimonio(
        efectivo=72_243_000,           # Cas. 36
        inversiones=0,                  # Cas. 37
        cxc=70_875_000,                 # Cas. 38
        inventarios=1_256_039_000,      # Cas. 39
        intangibles=0,                  # Cas. 40
        biologicos=0,                   # Cas. 41
        ppe=281_570_000,                # Cas. 42
        otros_activos=102_682_000,      # Cas. 43
        pasivos=1_534_040_000,          # Cas. 45
    )

    # Ingresos
    liq.cargar_ingresos(
        ingresos_ordinarios=1_082_118_000,  # Cas. 47
        ingresos_financieros=3_194_000,     # Cas. 48
        otros_ingresos=12_832_000,          # Cas. 57 (incapacidades EPS)
        devoluciones=0,                     # Cas. 59
        incrngo=0,                          # Cas. 60
    )

    # Costos y gastos (FISCALES, ya con ajuste por exceso de depreciación
    # contable sobre límite fiscal: -$27M en gastos de ventas)
    liq.cargar_costos_y_gastos(
        costos=341_324_000,              # Cas. 62
        gastos_administracion=60_298_000, # Cas. 63
        gastos_ventas=569_933_000,        # Cas. 64 ($596,932,913 - $27M depreciación)
        gastos_financieros=3_262_000,     # Cas. 65 (incluye GMF 50%)
        otros_gastos=0,                   # Cas. 66
    )

    # Datos informativos PILA
    liq.cargar_datos_informativos(
        nomina_total=257_729_000,
        seguridad_social=30_395_000,
        sena_icbf_caja=8_235_000,
    )

    # Retenciones
    liq.cargar_retenciones(
        autorretenciones=10_201_000,
        otras_retenciones=22_968_000,
    )
    liq.cargar_saldo_favor_ano_anterior(37_906_000)

    # Conciliación fiscal
    liq.set_utilidad_contable_antes_impuestos(79_150_862)
    liq.aplicar_provision_renta_no_deducible(42_849_000)
    liq.aplicar_gmf(2_655_013)

    liq.liquidar()
    return liq


# ============================================================
# TESTS — UNO POR GRUPO DE CASILLAS
# ============================================================

def _aprox(calculado: float, esperado: float) -> bool:
    return abs(round(calculado) - esperado) <= TOLERANCIA_PESOS


class TestPatrimonio:
    """Casillas 33-46 — Datos informativos y patrimonio."""

    def test_casilla_33_nomina(self, liq):
        assert _aprox(liq.formulario.declarante.total_costos_gastos_nomina, 257_729_000)

    def test_casilla_34_seguridad_social(self, liq):
        assert _aprox(liq.formulario.declarante.aportes_seguridad_social, 30_395_000)

    def test_casilla_44_patrimonio_bruto(self, liq):
        d = liq.formulario.to_dict()
        assert _aprox(d["casilla_44_total_patrimonio_bruto"], 1_783_409_000)

    def test_casilla_46_patrimonio_liquido(self, liq):
        d = liq.formulario.to_dict()
        assert _aprox(d["casilla_46_total_patrimonio_liquido"], 249_369_000)


class TestIngresos:
    """Casillas 47-61 — Ingresos."""

    def test_casilla_47_ordinarios(self, liq):
        assert _aprox(
            liq.formulario.ingresos.ingresos_brutos_actividades_ordinarias,
            1_082_118_000,
        )

    def test_casilla_58_ingresos_brutos(self, liq):
        d = liq.formulario.to_dict()
        assert _aprox(d["casilla_58_total_ingresos_brutos"], 1_098_144_000)

    def test_casilla_61_ingresos_netos(self, liq):
        d = liq.formulario.to_dict()
        assert _aprox(d["casilla_61_total_ingresos_netos"], 1_098_144_000)


class TestCostosGastos:
    """Casillas 62-67 — Costos y gastos deducibles."""

    def test_casilla_62_costos(self, liq):
        assert _aprox(liq.formulario.costos_y_deducciones.costos, 341_324_000)

    def test_casilla_64_gastos_ventas(self, liq):
        # Crítico: este es el valor con ajuste de -$27M por depreciación
        assert _aprox(
            liq.formulario.costos_y_deducciones.gastos_distribucion_ventas,
            569_933_000,
        )

    def test_casilla_67_total_deducible(self, liq):
        d = liq.formulario.to_dict()
        assert _aprox(d["casilla_67_total_costos_gastos_deducibles"], 974_817_000)


class TestRentaYImpuesto:
    """Casillas 72-99 — Renta y liquidación del impuesto."""

    def test_casilla_72_renta_liquida_ordinaria(self, liq):
        d = liq.formulario.to_dict()
        assert _aprox(d["casilla_72_renta_liquida_ordinaria"], 123_327_000)

    def test_casilla_79_renta_liquida_gravable(self, liq):
        d = liq.formulario.to_dict()
        assert _aprox(d["casilla_79_renta_liquida_gravable"], 123_327_000)

    def test_casilla_84_impuesto_35pct(self, liq):
        # 35% × 123,327,000 = 43,164,450 → redondeado 43,164,000
        assert _aprox(liq.formulario.liquidacion.impuesto_rentas_liquidas, 43_164_000)

    def test_casilla_99_total_impuesto_a_cargo(self, liq):
        d = liq.formulario.to_dict()
        assert _aprox(d["casilla_99_total_impuesto_a_cargo"], 43_164_000)


class TestRetencionesYSaldo:
    """Casillas 104-114 — Retenciones y saldo final."""

    def test_casilla_104_saldo_favor_anterior(self, liq):
        assert _aprox(liq.formulario.liquidacion.saldo_favor_ano_anterior, 37_906_000)

    def test_casilla_107_total_retenciones(self, liq):
        d = liq.formulario.to_dict()
        assert _aprox(d["casilla_107_total_retenciones"], 33_169_000)

    def test_casilla_113_saldo_a_pagar_es_cero(self, liq):
        d = liq.formulario.to_dict()
        assert d["casilla_113_total_saldo_a_pagar"] == 0

    def test_casilla_114_saldo_a_favor(self, liq):
        """⭐ Casilla final crítica: saldo a favor = $27,911,000."""
        d = liq.formulario.to_dict()
        assert _aprox(d["casilla_114_total_saldo_a_favor"], 27_911_000)


class TestConciliacionFiscal:
    """Validación de la conciliación fiscal interna."""

    def test_renta_liquida_fiscal_calculada(self, liq):
        """La conciliación debe cuadrar: 79.150.862 + 42.849.000 + 1.327.506 ≈ 123.327.368"""
        res = liq.resultado_conciliacion
        assert res is not None
        assert _aprox(res.renta_liquida_fiscal, 123_327_000)

    def test_partidas_aumentan_existen(self, liq):
        res = liq.resultado_conciliacion
        assert len(res.partidas_aumentan) >= 2  # provisión renta + GMF

    def test_total_aumentos(self, liq):
        # 42,849,000 (renta no deducible) + 1,327,506 (GMF 50% no deducible)
        res = liq.resultado_conciliacion
        assert _aprox(res.total_aumentos, 44_176_000)


# ============================================================
# Ejecución directa (modo CLI)
# ============================================================
if __name__ == "__main__":
    """Ejecuta sin pytest. Útil para smoke test rápido."""
    import io

    # Construir el liquidador
    parametros = ParametrosLiquidacion(
        ano_gravable=ANO_GRAVABLE,
        saldo_a_favor_ano_anterior=37_906_000,
        impuesto_neto_renta_ano_anterior=31_507_000,
        ano_actual_de_declaracion=3,
    )
    L = LiquidadorRenta(
        nit=NIT, razon_social=RAZON_SOCIAL,
        actividad_principal=ACTIVIDAD_PRINCIPAL, cod_seccional=COD_SECCIONAL,
        parametros=parametros,
    )
    L.cargar_patrimonio(
        efectivo=72_243_000, cxc=70_875_000, inventarios=1_256_039_000,
        ppe=281_570_000, otros_activos=102_682_000, pasivos=1_534_040_000,
    )
    L.cargar_ingresos(
        ingresos_ordinarios=1_082_118_000, ingresos_financieros=3_194_000,
        otros_ingresos=12_832_000,
    )
    L.cargar_costos_y_gastos(
        costos=341_324_000, gastos_administracion=60_298_000,
        gastos_ventas=569_933_000, gastos_financieros=3_262_000,
    )
    L.cargar_datos_informativos(
        nomina_total=257_729_000, seguridad_social=30_395_000, sena_icbf_caja=8_235_000,
    )
    L.cargar_retenciones(autorretenciones=10_201_000, otras_retenciones=22_968_000)
    L.cargar_saldo_favor_ano_anterior(37_906_000)
    L.set_utilidad_contable_antes_impuestos(79_150_862)
    L.aplicar_provision_renta_no_deducible(42_849_000)
    L.aplicar_gmf(2_655_013)
    L.liquidar()

    d = L.formulario.to_dict()

    casillas_clave = [
        ("44 Patrimonio bruto",         d["casilla_44_total_patrimonio_bruto"],       1_783_409_000),
        ("46 Patrimonio líquido",       d["casilla_46_total_patrimonio_liquido"],       249_369_000),
        ("58 Ingresos brutos",          d["casilla_58_total_ingresos_brutos"],        1_098_144_000),
        ("67 Total costos y gastos",    d["casilla_67_total_costos_gastos_deducibles"], 974_817_000),
        ("72 Renta líq. ordinaria",     d["casilla_72_renta_liquida_ordinaria"],        123_327_000),
        ("79 Renta líq. gravable",      d["casilla_79_renta_liquida_gravable"],         123_327_000),
        ("99 Total impuesto a cargo",   d["casilla_99_total_impuesto_a_cargo"],          43_164_000),
        ("107 Total retenciones",       d["casilla_107_total_retenciones"],              33_169_000),
        ("114 SALDO A FAVOR",           d["casilla_114_total_saldo_a_favor"],            27_911_000),
    ]
    print(f"\n{'='*80}")
    print(f"{RAZON_SOCIAL}  ·  AG {ANO_GRAVABLE}")
    print(f"{'='*80}")
    print(f"{'Casilla':<32}{'Plataforma':>20}{'Excel modelo':>20}{'Δ':>10}")
    print("-"*80)
    fallos = 0
    for nombre, plat, esp in casillas_clave:
        d_diff = round(plat) - esp
        ok = "✓" if abs(d_diff) <= TOLERANCIA_PESOS else "✗"
        if abs(d_diff) > TOLERANCIA_PESOS:
            fallos += 1
        print(f"  {nombre:<30}${round(plat):>18,}${esp:>18,}{d_diff:>+8,} {ok}")
    print("="*80)
    if fallos == 0:
        print(f"✅ ÉXITO — {len(casillas_clave)}/{len(casillas_clave)} casillas cuadran al peso")
        sys.exit(0)
    else:
        print(f"❌ {fallos} casilla(s) con diferencia > ${TOLERANCIA_PESOS:,}")
        sys.exit(1)
