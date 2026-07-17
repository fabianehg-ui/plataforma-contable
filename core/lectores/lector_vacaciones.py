"""
Lector de PDF de liquidaciones de VACACIONES y LIQUIDACIONES DEFINITIVAS.

Motivación (regla del usuario):
    A las **vacaciones** — cuando NO hacen parte de una liquidación definitiva —
    se les deduce **4% de pensión + 4% de salud** (8% en total) sobre el valor
    de las vacaciones. En una **liquidación definitiva** las vacaciones que se
    pagan NO llevan esa deducción de seguridad social.

Este módulo:
    - Recibe file-like objects (BytesIO) o bytes (igual que lector_pila).
    - Detecta si el documento es una liquidación de VACACIONES o una
      liquidación DEFINITIVA de contrato.
    - Extrae los campos y valores.
    - Para vacaciones (no definitiva) calcula el desglose 4% / 4% de la
      deducción y verifica contra lo que trae el documento.
    - Ofrece utilidades para DataFrame y Excel.

Formato de vacaciones soportado (texto plano extraído con pdfplumber):

    LIQUIDACION DE VACACIONES
    NOMBRE MARIA YORLADIS MORALES RAMOS
    CEDULA 43,101,052
    TIPO DE CONTRATO INDEFINIDO
    FECHA DE INGRESO: 16/02/2017
    PERIODO VACACIONES Periodo del 16 de febrero de 2025 al 15 de febrero de 2026
    FECHA DE DISFRUTE DE VACACIONES 13 5 2026
    FECHA DE REGRESO DE VACACIONES 1 6 2026
    DIAS HABILES DE VACACIONES 15
    DIAS DOMINICALES FESTIVOS DE VACACIONES 3
    TOTAL DIAS 18
    SALARIO MENSUAL 1,750,905
    PROMEDIO COMISIONES Y HORAS EXTRA 1,366,997
    VALOR DIA 103,930.08
    VACACIONES DIAS HABILES 103,930 * 15 1,558,951
    DIAS DOMINICALES FESTIVOS DE VACACIONES 103,930 * 3 311,790
    TOTAL VACACIONES 1,870,741
    MENOS SALUD Y PENSION -149,659
    1,721,083

Para la liquidación DEFINITIVA no hay un formato único garantizado, así que
el parser es best-effort: captura los conceptos con su valor y los totales,
y siempre expone el texto crudo para que el contador pueda revisarlo.

Requiere: pdfplumber
"""
from __future__ import annotations

import io
import re
from typing import TYPE_CHECKING, Union

import pandas as pd

if TYPE_CHECKING:
    from streamlit.runtime.uploaded_file_manager import UploadedFile  # noqa: F401


# Porcentajes de deducción de seguridad social del trabajador sobre vacaciones
PORC_PENSION = 0.04
PORC_SALUD = 0.04
PORC_TOTAL_SS = PORC_PENSION + PORC_SALUD  # 8%

# Cuentas PUC para el asiento del PAGO de vacaciones.
# La cuenta de débito (pago de vacaciones) la definió el usuario: 25301501.
# Las contrapartidas se reutilizan del módulo de nómina (procesador_nomina).
CUENTA_PAGO_VACACIONES = "25301501"   # Db — pago de vacaciones (pasivo)
CTA_DED_PENSION = "25503002"          # Cr — aporte pensión trabajador (4%)
CTA_DED_SALUD = "25500502"            # Cr — deducción salud trabajador (4%)
CTA_NETO = "25050501"                 # Cr — neto a pagar (salarios por pagar)

# Columnas del plano de Contai (idénticas a procesador_nomina.COLUMNAS_PLANO)
COLUMNAS_PLANO = [
    "CUENTA", "COMPROBANTE", "FECHA", "DOCUMENTO", "DOC REFERENCIA",
    "NIT", "DETALLE", "TR", "VALOR", "BASE", "CENTRO DE COSTO",
]


# ============================================================
# Utilidades de números
# ============================================================

