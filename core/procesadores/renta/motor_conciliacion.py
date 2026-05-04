"""
Motor de Conciliación Fiscal — Utilidad Contable → Renta Líquida.

Convierte la utilidad contable antes de impuestos en renta líquida fiscal
aplicando partidas conciliatorias permanentes y temporales.

Diseñado a partir del Anexo 17 del liquidador Excel oficial AG 2025.
"""
from dataclasses import dataclass, field
from typing import Optional


# ============================================================
# PARTIDAS CONCILIATORIAS
# ============================================================
@dataclass
class PartidaConciliatoria:
    """Una partida conciliatoria entre contabilidad y fiscal."""

    codigo: str  # ej. 'IMP_RENTA_NO_DEDUC', 'GMF_NO_DEDUC'
    nombre: str
    valor: float
    base_legal: str = ""  # ej. 'Art. 115 E.T.'
    tipo: str = "permanente"  # 'permanente' o 'temporal'
    direccion: str = "aumenta"  # 'aumenta' o 'disminuye' renta líquida
    notas: str = ""


# ============================================================
# CATÁLOGO ESTÁNDAR DE PARTIDAS PERMANENTES
# ============================================================
"""
Las partidas permanentes son las más comunes en una PJ típica:
"""
CATALOGO_PARTIDAS_PERMANENTES = {
    # AUMENTAN renta líquida (suman a la utilidad contable)
    "IMP_RENTA_NO_DEDUC": {
        "nombre": "Impuesto de renta y complementarios (no deducible)",
        "base_legal": "Art. 115 E.T. — el impuesto de renta NO es deducible",
        "direccion": "aumenta",
    },
    "GMF_NO_DEDUC": {
        "nombre": "GMF no deducible (50%)",
        "base_legal": "Art. 115 E.T. — solo 50% del 4×1000 es deducible",
        "direccion": "aumenta",
    },
    "MULTAS_SANCIONES": {
        "nombre": "Multas, sanciones e intereses moratorios",
        "base_legal": "Art. 115 E.T.",
        "direccion": "aumenta",
    },
    "GASTOS_SIN_SOPORTE": {
        "nombre": "Gastos sin soporte / sin factura electrónica",
        "base_legal": "Art. 771-2 E.T.",
        "direccion": "aumenta",
    },
    "GASTOS_SIN_RUT": {
        "nombre": "Pagos a personas no inscritas como responsables IVA",
        "base_legal": "Art. 177-2 E.T.",
        "direccion": "aumenta",
    },
    "GASTOS_NO_CAUSALIDAD": {
        "nombre": "Gastos sin relación de causalidad con la renta",
        "base_legal": "Art. 107 E.T.",
        "direccion": "aumenta",
    },
    "DEDUCCIONES_VEHICULOS": {
        "nombre": "Impuestos no deducibles (vehículos, predial no productivo)",
        "base_legal": "Art. 115 E.T.",
        "direccion": "aumenta",
    },
    "GASTOS_VIGENCIAS_ANTERIORES": {
        "nombre": "Gastos de vigencias anteriores",
        "base_legal": "Art. 105 E.T.",
        "direccion": "aumenta",
    },
    "DONACIONES_NO_DEDUC": {
        "nombre": "Donaciones no deducibles",
        "direccion": "aumenta",
    },
    # DISMINUYEN renta líquida (restan)
    "INCRNGO": {
        "nombre": "Ingresos no constitutivos de renta ni ganancia ocasional",
        "base_legal": "Arts. 36-1 a 56 E.T.",
        "direccion": "disminuye",
    },
    "RENTAS_EXENTAS": {
        "nombre": "Rentas exentas",
        "base_legal": "Art. 235-2 E.T. y siguientes",
        "direccion": "disminuye",
    },
    "DIVIDENDOS_NO_GRAVADOS": {
        "nombre": "Dividendos no gravados",
        "base_legal": "Art. 49 E.T.",
        "direccion": "disminuye",
    },
}


