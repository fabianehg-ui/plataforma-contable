"""
Modelo de datos para el Formulario 110 - Declaración de Renta Personas Jurídicas.

Contiene las 114 casillas del formulario, agrupadas por sección, según
el instructivo oficial DIAN (Resolución 000022 de 2023, vigente para AG 2025).
"""
from dataclasses import dataclass, field, asdict
from typing import Optional


# ============================================================
# DATOS DEL DECLARANTE (casillas 1-32)
# ============================================================
@dataclass
class DatosDeclarante:
    ano_gravable: int = 2025
    nit: str = ""
    dv: str = ""
    razon_social: str = ""
    cod_direccion_seccional: str = ""  # 12. ej. "11" Bogotá, "01" Medellín
    actividad_economica_principal: str = ""  # 24. CIIU 4 dígitos
    cod_correccion: Optional[int] = None  # 25
    no_formulario_anterior: Optional[str] = None  # 26
    fraccion_ano_siguiente: bool = False  # 29
    renuncia_rte: bool = False  # 30 régimen tributario especial
    vinculado_obras_impuestos: bool = False  # 31
    perdidas_acumuladas_sin_compensar: float = 0.0  # 32

    # Datos informativos (33-35)
    total_costos_gastos_nomina: float = 0.0  # 33
    aportes_seguridad_social: float = 0.0  # 34
    aportes_sena_icbf_caja: float = 0.0  # 35


# ============================================================
# PATRIMONIO (casillas 36-46)
# ============================================================
@dataclass
class Patrimonio:
    efectivo_y_equivalentes: float = 0.0  # 36
    inversiones_e_instrumentos: float = 0.0  # 37
    cuentas_documentos_arrend_por_cobrar: float = 0.0  # 38
    inventarios: float = 0.0  # 39
    activos_intangibles: float = 0.0  # 40
    activos_biologicos: float = 0.0  # 41
    propiedades_planta_equipo: float = 0.0  # 42
    otros_activos: float = 0.0  # 43
    pasivos: float = 0.0  # 45

    @property
    def total_patrimonio_bruto(self) -> float:  # 44 = 36+37+38+39+40+41+42+43
        return (
            self.efectivo_y_equivalentes
            + self.inversiones_e_instrumentos
            + self.cuentas_documentos_arrend_por_cobrar
            + self.inventarios
            + self.activos_intangibles
            + self.activos_biologicos
            + self.propiedades_planta_equipo
            + self.otros_activos
        )

    @property
    def total_patrimonio_liquido(self) -> float:  # 46 = 44 - 45
        return self.total_patrimonio_bruto - self.pasivos


# ============================================================
# INGRESOS (casillas 47-61)
# ============================================================
@dataclass
class Ingresos:
    ingresos_brutos_actividades_ordinarias: float = 0.0  # 47
    ingresos_financieros: float = 0.0  # 48
    dividendos_no_constitutivos: float = 0.0  # 49
    dividendos_chc: float = 0.0  # 50 prima en colocación
    dividendos_grav_tarifa_general: float = 0.0  # 51
    dividendos_pn_no_residente_2016_anteriores: float = 0.0  # 52
    dividendos_pn_no_residente_2017_siguientes: float = 0.0  # 53
    dividendos_grav_arts_245_246: float = 0.0  # 54
    dividendos_grav_general_ep: float = 0.0  # 55
    dividendos_megainversion_27pct: float = 0.0  # 56
    otros_ingresos: float = 0.0  # 57
    devoluciones_rebajas_descuentos: float = 0.0  # 59
    ingresos_no_constitutivos_renta: float = 0.0  # 60

    @property
    def total_ingresos_brutos(self) -> float:  # 58 = 47+48+...+57
        return (
            self.ingresos_brutos_actividades_ordinarias
            + self.ingresos_financieros
            + self.dividendos_no_constitutivos
            + self.dividendos_chc
            + self.dividendos_grav_tarifa_general
            + self.dividendos_pn_no_residente_2016_anteriores
            + self.dividendos_pn_no_residente_2017_siguientes
            + self.dividendos_grav_arts_245_246
            + self.dividendos_grav_general_ep
            + self.dividendos_megainversion_27pct
            + self.otros_ingresos
        )

    @property
    def total_ingresos_netos(self) -> float:  # 61 = 58 - 59 - 60
        return (
            self.total_ingresos_brutos
            - self.devoluciones_rebajas_descuentos
            - self.ingresos_no_constitutivos_renta
        )