def _a_numero(s, entero: bool = True):
    """Convierte un texto de importe a número.

    Soporta formato US (coma miles, punto decimal: '1,870,741.08') y
    formato EU (punto miles, coma decimal: '1.870.741,08').
    """
    if s is None:
        return 0 if entero else 0.0
    s = str(s).replace("$", "").replace(" ", "").strip()
    neg = s.startswith("-")
    s = s.lstrip("-").strip()
    if not s:
        return 0 if entero else 0.0

    tiene_coma = "," in s
    tiene_punto = "." in s

    if tiene_coma and tiene_punto:
        # El separador más a la derecha es el decimal
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")   # EU
        else:
            s = s.replace(",", "")                       # US
    elif tiene_coma:
        partes = s.split(",")
        # Si el último grupo tiene 3 dígitos -> es separador de miles
        if len(partes[-1]) == 3 and len(partes) > 1:
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")
    elif tiene_punto:
        partes = s.split(".")
        if len(partes[-1]) == 3 and len(partes) > 1:
            s = s.replace(".", "")
        # else: se asume decimal, se deja igual

    try:
        val = float(s)
    except ValueError:
        return 0 if entero else 0.0
    if neg:
        val = -val
    return int(round(val)) if entero else val


def _fmt(n) -> str:
    """Formatea 1870741 -> '1.870.741' (estilo colombiano)."""
    try:
        return f"$ {int(round(float(n))):,}".replace(",", ".")
    except (ValueError, TypeError):
        return "—"


# ============================================================
# Normalización de entrada -> texto
# ============================================================

def _pdf_a_texto(archivo_pdf: Union[bytes, io.BytesIO, "UploadedFile"]) -> str:
    try:
        import pdfplumber
    except ImportError as e:
        raise ImportError(
            "Falta pdfplumber. Agrégalo a requirements.txt: pdfplumber>=0.10.0"
        ) from e

    if isinstance(archivo_pdf, (bytes, bytearray)):
        stream = io.BytesIO(bytes(archivo_pdf))
    elif hasattr(archivo_pdf, "read"):
        data = archivo_pdf.read()
        if hasattr(archivo_pdf, "seek"):
            archivo_pdf.seek(0)
        stream = io.BytesIO(data)
    else:
        raise TypeError(f"Tipo de archivo no soportado: {type(archivo_pdf)}")

    texto = ""
    with pdfplumber.open(stream) as pdf:
        for page in pdf.pages:
            texto += (page.extract_text() or "") + "\n"

    if not texto.strip():
        raise ValueError("El PDF no contiene texto extraíble (¿es una imagen escaneada?)")
    return texto


# ============================================================
# Detección del tipo de documento
# ============================================================

def detectar_tipo(texto: str) -> str:
    """Devuelve 'vacaciones' o 'definitiva'."""
    t = texto.upper()
    señales_def = (
        "LIQUIDACION DEFINITIVA", "LIQUIDACIÓN DEFINITIVA",
        "LIQUIDACION FINAL", "LIQUIDACION DE CONTRATO",
        "LIQUIDACION DE PRESTACIONES", "INDEMNIZACION",
        "TERMINACION DEL CONTRATO", "RETIRO DEFINITIVO",
    )
    señales_vac = ("LIQUIDACION DE VACACIONES", "LIQUIDACIÓN DE VACACIONES")

    if any(s in t for s in señales_def):
        return "definitiva"
    if any(s in t for s in señales_vac):
        return "vacaciones"
    # Heurística: si hay cesantías/prima/intereses es una liquidación de prestaciones
    if ("CESANTIAS" in t or "CESANTÍAS" in t) and ("PRIMA" in t or "INTERESES" in t):
        return "definitiva"
    # Por defecto, tratar como vacaciones (documento pequeño)
    return "vacaciones"


# ============================================================
# Parseo VACACIONES
# ============================================================

def _campo(texto: str, patron: str) -> str:
    m = re.search(patron, texto, re.IGNORECASE | re.MULTILINE)
    return m.group(1).strip() if m else ""


