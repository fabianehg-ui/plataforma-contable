"""
Parámetros fiscales para Renta de Personas Jurídicas AG 2025.

Fuentes:
- Estatuto Tributario (E.T.)
- Ley 2277 de 2022 (reforma tributaria)
- Resolución DIAN 000022 de 2026 (plazos)
- Decreto 2229 de 2023 (calendario tributario)
"""
from dataclasses import dataclass


# ============================================================
# UVT POR AÑO
# ============================================================
UVT = {
    2024: 47_065,
    2025: 49_799,
    2026: 52_374,
}


# ============================================================
# TARIFAS GENERALES
# ============================================================
@dataclass(frozen=True)
class TarifasRenta:
    """Tarifas del impuesto sobre la renta para PJ AG 2025."""

    # Tarifa general (art. 240 E.T.)
    GENERAL: float = 0.35

    # Sectores con tarifas diferenciales (art. 240 E.T. parágrafos)
    HOTELES: float = 0.15  # nuevos hoteles, ecoturismo, agroturismo
    HOTELES_NUEVOS_MUNICIPIOS_PEQUEÑOS: float = 0.09
    EDITORIALES: float = 0.15
    INDUSTRIA_LICORERA_ESTATAL: float = 0.09
    USUARIOS_ZONA_FRANCA: float = 0.20

    # Ganancias ocasionales
    GANANCIAS_OCASIONALES: float = 0.15

    # Tasa Mínima de Tributación (TMT) — Ley 2277/2022 art. 240 par. 6
    TMT: float = 0.15

    # Sobretasas (renta líquida ≥ 120.000 UVT)
    SOBRETASA_FINANCIERAS: float = 0.05  # sobre renta gravable (5 puntos adicionales)
    SOBRETASA_HIDROCARBUROS_MIN: float = 0.0
    SOBRETASA_HIDROCARBUROS_MAX: float = 0.15
    SOBRETASA_CARBON_MIN: float = 0.0
    SOBRETASA_CARBON_MAX: float = 0.10
    SOBRETASA_HIDROELECTRICAS: float = 0.03


# ============================================================
# DESCUENTOS Y LÍMITES
# ============================================================
@dataclass(frozen=True)
class LimitesDeducciones:
    """Límites a deducciones y descuentos aplicables AG 2025."""

    # GMF (4×1000) — art. 115 E.T.
    # Solo el 50% es deducible si está debidamente certificado
    GMF_PORCENTAJE_DEDUCIBLE: float = 0.50

    # ICA — art. 115 E.T.
    # 100% deducible cuando se pagó efectivamente en el año
    # (o como descuento art. 115 par. 1, pero esa opción se eliminó AG 2024)
    ICA_PORCENTAJE_DEDUCIBLE: float = 1.00

    # Beneficios tributarios límite (art. 259-1 E.T.)
    LIMITE_BENEFICIOS_PCT_RLG: float = 0.03

    # Pagos al exterior — máximo 15% renta líquida (art. 122 E.T.)
    LIMITE_PAGOS_EXTERIOR_PCT_RL: float = 0.15

    # Descuentos tributarios — limite art. 259 E.T.
    # No pueden superar el 25% del impuesto a cargo
    LIMITE_DESCUENTOS_PCT_IMPUESTO: float = 0.25


# ============================================================
# RENTA PRESUNTIVA
# ============================================================
@dataclass(frozen=True)
class RentaPresuntiva:
    """Renta presuntiva: 0% para AG 2021 y siguientes (Ley 2010/2019 art. 90)."""

    PORCENTAJE_AG_2025: float = 0.00


# ============================================================
# ANTICIPO RENTA AÑO SIGUIENTE (art. 807 E.T.)
# ============================================================
@dataclass(frozen=True)
class AnticipoRenta:
    """Cálculo del anticipo de renta año siguiente."""

    # Primer año declarando: 25%
    # Segundo año: 50%
    # Tercer año en adelante: 75%
    PCT_PRIMER_ANO: float = 0.25
    PCT_SEGUNDO_ANO: float = 0.50
    PCT_TERCER_ANO_EN_ADELANTE: float = 0.75


