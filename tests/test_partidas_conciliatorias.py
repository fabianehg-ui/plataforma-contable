"""
Tests unitarios del MotorConciliacion.

Verifica:
  - El catálogo CATALOGO_PARTIDAS_PERMANENTES está bien definido
  - agregar_partida/agregar_partida_estandar funcionan
  - aplicar_gmf agrega solo el 50% como no deducible
  - aplicar_impuesto_renta_no_deducible agrega la provisión
  - ejecutar() agrupa correctamente aumentos/disminuciones
  - El cálculo de renta_liquida_fiscal cuadra
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from core.procesadores.renta import (
    PartidaConciliatoria,
    CATALOGO_PARTIDAS_PERMANENTES,
    MotorConciliacion,
    ResultadoConciliacion,
)


# ============================================================
# CATÁLOGO DE PARTIDAS
# ============================================================
class TestCatalogoPartidas:

    def test_catalogo_no_vacio(self):
        assert len(CATALOGO_PARTIDAS_PERMANENTES) > 0

    def test_catalogo_contiene_imp_renta_no_deduc(self):
        assert "IMP_RENTA_NO_DEDUC" in CATALOGO_PARTIDAS_PERMANENTES

    def test_catalogo_contiene_gmf_no_deduc(self):
        assert "GMF_NO_DEDUC" in CATALOGO_PARTIDAS_PERMANENTES

    def test_cada_partida_tiene_nombre_y_direccion(self):
        for codigo, partida in CATALOGO_PARTIDAS_PERMANENTES.items():
            assert "nombre" in partida, f"{codigo} no tiene 'nombre'"
            assert "direccion" in partida, f"{codigo} no tiene 'direccion'"
            assert partida["direccion"] in ("aumenta", "disminuye")


# ============================================================
# MOTOR — agregar_partida
# ============================================================
class TestAgregarPartida:

    def test_agregar_partida_simple(self):
        motor = MotorConciliacion()
        motor.agregar_partida(PartidaConciliatoria(
            codigo="TEST", nombre="Prueba", valor=1000,
            direccion="aumenta", base_legal="Test"
        ))
        assert len(motor.partidas) == 1

    def test_no_agrega_partidas_en_cero(self):
        """Las partidas con valor <=0 se ignoran silenciosamente."""
        motor = MotorConciliacion()
        motor.agregar_partida(PartidaConciliatoria(
            codigo="VACIA", nombre="Vacía", valor=0, direccion="aumenta"
        ))
        assert len(motor.partidas) == 0

    def test_no_agrega_partidas_negativas(self):
        motor = MotorConciliacion()
        motor.agregar_partida(PartidaConciliatoria(
            codigo="NEG", nombre="Negativa", valor=-100, direccion="aumenta"
        ))
        assert len(motor.partidas) == 0

    def test_agregar_partida_estandar_con_codigo_invalido(self):
        motor = MotorConciliacion()
        with pytest.raises(ValueError, match="no está en el catálogo"):
            motor.agregar_partida_estandar("CODIGO_INEXISTENTE", 1000)

    def test_agregar_partida_estandar_correcto(self):
        motor = MotorConciliacion()
        motor.agregar_partida_estandar("IMP_RENTA_NO_DEDUC", 42_849_000)
        assert len(motor.partidas) == 1
        assert motor.partidas[0].codigo == "IMP_RENTA_NO_DEDUC"
        assert motor.partidas[0].valor == 42_849_000
        assert motor.partidas[0].direccion == "aumenta"


# ============================================================
# GMF (50% no deducible)
# ============================================================
class TestGMF:

    def test_aplicar_gmf_50pct(self):
        """El 50% del GMF certificado no es deducible (Art. 115 ET)."""
        motor = MotorConciliacion()
        deducible, no_deducible = motor.aplicar_gmf(2_655_013)

        assert deducible == pytest.approx(1_327_506.5)
        assert no_deducible == pytest.approx(1_327_506.5)
        assert len(motor.partidas) == 1
        assert motor.partidas[0].codigo == "GMF_NO_DEDUC"

    def test_gmf_cero_no_agrega_partida(self):
        motor = MotorConciliacion()
        deducible, no_deducible = motor.aplicar_gmf(0)
        assert deducible == 0
        assert no_deducible == 0
        assert len(motor.partidas) == 0


# ============================================================
# Provisión de renta no deducible
# ============================================================
class TestProvisionRenta:

    def test_aplicar_provision(self):
        motor = MotorConciliacion()
        motor.aplicar_impuesto_renta_no_deducible(42_849_000)
        assert len(motor.partidas) == 1
        assert motor.partidas[0].codigo == "IMP_RENTA_NO_DEDUC"
        assert motor.partidas[0].valor == 42_849_000

    def test_provision_cero_no_agrega(self):
        motor = MotorConciliacion()
        motor.aplicar_impuesto_renta_no_deducible(0)
        assert len(motor.partidas) == 0


# ============================================================
# ejecutar() — agrupa y calcula
# ============================================================
class TestEjecutar:

    def test_resultado_agrupa_por_direccion(self):
        motor = MotorConciliacion()
        motor.agregar_partida(PartidaConciliatoria(
            codigo="A", nombre="Aumenta", valor=100, direccion="aumenta"))
        motor.agregar_partida(PartidaConciliatoria(
            codigo="B", nombre="Disminuye", valor=50, direccion="disminuye"))

        res = motor.ejecutar(utilidad_contable_antes_impuestos=1000)

        assert isinstance(res, ResultadoConciliacion)
        assert len(res.partidas_aumentan) == 1
        assert len(res.partidas_disminuyen) == 1
        assert res.total_aumentos == 100
        assert res.total_disminuciones == 50

    def test_renta_liquida_fiscal_quinto_sentido(self):
        """Caso real: 79.150.862 + 42.849.000 + 1.327.506 = 123.327.368"""
        motor = MotorConciliacion()
        motor.aplicar_impuesto_renta_no_deducible(42_849_000)
        motor.aplicar_gmf(2_655_013)

        res = motor.ejecutar(utilidad_contable_antes_impuestos=79_150_862)

        # Total aumentos = 42.849.000 + 1.327.506,5 = 44.176.506,5
        assert res.total_aumentos == pytest.approx(44_176_506.5)
        # Renta líquida fiscal = 79.150.862 + 44.176.506,5 = 123.327.368,5
        assert res.renta_liquida_fiscal == pytest.approx(123_327_368.5)
