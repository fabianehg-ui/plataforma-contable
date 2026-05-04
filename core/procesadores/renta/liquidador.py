"""
Liquidador del Formulario 110 - Declaración de Renta Personas Jurídicas AG 2025.

Orquesta el cálculo completo:
  Balance contable → Conciliación fiscal → Form 110 → Liquidación de impuesto

Diseñado para ser MULTI-EMPRESA: cada empresa configura su propio mapeo
PUC → casilla Form 110 y sus propias partidas conciliatorias.
"""
from dataclasses import dataclass, field
from typing import Optional

from .modelo_form110 import (
    Formulario110,
    DatosDeclarante,
    Patrimonio,
    Ingresos,
    CostosYDeducciones,
    Renta,
    GananciasOcasionales,
    LiquidacionPrivada,
)
from .motor_conciliacion import (
    MotorConciliacion,
    ResultadoConciliacion,
    ConciliacionPatrimonial,
    PartidaConciliatoria,
)
from .parametros_fiscales import (
    UVT,
    TarifasRenta,
    LimitesDeducciones,
    Sanciones,
    redondear_dian,
)


# ============================================================
# MAPEO PUC → CASILLA FORM 110
# ============================================================
"""
Reglas estándar de mapeo de cuentas del PUC colombiano a las casillas del 110.
Estas reglas son el DEFAULT — cada empresa puede sobrescribirlas según necesite.
"""

MAPEO_PUC_PATRIMONIO = {
    # PATRIMONIO (Activos cuenta 1)
    # Casilla 36: Efectivo y equivalentes
    "11": ("efectivo_y_equivalentes",),  # toda cuenta 11
    # Casilla 37: Inversiones e instrumentos financieros derivados
    "12": ("inversiones_e_instrumentos",),
    # Casilla 38: Cuentas por cobrar y arrendamientos financieros
    "13": ("cuentas_documentos_arrend_por_cobrar",),
    # Casilla 39: Inventarios
    "14": ("inventarios",),
    # Casilla 42: Propiedades, planta y equipo
    "15": ("propiedades_planta_equipo",),
    # Casilla 40: Activos intangibles
    "16": ("activos_intangibles",),
    # Casilla 17 (diferidos), 18 (otros activos), 19 (impuestos): casilla 43 Otros
    "17": ("otros_activos",),
    "18": ("otros_activos",),
    "19": ("otros_activos",),
    # PASIVOS (cuenta 2) → casilla 45
    "2": ("pasivos",),
}


MAPEO_PUC_INGRESOS = {
    # Casilla 47: Ingresos brutos actividades ordinarias
    "41": ("ingresos_brutos_actividades_ordinarias",),
    # Casilla 48: Ingresos financieros
    "421005": ("ingresos_financieros",),  # 4210 financieros completo
    "4210": ("ingresos_financieros",),
    "43": ("ingresos_financieros",),  # Si hay grupo 43 financieros
    # Casilla 57: Otros ingresos (todo lo demás de cuenta 42)
    "42": ("otros_ingresos",),
    # Casilla 59: Devoluciones (cuentas 4175, 4180, 4275)
    "4175": ("devoluciones_rebajas_descuentos",),
    "4180": ("devoluciones_rebajas_descuentos",),
    "4275": ("devoluciones_rebajas_descuentos",),
}


MAPEO_PUC_COSTOS_GASTOS = {
    # Casilla 62: Costos
    "6": ("costos",),  # cuenta 6 completa
    "7": ("costos",),  # cuenta 7 (costos de producción)
    # Casilla 63: Gastos de administración
    "51": ("gastos_administracion",),
    # Casilla 64: Gastos de distribución y ventas
    "52": ("gastos_distribucion_ventas",),
    # Casilla 65: Gastos financieros
    "5305": ("gastos_financieros",),  # 53-05 = financieros
    "530505": ("gastos_financieros",),
    "530525": ("gastos_financieros",),  # 530525 GMF
    "530555": ("gastos_financieros",),
    # Casilla 66: Otros gastos y deducciones
    "53": ("otros_gastos_deducciones",),  # resto de no operacionales
    # Cuenta 54 Impuesto de renta: NO va al formulario, se concilia
}


