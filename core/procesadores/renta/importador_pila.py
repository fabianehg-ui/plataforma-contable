"""
Importador de PILA (Planilla Integrada de Liquidación de Aportes).

Lee el archivo XLS exportado por operadores PILA (Aportes en Línea, SOI,
MiPlanilla, etc.) y extrae los aportes pagados por el empleador para
seguridad social (Pensión, Salud, ARL) y parafiscales (Caja, SENA, ICBF).

Hojas esperadas:
    - "Consolidado, Seguridad Social" — pensión, salud, riesgos
    - "Consolidado, Parafiscales" — caja, sena, icbf

El archivo cubre los 12 períodos de cotización del año gravable: enero a
diciembre se reportan/pagan en febrero del año siguiente al mes que
corresponda. Por lo tanto un AG 2025 abarca pagos hechos entre febrero/2025
y enero/2026 con períodos de cotización 202501 a 202512.

Convención del archivo: "Total Aporte obligatorio" trae SOLO la parte del
empleador (no incluye el aporte del trabajador).

Salida:
    ResumenPILA con totales por subsistema, por mes, y por nómina (admin/ventas)
    para alimentar las casillas 33, 34 y 35 del Formulario 110 y el anexo
    de pagos efectivos a seguridad social.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Iterable
import logging
import unicodedata

log = logging.getLogger(__name__)


# ============================================================
# CONSTANTES
# ============================================================

# Códigos PUC de gastos de personal por tipo de nómina.
# La PILA no distingue admin/ventas; ese reparto se hace contra el balance.
RANGO_NOMINA_ADMIN_INICIO = "5105"
RANGO_NOMINA_ADMIN_FIN_PREFIJO = "510539"  # Cesantías, primas, vacaciones
RANGO_NOMINA_VENTAS_INICIO = "5205"
RANGO_NOMINA_VENTAS_FIN_PREFIJO = "520539"
# Costos de nómina (mano de obra directa o indirecta de producción)
RANGO_NOMINA_COSTOS_INICIO_72 = "7205"
RANGO_NOMINA_COSTOS_FIN_72 = "720539"
RANGO_NOMINA_COSTOS_INICIO_73 = "7305"
RANGO_NOMINA_COSTOS_FIN_73 = "730539"


# ============================================================
# MODELO DE DATOS
# ============================================================

@dataclass
class PagoPILA:
    """Un pago/planilla individual de la PILA."""
    subsistema: str          # "Pensión", "Salud", "Riesgos", "Cajas de compensación", "SENA", "ICBF"
    periodo_cotizacion: str  # "202501" formato YYYYMM
    fecha_pago: str          # Fecha en que se pagó la planilla
    aporte_empleador: float  # Solo parte del empleador

    @property
    def mes_periodo(self) -> int:
        """Mes del periodo de cotización (1-12)."""
        try:
            return int(self.periodo_cotizacion[-2:])
        except (ValueError, IndexError):
            return 0

    @property
    def ano_periodo(self) -> int:
        """Año del periodo de cotización."""
        try:
            return int(self.periodo_cotizacion[:4])
        except (ValueError, IndexError):
            return 0


@dataclass
class ResumenPILA:
    """Resumen agregado de la PILA, listo para alimentar el Form 110."""

    # Totales por subsistema (todo el año gravable)
    pension: float = 0.0
    salud: float = 0.0
    riesgos: float = 0.0
    caja: float = 0.0
    sena: float = 0.0
    icbf: float = 0.0

    # Lista cruda de pagos para el anexo detallado
    pagos: list[PagoPILA] = field(default_factory=list)

    # Metadata
    ano_gravable: int = 2025
    periodos_cubiertos: list[str] = field(default_factory=list)
    total_planillas: int = 0

    @property
    def seguridad_social_empleador(self) -> float:
        """Cas. 34 del Formulario 110: aportes a seguridad social del empleador."""
        return self.pension + self.salud + self.riesgos

    @property
    def parafiscales(self) -> float:
        """Cas. 35 del Formulario 110: SENA + ICBF + Caja."""
        return self.sena + self.icbf + self.caja

    @property
    def total_aportes(self) -> float:
        return self.seguridad_social_empleador + self.parafiscales

    def por_mes(self, subsistemas: Optional[Iterable[str]] = None) -> dict[int, float]:
        """
        Retorna un dict {mes: total} con los pagos del año.
        Si se pasa subsistemas, solo suma los que estén en la lista.

        Útil para el Anexo 21 del liquidador (tabla mensual por concepto).
        """
        subs_normalizados = None
        if subsistemas is not None:
            subs_normalizados = {_normalizar(s) for s in subsistemas}
        out = {m: 0.0 for m in range(1, 13)}
        for pago in self.pagos:
            if subs_normalizados is not None and _normalizar(pago.subsistema) not in subs_normalizados:
                continue
            mes = pago.mes_periodo
            if 1 <= mes <= 12:
                out[mes] += pago.aporte_empleador
        return out

    def resumen_texto(self) -> str:
        """Texto legible para mostrar al usuario tras importar."""
        lineas = [
            f"PILA importada — {self.total_planillas} planillas",
            f"Períodos cubiertos: {len(self.periodos_cubiertos)} ({', '.join(self.periodos_cubiertos[:3])}...)",
            "",
            "Aportes del empleador:",
            f"  Pensión          ${self.pension:>15,.0f}",
            f"  Salud            ${self.salud:>15,.0f}",
            f"  Riesgos (ARL)    ${self.riesgos:>15,.0f}",
            f"  ─────────────────────────────────────",
            f"  Cas. 34 Total    ${self.seguridad_social_empleador:>15,.0f}",
            "",
            f"  Caja             ${self.caja:>15,.0f}",
            f"  SENA             ${self.sena:>15,.0f}",
            f"  ICBF             ${self.icbf:>15,.0f}",
            f"  ─────────────────────────────────────",
            f"  Cas. 35 Total    ${self.parafiscales:>15,.0f}",
        ]
        return "\n".join(lineas)


# ============================================================
# IMPORTADOR
# ============================================================

class ImportadorPILA:
    """Lee un archivo XLS/XLSX de PILA y devuelve un ResumenPILA."""

    HOJA_SS = "Consolidado, Seguridad Social"
    HOJA_PARAFISCALES = "Consolidado, Parafiscales"

    # Nombres de columnas esperadas (tolerantes a espacios y acentos)
    COL_SUBSISTEMA = "subsistema"
    COL_PERIODO = "periodo de cotizacion"
    COL_FECHA = "fecha de pago de la planilla"
    COL_APORTE_SS = "total aporte obligatorio"
    COL_APORTE_PAR = "valor aporte"

    def importar(self, ruta: str | Path, ano_gravable: int = 2025) -> ResumenPILA:
        """Importa una PILA y retorna el resumen agregado."""
        try:
            import pandas as pd  # noqa
        except ImportError as e:
            raise ImportError(
                "pandas es requerido para importar PILA. "
                "Instalar con: pip install pandas xlrd openpyxl"
            ) from e

        ruta = Path(ruta)
        if not ruta.exists():
            raise FileNotFoundError(f"Archivo no encontrado: {ruta}")

        resumen = ResumenPILA(ano_gravable=ano_gravable)

        # 1. Seguridad Social
        try:
            self._procesar_hoja_ss(ruta, resumen)
        except Exception as e:
            log.warning("No se pudo procesar hoja '%s': %s", self.HOJA_SS, e)

        # 2. Parafiscales
        try:
            self._procesar_hoja_parafiscales(ruta, resumen)
        except Exception as e:
            log.warning("No se pudo procesar hoja '%s': %s", self.HOJA_PARAFISCALES, e)

        # Metadata
        resumen.total_planillas = len(resumen.pagos)
        resumen.periodos_cubiertos = sorted({p.periodo_cotizacion for p in resumen.pagos})

        log.info(
            "PILA importada: %d planillas, períodos %s, SS empleador $%s, "
            "parafiscales $%s",
            resumen.total_planillas,
            f"{len(resumen.periodos_cubiertos)} meses",
            f"{resumen.seguridad_social_empleador:,.0f}",
            f"{resumen.parafiscales:,.0f}",
        )
        return resumen

    def _procesar_hoja_ss(self, ruta: Path, resumen: ResumenPILA) -> None:
        """Lee la hoja de seguridad social y agrega los pagos al resumen."""
        import pandas as pd
        df = pd.read_excel(ruta, sheet_name=self.HOJA_SS)
        df.columns = [_normalizar(c) for c in df.columns]

        col_sub = self._col(df, self.COL_SUBSISTEMA)
        col_per = self._col(df, self.COL_PERIODO)
        col_fec = self._col(df, self.COL_FECHA)
        col_apt = self._col(df, self.COL_APORTE_SS)

        for _, row in df.iterrows():
            sub_raw = str(row[col_sub]) if pd.notna(row[col_sub]) else ""
            sub = _reparar_encoding(sub_raw)
            if not sub:
                continue
            aporte = self._a_float(row[col_apt])
            if aporte == 0:
                continue
            pago = PagoPILA(
                subsistema=sub,
                periodo_cotizacion=str(row[col_per]).strip() if pd.notna(row[col_per]) else "",
                fecha_pago=str(row[col_fec]) if pd.notna(row[col_fec]) else "",
                aporte_empleador=aporte,
            )
            # Filtrar por año gravable: solo periodos AAAA01..AAAA12
            mes = pago.mes_periodo
            ano = pago.ano_periodo
            if ano != resumen.ano_gravable or not (1 <= mes <= 12):
                continue
            resumen.pagos.append(pago)

            # Sumar al subsistema correspondiente
            sub_norm = _normalizar(sub)
            if "pension" in sub_norm:
                resumen.pension += aporte
            elif "salud" in sub_norm:
                resumen.salud += aporte
            elif "riesgos" in sub_norm or "arl" in sub_norm:
                resumen.riesgos += aporte
            else:
                log.debug("Subsistema SS no reconocido: %s", sub)

    def _procesar_hoja_parafiscales(self, ruta: Path, resumen: ResumenPILA) -> None:
        """Lee la hoja de parafiscales y agrega los pagos al resumen."""
        import pandas as pd
        df = pd.read_excel(ruta, sheet_name=self.HOJA_PARAFISCALES)
        df.columns = [_normalizar(c) for c in df.columns]

        col_sub = self._col(df, self.COL_SUBSISTEMA)
        col_per = self._col(df, self.COL_PERIODO)
        col_fec = self._col(df, self.COL_FECHA)
        col_apt = self._col(df, self.COL_APORTE_PAR)

        for _, row in df.iterrows():
            sub_raw = str(row[col_sub]) if pd.notna(row[col_sub]) else ""
            sub = _reparar_encoding(sub_raw)
            if not sub:
                continue
            aporte = self._a_float(row[col_apt])
            if aporte == 0:
                continue
            pago = PagoPILA(
                subsistema=sub,
                periodo_cotizacion=str(row[col_per]).strip() if pd.notna(row[col_per]) else "",
                fecha_pago=str(row[col_fec]) if pd.notna(row[col_fec]) else "",
                aporte_empleador=aporte,
            )
            mes = pago.mes_periodo
            ano = pago.ano_periodo
            if ano != resumen.ano_gravable or not (1 <= mes <= 12):
                continue
            resumen.pagos.append(pago)

            sub_norm = _normalizar(sub)
            if "caja" in sub_norm or "compensacion" in sub_norm:
                resumen.caja += aporte
            elif "sena" in sub_norm:
                resumen.sena += aporte
            elif "icbf" in sub_norm:
                resumen.icbf += aporte
            else:
                log.debug("Subsistema parafiscal no reconocido: %s", sub)

    def _col(self, df, nombre_normalizado: str) -> str:
        """Encuentra el nombre real de columna que matchea (tolerante)."""
        for c in df.columns:
            if nombre_normalizado in c:
                return c
        raise KeyError(
            f"Columna '{nombre_normalizado}' no encontrada en hoja. "
            f"Columnas disponibles: {list(df.columns)}"
        )

    @staticmethod
    def _a_float(v) -> float:
        if v is None:
            return 0.0
        if isinstance(v, (int, float)):
            try:
                f = float(v)
                return 0.0 if abs(f) < 0.005 else f
            except (ValueError, TypeError):
                return 0.0
        try:
            s = str(v).replace(",", "").replace(" ", "")
            return float(s)
        except (ValueError, TypeError):
            return 0.0


# ============================================================
# CÁLCULO DE NÓMINA TOTAL (Cas. 33) DESDE EL BALANCE
# ============================================================

def calcular_nomina_desde_balance(balance) -> dict:
    """
    Calcula el total de nómina del año (Cas. 33) sumando todas las cuentas
    de gastos de personal del balance.

    Cas. 33 se conforma por las cuentas:
      - 5105xx hasta 51053999 (gastos de personal admin)
      - 5205xx hasta 52053999 (gastos de personal ventas)
      - 7205xx hasta 72053999 (mano de obra directa)
      - 7305xx hasta 73053999 (mano de obra indirecta)

    "Hasta xx0539" significa hasta cesantías/primas/vacaciones/intereses,
    que es donde típicamente termina el detalle de devengado en el PUC.
    Otros conceptos posteriores (como dotación, capacitación) suelen ir
    como gastos generales, no nómina.

    Args:
        balance: BalanceSiigo del importador_siigo

    Returns:
        dict con desglose:
          {
            "admin": float,      # 5105xx
            "ventas": float,     # 5205xx
            "costos_72": float,  # 7205xx
            "costos_73": float,  # 7305xx
            "total": float,      # suma para Cas. 33
            "detalle": [(codigo, nombre, saldo), ...]  # para auditar
          }
    """
    PREFIJOS = {
        "admin": ("5105", "510539"),
        "ventas": ("5205", "520539"),
        "costos_72": ("7205", "720539"),
        "costos_73": ("7305", "730539"),
    }

    out = {"admin": 0.0, "ventas": 0.0, "costos_72": 0.0, "costos_73": 0.0,
           "total": 0.0, "detalle": []}

    for codigo, cta in balance.cuentas.items():
        c = codigo.strip()
        # Solo cuentas hoja para evitar doble conteo
        if not _es_cuenta_hoja(c, balance.cuentas.keys()):
            continue

        for tipo, (inicio, fin) in PREFIJOS.items():
            # La cuenta debe empezar por el prefijo de inicio (ej: "5105")
            # y tener 4 dígitos del prefijo + dígitos adicionales hasta xx0539
            # En PUC: 5105 (grupo) > 510506 (cuenta) > 51050601 (subcuenta)
            # Queremos todo lo que empiece por 5105 y cuyos dígitos 5-6 sean ≤ 39
            if c.startswith(inicio) and len(c) >= 6:
                try:
                    digitos_5_6 = int(c[4:6])
                    if 0 <= digitos_5_6 <= 39:
                        valor = cta.saldo_nuevo
                        if abs(valor) > 0.005:
                            out[tipo] += valor
                            out["detalle"].append((c, cta.nombre, valor))
                except ValueError:
                    pass

    out["total"] = out["admin"] + out["ventas"] + out["costos_72"] + out["costos_73"]
    return out


# ============================================================
# VALIDACIÓN: NÓMINA BALANCE vs APORTES PILA
# ============================================================

def validar_pila_vs_balance(resumen_pila: ResumenPILA, nomina_balance: dict) -> dict:
    """
    Compara los aportes pagados según PILA con la causación contable de
    nómina, para detectar inconsistencias.

    Heurística básica: Si pagas $32M de pensión al 12% empleador, la base
    de cotización mínima fue $32M / 0.12 ≈ $266M. Esa base debería ser
    cercana a salarios + horas extras del balance (~$152M en Quinto Sentidos).
    Si la diferencia es mayor a 30%, alertar.

    Esto NO bloquea la importación — solo informa.

    Returns:
        dict con flags de validación:
          {
            "cuadra": bool,
            "alertas": [str, ...],
            "info": [str, ...]
          }
    """
    out = {"cuadra": True, "alertas": [], "info": []}

    base_implicita_pension = resumen_pila.pension / 0.12 if resumen_pila.pension else 0
    base_admin = nomina_balance.get("admin", 0)
    base_ventas = nomina_balance.get("ventas", 0)
    base_total_balance = base_admin + base_ventas

    if base_total_balance > 0 and base_implicita_pension > 0:
        diff_pct = abs(base_implicita_pension - base_total_balance) / base_total_balance
        if diff_pct > 0.30:
            out["cuadra"] = False
            out["alertas"].append(
                f"⚠️ Base implícita PILA (${base_implicita_pension:,.0f}) vs "
                f"nómina balance (${base_total_balance:,.0f}) difiere en "
                f"{diff_pct*100:.0f}%. Revisar causación o aportes."
            )
        else:
            out["info"].append(
                f"✓ Base implícita PILA cuadra dentro del 30% con balance "
                f"(diferencia {diff_pct*100:.0f}%)"
            )

    return out


# ============================================================
# UTILIDADES INTERNAS
# ============================================================

def _normalizar(s: str) -> str:
    """Quita acentos, pasa a minúsculas, normaliza espacios."""
    if s is None:
        return ""
    s = str(s)
    # Quitar tildes
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.lower().strip().replace("\n", " ").replace("  ", " ")


def _reparar_encoding(s: str) -> str:
    """Repara mojibake típico de PILA (Pensión → PensiÃ³n)."""
    if not s:
        return s
    return (
        s.replace("Ã³", "ó").replace("Ã±", "ñ").replace("Ã©", "é")
         .replace("Ã­", "í").replace("Ãº", "ú").replace("Ã¡", "á")
         .replace("Ã‰", "É").replace("Ã“", "Ó").replace("Ã‘", "Ñ")
    )


def _es_cuenta_hoja(codigo: str, todos_los_codigos) -> bool:
    """Una cuenta es hoja si no hay otra cuenta más larga que empiece por ella."""
    for otro in todos_los_codigos:
        if len(otro) > len(codigo) and otro.startswith(codigo):
            return False
    return True