# ============================================================
# RESULTADO DE LA CONCILIACIÓN
# ============================================================
@dataclass
class ResultadoConciliacion:
    """Resultado de aplicar la conciliación contable-fiscal."""

    utilidad_contable_antes_impuestos: float
    partidas_aumentan: list[PartidaConciliatoria] = field(default_factory=list)
    partidas_disminuyen: list[PartidaConciliatoria] = field(default_factory=list)

    @property
    def total_aumentos(self) -> float:
        return sum(p.valor for p in self.partidas_aumentan)

    @property
    def total_disminuciones(self) -> float:
        return sum(p.valor for p in self.partidas_disminuyen)

    @property
    def renta_liquida_fiscal(self) -> float:
        """Utilidad contable + aumentos - disminuciones."""
        return (
            self.utilidad_contable_antes_impuestos
            + self.total_aumentos
            - self.total_disminuciones
        )

    def resumen(self) -> str:
        """Genera un resumen legible de la conciliación."""
        lineas = [
            "="*80,
            "CONCILIACIÓN FISCAL — Contable vs Fiscal",
            "="*80,
            f"Utilidad contable antes de impuestos:     ${self.utilidad_contable_antes_impuestos:>18,.0f}",
            "",
            "(+) DIFERENCIAS PERMANENTES QUE AUMENTAN RENTA",
        ]
        for p in self.partidas_aumentan:
            lineas.append(f"    {p.nombre[:55]:<55} ${p.valor:>15,.0f}")
        lineas.append(f"    {'TOTAL AUMENTOS':<55} ${self.total_aumentos:>15,.0f}")
        lineas.append("")
        lineas.append("(-) DIFERENCIAS PERMANENTES QUE DISMINUYEN RENTA")
        for p in self.partidas_disminuyen:
            lineas.append(f"    {p.nombre[:55]:<55} ${p.valor:>15,.0f}")
        lineas.append(f"    {'TOTAL DISMINUCIONES':<55} ${self.total_disminuciones:>15,.0f}")
        lineas.append("")
        lineas.append("="*80)
        lineas.append(f"RENTA LÍQUIDA ORDINARIA DEL EJERCICIO:    ${self.renta_liquida_fiscal:>18,.0f}")
        lineas.append("="*80)
        return "\n".join(lineas)


# ============================================================
# MOTOR PRINCIPAL
# ============================================================
class MotorConciliacion:
    """Motor que ejecuta la conciliación contable-fiscal."""

    def __init__(self):
        self.partidas: list[PartidaConciliatoria] = []

    def agregar_partida(self, partida: PartidaConciliatoria):
        """Agrega una partida conciliatoria."""
        if partida.valor <= 0:
            return  # ignorar partidas en cero o negativas
        self.partidas.append(partida)

    def agregar_partida_estandar(self, codigo: str, valor: float, notas: str = ""):
        """Agrega una partida del catálogo estándar."""
        if codigo not in CATALOGO_PARTIDAS_PERMANENTES:
            raise ValueError(f"Código '{codigo}' no está en el catálogo")
        cfg = CATALOGO_PARTIDAS_PERMANENTES[codigo]
        self.agregar_partida(
            PartidaConciliatoria(
                codigo=codigo,
                nombre=cfg["nombre"],
                valor=valor,
                base_legal=cfg.get("base_legal", ""),
                direccion=cfg["direccion"],
                tipo="permanente",
                notas=notas,
            )
        )

    def aplicar_gmf(self, gmf_certificado_total: float) -> tuple[float, float]:
        """
        Aplica las reglas de GMF.

        Returns:
            (gmf_deducible, gmf_no_deducible)
        """
        deducible = gmf_certificado_total * 0.50
        no_deducible = gmf_certificado_total - deducible
        if no_deducible > 0:
            self.agregar_partida_estandar(
                "GMF_NO_DEDUC",
                no_deducible,
                notas=f"GMF certificado: ${gmf_certificado_total:,.0f}, 50% no deducible",
            )
        return deducible, no_deducible

    def aplicar_impuesto_renta_no_deducible(self, provision_renta: float):
        """Suma la provisión del impuesto de renta a la utilidad."""
        if provision_renta > 0:
            self.agregar_partida_estandar(
                "IMP_RENTA_NO_DEDUC",
                provision_renta,
                notas="Provisión de renta de la cuenta 5405",
            )

    def ejecutar(self, utilidad_contable_antes_impuestos: float) -> ResultadoConciliacion:
        """Ejecuta la conciliación y devuelve el resultado."""
        aumentan = [p for p in self.partidas if p.direccion == "aumenta"]
        disminuyen = [p for p in self.partidas if p.direccion == "disminuye"]

        return ResultadoConciliacion(
            utilidad_contable_antes_impuestos=utilidad_contable_antes_impuestos,
            partidas_aumentan=aumentan,
            partidas_disminuyen=disminuyen,
        )