# ============================================================
# SANCIONES
# ============================================================
@dataclass(frozen=True)
class Sanciones:
    """Sanciones por extemporaneidad (art. 641 E.T.)."""

    # Por mes o fracción de mes de retraso
    EXTEMPORANEIDAD_PCT_VOLUNTARIA: float = 0.05  # antes del emplazamiento
    EXTEMPORANEIDAD_PCT_EMPLAZAMIENTO: float = 0.10  # después del emplazamiento

    # Sanción mínima 2026: 10 UVT
    SANCION_MINIMA_UVT: int = 10


# ============================================================
# PLAZOS AG 2025 (Decreto 2229/2023, Res. DIAN 000022/2026)
# ============================================================
PLAZOS_PJ_AG2025 = {
    # Grandes contribuyentes (1ra cuota: feb 2026, 2da y declaración: abril 2026)
    'gran_contribuyente_primera_cuota': ('2026-02-10', '2026-02-23'),
    'gran_contribuyente_declaracion': ('2026-04-13', '2026-04-27'),
    # PJ no grandes contribuyentes (mayo-junio 2026 según último dígito NIT)
    'pj_normal_declaracion': {
        '1': '2026-05-14', '2': '2026-05-15', '3': '2026-05-19', '4': '2026-05-20',
        '5': '2026-05-21', '6': '2026-05-22', '7': '2026-05-23', '8': '2026-05-26',
        '9': '2026-05-27', '0': '2026-05-28',
    },
}


# ============================================================
# UTILIDADES
# ============================================================
def calcular_uvt(valor: float, ano: int = 2025) -> float:
    """Convierte un valor en pesos a UVT."""
    return valor / UVT[ano]


def aplicar_uvt(uvt_cantidad: float, ano: int = 2025) -> float:
    """Convierte una cantidad en UVT a pesos."""
    return uvt_cantidad * UVT[ano]


def redondear_dian(valor: float) -> int:
    """
    Redondeo oficial DIAN para casillas del formulario.
    Las casillas se reportan en miles, redondeando al millar más cercano.
    """
    # Truncar a entero primero, luego redondear al millar
    return round(valor / 1000) * 1000


# ============================================================
# REGLAS DE LIQUIDACIÓN — Reglas de oro
# ============================================================
"""
RECORDATORIOS CRÍTICOS para la liquidación de renta PJ AG 2025:

1. La provisión del impuesto de renta (cuenta 5405) NO es deducible.
   Suma a la utilidad contable para calcular renta líquida.

2. El GMF (4×1000) solo es deducible al 50%, debidamente certificado.
   El otro 50% es no deducible y suma a renta.

3. El ICA es 100% deducible si se pagó efectivamente en el año.
   La opción de tomar el 50% como descuento tributario fue ELIMINADA
   a partir de AG 2024 (Ley 2277/2022).

4. Renta presuntiva: 0% desde AG 2021. Solo aplica si el patrimonio
   tiene activos exceptuados con renta gravable propia.

5. Patrimonio: se reporta a VALOR FISCAL al 31-DIC, no contable.
   Hay diferencias por: depreciación fiscal vs contable, valor razonable
   de inversiones, deterioro NO aceptado fiscalmente, etc.

6. Conciliación patrimonial: si la diferencia patrimonial supera
   las rentas ajustadas, se genera renta por comparación patrimonial
   (art. 236-239 E.T.). En la práctica casi nunca aplica.

7. Tasa Mínima de Tributación (TMT): el impuesto neto de renta no puede
   ser inferior al 15% de la utilidad contable depurada. Si lo es, se
   adiciona la diferencia (Valor a Adicionar - VAA, casilla 92).
"""