# ============================================================
# COSTOS Y DEDUCCIONES (casillas 62-67)
# ============================================================
@dataclass
class CostosYDeducciones:
    costos: float = 0.0  # 62
    gastos_administracion: float = 0.0  # 63
    gastos_distribucion_ventas: float = 0.0  # 64
    gastos_financieros: float = 0.0  # 65
    otros_gastos_deducciones: float = 0.0  # 66

    @property
    def total_costos_gastos_deducibles(self) -> float:  # 67
        return (
            self.costos
            + self.gastos_administracion
            + self.gastos_distribucion_ventas
            + self.gastos_financieros
            + self.otros_gastos_deducciones
        )


# ============================================================
# RENTA (casillas 68-79)
# ============================================================
@dataclass
class Renta:
    inversiones_efectuadas_ano: float = 0.0  # 68 (ESAL/RTE)
    inversiones_liquidadas_ano_anterior: float = 0.0  # 69 (ESAL/RTE)
    renta_recuperacion_deducciones: float = 0.0  # 70
    renta_pasiva_ece: float = 0.0  # 71
    compensaciones: float = 0.0  # 74
    renta_presuntiva: float = 0.0  # 76 (0% AG 2025)
    renta_exenta: float = 0.0  # 77
    rentas_gravables: float = 0.0  # 78


# ============================================================
# GANANCIAS OCASIONALES (casillas 80-83)
# ============================================================
@dataclass
class GananciasOcasionales:
    ingresos_ganancias_ocasionales: float = 0.0  # 80
    costos_ganancias_ocasionales: float = 0.0  # 81
    ganancias_no_gravadas_exentas: float = 0.0  # 82

    @property
    def ganancias_ocasionales_gravables(self) -> float:  # 83
        return max(
            0,
            self.ingresos_ganancias_ocasionales
            - self.costos_ganancias_ocasionales
            - self.ganancias_no_gravadas_exentas,
        )


