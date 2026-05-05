"""
Importador de PILA (Planilla Integrada de Liquidación de Aportes).

Lee el archivo XLS exportado por operadores PILA y extrae los aportes pagados
por el empleador para seguridad social (Pensión, Salud, ARL) y parafiscales
(Caja, SENA, ICBF).

Estrategia: usar las hojas DETALLADAS (no las consolidadas) porque traen la
discriminación correcta entre aporte empleador (deducible) y aporte trabajador
(no deducible), permitiendo clasificar por administradora.

Hojas esperadas:
    - "Seguridad Social"  — detalle por administradora (preferida)
    - "Parafiscales"      — detalle de parafiscales (preferida)
    - Fallback: "Consolidado, Seguridad Social" / "Consolidado, Parafiscales"

EXONERACIÓN LEY 1819/2016:
    Casi todas las empresas en Colombia están exoneradas del aporte de salud
    al empleador (8.5%) y de SENA/ICBF, salvo:
      - Entidades sin ánimo de lucro (ESAL)
      - Empresas con empleados que devengan más de 10 SMMLV

    Para los empleados exonerados, el operador PILA reporta tarifa empleador 0%
    y aporte empleador $0 en salud, pero el trabajador sigue aportando su 4%
    (descontado del salario).

    La columna 'Aporte Empleador' del detalle ya respeta esto: trae el valor
    real pagado por la empresa. Por eso es la fuente correcta para Cas. 34.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Iterable
import logging
import unicodedata

log = logging.getLogger(__name__)


# ============================================================
# CLASIFICACIÓN DE ADMINISTRADORAS
# ============================================================

# SURA puede ser de cualquier subsistema. Se identifica con casos especiales.
CASOS_ESPECIALES = {
    "EPS SURA": "Salud",
    "SURA EPS": "Salud",
    "PENSIONES SURA": "Pensión",
    "SURA PENSIONES": "Pensión",
    "ARL SURA": "Riesgos",
    "SURA ARL": "Riesgos",
    "SEGUROS DE VIDA SURAMERICANA": "Riesgos",
}

# Palabras clave por subsistema (orden: ARL antes de SALUD por ambigüedad)
KEYWORDS_PENSION = {
    "COLPENSIONES", "PORVENIR", "PROTECCION", "PROTECCIÓN",
    "COLFONDOS", "OLD MUTUAL", "SKANDIA",
    "PENSION", "PENSIÓN", "PENSIONES", "AFP",
}
KEYWORDS_ARL = {
    "RIESGOS PROFESIONALES", "RIESGOS LABORALES",
    "ARL", "POSITIVA", "COLPATRIA ARL",
    "BOLIVAR ARL", "COLMENA RIESGOS", "COLMENA",
    "EQUIDAD ARL", "AURORA", "LIBERTY ARL",
    "MAPFRE ARL", "AXA RIESGOS",
}
KEYWORDS_SALUD = {
    "EPS", "SALUD TOTAL", "SANITAS", "COMPENSAR", "NUEVA EPS",
    "COOMEVA", "CAFESALUD", "FAMISANAR", "ALIANSALUD", "ASMET",
    "MUTUAL SER", "EMSSANAR", "SALUD MIA", "MEDIMAS",
}


def clasificar_administradora(nombre: str) -> Optional[str]:
    """Clasifica administradora a 'Pensión', 'Salud', 'Riesgos' o None."""
    if not nombre:
        return None
    n = str(nombre).upper().strip()

    for clave, sub in CASOS_ESPECIALES.items():
        if clave in n:
            return sub

    for kw in KEYWORDS_PENSION:
        if kw in n:
            return "Pensión"
    for kw in KEYWORDS_ARL:
        if kw in n:
            return "Riesgos"
    for kw in KEYWORDS_SALUD:
        if kw in n:
            return "Salud"
    return None


# ============================================================
# MODELO
# ============================================================

@dataclass
class PagoPILA:
    subsistema: str
    administradora: str
    periodo_cotizacion: str
    fecha_pago: str
    aporte_empleador: float
    ibc: float = 0.0

    @property
    def mes_periodo(self) -> int:
        try:
            return int(self.periodo_cotizacion[-2:])
        except (ValueError, IndexError):
            return 0

    @property
    def ano_periodo(self) -> int:
        try:
            return int(self.periodo_cotizacion[:4])
        except (ValueError, IndexError):
            return 0


@dataclass
class ResumenPILA:
    pension: float = 0.0
    salud: float = 0.0
    riesgos: float = 0.0
    caja: float = 0.0
    sena: float = 0.0
    icbf: float = 0.0
    pagos: list[PagoPILA] = field(default_factory=list)
    ano_gravable: int = 2025
    periodos_cubiertos: list[str] = field(default_factory=list)
    total_planillas: int = 0
    administradoras_no_clasificadas: list[str] = field(default_factory=list)

    @property
    def seguridad_social_empleador(self) -> float:
        return self.pension + self.salud + self.riesgos

    @property
    def parafiscales(self) -> float:
        return self.sena + self.icbf + self.caja

    @property
    def total_aportes(self) -> float:
        return self.seguridad_social_empleador + self.parafiscales

    def por_mes(self, subsistemas: Optional[Iterable[str]] = None) -> dict[int, float]:
        subs_norm = None
        if subsistemas is not None:
            subs_norm = {_normalizar(s) for s in subsistemas}
        out = {m: 0.0 for m in range(1, 13)}
        for pago in self.pagos:
            if subs_norm is not None and _normalizar(pago.subsistema) not in subs_norm:
                continue
            mes = pago.mes_periodo
            if 1 <= mes <= 12:
                out[mes] += pago.aporte_empleador
        return out

    def resumen_texto(self) -> str:
        lineas = [
            f"PILA importada — {self.total_planillas} aportes individuales",
            f"Períodos: {len(self.periodos_cubiertos)}",
            "",
            "Aportes empleador (deducibles):",
            f"  Pensión          ${self.pension:>15,.0f}",
            f"  Salud            ${self.salud:>15,.0f}",
            f"  Riesgos (ARL)    ${self.riesgos:>15,.0f}",
            f"  Cas. 34 Total    ${self.seguridad_social_empleador:>15,.0f}",
            "",
            f"  Caja             ${self.caja:>15,.0f}",
            f"  SENA             ${self.sena:>15,.0f}",
            f"  ICBF             ${self.icbf:>15,.0f}",
            f"  Cas. 35 Total    ${self.parafiscales:>15,.0f}",
        ]
        if self.administradoras_no_clasificadas:
            lineas.append("")
            lineas.append("⚠️ Administradoras no clasificadas:")
            for a in self.administradoras_no_clasificadas:
                lineas.append(f"  - {a}")
        return "\n".join(lineas)


# ============================================================
# IMPORTADOR
# ============================================================

class ImportadorPILA:

    HOJA_SS_DETALLE = "Seguridad Social"
    HOJA_PARAFISCALES_DETALLE = "Parafiscales"
    HOJA_SS_CONSOLIDADO = "Consolidado, Seguridad Social"
    HOJA_PARAFISCALES_CONSOLIDADO = "Consolidado, Parafiscales"

    def importar(self, ruta: str | Path, ano_gravable: int = 2025) -> ResumenPILA:
        try:
            import pandas as pd  # noqa
        except ImportError as e:
            raise ImportError(
                "pandas requerido. pip install pandas xlrd openpyxl"
            ) from e

        ruta = Path(ruta)
        if not ruta.exists():
            raise FileNotFoundError(f"Archivo no encontrado: {ruta}")

        resumen = ResumenPILA(ano_gravable=ano_gravable)
        import pandas as pd
        xls = pd.ExcelFile(ruta)
        hojas = set(xls.sheet_names)

        if self.HOJA_SS_DETALLE in hojas:
            self._procesar_ss_detallada(ruta, resumen)
        elif self.HOJA_SS_CONSOLIDADO in hojas:
            self._procesar_ss_consolidada(ruta, resumen)
        else:
            log.warning("Sin hoja de seguridad social")

        if self.HOJA_PARAFISCALES_DETALLE in hojas:
            self._procesar_parafiscales_detallada(ruta, resumen)
        elif self.HOJA_PARAFISCALES_CONSOLIDADO in hojas:
            self._procesar_parafiscales_consolidada(ruta, resumen)
        else:
            log.warning("Sin hoja de parafiscales")

        resumen.total_planillas = len(resumen.pagos)
        resumen.periodos_cubiertos = sorted({
            p.periodo_cotizacion for p in resumen.pagos if p.periodo_cotizacion
        })
        return resumen

    def _procesar_ss_detallada(self, ruta: Path, resumen: ResumenPILA) -> None:
        import pandas as pd
        df = pd.read_excel(ruta, sheet_name=self.HOJA_SS_DETALLE)

        col_adm = self._col(df, ["administradora"], excluir=["codigo", "nit"])
        col_per = self._col(df, ["periodo", "cotizacion"])
        col_fec = self._col(df, ["fecha", "pago"], opcional=True)
        col_apt = self._col(df, ["aporte", "empleador"], excluir=["voluntario", "afp"])
        col_ibc = self._col(df, ["ibc"], opcional=True)

        if not col_adm or not col_per or not col_apt:
            log.error("Columnas SS detalle no encontradas. Disponibles: %s",
                      list(df.columns))
            return

        admins_no_clas = set()
        for _, row in df.iterrows():
            adm = str(row[col_adm]).strip() if pd.notna(row[col_adm]) else ""
            if not adm:
                continue
            sub = clasificar_administradora(adm)
            if sub is None:
                admins_no_clas.add(adm)
                continue

            periodo = str(row[col_per]).strip() if pd.notna(row[col_per]) else ""
            if not periodo or len(periodo) < 6:
                continue
            ano_str = periodo[:4]
            mes_str = periodo[-2:]
            if not ano_str.isdigit() or not mes_str.isdigit():
                continue
            ano = int(ano_str)
            mes = int(mes_str)
            if ano != resumen.ano_gravable or not (1 <= mes <= 12):
                continue

            aporte = self._a_float(row[col_apt])
            ibc = self._a_float(row[col_ibc]) if col_ibc else 0.0
            fecha = str(row[col_fec]) if col_fec and pd.notna(row[col_fec]) else ""

            pago = PagoPILA(
                subsistema=sub, administradora=adm,
                periodo_cotizacion=periodo, fecha_pago=fecha,
                aporte_empleador=aporte, ibc=ibc,
            )
            resumen.pagos.append(pago)

            if sub == "Pensión":
                resumen.pension += aporte
            elif sub == "Salud":
                resumen.salud += aporte
            elif sub == "Riesgos":
                resumen.riesgos += aporte

        resumen.administradoras_no_clasificadas = sorted(admins_no_clas)

    def _procesar_parafiscales_detallada(self, ruta: Path, resumen: ResumenPILA) -> None:
        import pandas as pd
        df = pd.read_excel(ruta, sheet_name=self.HOJA_PARAFISCALES_DETALLE)

        col_adm = self._col(df, ["administradora"], excluir=["codigo", "nit"])
        col_per = self._col(df, ["periodo", "cotizacion"])
        col_fec = self._col(df, ["fecha", "pago"], opcional=True)
        col_apt = self._col(df, ["valor", "aporte"], excluir=["total a pagar"])

        if not col_adm or not col_per or not col_apt:
            log.error("Columnas parafiscales no encontradas. Disponibles: %s",
                      list(df.columns))
            return

        for _, row in df.iterrows():
            adm = str(row[col_adm]).strip() if pd.notna(row[col_adm]) else ""
            if not adm:
                continue

            adm_norm = _normalizar(adm)
            if "caja" in adm_norm or "compensacion" in adm_norm or "comfa" in adm_norm or "comfenalco" in adm_norm:
                sub = "Cajas de compensación"
            elif "sena" in adm_norm:
                sub = "SENA"
            elif "icbf" in adm_norm or "bienestar" in adm_norm:
                sub = "ICBF"
            else:
                continue

            periodo = str(row[col_per]).strip() if pd.notna(row[col_per]) else ""
            if not periodo or len(periodo) < 6:
                continue
            ano_str = periodo[:4]
            mes_str = periodo[-2:]
            if not ano_str.isdigit() or not mes_str.isdigit():
                continue
            ano = int(ano_str)
            mes = int(mes_str)
            if ano != resumen.ano_gravable or not (1 <= mes <= 12):
                continue

            aporte = self._a_float(row[col_apt])
            fecha = str(row[col_fec]) if col_fec and pd.notna(row[col_fec]) else ""

            pago = PagoPILA(
                subsistema=sub, administradora=adm,
                periodo_cotizacion=periodo, fecha_pago=fecha,
                aporte_empleador=aporte,
            )
            resumen.pagos.append(pago)

            if sub == "Cajas de compensación":
                resumen.caja += aporte
            elif sub == "SENA":
                resumen.sena += aporte
            elif sub == "ICBF":
                resumen.icbf += aporte

    def _procesar_ss_consolidada(self, ruta: Path, resumen: ResumenPILA) -> None:
        """Fallback. Usa 'Total Aporte obligatorio' (puede inflar con aporte trabajador)."""
        import pandas as pd
        df = pd.read_excel(ruta, sheet_name=self.HOJA_SS_CONSOLIDADO)
        col_sub = self._col(df, ["subsistema"])
        col_per = self._col(df, ["periodo", "cotizacion"])
        col_apt = self._col(df, ["total", "aporte", "obligatorio"])
        if not col_sub or not col_per or not col_apt:
            return

        for _, row in df.iterrows():
            sub = _reparar_encoding(str(row[col_sub]) if pd.notna(row[col_sub]) else "")
            sub_norm = _normalizar(sub)
            if "pension" in sub_norm:
                clase = "Pensión"
            elif "salud" in sub_norm:
                clase = "Salud"
            elif "riesgos" in sub_norm:
                clase = "Riesgos"
            else:
                continue

            periodo = str(row[col_per]).strip() if pd.notna(row[col_per]) else ""
            if not periodo or len(periodo) < 6:
                continue
            try:
                ano = int(periodo[:4]); mes = int(periodo[-2:])
            except ValueError:
                continue
            if ano != resumen.ano_gravable or not (1 <= mes <= 12):
                continue

            aporte = self._a_float(row[col_apt])
            pago = PagoPILA(subsistema=clase, administradora="(consolidado)",
                            periodo_cotizacion=periodo, fecha_pago="",
                            aporte_empleador=aporte)
            resumen.pagos.append(pago)
            if clase == "Pensión": resumen.pension += aporte
            elif clase == "Salud": resumen.salud += aporte
            elif clase == "Riesgos": resumen.riesgos += aporte

    def _procesar_parafiscales_consolidada(self, ruta: Path, resumen: ResumenPILA) -> None:
        import pandas as pd
        df = pd.read_excel(ruta, sheet_name=self.HOJA_PARAFISCALES_CONSOLIDADO)
        col_sub = self._col(df, ["subsistema"])
        col_per = self._col(df, ["periodo", "cotizacion"])
        col_apt = self._col(df, ["valor", "aporte"])
        if not col_sub or not col_per or not col_apt:
            return

        for _, row in df.iterrows():
            sub = _reparar_encoding(str(row[col_sub]) if pd.notna(row[col_sub]) else "")
            sub_norm = _normalizar(sub)
            if "caja" in sub_norm or "compensacion" in sub_norm:
                clase = "Cajas de compensación"
            elif "sena" in sub_norm:
                clase = "SENA"
            elif "icbf" in sub_norm:
                clase = "ICBF"
            else:
                continue

            periodo = str(row[col_per]).strip() if pd.notna(row[col_per]) else ""
            if not periodo or len(periodo) < 6:
                continue
            try:
                ano = int(periodo[:4]); mes = int(periodo[-2:])
            except ValueError:
                continue
            if ano != resumen.ano_gravable or not (1 <= mes <= 12):
                continue

            aporte = self._a_float(row[col_apt])
            pago = PagoPILA(subsistema=clase, administradora="(consolidado)",
                            periodo_cotizacion=periodo, fecha_pago="",
                            aporte_empleador=aporte)
            resumen.pagos.append(pago)
            if clase == "Cajas de compensación": resumen.caja += aporte
            elif clase == "SENA": resumen.sena += aporte
            elif clase == "ICBF": resumen.icbf += aporte

    def _col(self, df, claves, excluir=None, opcional=False):
        excluir = excluir or []
        excl_norm = [_normalizar(e) for e in excluir]
        claves_norm = [_normalizar(k) for k in claves]
        for col in df.columns:
            col_norm = _normalizar(str(col))
            if all(k in col_norm for k in claves_norm):
                if any(e in col_norm for e in excl_norm):
                    continue
                return col
        return None

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
            s = str(v).replace(",", "").replace(" ", "").replace("$", "")
            return float(s)
        except (ValueError, TypeError):
            return 0.0


# ============================================================
# NÓMINA DESDE BALANCE (Cas. 33)
# ============================================================

def calcular_nomina_desde_balance(balance) -> dict:
    """Suma cuentas 5105xx, 5205xx, 7205xx, 7305xx hasta dígitos 5-6 ≤ 39."""
    PREFIJOS = {
        "admin": ("5105", 39),
        "ventas": ("5205", 39),
        "costos_72": ("7205", 39),
        "costos_73": ("7305", 39),
    }
    out = {"admin": 0.0, "ventas": 0.0, "costos_72": 0.0, "costos_73": 0.0,
           "total": 0.0, "detalle": []}
    todos = balance.cuentas.keys()
    for codigo, cta in balance.cuentas.items():
        c = codigo.strip()
        if not _es_cuenta_hoja(c, todos):
            continue
        for tipo, (inicio, max_subgrupo) in PREFIJOS.items():
            if c.startswith(inicio) and len(c) >= 6:
                try:
                    digitos_5_6 = int(c[4:6])
                    if 0 <= digitos_5_6 <= max_subgrupo:
                        v = cta.saldo_nuevo
                        if abs(v) > 0.005:
                            out[tipo] += v
                            out["detalle"].append((c, cta.nombre, v))
                except ValueError:
                    pass
    out["total"] = out["admin"] + out["ventas"] + out["costos_72"] + out["costos_73"]
    return out


# ============================================================
# VALIDACIÓN
# ============================================================

def validar_pila_vs_balance(resumen_pila: ResumenPILA, nomina_balance: dict) -> dict:
    out = {"cuadra": True, "alertas": [], "info": []}
    base_implicita = resumen_pila.pension / 0.12 if resumen_pila.pension else 0
    nomina_total = nomina_balance.get("admin", 0) + nomina_balance.get("ventas", 0)

    if nomina_total > 0 and base_implicita > 0:
        diff_pct = abs(base_implicita - nomina_total) / nomina_total
        if diff_pct > 0.40:
            out["cuadra"] = False
            out["alertas"].append(
                f"⚠️ Base implícita PILA (${base_implicita:,.0f}) vs "
                f"nómina balance (${nomina_total:,.0f}) difiere {diff_pct*100:.0f}%."
            )
        else:
            out["info"].append(
                f"✓ Base implícita PILA cuadra dentro del 40% (diff {diff_pct*100:.0f}%)"
            )

    if resumen_pila.salud == 0 and resumen_pila.pension > 0:
        out["info"].append(
            "ℹ️ Salud en cero: empresa exonerada por Ley 1819/2016. "
            "Solo el trabajador paga su 4% (descontado de nómina)."
        )
    if resumen_pila.sena == 0 and resumen_pila.icbf == 0 and resumen_pila.caja > 0:
        out["info"].append(
            "ℹ️ SENA e ICBF en cero: empresa exonerada. Solo Caja al 4%."
        )

    return out


# ============================================================
# UTILIDADES
# ============================================================

def _normalizar(s: str) -> str:
    if s is None:
        return ""
    s = str(s)
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.lower().strip().replace("\n", " ").replace("  ", " ")


def _reparar_encoding(s: str) -> str:
    if not s:
        return s
    return (
        s.replace("Ã³", "ó").replace("Ã±", "ñ").replace("Ã©", "é")
         .replace("Ã­", "í").replace("Ãº", "ú").replace("Ã¡", "á")
         .replace("Ã‰", "É").replace("Ã“", "Ó").replace("Ã‘", "Ñ")
    )


def _es_cuenta_hoja(codigo: str, todos_los_codigos) -> bool:
    for otro in todos_los_codigos:
        if len(otro) > len(codigo) and otro.startswith(codigo):
            return False
    return True