def _parsear_vacaciones(texto: str) -> dict:
    d: dict = {"tipo": "vacaciones"}

    d["nombre"] = _campo(texto, r"^NOMBRE\s+(.+)$")
    d["cedula"] = re.sub(r"[.\s,]", "", _campo(texto, r"^C[EÉ]DULA\s+([\d.,\s]+)$"))
    d["tipo_contrato"] = _campo(texto, r"TIPO DE CONTRATO\s+(.+)")
    d["fecha_ingreso"] = _campo(texto, r"FECHA DE INGRESO:?\s+([\d/]+)")
    d["periodo"] = _campo(texto, r"PERIODO VACACIONES\s+(.+)")
    d["fecha_disfrute"] = _campo(texto, r"FECHA DE DISFRUTE DE VACACIONES\s+(.+)")
    d["fecha_regreso"] = _campo(texto, r"FECHA DE REGRESO DE VACACIONES\s+(.+)")

    # Días: anclar SOLO a las líneas-encabezado (número entero solo, sin '*')
    m = re.search(r"^DIAS HABILES DE VACACIONES\s+(\d+)\s*$", texto, re.IGNORECASE | re.MULTILINE)
    d["dias_habiles"] = int(m.group(1)) if m else 0
    m = re.search(r"^DIAS DOMINICALES FESTIVOS DE VACACIONES\s+(\d+)\s*$", texto, re.IGNORECASE | re.MULTILINE)
    d["dias_festivos"] = int(m.group(1)) if m else 0
    m = re.search(r"^TOTAL DIAS\s+(\d+)", texto, re.IGNORECASE | re.MULTILINE)
    d["total_dias"] = int(m.group(1)) if m else (d["dias_habiles"] + d["dias_festivos"])

    d["salario_mensual"] = _a_numero(_campo(texto, r"SALARIO MENSUAL\s+([\d.,]+)"))
    d["promedio_comisiones"] = _a_numero(_campo(texto, r"PROMEDIO COMISIONES Y HORAS EXTRA\s+([\d.,]+)"))
    d["valor_dia"] = _a_numero(_campo(texto, r"VALOR DIA\s+([\d.,]+)"), entero=False)

    # Valores de las dos líneas de detalle (último número de cada línea)
    m = re.search(r"VACACIONES DIAS HABILES\s+[\d.,]+\s*\*\s*\d+\s+([\d.,]+)", texto, re.IGNORECASE)
    d["valor_dias_habiles"] = _a_numero(m.group(1)) if m else 0
    m = re.search(r"DIAS DOMINICALES FESTIVOS DE VACACIONES\s+[\d.,]+\s*\*\s*\d+\s+([\d.,]+)", texto, re.IGNORECASE)
    d["valor_dias_festivos"] = _a_numero(m.group(1)) if m else 0

    d["total_vacaciones"] = _a_numero(_campo(texto, r"TOTAL VACACIONES\s+([\d.,]+)"))
    if not d["total_vacaciones"]:
        d["total_vacaciones"] = d["valor_dias_habiles"] + d["valor_dias_festivos"]

    # Deducción que trae el documento (si la trae)
    m = re.search(r"MENOS\s+SALUD\s+Y\s+PENSION\s+-?\s*([\d.,]+)", texto, re.IGNORECASE)
    d["deduccion_documento"] = _a_numero(m.group(1)) if m else 0

    # Neto IMPRESO en el documento (la cifra suelta tras la deducción).
    # Puede diferir en $1-2 de total-deducción por redondeos internos del Excel origen.
    m = re.search(
        r"MENOS\s+SALUD\s+Y\s+PENSION\s+-?\s*[\d.,]+\s*\n(?:[-\s]*\n)?\s*([\d.,]+)",
        texto, re.IGNORECASE,
    )
    d["neto_documento"] = _a_numero(m.group(1)) if m else (
        d["total_vacaciones"] - d["deduccion_documento"]
    )

    # === Regla del usuario: 4% pensión + 4% salud sobre las vacaciones ===
    base = d["total_vacaciones"]
    d["base_deduccion"] = base
    ded_total = int(round(base * PORC_TOTAL_SS))
    ded_pension = int(round(base * PORC_PENSION))
    ded_salud = ded_total - ded_pension  # para que pensión + salud == 8% exacto
    d["deduccion_pension"] = ded_pension
    d["deduccion_salud"] = ded_salud
    d["deduccion_total_calculada"] = ded_total
    d["neto_calculado"] = base - ded_total

    # ¿Coincide lo calculado con lo del documento? (tolerancia $2 por redondeos)
    d["deduccion_cuadra"] = (
        d["deduccion_documento"] == 0
        or abs(d["deduccion_documento"] - ded_total) <= 2
    )
    return d


# ============================================================
# Parseo LIQUIDACIÓN DEFINITIVA (best-effort)
# ============================================================