# ============================================================
# LIQUIDACIÓN PRIVADA (casillas 84-117)
# ============================================================
@dataclass
class LiquidacionPrivada:
    impuesto_rentas_liquidas: float = 0.0  # 84 = 79 × tarifa
    sobretasa_puntos_adicionales: float = 0.0  # 85
    impuesto_dividendos_10pct_20pct: float = 0.0  # 86
    impuesto_dividendos_240: float = 0.0  # 87
    impuesto_dividendos_27pct: float = 0.0  # 88
    impuesto_dividendos_240et: float = 0.0  # 89
    impuesto_dividendos_33pct: float = 0.0  # 90
    valor_a_adicionar_vaa: float = 0.0  # 92 (TMT)
    descuentos_tributarios: float = 0.0  # 93
    impuesto_a_adicionar_ia: float = 0.0  # 95
    impuesto_ganancias_ocasionales: float = 0.0  # 97
    descuento_imp_pagados_exterior_go: float = 0.0  # 98
    inversion_obras_impuestos_modalidad1: float = 0.0  # 100
    descuento_obras_impuestos_modalidad2: float = 0.0  # 101
    credito_fiscal_256_1: float = 0.0  # 102
    anticipo_renta_ano_anterior: float = 0.0  # 103
    saldo_favor_ano_anterior: float = 0.0  # 104
    autorretenciones: float = 0.0  # 105
    otras_retenciones: float = 0.0  # 106
    anticipo_renta_ano_siguiente: float = 0.0  # 108
    anticipo_puntos_ano_anterior: float = 0.0  # 109
    anticipo_puntos_ano_siguiente: float = 0.0  # 110
    sanciones: float = 0.0  # 112
    valor_obras_modalidad_1: float = 0.0  # 115
    valor_total_obras_modalidad_2: float = 0.0  # 116
    aporte_voluntario_244_1: float = 0.0  # 117

    @property
    def total_impuesto_rentas_liquidas(self) -> float:  # 91
        return (
            self.impuesto_rentas_liquidas
            + self.sobretasa_puntos_adicionales
            + self.impuesto_dividendos_10pct_20pct
            + self.impuesto_dividendos_240
            + self.impuesto_dividendos_27pct
            + self.impuesto_dividendos_240et
            + self.impuesto_dividendos_33pct
        )

    @property
    def impuesto_neto_renta_sin_adicional(self) -> float:  # 94 = 91 + 92 - 93
        return max(
            0,
            self.total_impuesto_rentas_liquidas
            + self.valor_a_adicionar_vaa
            - self.descuentos_tributarios,
        )

    @property
    def impuesto_neto_renta_con_adicional(self) -> float:  # 96 = 94 + 95
        return self.impuesto_neto_renta_sin_adicional + self.impuesto_a_adicionar_ia

    @property
    def total_impuesto_a_cargo(self) -> float:  # 99 = 96 + 97 - 98
        return max(
            0,
            self.impuesto_neto_renta_con_adicional
            + self.impuesto_ganancias_ocasionales
            - self.descuento_imp_pagados_exterior_go,
        )

    @property
    def total_retenciones_ano_gravable(self) -> float:  # 107
        return self.autorretenciones + self.otras_retenciones

    @property
    def saldo_a_pagar_por_impuesto(self) -> float:  # 111
        # 111 = 99 + 108 + 110 - 100 - 101 - 102 - 103 - 104 - 107 - 109
        diff = (
            self.total_impuesto_a_cargo
            + self.anticipo_renta_ano_siguiente
            + self.anticipo_puntos_ano_siguiente
            - self.inversion_obras_impuestos_modalidad1
            - self.descuento_obras_impuestos_modalidad2
            - self.credito_fiscal_256_1
            - self.anticipo_renta_ano_anterior
            - self.saldo_favor_ano_anterior
            - self.total_retenciones_ano_gravable
            - self.anticipo_puntos_ano_anterior
        )
        return max(0, diff)

    @property
    def total_saldo_a_pagar(self) -> float:  # 113
        return self.saldo_a_pagar_por_impuesto + self.sanciones

    @property
    def total_saldo_a_favor(self) -> float:  # 114
        # 114 = 100 + 101 + 102 + 103 + 104 + 107 + 109 - 99 - 108 - 110 - 112
        diff = (
            self.inversion_obras_impuestos_modalidad1
            + self.descuento_obras_impuestos_modalidad2
            + self.credito_fiscal_256_1
            + self.anticipo_renta_ano_anterior
            + self.saldo_favor_ano_anterior
            + self.total_retenciones_ano_gravable
            + self.anticipo_puntos_ano_anterior
            - self.total_impuesto_a_cargo
            - self.anticipo_renta_ano_siguiente
            - self.anticipo_puntos_ano_siguiente
            - self.sanciones
        )
        return max(0, diff)


