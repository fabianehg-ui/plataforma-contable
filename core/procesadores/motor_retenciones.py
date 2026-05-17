"""
core/procesadores/motor_retenciones.py

Calcula retención en la fuente y reteIVA según:
  - Periodo de vigencia normativa (Decreto 572/2025 vs anterior)
  - Concepto de retención (compras, servicios, honorarios, arrendamiento, transporte, etc.)
  - Régimen del proveedor (O-13 Gran Contrib, O-15 Autoret, O-23 Agente IVA, O-47 RST, R-99-PN)
  - Tarifa declarante / no declarante
  - Cuantía mínima (UVT × valor UVT del año)

Diseñado para ser configurable: toda la tabla vive en tabla_retenciones.json.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional


@dataclass
class ResultadoRetencion:
    """Resultado del cálculo para una compra."""
    aplica_retefuente: bool
    valor_retefuente: float
    concepto_retencion: str            # ej. "compras", "servicios"
    tarifa_retefuente: float           # ej. 0.025
    base_minima_aplicada: float        # cuantía mínima en pesos para retefuente
    razon_no_retefuente: Optional[str] = None  # si no se retuvo, explica por qué

    aplica_reteiva: bool = False
    valor_reteiva: float = 0.0
    tarifa_reteiva: float = 0.0

    # Cuenta PUC sugerida para la línea contable de retención
    cuenta_retefuente_puc: str = ""
    cuenta_reteiva_puc: str = ""

    # Metadata
    regimen_proveedor: str = ""
    nombre_regimen: str = ""
    periodo_normativo: str = ""


class MotorRetenciones:
    """Motor que aplica las retenciones según la tabla configurable."""

    def __init__(self, ruta_tabla: str, ruta_mapeo_concepto: str):
        with open(ruta_tabla, encoding="utf-8") as f:
            self.tabla = json.load(f)
        with open(ruta_mapeo_concepto, encoding="utf-8") as f:
            self.mapeo_concepto = json.load(f)["mapeo"]

        self.cuentas_puc = self.tabla.get("cuentas_puc", {})

    # ─── API pública ─────────────────────────────────────────

    def concepto_para_cuenta(self, cuenta_gasto: str) -> str:
        """Devuelve el concepto de retención asociado a una cuenta PUC."""
        info = self.mapeo_concepto.get(cuenta_gasto)
        if info:
            return info.get("concepto_retencion", "compras")
        # Si la cuenta no está en el mapeo, asumir "compras" (es lo más común)
        return "compras"

    def calcular(
        self,
        fecha_factura: date,
        base_gravable: float,         # base SIN IVA (la base sobre la que se retiene renta)
        iva: float,                   # IVA pagado (para reteIVA)
        cuenta_gasto: str,            # cuenta PUC del gasto
        regimen_proveedor: str = "R-99-PN",
        declarante: bool = True,      # por defecto asume declarante (tarifa más baja)
        # Override del concepto (si la cuenta no es suficiente)
        concepto_override: Optional[str] = None,
    ) -> ResultadoRetencion:
        """
        Calcula las retenciones de renta e IVA para una compra.

        Args:
            fecha_factura: fecha del documento (determina el periodo normativo).
            base_gravable: base sin IVA (sobre la que se aplica retefuente).
            iva: IVA pagado (sobre el que se calcula reteIVA).
            cuenta_gasto: cuenta PUC del gasto (decide el concepto).
            regimen_proveedor: TaxLevelCode del XML (R-99-PN, O-13, O-15, O-23, O-47).
            declarante: si el proveedor es declarante de renta (afecta tarifa).
            concepto_override: si se quiere forzar un concepto específico.

        Returns:
            ResultadoRetencion con valores y metadata.
        """
        # 1. Determinar concepto
        concepto = concepto_override or self.concepto_para_cuenta(cuenta_gasto)

        # 2. Determinar periodo normativo aplicable
        periodo = self._periodo_aplicable(fecha_factura)
        periodo_id = periodo["id"]

        # 3. Reglas por régimen
        reglas_regimen = self.tabla["reglas_por_regimen"].get(
            regimen_proveedor,
            self.tabla["reglas_por_regimen"]["R-99-PN"],  # fallback
        )
        nombre_regimen = reglas_regimen.get("nombre", regimen_proveedor)
        aplicar_retefuente = reglas_regimen["aplicar_retefuente"]
        aplicar_reteiva = reglas_regimen["aplicar_reteiva"]

        # 4. Calcular retefuente
        valor_retefuente = 0.0
        tarifa_retefuente = 0.0
        base_minima = 0.0
        razon_no = None
        cuenta_retef = ""

        info_concepto = periodo["retefuente"].get(concepto)
        if not info_concepto:
            razon_no = f"Concepto '{concepto}' no encontrado en tabla"
            aplicar_retefuente = False
        else:
            tarifa_retefuente = (
                info_concepto["tarifa_declarante"] if declarante
                else info_concepto["tarifa_no_declarante"]
            )

            # Cuantía mínima en pesos
            anio = fecha_factura.year
            uvt = self.tabla["uvt"].get(str(anio), self.tabla["uvt"]["2026"])
            base_minima = info_concepto["base_uvt"] * uvt

            if not aplicar_retefuente:
                razon_no = f"Régimen {regimen_proveedor} ({nombre_regimen}) no sujeto a retefuente"
            elif tarifa_retefuente == 0:
                razon_no = f"Concepto '{concepto}' con tarifa 0 ({info_concepto.get('obs', '')})"
                aplicar_retefuente = False
            elif base_gravable < base_minima:
                razon_no = f"Base ${base_gravable:,.0f} < cuantía mínima ${base_minima:,.0f} ({info_concepto['base_uvt']} UVT)"
                aplicar_retefuente = False
            else:
                valor_retefuente = round(base_gravable * tarifa_retefuente, 0)
                cuenta_retef = self._cuenta_puc_retefuente(concepto)

        # 5. Calcular reteIVA (solo si proveedor es RST y hay IVA)
        valor_reteiva = 0.0
        tarifa_reteiva = 0.0
        cuenta_reteiva = ""
        if aplicar_reteiva and iva > 0:
            tarifa_reteiva = periodo["reteiva"]["tarifa_general"]
            valor_reteiva = round(iva * tarifa_reteiva, 0)
            cuenta_reteiva = self.cuentas_puc.get("reteiva", "23677005")

        return ResultadoRetencion(
            aplica_retefuente=aplicar_retefuente and valor_retefuente > 0,
            valor_retefuente=valor_retefuente,
            concepto_retencion=concepto,
            tarifa_retefuente=tarifa_retefuente,
            base_minima_aplicada=base_minima,
            razon_no_retefuente=razon_no,
            aplica_reteiva=aplicar_reteiva and valor_reteiva > 0,
            valor_reteiva=valor_reteiva,
            tarifa_reteiva=tarifa_reteiva,
            cuenta_retefuente_puc=cuenta_retef,
            cuenta_reteiva_puc=cuenta_reteiva,
            regimen_proveedor=regimen_proveedor,
            nombre_regimen=nombre_regimen,
            periodo_normativo=periodo_id,
        )

    # ─── Helpers privados ────────────────────────────────────

    def _periodo_aplicable(self, fecha: date) -> dict:
        """Devuelve el periodo normativo que aplica para una fecha."""
        for periodo in self.tabla["periodos"]:
            desde = datetime.strptime(periodo["vigencia_desde"], "%Y-%m-%d").date()
            hasta = datetime.strptime(periodo["vigencia_hasta"], "%Y-%m-%d").date()
            if desde <= fecha <= hasta:
                return periodo
        # Fallback: el último periodo (más reciente)
        return self.tabla["periodos"][-1]

    def _cuenta_puc_retefuente(self, concepto: str) -> str:
        """Cuenta PUC sugerida según concepto."""
        mapeo = {
            "compras":                  "retefuente_compras",
            "servicios":                "retefuente_servicios",
            "honorarios":               "retefuente_honorarios",
            "arrendamiento_inmueble":   "retefuente_arrendamiento",
            "arrendamiento_mueble":     "retefuente_arrendamiento",
            "transporte_carga":         "retefuente_transporte",
            "servicios_publicos":       "retefuente_otros",
        }
        key = mapeo.get(concepto, "retefuente_otros")
        return self.cuentas_puc.get(key, "23659501")