# ============================================================
# CONCILIACIÓN PATRIMONIAL (art. 236-239 E.T.)
# ============================================================
@dataclass
class ConciliacionPatrimonial:
    """
    Conciliación patrimonial — verifica que el aumento patrimonial
    sea consistente con las rentas declaradas.
    """

    patrimonio_liquido_actual: float  # 31-DIC año gravable
    patrimonio_liquido_anterior: float  # 31-DIC año anterior
    valorizaciones: float = 0.0
    desvalorizaciones: float = 0.0
    renta_liquida_fiscal: float = 0.0
    rentas_exentas: float = 0.0
    incrngo: float = 0.0
    ganancia_ocasional_gravable: float = 0.0
    impuestos_pagados_vigencia_anterior: float = 0.0
    retenciones_practicadas: float = 0.0
    primera_declaracion: bool = False

    @property
    def diferencia_patrimonial(self) -> float:
        """Aumento o disminución del patrimonio (ajustado)."""
        return (
            self.patrimonio_liquido_actual
            + self.desvalorizaciones
            - self.valorizaciones
            - self.patrimonio_liquido_anterior
        )

    @property
    def rentas_ajustadas(self) -> float:
        """Total de rentas que justifican el aumento patrimonial."""
        return (
            self.renta_liquida_fiscal
            + self.rentas_exentas
            + self.incrngo
            + self.ganancia_ocasional_gravable
            - self.impuestos_pagados_vigencia_anterior
            - self.retenciones_practicadas
        )

    @property
    def renta_por_comparacion_patrimonial(self) -> float:
        """
        Si la diferencia patrimonial supera las rentas ajustadas,
        se genera renta por comparación patrimonial.
        """
        if self.primera_declaracion:
            return 0  # No aplica en primera declaración
        diferencia = self.diferencia_patrimonial - self.rentas_ajustadas
        return max(0, diferencia)

    def resumen(self) -> str:
        return f"""
{'='*80}
CONCILIACIÓN PATRIMONIAL (Art. 236-239 E.T.)
{'='*80}
Patrimonio líquido año actual:        ${self.patrimonio_liquido_actual:>18,.0f}
(-) Patrimonio líquido año anterior:  ${self.patrimonio_liquido_anterior:>18,.0f}
(+) Desvalorizaciones:                ${self.desvalorizaciones:>18,.0f}
(-) Valorizaciones:                   ${self.valorizaciones:>18,.0f}
{'─'*80}
DIFERENCIA PATRIMONIAL:               ${self.diferencia_patrimonial:>18,.0f}

Renta líquida fiscal:                 ${self.renta_liquida_fiscal:>18,.0f}
(+) Rentas exentas:                   ${self.rentas_exentas:>18,.0f}
(+) INCRNGO:                          ${self.incrngo:>18,.0f}
(+) Ganancia ocasional gravable:      ${self.ganancia_ocasional_gravable:>18,.0f}
(-) Impuestos vigencia anterior:      ${self.impuestos_pagados_vigencia_anterior:>18,.0f}
(-) Retenciones practicadas:          ${self.retenciones_practicadas:>18,.0f}
{'─'*80}
RENTAS AJUSTADAS:                     ${self.rentas_ajustadas:>18,.0f}

{'='*80}
RENTA POR COMPARACIÓN PATRIMONIAL:    ${self.renta_por_comparacion_patrimonial:>18,.0f}
{'='*80}
{
    '✓ NO existe renta por comparación patrimonial'
    if self.renta_por_comparacion_patrimonial == 0
    else '⚠ EXISTE renta por comparación patrimonial — revisar'
}
"""