# ============================================================
# FORMULARIO 110 COMPLETO
# ============================================================
@dataclass
class Formulario110:
    declarante: DatosDeclarante = field(default_factory=DatosDeclarante)
    patrimonio: Patrimonio = field(default_factory=Patrimonio)
    ingresos: Ingresos = field(default_factory=Ingresos)
    costos_y_deducciones: CostosYDeducciones = field(default_factory=CostosYDeducciones)
    renta: Renta = field(default_factory=Renta)
    ganancias_ocasionales: GananciasOcasionales = field(default_factory=GananciasOcasionales)
    liquidacion: LiquidacionPrivada = field(default_factory=LiquidacionPrivada)

    @property
    def renta_liquida_ordinaria_ejercicio(self) -> float:
        """Casilla 72 = 61 + 69 + 70 + 71 - 52 - 53 - 54 - 55 - 56 - 67 - 68"""
        # En su forma simplificada para PJ del régimen ordinario sin dividendos especiales:
        # = ingresos netos - costos y gastos - inversiones (RTE) + recuperaciones + ECE
        return max(
            0,
            self.ingresos.total_ingresos_netos
            + self.renta.inversiones_liquidadas_ano_anterior
            + self.renta.renta_recuperacion_deducciones
            + self.renta.renta_pasiva_ece
            - self.ingresos.dividendos_pn_no_residente_2016_anteriores
            - self.ingresos.dividendos_pn_no_residente_2017_siguientes
            - self.ingresos.dividendos_grav_arts_245_246
            - self.ingresos.dividendos_grav_general_ep
            - self.ingresos.dividendos_megainversion_27pct
            - self.costos_y_deducciones.total_costos_gastos_deducibles
            - self.renta.inversiones_efectuadas_ano,
        )

    @property
    def perdida_liquida_ejercicio(self) -> float:
        """Casilla 73 = (-1) × casilla 72 si negativa"""
        renta = (
            self.ingresos.total_ingresos_netos
            + self.renta.inversiones_liquidadas_ano_anterior
            + self.renta.renta_recuperacion_deducciones
            + self.renta.renta_pasiva_ece
            - self.ingresos.dividendos_pn_no_residente_2016_anteriores
            - self.ingresos.dividendos_pn_no_residente_2017_siguientes
            - self.ingresos.dividendos_grav_arts_245_246
            - self.ingresos.dividendos_grav_general_ep
            - self.ingresos.dividendos_megainversion_27pct
            - self.costos_y_deducciones.total_costos_gastos_deducibles
            - self.renta.inversiones_efectuadas_ano
        )
        return max(0, -renta)

    @property
    def renta_liquida(self) -> float:
        """Casilla 75 = 72 - 74"""
        return max(0, self.renta_liquida_ordinaria_ejercicio - self.renta.compensaciones)

    @property
    def renta_liquida_gravable(self) -> float:
        """Casilla 79 = max(75, 76) - 77 + 78"""
        base = max(self.renta_liquida, self.renta.renta_presuntiva)
        return max(0, base - self.renta.renta_exenta + self.renta.rentas_gravables)

    def to_dict(self) -> dict:
        """Exporta a diccionario plano con todas las casillas."""
        return {
            **asdict(self.declarante),
            "patrimonio": asdict(self.patrimonio),
            "ingresos": asdict(self.ingresos),
            "costos_y_deducciones": asdict(self.costos_y_deducciones),
            "renta": asdict(self.renta),
            "ganancias_ocasionales": asdict(self.ganancias_ocasionales),
            "liquidacion": asdict(self.liquidacion),
            # Calculados
            "casilla_44_total_patrimonio_bruto": self.patrimonio.total_patrimonio_bruto,
            "casilla_46_total_patrimonio_liquido": self.patrimonio.total_patrimonio_liquido,
            "casilla_58_total_ingresos_brutos": self.ingresos.total_ingresos_brutos,
            "casilla_61_total_ingresos_netos": self.ingresos.total_ingresos_netos,
            "casilla_67_total_costos_gastos_deducibles": self.costos_y_deducciones.total_costos_gastos_deducibles,
            "casilla_72_renta_liquida_ordinaria": self.renta_liquida_ordinaria_ejercicio,
            "casilla_73_perdida_liquida": self.perdida_liquida_ejercicio,
            "casilla_75_renta_liquida": self.renta_liquida,
            "casilla_79_renta_liquida_gravable": self.renta_liquida_gravable,
            "casilla_83_ganancias_ocasionales_gravables": self.ganancias_ocasionales.ganancias_ocasionales_gravables,
            "casilla_91_total_impuesto_rentas_liquidas": self.liquidacion.total_impuesto_rentas_liquidas,
            "casilla_94_impuesto_neto_sin_adicional": self.liquidacion.impuesto_neto_renta_sin_adicional,
            "casilla_96_impuesto_neto_con_adicional": self.liquidacion.impuesto_neto_renta_con_adicional,
            "casilla_99_total_impuesto_a_cargo": self.liquidacion.total_impuesto_a_cargo,
            "casilla_107_total_retenciones": self.liquidacion.total_retenciones_ano_gravable,
            "casilla_111_saldo_pagar_impuesto": self.liquidacion.saldo_a_pagar_por_impuesto,
            "casilla_113_total_saldo_a_pagar": self.liquidacion.total_saldo_a_pagar,
            "casilla_114_total_saldo_a_favor": self.liquidacion.total_saldo_a_favor,
        }