# Conceptos típicos de una liquidación definitiva y su etiqueta normalizada
_CONCEPTOS_DEF = [
    (r"CESANT[IÍ]AS?\b(?!.*INTERES)", "Cesantías"),
    (r"INTERES(?:ES)?\s+.*CESANT|INTERESES A LAS CESANT", "Intereses a las cesantías"),
    (r"PRIMA(?:\s+DE\s+SERVICIOS)?", "Prima de servicios"),
    (r"VACACIONES", "Vacaciones"),
    (r"INDEMNIZACI[OÓ]N", "Indemnización"),
    (r"BONIFICACI[OÓ]N", "Bonificación"),
    (r"SALARIO|SUELDO", "Salario / sueldo pendiente"),
    (r"RETROACTIVO", "Retroactivo"),
]


def _parsear_definitiva(texto: str) -> dict:
    d: dict = {"tipo": "definitiva"}

    d["nombre"] = _campo(texto, r"^NOMBRE\s+(.+)$") or _campo(texto, r"NOMBRE:?\s+(.+)")
    d["cedula"] = re.sub(r"[.\s,]", "", _campo(texto, r"C[EÉ]DULA:?\s+([\d.,\s]+)"))
    d["fecha_ingreso"] = _campo(texto, r"FECHA DE INGRESO:?\s+([\d/]+)")
    d["fecha_retiro"] = (
        _campo(texto, r"FECHA DE (?:RETIRO|EGRESO|SALIDA|TERMINACI[OÓ]N):?\s+([\d/]+)")
    )

    conceptos = []
    for linea in texto.split("\n"):
        linea_limpia = linea.strip()
        if not linea_limpia:
            continue
        # Buscar un importe al final de la línea
        m_val = re.search(r"([\-]?\$?\s*[\d][\d.,]*\d)\s*$", linea_limpia)
        if not m_val:
            continue
        valor = _a_numero(m_val.group(1))
        etiqueta_txt = linea_limpia[: m_val.start()].strip()
        if not etiqueta_txt:
            continue
        et_norm = None
        for patron, nombre in _CONCEPTOS_DEF:
            if re.search(patron, etiqueta_txt, re.IGNORECASE):
                et_norm = nombre
                break
        # Detectar deducción / neto / total aunque no sea un "concepto" devengado
        es_deduccion = bool(re.search(r"MENOS|DEDUCC|SALUD\s+Y\s+PENSION|RETENCION", etiqueta_txt, re.IGNORECASE))
        es_total = bool(re.search(r"TOTAL|NETO\s+A\s+PAGAR|NETO", etiqueta_txt, re.IGNORECASE))
        conceptos.append({
            "etiqueta_original": etiqueta_txt,
            "concepto": et_norm or etiqueta_txt.title(),
            "valor": valor,
            "es_deduccion": es_deduccion,
            "es_total": es_total,
        })

    d["conceptos"] = conceptos
    # Valor de vacaciones dentro de la definitiva (informativo; SIN deducción SS)
    vac = next((c["valor"] for c in conceptos
                if re.search(r"VACACIONES", c["etiqueta_original"], re.IGNORECASE)), 0)
    d["valor_vacaciones"] = vac
    d["nota_vacaciones"] = (
        "En liquidación definitiva las vacaciones NO llevan deducción de 4% "
        "pensión ni 4% salud."
    )
    d["texto_crudo"] = texto
    return d


# ============================================================
# API pública
# ============================================================

def leer_documento(archivo_pdf: Union[bytes, io.BytesIO, "UploadedFile"],
                   forzar_tipo: str | None = None) -> dict:
    """Lee un PDF de vacaciones o liquidación definitiva.

    Args:
        archivo_pdf: bytes, BytesIO o UploadedFile de Streamlit.
        forzar_tipo: 'vacaciones' | 'definitiva' para saltar la autodetección.

    Returns:
        dict con los datos extraídos. La clave 'tipo' dice cuál es.
    """
    texto = _pdf_a_texto(archivo_pdf)
    tipo = forzar_tipo or detectar_tipo(texto)
    if tipo == "definitiva":
        datos = _parsear_definitiva(texto)
    else:
        datos = _parsear_vacaciones(texto)
    datos["texto_crudo"] = texto
    return datos


# ============================================================
# Utilidades para la UI web
# ============================================================

