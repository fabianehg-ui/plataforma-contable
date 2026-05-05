"""
Módulo de Declaración de Renta — Personas Jurídicas

Provee toda la lógica para liquidar el Formulario 110 partiendo del balance
contable de una empresa, aplicando conciliación fiscal automática y generando
los entregables (Form 110, Excel comparativo, dictamen Word).

Uso típico:

    from core.procesadores.renta import LiquidadorRenta, ParametrosLiquidacion

    liq = LiquidadorRenta(
        nit="900533491-5",
        razon_social="QUINTO SENTIDOS S.A.S.",
        ano_gravable=2025,
        parametros=ParametrosLiquidacion(),
    )

    liq.cargar_patrimonio(...)
    liq.cargar_ingresos(...)
    liq.cargar_costos_y_gastos(...)
    liq.set_utilidad_contable_antes_impuestos(79_150_862)
    liq.aplicar_provision_renta_no_deducible(42_849_000)
    liq.aplicar_gmf(2_655_013)
    liq.cargar_retenciones(otras=22_968_000, autorretenciones=10_201_000)
    liq.cargar_saldo_favor_ano_anterior(37_906_000)

    f110 = liq.liquidar()
    print(liq.reporte_completo())
"""

from .parametros_fiscales import (
    UVT,
    TarifasRenta,
    LimitesDeducciones,
    RentaPresuntiva,
    AnticipoRenta,
    Sanciones,
    PLAZOS_PJ_AG2025,
    redondear_dian,
    calcular_uvt,
    aplicar_uvt,
)

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
    PartidaConciliatoria,
    CATALOGO_PARTIDAS_PERMANENTES,
    MotorConciliacion,
    ResultadoConciliacion,
    ConciliacionPatrimonial,
)

from .liquidador import (
    LiquidadorRenta,
    ParametrosLiquidacion,
    MAPEO_PUC_PATRIMONIO,
    MAPEO_PUC_INGRESOS,
    MAPEO_PUC_COSTOS_GASTOS,
)

# Repositorio Supabase (lazy import - solo se carga si hay supabase configurado)
try:
    from .repositorio import RepositorioRenta
except ImportError:
    RepositorioRenta = None  # type: ignore

# Importador de balance Siigo
from .importador_siigo import ImportadorBalanceSiigo

# Importador PILA (seguridad social y parafiscales)
from .importador_pila import (
    ImportadorPILA,
    ResumenPILA,
    PagoPILA,
    calcular_nomina_desde_balance,
    validar_pila_vs_balance,
)

# Importador de certificados de retención
from .importador_certificados import (
    ImportadorCertificadosZIP,
    ResumenCertificados,
    CertificadoRetencion,
    InventarioPDF,
    conciliar_certificados_vs_balance,
)

# Exportadores
from .exportadores import generar_excel_comparativo, generar_dictamen_word

__all__ = [
    # Parámetros
    'UVT',
    'TarifasRenta', 'LimitesDeducciones', 'RentaPresuntiva',
    'AnticipoRenta', 'Sanciones',
    'PLAZOS_PJ_AG2025',
    'redondear_dian', 'calcular_uvt', 'aplicar_uvt',
    # Form 110
    'Formulario110',
    'DatosDeclarante', 'Patrimonio', 'Ingresos',
    'CostosYDeducciones', 'Renta', 'GananciasOcasionales',
    'LiquidacionPrivada',
    # Conciliación
    'PartidaConciliatoria', 'CATALOGO_PARTIDAS_PERMANENTES',
    'MotorConciliacion', 'ResultadoConciliacion',
    'ConciliacionPatrimonial',
    # Liquidador
    'LiquidadorRenta', 'ParametrosLiquidacion',
    'MAPEO_PUC_PATRIMONIO', 'MAPEO_PUC_INGRESOS', 'MAPEO_PUC_COSTOS_GASTOS',
    # Persistencia
    'RepositorioRenta',
    # Importador
    'ImportadorBalanceSiigo',
    # PILA
    'ImportadorPILA', 'ResumenPILA', 'PagoPILA',
    'calcular_nomina_desde_balance', 'validar_pila_vs_balance',
    # Certificados de retención
    'ImportadorCertificadosZIP', 'ResumenCertificados',
    'CertificadoRetencion', 'InventarioPDF',
    'conciliar_certificados_vs_balance',
    # Exportadores
    'generar_excel_comparativo', 'generar_dictamen_word',
]