# ============================================================
# LIQUIDADOR PRINCIPAL
# ============================================================
@dataclass
class ParametrosLiquidacion:
    """Parámetros de configuración para una liquidación específica."""

    ano_gravable: int = 2025
    es_gran_contribuyente: bool = False
    aplicar_tarifa_general: bool = True
    tarifa_personalizada: Optional[float] = None  # ej. 0.15 para hoteles
    aplicar_tmt: bool = True

    # Datos del año anterior
    patrimonio_liquido_ano_anterior: float = 0.0
    saldo_a_favor_ano_anterior: float = 0.0
    impuesto_neto_renta_ano_anterior: float = 0.0  # para calcular anticipo
    ano_actual_de_declaracion: int = 1  # 1=primer, 2=segundo, 3+=tercero o más

    # Anticipo del año anterior pagado
    anticipo_pagado_ano_anterior: float = 0.0


class LiquidadorRenta:
    """
    Liquidador completo del Formulario 110.

    Flujo de uso:
        1. Cargar saldos del balance auxiliar
        2. Configurar partidas conciliatorias
        3. Configurar retenciones, GMF, ICA, etc.
        4. Llamar liquidar() → devuelve Formulario110 completo
    """

    def __init__(
        self,
        nit: str,
        razon_social: str,
        actividad_principal: str = "",
        cod_seccional: str = "",
        parametros: Optional[ParametrosLiquidacion] = None,
    ):
        # Atributos públicos para uso externo (UI, exportadores, persistencia)
        self.nit = nit
        self.razon_social = razon_social
        self.actividad_principal = actividad_principal

        self.f110 = Formulario110()
        self.f110.declarante.nit = nit
        self.f110.declarante.razon_social = razon_social
        self.f110.declarante.actividad_economica_principal = actividad_principal
        self.f110.declarante.cod_direccion_seccional = cod_seccional
        self.parametros = parametros or ParametrosLiquidacion()
        self.f110.declarante.ano_gravable = self.parametros.ano_gravable
        self.ano_gravable = self.parametros.ano_gravable

        self.motor_conciliacion = MotorConciliacion()
        self.utilidad_contable_antes_impuestos: float = 0.0
        self.resultado_conciliacion: Optional[ResultadoConciliacion] = None
        self.conciliacion_patrimonial: Optional[ConciliacionPatrimonial] = None

    @property
    def formulario(self) -> "Formulario110":
        """Alias público de f110 para uso por exportadores y persistencia."""
        return self.f110

    # --- Carga de datos del balance ---

    def cargar_patrimonio(
        self,
        efectivo: float = 0,
        inversiones: float = 0,
        cxc: float = 0,
        inventarios: float = 0,
        intangibles: float = 0,
        biologicos: float = 0,
        ppe: float = 0,
        otros_activos: float = 0,
        pasivos: float = 0,
    ):
        """Carga los saldos patrimoniales (al 31-dic, valor fiscal)."""
        p = self.f110.patrimonio
        p.efectivo_y_equivalentes = efectivo
        p.inversiones_e_instrumentos = inversiones
        p.cuentas_documentos_arrend_por_cobrar = cxc
        p.inventarios = inventarios
        p.activos_intangibles = intangibles
        p.activos_biologicos = biologicos
        p.propiedades_planta_equipo = ppe
        p.otros_activos = otros_activos
        p.pasivos = pasivos

    def cargar_ingresos(
        self,
        ingresos_ordinarios: float = 0,
        ingresos_financieros: float = 0,
        otros_ingresos: float = 0,
        devoluciones: float = 0,
        incrngo: float = 0,
        dividendos_no_constitutivos: float = 0,
    ):
        """Carga los ingresos del año."""
        i = self.f110.ingresos
        i.ingresos_brutos_actividades_ordinarias = ingresos_ordinarios
        i.ingresos_financieros = ingresos_financieros
        i.otros_ingresos = otros_ingresos
        i.devoluciones_rebajas_descuentos = devoluciones
        i.ingresos_no_constitutivos_renta = incrngo
        i.dividendos_no_constitutivos = dividendos_no_constitutivos

    def cargar_costos_y_gastos(
        self,
        costos: float = 0,
        gastos_administracion: float = 0,
        gastos_ventas: float = 0,
        gastos_financieros: float = 0,
        otros_gastos: float = 0,
    ):
        """Carga los costos y gastos del año (CONTABLES, antes de conciliación)."""
        cg = self.f110.costos_y_deducciones
        cg.costos = costos
        cg.gastos_administracion = gastos_administracion
        cg.gastos_distribucion_ventas = gastos_ventas
        cg.gastos_financieros = gastos_financieros
        cg.otros_gastos_deducciones = otros_gastos

    def cargar_datos_informativos(
        self,
        nomina_total: float = 0,
        seguridad_social: float = 0,
        sena_icbf_caja: float = 0,
    ):
        """Carga los datos informativos (casillas 33-35)."""
        d = self.f110.declarante
        d.total_costos_gastos_nomina = nomina_total
        d.aportes_seguridad_social = seguridad_social
        d.aportes_sena_icbf_caja = sena_icbf_caja

    def cargar_retenciones(
        self,
        autorretenciones: float = 0,
        otras_retenciones: float = 0,
    ):
        """Carga retenciones que le practicaron a la empresa."""
        l = self.f110.liquidacion
        l.autorretenciones = autorretenciones
        l.otras_retenciones = otras_retenciones

    def cargar_saldo_favor_ano_anterior(self, valor: float):
        """Saldo a favor del año anterior sin solicitud de devolución."""
        self.f110.liquidacion.saldo_favor_ano_anterior = valor

    # --- Configuración de la conciliación fiscal ---

    def set_utilidad_contable_antes_impuestos(self, valor: float):
        """
        Define la utilidad contable antes de impuestos.
        Esta es la BASE de la conciliación fiscal.
        """
        self.utilidad_contable_antes_impuestos = valor

    def agregar_partida_conciliatoria(self, partida: PartidaConciliatoria):
        """Agrega una partida conciliatoria personalizada."""
        self.motor_conciliacion.agregar_partida(partida)

    def aplicar_gmf(self, gmf_certificado_total: float):
        """Aplica las reglas de GMF (50% no deducible)."""
        return self.motor_conciliacion.aplicar_gmf(gmf_certificado_total)

    def aplicar_provision_renta_no_deducible(self, provision: float):
        """Suma la provisión del impuesto de renta del PyG."""
        self.motor_conciliacion.aplicar_impuesto_renta_no_deducible(provision)

    # --- Cálculo principal ---

    def liquidar(self) -> Formulario110:
        """Ejecuta la liquidación completa y devuelve el Form 110."""
        # Paso 1: Conciliación fiscal
        self.resultado_conciliacion = self.motor_conciliacion.ejecutar(
            self.utilidad_contable_antes_impuestos
        )

        # Paso 2: Aplicar el resultado al Form 110
        # La renta líquida ordinaria (casilla 72) viene de la conciliación
        # PERO el formulario la calcula internamente como ingresos - costos
        # Por lo que tenemos que asegurarnos que cuadre.
        renta_liquida_fiscal = self.resultado_conciliacion.renta_liquida_fiscal

        # Sobrescribimos las rentas gravables (casilla 78) si hay descuadre
        # entre el cálculo aritmético del form (ingresos - gastos) y la conciliación.
        renta_aritmetica = (
            self.f110.ingresos.total_ingresos_netos
            - self.f110.costos_y_deducciones.total_costos_gastos_deducibles
        )
        diferencia = renta_liquida_fiscal - renta_aritmetica
        if abs(diferencia) > 1:
            # Si la conciliación dice más que la aritmética del form,
            # añadimos la diferencia como "rentas gravables" (casilla 78)
            # Esto cuadra el form con la conciliación
            self.f110.renta.rentas_gravables = max(0, diferencia)
            # Si la conciliación dice menos, ajustamos vía casilla 77 (renta exenta)
            if diferencia < 0:
                self.f110.renta.renta_exenta = abs(diferencia)

        # Paso 3: Calcular impuesto sobre la renta líquida gravable
        renta_gravable = self.f110.renta_liquida_gravable
        tarifa = (
            self.parametros.tarifa_personalizada
            if self.parametros.tarifa_personalizada is not None
            else TarifasRenta.GENERAL
        )
        self.f110.liquidacion.impuesto_rentas_liquidas = renta_gravable * tarifa

        # Paso 4: Aplicar Tasa Mínima de Tributación (TMT)
        if self.parametros.aplicar_tmt:
            self._aplicar_tmt()

        # Paso 5: Calcular anticipo del año siguiente
        self._calcular_anticipo()

        return self.f110

    def _aplicar_tmt(self):
        """
        Aplica la Tasa Mínima de Tributación (Ley 2277/2022).
        El impuesto neto no puede ser inferior al 15% de la utilidad depurada.
        """
        utilidad_depurada = (
            self.utilidad_contable_antes_impuestos  # UD = utilidad contable
            # Aquí podrían restar partidas exoneradas. Simplificado por ahora.
        )
        impuesto_minimo = utilidad_depurada * TarifasRenta.TMT
        impuesto_neto = self.f110.liquidacion.impuesto_neto_renta_sin_adicional

        if impuesto_neto < impuesto_minimo:
            # Adicionar la diferencia
            self.f110.liquidacion.valor_a_adicionar_vaa = impuesto_minimo - impuesto_neto

    def _calcular_anticipo(self):
        """
        Calcula el anticipo del año siguiente (art. 807 E.T.).

        Anticipo = (Impuesto neto renta - Retenciones) × %
        donde %:
          - 25% primer año
          - 50% segundo año
          - 75% tercer año en adelante
        """
        impuesto = self.f110.liquidacion.impuesto_neto_renta_con_adicional
        retenciones = self.f110.liquidacion.total_retenciones_ano_gravable
        base_anticipo = max(0, impuesto - retenciones)

        if self.parametros.ano_actual_de_declaracion == 1:
            pct = 0.25
        elif self.parametros.ano_actual_de_declaracion == 2:
            pct = 0.50
        else:
            pct = 0.75

        # En el caso de QUINTO SENTIDO, hay saldo a favor anterior y queda con saldo a favor
        # Por lo cual el anticipo es 0 (no hay saldo a pagar)
        # Si hay anticipo del año anterior, también se descuenta
        anticipo_calculado = base_anticipo * pct - self.parametros.anticipo_pagado_ano_anterior
        # Si el resultado total queda en saldo a favor, no anticipa
        # Esta lógica simplificada — en producción puede ser más sofisticada
        if self.f110.liquidacion.total_saldo_a_favor > 0:
            self.f110.liquidacion.anticipo_renta_ano_siguiente = 0
        else:
            self.f110.liquidacion.anticipo_renta_ano_siguiente = max(0, anticipo_calculado)

    # --- Reportes ---

    def reporte_completo(self) -> str:
        """Genera reporte legible completo de la liquidación."""
        lineas = []
        lineas.append("="*92)
        lineas.append(f"  LIQUIDACIÓN DE RENTA - {self.f110.declarante.razon_social}")
        lineas.append(f"  NIT: {self.f110.declarante.nit}-{self.f110.declarante.dv}")
        lineas.append(f"  Año Gravable: {self.f110.declarante.ano_gravable}")
        lineas.append("="*92)
        if self.resultado_conciliacion:
            lineas.append(self.resultado_conciliacion.resumen())
        lineas.append("")
        lineas.append("-"*92)
        lineas.append("FORMULARIO 110 - PRINCIPALES CASILLAS")
        lineas.append("-"*92)
        d = self.f110.to_dict()
        casillas_clave = [
            ("44", "Total patrimonio bruto", d["casilla_44_total_patrimonio_bruto"]),
            ("45", "Pasivos", self.f110.patrimonio.pasivos),
            ("46", "Total patrimonio líquido", d["casilla_46_total_patrimonio_liquido"]),
            ("58", "Total ingresos brutos", d["casilla_58_total_ingresos_brutos"]),
            ("61", "Total ingresos netos", d["casilla_61_total_ingresos_netos"]),
            ("67", "Total costos y gastos deducibles", d["casilla_67_total_costos_gastos_deducibles"]),
            ("72", "Renta líquida ordinaria del ejercicio", d["casilla_72_renta_liquida_ordinaria"]),
            ("75", "Renta líquida", d["casilla_75_renta_liquida"]),
            ("79", "Renta líquida gravable", d["casilla_79_renta_liquida_gravable"]),
            ("84", "Impuesto sobre rentas líquidas (35%)", self.f110.liquidacion.impuesto_rentas_liquidas),
            ("91", "Total impuesto rentas líquidas", d["casilla_91_total_impuesto_rentas_liquidas"]),
            ("94", "Impuesto neto renta sin adicional", d["casilla_94_impuesto_neto_sin_adicional"]),
            ("99", "Total impuesto a cargo", d["casilla_99_total_impuesto_a_cargo"]),
            ("104", "Saldo a favor año anterior", self.f110.liquidacion.saldo_favor_ano_anterior),
            ("107", "Total retenciones del año", d["casilla_107_total_retenciones"]),
            ("108", "Anticipo año siguiente", self.f110.liquidacion.anticipo_renta_ano_siguiente),
            ("111", "Saldo a pagar por impuesto", d["casilla_111_saldo_pagar_impuesto"]),
            ("113", "Total saldo a pagar", d["casilla_113_total_saldo_a_pagar"]),
            ("114", "Total saldo a favor", d["casilla_114_total_saldo_a_favor"]),
        ]
        for cas, desc, val in casillas_clave:
            lineas.append(f"  Cas. {cas:>3}  {desc:<55} ${val:>15,.0f}")
        return "\n".join(lineas)