def vacaciones_a_dataframe(d: dict) -> pd.DataFrame:
    """Desglose de una liquidación de vacaciones (concepto / valor)."""
    filas = [
        ("Vacaciones días hábiles", d.get("valor_dias_habiles", 0)),
        ("Vacaciones días dominicales/festivos", d.get("valor_dias_festivos", 0)),
        ("TOTAL VACACIONES (base)", d.get("total_vacaciones", 0)),
        ("(−) Deducción pensión 4%", -d.get("deduccion_pension", 0)),
        ("(−) Deducción salud 4%", -d.get("deduccion_salud", 0)),
        ("(−) Total deducción 8%", -d.get("deduccion_total_calculada", 0)),
        ("NETO A PAGAR", d.get("neto_calculado", 0)),
    ]
    return pd.DataFrame(filas, columns=["Concepto", "Valor"])


def encabezado_vacaciones(d: dict) -> pd.DataFrame:
    filas = [
        ("Nombre", d.get("nombre", "")),
        ("Cédula", d.get("cedula", "")),
        ("Tipo de contrato", d.get("tipo_contrato", "")),
        ("Fecha de ingreso", d.get("fecha_ingreso", "")),
        ("Periodo de vacaciones", d.get("periodo", "")),
        ("Fecha de disfrute", d.get("fecha_disfrute", "")),
        ("Fecha de regreso", d.get("fecha_regreso", "")),
        ("Días hábiles", d.get("dias_habiles", 0)),
        ("Días dominicales/festivos", d.get("dias_festivos", 0)),
        ("Total días", d.get("total_dias", 0)),
        ("Salario mensual", d.get("salario_mensual", 0)),
        ("Promedio comisiones/horas extra", d.get("promedio_comisiones", 0)),
        ("Valor día", d.get("valor_dia", 0)),
    ]
    return pd.DataFrame(filas, columns=["Campo", "Valor"])


def definitiva_a_dataframe(d: dict) -> pd.DataFrame:
    conceptos = d.get("conceptos", [])
    if not conceptos:
        return pd.DataFrame(columns=["Concepto", "Valor", "Tipo"])
    filas = []
    for c in conceptos:
        tipo = "Total" if c["es_total"] else ("Deducción" if c["es_deduccion"] else "Devengado")
        filas.append({"Concepto": c["concepto"], "Valor": c["valor"], "Tipo": tipo})
    return pd.DataFrame(filas)


