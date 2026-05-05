"""
Importador de Certificados de Retención en la Fuente.

Procesa el ZIP típico del contador que contiene:
  - PDFs de certificados individuales (uno por retenedor o por mes)
  - Excel consolidado "LISTADO Y VALOR CERTIFICADOS...xlsx" con la conciliación
    manual contra balance que prepara el contador
  - Subcarpeta RETEIVA/ con certificados de retención de IVA (NO va al F-110)

FASE 1 (este módulo):
  - Lee el Excel consolidado (fuente principal de valores y conciliación)
  - Inventaría los PDFs (no los parsea, solo cuenta y agrupa por proveedor)
  - Audita cruzando NITs del Excel con nombres de PDFs
  - Auto-clasifica retenciones sin PUC asignada (Bancolombia, Silla Tres, etc.)
  - Calcula 3 cifras para Cas. 106: contable, certificados-Excel, conciliado

FASE 2 (próximo sprint, fuera de este módulo):
  - Parser PDF por formato de retenedor
  - Validación valor-por-valor PDF vs Excel
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import logging
import re
import unicodedata
import zipfile

log = logging.getLogger(__name__)


# ============================================================
# AUTO-CLASIFICACIÓN POR CONCEPTO
# ============================================================

# Cuando el contador no asignó cuenta PUC, intentamos auto-clasificar
# por palabra clave en la columna "Concepto" del Excel.
AUTO_CLASIFICACION = {
    "SERVICIOS": "195502",       # Retención servicios 4% (la más común)
    "COMPRAS": "195505",          # Retención compras 2.5%
    "ARRENDAMIENTO": "195502",    # Servicios 4% por defecto
    "ARREND MUEBLE": "195502",
    "ARREND INMUEBLE": "195502",
    "HONORARIOS": "195501",       # Aunque no aparece en este balance, dejarlo
    "INTERESES": "195504",        # Servicios 1%
    "RENDIMIENTOS": "195507",     # Rendimientos financieros 7%
    "RENDIMIENTOS FINANCIEROS": "195507",
}


# ============================================================
# MODELO DE DATOS
# ============================================================

@dataclass
class CertificadoRetencion:
    """Una línea individual del Excel de certificados."""
    nit_retenedor: str
    nombre_retenedor: str
    base_retencion: float
    valor_retencion: float
    concepto: str                       # SERVICIOS, COMPRAS, etc.
    cuenta_puc: Optional[str] = None    # 195501, 195502, etc.
    cuenta_puc_origen: str = "Excel"    # "Excel" | "Auto-clasificado" | "Sin clasificar"
    # Datos de conciliación (si el contador los puso en el Excel)
    saldo_contable: Optional[float] = None
    total_certificado: Optional[float] = None
    diferencia: Optional[float] = None
    accion: Optional[str] = None        # "subir" | "bajar" | None

    @property
    def cas_destino(self) -> int:
        """Cas. 105 si es autorretención (195519), Cas. 106 si es retenido (195515)."""
        if self.cuenta_puc and self.cuenta_puc.startswith("195519"):
            return 105
        return 106


@dataclass
class InventarioPDF:
    """Resumen de los PDFs encontrados en el ZIP (sin parsear contenido)."""
    nombre_archivo: str
    tamano_bytes: int
    es_reteiva: bool = False           # En subcarpeta RETEIVA/
    proveedor_inferido: str = ""        # Heurística por nombre de archivo
    nit_inferido: str = ""              # NIT en el nombre, si lo hay


@dataclass
class ResumenCertificados:
    """Resultado completo de la importación de certificados."""

    # Lista de certificados leídos del Excel
    certificados: list[CertificadoRetencion] = field(default_factory=list)

    # Inventario de PDFs
    pdfs: list[InventarioPDF] = field(default_factory=list)
    pdfs_reteiva: list[InventarioPDF] = field(default_factory=list)
    excel_encontrado: bool = False
    excel_nombre: str = ""

    # Auditoría cruzada
    nits_en_excel: set[str] = field(default_factory=set)
    nits_en_pdfs: set[str] = field(default_factory=set)
    nits_solo_pdf: set[str] = field(default_factory=set)      # PDFs sin entrada en Excel
    nits_solo_excel: set[str] = field(default_factory=set)    # Excel sin PDF de respaldo

    # Errores y advertencias
    errores: list[str] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)

    # Totales calculados
    total_excel: float = 0.0           # Suma de todos los valor_retencion del Excel
    total_excel_conciliado: float = 0.0  # Suma de "Total_Cert" del Excel (con ajustes)
    total_autorretencion: float = 0.0    # Cuentas 195519 del Excel (Cas. 105)
    total_retenciones: float = 0.0       # Cuentas 195515 del Excel (Cas. 106)

    # Sumas por cuenta PUC (para conciliar contra balance)
    por_cuenta_puc: dict[str, float] = field(default_factory=dict)

    def resumen_texto(self) -> str:
        lineas = [
            f"Certificados procesados:",
            f"  - PDFs (retención fuente): {len(self.pdfs)}",
            f"  - PDFs (reteIVA, no F-110): {len(self.pdfs_reteiva)}",
            f"  - Excel encontrado: {'sí' if self.excel_encontrado else 'NO'}",
            f"  - Filas válidas en Excel: {len(self.certificados)}",
            "",
            f"Totales según Excel:",
            f"  - Cas. 105 (autorretenciones): ${self.total_autorretencion:,.0f}",
            f"  - Cas. 106 (retenciones recibidas): ${self.total_retenciones:,.0f}",
        ]
        if self.advertencias:
            lineas.append("")
            lineas.append("Advertencias:")
            for a in self.advertencias[:5]:
                lineas.append(f"  ⚠️ {a}")
        return "\n".join(lineas)


# ============================================================
# IMPORTADOR
# ============================================================

class ImportadorCertificadosZIP:
    """
    Lee un ZIP con certificados de retención.

    Espera estructura típica:
        CERTIFICADOS/
            *.pdf                            # Certificados individuales
            LISTADO Y VALOR CERTIFICADOS *.xlsx  # Excel consolidado del contador
            RETEIVA/                         # Subcarpeta (no va al F-110)
                *.pdf
    """

    PATRON_EXCEL_LISTADO = re.compile(
        r"LISTADO.*VALOR.*CERTIFICADOS.*\.xlsx?$",
        re.IGNORECASE
    )
    # Detectar NIT en nombres de archivo (formato 9 dígitos con o sin guion)
    PATRON_NIT = re.compile(r"\b(\d{9})\b")

    def importar(self, ruta_zip: str | Path) -> ResumenCertificados:
        ruta_zip = Path(ruta_zip)
        if not ruta_zip.exists():
            raise FileNotFoundError(f"ZIP no encontrado: {ruta_zip}")

        resumen = ResumenCertificados()

        # 1. Inspeccionar ZIP e inventariar archivos
        self._inventariar_zip(ruta_zip, resumen)

        # 2. Si hay Excel, parsearlo
        if resumen.excel_encontrado:
            try:
                self._parsear_excel(ruta_zip, resumen)
            except Exception as e:
                log.exception("Error parseando Excel del contador")
                resumen.errores.append(f"Error leyendo Excel: {e}")

        # 3. Auditoría cruzada NIT Excel vs PDFs
        self._auditar_cruzada(resumen)

        # 4. Calcular totales
        self._calcular_totales(resumen)

        return resumen

    def _inventariar_zip(self, ruta_zip: Path, resumen: ResumenCertificados) -> None:
        """Recorre el ZIP y clasifica archivos sin extraer contenido."""
        with zipfile.ZipFile(ruta_zip, "r") as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                # Normalizar el path: algunos ZIPs traen carpeta raíz "CERTIFICADOS/"
                nombre_completo = info.filename
                nombre = Path(nombre_completo).name
                ruta_relativa = nombre_completo.replace("\\", "/")

                # Ignorar archivos del sistema
                if nombre.startswith(".") or nombre.lower() in ("thumbs.db", ".ds_store"):
                    continue

                ext = nombre.lower().rsplit(".", 1)[-1] if "." in nombre else ""

                # Excel del contador
                if ext in ("xlsx", "xls") and self.PATRON_EXCEL_LISTADO.search(nombre):
                    resumen.excel_encontrado = True
                    resumen.excel_nombre = nombre
                    continue

                # PDFs
                if ext != "pdf":
                    continue

                es_reteiva = "RETEIVA" in ruta_relativa.upper() or "/RETEIVA/" in ruta_relativa.upper()
                inv = InventarioPDF(
                    nombre_archivo=nombre,
                    tamano_bytes=info.file_size,
                    es_reteiva=es_reteiva,
                    proveedor_inferido=self._inferir_proveedor(nombre),
                    nit_inferido=self._extraer_nit(nombre),
                )
                if es_reteiva:
                    resumen.pdfs_reteiva.append(inv)
                else:
                    resumen.pdfs.append(inv)
                if inv.nit_inferido:
                    resumen.nits_en_pdfs.add(inv.nit_inferido)

        if not resumen.excel_encontrado:
            resumen.advertencias.append(
                "No se encontró Excel 'LISTADO Y VALOR CERTIFICADOS' en el ZIP. "
                "Sin él no se puede hacer conciliación automática."
            )

    def _parsear_excel(self, ruta_zip: Path, resumen: ResumenCertificados) -> None:
        """Extrae el Excel del ZIP y lo lee."""
        import pandas as pd
        import tempfile

        with zipfile.ZipFile(ruta_zip, "r") as zf:
            # Encontrar el path interno del Excel
            target = None
            for info in zf.infolist():
                nombre = Path(info.filename).name
                if self.PATRON_EXCEL_LISTADO.search(nombre):
                    target = info.filename
                    break
            if not target:
                return

            # Extraer a archivo temporal
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                tmp.write(zf.read(target))
                tmp_path = tmp.name

        # Leer Excel: la estructura típica tiene 3 filas de encabezado
        # Fila 1: nombre empresa
        # Fila 2: vacía
        # Fila 3: vacía
        # Fila 4: encabezados (NIT, RETENEDOR, BASE RETENCION, VALOR RETENCION, CONCEPTO, ...)
        # Fila 5+: datos
        df = pd.read_excel(tmp_path, sheet_name=0, skiprows=3, header=None)

        # Asignar nombres a las columnas conocidas (16 columnas según Quinto)
        nombres_col = [
            "NIT", "Retenedor", "Base", "Valor_Cert", "Concepto", "Cuenta_PUC",
            "_col6", "Concepto_Detalle", "_NIT_v2", "_Retenedor_v2", "_col10",
            "Saldo_Contable", "_col12", "Total_Cert", "Diferencia", "Accion"
        ]
        # Ajustar al número real de columnas que tiene el archivo
        n_cols = min(len(nombres_col), len(df.columns))
        df = df.iloc[:, :n_cols]
        df.columns = nombres_col[:n_cols]

        # Filtrar filas con NIT válido (excluyendo el encabezado "NIT" duplicado)
        df["NIT"] = df["NIT"].astype(str).str.strip()
        df = df[df["NIT"].notna() & (df["NIT"] != "") & (df["NIT"] != "NIT")
                & (df["NIT"] != "nan")]

        for _, row in df.iterrows():
            try:
                nit = self._normalizar_nit(row["NIT"])
                if not nit:
                    continue
                retenedor = str(row["Retenedor"]).strip() if pd.notna(row["Retenedor"]) else ""
                base = self._a_float(row.get("Base"))
                valor = self._a_float(row.get("Valor_Cert"))
                concepto = str(row.get("Concepto", "")).strip().upper() if pd.notna(row.get("Concepto")) else ""

                if valor == 0:
                    continue  # Líneas vacías o totales

                # Cuenta PUC: del Excel si existe, sino auto-clasificar
                cuenta_puc_raw = row.get("Cuenta_PUC")
                cuenta_puc = None
                cuenta_origen = "Sin clasificar"
                if pd.notna(cuenta_puc_raw):
                    try:
                        cuenta_puc = str(int(float(cuenta_puc_raw)))
                        cuenta_origen = "Excel"
                    except (ValueError, TypeError):
                        pass

                if cuenta_puc is None and concepto:
                    # Auto-clasificar
                    for clave, puc in AUTO_CLASIFICACION.items():
                        if clave in concepto:
                            cuenta_puc = puc
                            cuenta_origen = "Auto-clasificado"
                            break

                # Conciliación si está en el Excel
                saldo_cont = self._a_float(row.get("Saldo_Contable"))
                total_cert = self._a_float(row.get("Total_Cert"))
                dif = self._a_float(row.get("Diferencia"))
                accion_raw = row.get("Accion")
                accion = str(accion_raw).strip().lower() if pd.notna(accion_raw) else None
                if accion in ("nan", ""):
                    accion = None

                cert = CertificadoRetencion(
                    nit_retenedor=nit,
                    nombre_retenedor=retenedor,
                    base_retencion=base,
                    valor_retencion=valor,
                    concepto=concepto,
                    cuenta_puc=cuenta_puc,
                    cuenta_puc_origen=cuenta_origen,
                    saldo_contable=saldo_cont if saldo_cont != 0 else None,
                    total_certificado=total_cert if total_cert != 0 else None,
                    diferencia=dif if dif != 0 else None,
                    accion=accion,
                )
                resumen.certificados.append(cert)
                resumen.nits_en_excel.add(nit)
            except Exception as e:
                log.warning("Saltando fila con error: %s", e)

    def _auditar_cruzada(self, resumen: ResumenCertificados) -> None:
        """
        Compara NITs del Excel con NITs encontrados en nombres de PDFs.
        Genera advertencias por inconsistencias.
        """
        if not resumen.excel_encontrado:
            return

        resumen.nits_solo_excel = resumen.nits_en_excel - resumen.nits_en_pdfs
        resumen.nits_solo_pdf = resumen.nits_en_pdfs - resumen.nits_en_excel

        # Filtrar el NIT propio de la empresa (que aparece en muchos PDFs DIAN)
        nit_empresa_candidatos = {n for n in resumen.nits_en_pdfs
                                  if sum(1 for p in resumen.pdfs if p.nit_inferido == n) >= 3}
        if nit_empresa_candidatos:
            # El NIT que más se repite en PDFs es probablemente el de la empresa
            resumen.nits_solo_pdf -= nit_empresa_candidatos

        if resumen.nits_solo_pdf:
            resumen.advertencias.append(
                f"PDFs sin entrada en Excel ({len(resumen.nits_solo_pdf)} NITs): "
                + ", ".join(sorted(resumen.nits_solo_pdf)[:5])
            )
        if resumen.nits_solo_excel:
            resumen.advertencias.append(
                f"Excel sin PDF de respaldo ({len(resumen.nits_solo_excel)} NITs): "
                + ", ".join(sorted(resumen.nits_solo_excel)[:5])
            )

        # Auto-clasificadas: avisar para revisión
        auto_clasif = [c for c in resumen.certificados
                       if c.cuenta_puc_origen == "Auto-clasificado"]
        if auto_clasif:
            resumen.advertencias.append(
                f"{len(auto_clasif)} certificados auto-clasificados "
                f"(verificar cuenta PUC asignada): "
                + ", ".join(sorted({c.nombre_retenedor for c in auto_clasif})[:3])
            )

        sin_clasif = [c for c in resumen.certificados if c.cuenta_puc is None]
        if sin_clasif:
            resumen.advertencias.append(
                f"{len(sin_clasif)} certificados sin cuenta PUC ni concepto reconocible. "
                f"Total: ${sum(c.valor_retencion for c in sin_clasif):,.0f}"
            )

    def _calcular_totales(self, resumen: ResumenCertificados) -> None:
        for c in resumen.certificados:
            resumen.total_excel += c.valor_retencion
            if c.total_certificado:
                resumen.total_excel_conciliado += c.total_certificado
            else:
                # Si no hay total conciliado, usa el certificado original
                resumen.total_excel_conciliado += c.valor_retencion

            if c.cuenta_puc:
                resumen.por_cuenta_puc[c.cuenta_puc] = (
                    resumen.por_cuenta_puc.get(c.cuenta_puc, 0) + c.valor_retencion
                )
                if c.cuenta_puc.startswith("195519"):
                    resumen.total_autorretencion += c.valor_retencion
                elif c.cuenta_puc.startswith("195515") or c.cuenta_puc.startswith("1955"):
                    # Fallback: si la cuenta es 1955xx (sin más detalle), asumimos que es Cas. 106
                    if not c.cuenta_puc.startswith("195519"):
                        resumen.total_retenciones += c.valor_retencion

    # ---------- HELPERS ----------

    def _inferir_proveedor(self, nombre: str) -> str:
        """Heurística: extraer nombre del proveedor del archivo."""
        n = nombre.upper()
        proveedores_conocidos = [
            "BANCOLOMBIA", "ASPAEN", "INTERQUIROFANOS", "CLINICA LAS AMERICAS",
            "CLINICA OFTALMOLOGICA", "FIDUCIARIA", "DIAN",
        ]
        for p in proveedores_conocidos:
            if p in n:
                return p.title()
        # Si no, usar primera palabra
        return nombre.split()[0] if nombre else "Desconocido"

    def _extraer_nit(self, nombre: str) -> str:
        """Busca un NIT (9 dígitos) en el nombre del archivo."""
        m = self.PATRON_NIT.search(nombre)
        if m:
            return m.group(1)
        return ""

    @staticmethod
    def _normalizar_nit(nit_raw) -> str:
        """Convierte NIT a formato consistente (solo dígitos del cuerpo)."""
        if nit_raw is None:
            return ""
        s = str(nit_raw).strip()
        # Quitar guiones y espacios
        s = s.replace("-", "").replace(".", "").replace(" ", "")
        # Quitar prefijo "N" si lo tiene (algunos formatos PILA)
        if s.upper().startswith("N"):
            s = s[1:]
        # Tomar solo dígitos
        s = "".join(c for c in s if c.isdigit())
        # Si es número largo, quitar dígito de verificación
        if len(s) == 10:
            s = s[:9]
        return s if s.isdigit() and len(s) >= 8 else ""

    @staticmethod
    def _a_float(v) -> float:
        if v is None:
            return 0.0
        try:
            import pandas as pd
            if pd.isna(v):
                return 0.0
        except Exception:
            pass
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
# CONCILIACIÓN CON BALANCE
# ============================================================

def conciliar_certificados_vs_balance(
    resumen_certs: ResumenCertificados,
    balance,
) -> dict:
    """
    Compara las sumas de certificados (del Excel) contra los saldos
    contables de las cuentas 195515xx y 195519xx del balance.

    Returns:
        dict con:
          - 'conciliacion_106': lista de filas con cuenta, contable, certificados, dif
          - 'total_106_contable': suma 195515xx del balance
          - 'total_106_certificados': suma según Excel
          - 'total_106_excel_conciliado': suma "Total_Cert" del Excel (lo que el contador propone)
          - 'total_105_contable': suma 195519xx del balance
          - 'total_105_certificados': autorretenciones según Excel
    """
    out = {
        "conciliacion_106": [],
        "conciliacion_105": [],
        "total_106_contable": 0.0,
        "total_106_certificados": 0.0,
        "total_106_excel_conciliado": 0.0,
        "total_105_contable": 0.0,
        "total_105_certificados": 0.0,
    }

    # Recorrer cuentas hoja del balance
    cuentas_106 = {}  # cod_completo (8 dígitos) -> saldo
    cuentas_105 = {}
    for cod, cta in balance.cuentas.items():
        c = cod.strip()
        # Cuentas hoja de 195515xx
        if c.startswith("195515") and len(c) == 8:
            # Verificar que sea hoja
            if not _es_hoja(c, balance.cuentas.keys()):
                continue
            cuentas_106[c] = cta.saldo_nuevo
            out["total_106_contable"] += cta.saldo_nuevo
        elif c.startswith("195519") and len(c) == 8:
            if not _es_hoja(c, balance.cuentas.keys()):
                continue
            cuentas_105[c] = cta.saldo_nuevo
            out["total_105_contable"] += cta.saldo_nuevo

    # Sumas por cuenta PUC desde el Excel (mapean por los primeros 6 dígitos)
    sumas_excel = {}
    for cert in resumen_certs.certificados:
        if not cert.cuenta_puc:
            continue
        # Normalizar a 8 dígitos. El Excel suele tener 6 dígitos (195502, 195505).
        # Las cuentas del balance son 8 dígitos (19551502, 19551505).
        puc = cert.cuenta_puc
        if len(puc) == 6 and puc.startswith("1955"):
            # Convertir 195502 -> 19551502 (insertar el "15" después de 1955)
            puc_8 = puc[:4] + "15" + puc[4:]
        elif len(puc) == 8:
            puc_8 = puc
        else:
            puc_8 = puc
        sumas_excel[puc_8] = sumas_excel.get(puc_8, 0) + cert.valor_retencion
        if puc_8.startswith("195515"):
            out["total_106_certificados"] += cert.valor_retencion
        elif puc_8.startswith("195519"):
            out["total_105_certificados"] += cert.valor_retencion

    out["total_106_excel_conciliado"] = resumen_certs.total_excel_conciliado

    # Construir tabla de conciliación 106
    todas_106 = sorted(set(list(cuentas_106.keys()) + [k for k in sumas_excel if k.startswith("195515")]))
    for cuenta in todas_106:
        contable = cuentas_106.get(cuenta, 0)
        certificado = sumas_excel.get(cuenta, 0)
        out["conciliacion_106"].append({
            "cuenta": cuenta,
            "contable": contable,
            "certificado": certificado,
            "diferencia": contable - certificado,
        })

    todas_105 = sorted(set(list(cuentas_105.keys()) + [k for k in sumas_excel if k.startswith("195519")]))
    for cuenta in todas_105:
        contable = cuentas_105.get(cuenta, 0)
        certificado = sumas_excel.get(cuenta, 0)
        out["conciliacion_105"].append({
            "cuenta": cuenta,
            "contable": contable,
            "certificado": certificado,
            "diferencia": contable - certificado,
        })

    return out


def _es_hoja(codigo: str, todos_los_codigos) -> bool:
    """True si no hay otra cuenta más larga que empiece por este código."""
    for otro in todos_los_codigos:
        if len(otro) > len(codigo) and otro.startswith(codigo):
            return False
    return True