def exportar_excel(d: dict) -> bytes:
    """Exporta el documento leído a un Excel."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xl:
        if d.get("tipo") == "definitiva":
            encabezado_vacaciones(d).head(0)  # noop para mantener import
            df_enc = pd.DataFrame([
                {"Campo": "Nombre", "Valor": d.get("nombre", "")},
                {"Campo": "Cédula", "Valor": d.get("cedula", "")},
                {"Campo": "Fecha de ingreso", "Valor": d.get("fecha_ingreso", "")},
                {"Campo": "Fecha de retiro", "Valor": d.get("fecha_retiro", "")},
                {"Campo": "Tipo documento", "Valor": "Liquidación definitiva"},
            ])
            df_enc.to_excel(xl, sheet_name="Encabezado", index=False)
            definitiva_a_dataframe(d).to_excel(xl, sheet_name="Conceptos", index=False)
        else:
            encabezado_vacaciones(d).to_excel(xl, sheet_name="Encabezado", index=False)
            vacaciones_a_dataframe(d).to_excel(xl, sheet_name="Desglose", index=False)
    return buf.getvalue()


def generar_plano_vacaciones(
    d: dict,
    comprobante: str = "11",
    documento: str = "",
    fecha: str = "",
    doc_referencia: str = "",
    centro_costo: str = "",
    cuenta_pago: str = CUENTA_PAGO_VACACIONES,
) -> pd.DataFrame:
    """Genera el plano contable del PAGO de vacaciones (solo tipo 'vacaciones').

    Asiento (cuadra exacto):
        Db  {cuenta_pago}   TOTAL VACACIONES
          Cr  25503002      pensión 4%
          Cr  25500502      salud 4%
          Cr  25050501      neto a pagar

    Args:
        d: dict devuelto por leer_documento (tipo 'vacaciones').
        comprobante: número de comprobante (por defecto '11', causación nómina).
        documento: consecutivo del documento.
        fecha: fecha en formato MM/DD/AAAA. Si viene vacía se deja en blanco.
        doc_referencia: referencia (por defecto la cédula del empleado).
        centro_costo: centro de costo (por defecto en blanco).
        cuenta_pago: cuenta de débito del pago de vacaciones.

    Returns:
        DataFrame con las columnas de COLUMNAS_PLANO.

    Raises:
        ValueError si el documento no es de tipo vacaciones o no cuadra.
    """
    if d.get("tipo") != "vacaciones":
        raise ValueError(
            "El plano de pago de vacaciones solo aplica a documentos de tipo "
            "'vacaciones', no a liquidaciones definitivas."
        )

    total = int(d.get("total_vacaciones", 0))
    pension = int(d.get("deduccion_pension", 0))
    salud = int(d.get("deduccion_salud", 0))
    neto = total - pension - salud  # garantiza cuadre exacto

    nit = d.get("cedula", "") or ""
    ref = doc_referencia or nit
    detalle = f"PAGO VACACIONES {d.get('nombre', '')}".strip()

    def _fila(cuenta, tr, valor, base=0):
        return {
            "CUENTA": cuenta,
            "COMPROBANTE": str(comprobante),
            "FECHA": fecha,
            "DOCUMENTO": str(documento),
            "DOC REFERENCIA": str(ref),
            "NIT": str(nit),
            "DETALLE": detalle,
            "TR": tr,           # '1' = Db, '2' = Cr
            "VALOR": int(valor),
            "BASE": int(base),
            "CENTRO DE COSTO": centro_costo,
        }

    filas = [
        _fila(cuenta_pago, "1", total),          # Db pago de vacaciones
        _fila(CTA_DED_PENSION, "2", pension, base=total),  # Cr pensión 4%
        _fila(CTA_DED_SALUD, "2", salud, base=total),      # Cr salud 4%
        _fila(CTA_NETO, "2", neto),              # Cr neto a pagar
    ]
    return pd.DataFrame(filas, columns=COLUMNAS_PLANO)


def plano_a_tsv(df: pd.DataFrame, incluir_encabezado: bool = False) -> bytes:
    """Exporta el plano a texto tab-delimitado CRLF (formato Contai).

    IMPORTANTE: por defecto NO incluye encabezado. Contai importa solo
    registros de datos; si se anteponen las filas 'sep=' o los títulos de
    columna ('CUENTA', 'COMPROBANTE', ...), Contai los lee como un registro
    y genera inconsistencias ("la cuenta NO existe en el Plan de Cuentas").

    Usa incluir_encabezado=True solo para abrir el archivo en Excel, NUNCA
    para importar a Contai.
    """
    df_out = df[COLUMNAS_PLANO].copy()
    for col in df_out.columns:
        df_out[col] = df_out[col].astype(str).str.replace("\t", " ", regex=False)

    lineas = []
    if incluir_encabezado:
        lineas.append("sep=\t")
        lineas.append("\t".join(COLUMNAS_PLANO))
    for _, row in df_out.iterrows():
        lineas.append("\t".join(str(row[c]) for c in COLUMNAS_PLANO))
    return ("\r\n".join(lineas) + "\r\n").encode("utf-8")


def resumen_texto(d: dict) -> str:
    if d.get("tipo") == "definitiva":
        lineas = [
            "LIQUIDACIÓN DEFINITIVA",
            f"Nombre: {d.get('nombre','')}",
            f"Cédula: {d.get('cedula','')}",
            f"Fecha ingreso: {d.get('fecha_ingreso','')}  Fecha retiro: {d.get('fecha_retiro','')}",
            f"Vacaciones en la liquidación: {_fmt(d.get('valor_vacaciones',0))} (sin deducción SS)",
        ]
        return "\n".join(lineas)
    lineas = [
        "LIQUIDACIÓN DE VACACIONES",
        f"Nombre: {d.get('nombre','')}",
        f"Cédula: {d.get('cedula','')}",
        f"Días: {d.get('dias_habiles',0)} hábiles + {d.get('dias_festivos',0)} festivos = {d.get('total_dias',0)}",
        f"Total vacaciones (base): {_fmt(d.get('total_vacaciones',0))}",
        f"  (−) Pensión 4%: {_fmt(d.get('deduccion_pension',0))}",
        f"  (−) Salud 4%:   {_fmt(d.get('deduccion_salud',0))}",
        f"  (−) Total 8%:   {_fmt(d.get('deduccion_total_calculada',0))}",
        f"Neto a pagar:     {_fmt(d.get('neto_calculado',0))}",
    ]
    if d.get("deduccion_documento"):
        estado = "cuadra ✔" if d.get("deduccion_cuadra") else "NO cuadra ✖"
        lineas.append(
            f"Deducción en el documento: {_fmt(d.get('deduccion_documento',0))} ({estado})"
        )
    return "\n".join(lineas)
