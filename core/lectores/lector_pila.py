"""
Lector de PDF de planilla PILA - versión web.

Adaptado de lector_pila.py del .exe original.

Cambios vs versión escritorio:
    - Recibe file-like objects (BytesIO) o bytes, en vez de rutas de archivo
    - No depende de configuración global
    - Agrega utilidades para convertir el resultado a DataFrame y Excel

El formato del PDF es el generado por Enlace Operativo (SuAporte):
    - Encabezado con datos del aportante
    - Tabla por empleado con: cédula, nombre, IBC, aportes por concepto
    - Totales agregados

Requiere: pdfplumber
"""
from __future__ import annotations
import io
import re
from typing import TYPE_CHECKING, Union

import pandas as pd

if TYPE_CHECKING:
    # Solo se importa para chequeo de tipos; no afecta runtime ni
    # requiere streamlit instalado para que el módulo se pueda importar.
    from streamlit.runtime.uploaded_file_manager import UploadedFile  # noqa: F401


def extraer_pila(archivo_pdf: Union[bytes, io.BytesIO, "UploadedFile"]) -> dict:
    """Extrae los datos del PDF de planilla PILA.

    Args:
        archivo_pdf: puede ser bytes, BytesIO, o un UploadedFile de Streamlit.

    Returns:
        dict con periodo_cotizacion, numero_planilla, razon_social, nit_empresa,
        empleados (lista), totales (dict).

    Raises:
        ImportError si pdfplumber no está instalado.
        ValueError si el PDF está vacío o no se puede parsear.
    """
    try:
        import pdfplumber
    except ImportError as e:
        raise ImportError(
            "Falta pdfplumber. Agrégalo a requirements.txt: "
            "pdfplumber>=0.10.0"
        ) from e

    # Normalizar entrada a BytesIO
    if isinstance(archivo_pdf, (bytes, bytearray)):
        stream = io.BytesIO(bytes(archivo_pdf))
    elif hasattr(archivo_pdf, "read"):
        data = archivo_pdf.read()
        if hasattr(archivo_pdf, "seek"):
            archivo_pdf.seek(0)
        stream = io.BytesIO(data)
    else:
        raise TypeError(f"Tipo de archivo no soportado: {type(archivo_pdf)}")

    texto_completo = ""
    with pdfplumber.open(stream) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            texto_completo += t + "\n"

    if not texto_completo.strip():
        raise ValueError("El PDF no contiene texto extraíble")

    resultado = {
        "periodo_cotizacion": _extraer_campo(
            texto_completo,
            r"Periodo\s*Cotizaci[oó]n[:\s]+([^\n]+?)(?=\s{2}|\n|Periodo)",
        ),
        "periodo_servicio": _extraer_campo(
            texto_completo, r"Periodo\s*Servicio[:\s]+([^\n]+)"
        ),
        "numero_planilla": _extraer_campo(
            texto_completo, r"N[uú]mero\s*Planilla[:\s]+(\d+)"
        ),
        "razon_social": _extraer_campo(
            texto_completo,
            r"Raz[oó]n\s*Social\s+([A-ZÁÉÍÓÚÑ][^\n]*?)(?=\s{2,}|\n|Direcci)",
        ),
        "nit_empresa": "",
        "empleados": _extraer_empleados(texto_completo),
        "totales": _extraer_totales(texto_completo),
    }

    # Extraer NIT del documento (viene tipo "NI900473959")
    m = re.search(r"NI(\d{9,11})", texto_completo)
    if m:
        resultado["nit_empresa"] = m.group(1)

    return resultado


# ============================================================
# Helpers de parseo (copiados del original)
# ============================================================

def _extraer_campo(texto: str, patron: str) -> str:
    m = re.search(patron, texto, re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _limpiar_valor(s) -> int:
    """Convierte '$ 3.680.679' o '3,680,679' a int 3680679."""
    if not s:
        return 0
    s = str(s).replace("$", "").replace(".", "").replace(",", "").strip()
    try:
        return int(s)
    except ValueError:
        return 0


def _extraer_empleados(texto: str) -> list:
    empleados = []

    m_inicio = re.search(r"II\.\s*DETALLE\s*DEL\s*APORTANTE", texto, re.IGNORECASE)
    m_fin = re.search(r"III\.\s*TOTALES", texto, re.IGNORECASE)

    if m_inicio and m_fin:
        bloque = texto[m_inicio.end():m_fin.start()]
    else:
        bloque = texto

    por_empleado = {}

    for linea in bloque.split("\n"):
        linea = linea.strip()
        if not linea.startswith("CC "):
            continue

        m = re.match(
            r"CC\s+(\d+)\s+([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s]+?)(?=\s+\d{2}\s+\d{2}\s)",
            linea,
        )
        if not m:
            m = re.match(
                r"CC\s+(\d+)\s+([A-ZÁÉÍÓÚÑ].+?)"
                r"(?=\s+PROTECCION|\s+COLFONDOS|\s+PORVENIR|\s+SKANDIA|\s+\$)",
                linea,
            )
        if not m:
            continue

        cedula = m.group(1).strip()
        nombre = " ".join(m.group(2).split())

        valores = re.findall(r"\$\s*([\d\.,]+)", linea)
        if len(valores) < 4:
            continue

        v = [_limpiar_valor(x) for x in valores]
        while len(v) < 8:
            v.append(0)

        if cedula in por_empleado:
            emp = por_empleado[cedula]
            emp["ibc_pension"] += v[0]
            emp["aporte_pension"] += v[1]
            emp["ibc_salud"] += v[2]
            emp["aporte_salud"] += v[3]
            emp["ibc_riesgos"] += v[4]
            emp["aporte_riesgos"] += v[5]
            emp["ibc_cajas"] += v[6]
            emp["aporte_cajas"] += v[7]
        else:
            por_empleado[cedula] = {
                "cedula": cedula,
                "nombre": nombre,
                "ibc_pension": v[0],
                "aporte_pension": v[1],
                "ibc_salud": v[2],
                "aporte_salud": v[3],
                "ibc_riesgos": v[4],
                "aporte_riesgos": v[5],
                "ibc_cajas": v[6],
                "aporte_cajas": v[7],
            }

    empleados = list(por_empleado.values())
    return empleados


def _extraer_totales(texto: str) -> dict:
    m_inicio = re.search(r"III\.?\s*TOTALES", texto, re.IGNORECASE)
    if not m_inicio:
        return {}

    bloque = texto[m_inicio.end():]
    valores = re.findall(r"\$\s*([\d\.,]+)", bloque)
    v = [_limpiar_valor(x) for x in valores]

    def get(i, default=0):
        return v[i] if i < len(v) else default

    return {
        "ibc_pension": get(0),
        "ibc_salud": get(1),
        "ibc_riesgos": get(2),
        "ibc_cajas": get(3),
        "aporte_pension": get(4),
        "aporte_fsp": get(5),
        "aporte_fss": get(6),
        "aporte_salud": get(7),
        "aporte_riesgos": get(8),
        "aporte_cajas": get(9),
        "aporte_sena": get(10),
        "aporte_icbf": get(11),
        "aporte_esap": get(12),
        "aporte_mineducacion": get(13),
        "subtotal": get(len(v) - 3) if len(v) >= 3 else 0,
        "total_intereses": get(len(v) - 2) if len(v) >= 2 else 0,
        "total_final": get(len(v) - 1) if len(v) >= 1 else 0,
    }


# ============================================================
# Utilidades específicas para la UI web
# ============================================================

def empleados_a_dataframe(datos_pila: dict) -> pd.DataFrame:
    """Convierte la lista de empleados a DataFrame para visualización."""
    empleados = datos_pila.get("empleados", [])
    if not empleados:
        return pd.DataFrame(columns=[
            "Cédula", "Nombre", "IBC Pensión", "Aporte Pensión",
            "IBC Salud", "Aporte Salud", "IBC Riesgos", "Aporte Riesgos",
            "IBC Cajas", "Aporte Cajas", "Total Empleado",
        ])

    filas = []
    for e in empleados:
        total_empleado = (
            e["aporte_pension"] + e["aporte_salud"]
            + e["aporte_riesgos"] + e["aporte_cajas"]
        )
        filas.append({
            "Cédula": e["cedula"],
            "Nombre": e["nombre"],
            "IBC Pensión": e["ibc_pension"],
            "Aporte Pensión": e["aporte_pension"],
            "IBC Salud": e["ibc_salud"],
            "Aporte Salud": e["aporte_salud"],
            "IBC Riesgos": e["ibc_riesgos"],
            "Aporte Riesgos": e["aporte_riesgos"],
            "IBC Cajas": e["ibc_cajas"],
            "Aporte Cajas": e["aporte_cajas"],
            "Total Empleado": total_empleado,
        })
    return pd.DataFrame(filas)


def totales_a_dataframe(datos_pila: dict) -> pd.DataFrame:
    """Convierte los totales a DataFrame de 2 columnas (Concepto, Valor)."""
    tot = datos_pila.get("totales", {})
    etiquetas = [
        ("IBC Pensión", "ibc_pension"),
        ("IBC Salud", "ibc_salud"),
        ("IBC Riesgos", "ibc_riesgos"),
        ("IBC Cajas", "ibc_cajas"),
        ("Aporte Pensión", "aporte_pension"),
        ("Aporte FSP", "aporte_fsp"),
        ("Aporte FSS", "aporte_fss"),
        ("Aporte Salud (solo 4% empleado)", "aporte_salud"),
        ("Aporte Riesgos (ARL)", "aporte_riesgos"),
        ("Aporte Cajas (CCF)", "aporte_cajas"),
        ("Aporte SENA (exonerado)", "aporte_sena"),
        ("Aporte ICBF (exonerado)", "aporte_icbf"),
        ("Aporte ESAP", "aporte_esap"),
        ("Aporte MinEducación", "aporte_mineducacion"),
        ("Subtotal", "subtotal"),
        ("Total Intereses", "total_intereses"),
        ("TOTAL FINAL", "total_final"),
    ]
    return pd.DataFrame([
        {"Concepto": et, "Valor": tot.get(clave, 0)} for et, clave in etiquetas
    ])


def resumen_texto(datos_pila: dict) -> str:
    """Resumen corto en texto plano (para log)."""
    tot = datos_pila.get("totales", {})
    empleados = datos_pila.get("empleados", [])
    lineas = [
        f"Empresa: {datos_pila.get('razon_social', '')}",
        f"NIT: {datos_pila.get('nit_empresa', '')}",
        f"Periodo cotización: {datos_pila.get('periodo_cotizacion', '')}",
        f"Periodo servicio: {datos_pila.get('periodo_servicio', '')}",
        f"Número planilla: {datos_pila.get('numero_planilla', '')}",
        f"Empleados: {len(empleados)}",
        "",
        "Totales:",
        f"  Aporte Pensión:  ${tot.get('aporte_pension', 0):>15,}",
        f"  Aporte Salud:    ${tot.get('aporte_salud', 0):>15,}",
        f"  Aporte ARL:      ${tot.get('aporte_riesgos', 0):>15,}",
        f"  Aporte Cajas:    ${tot.get('aporte_cajas', 0):>15,}",
        f"  TOTAL FINAL:     ${tot.get('total_final', 0):>15,}",
    ]
    return "\n".join(lineas)


def exportar_excel(datos_pila: dict) -> bytes:
    """Exporta los datos del PILA a un Excel de varias hojas."""
    df_emp = empleados_a_dataframe(datos_pila)
    df_tot = totales_a_dataframe(datos_pila)

    df_resumen = pd.DataFrame([
        {"Campo": "Empresa", "Valor": datos_pila.get("razon_social", "")},
        {"Campo": "NIT", "Valor": datos_pila.get("nit_empresa", "")},
        {"Campo": "Periodo cotización", "Valor": datos_pila.get("periodo_cotizacion", "")},
        {"Campo": "Periodo servicio", "Valor": datos_pila.get("periodo_servicio", "")},
        {"Campo": "Número planilla", "Valor": datos_pila.get("numero_planilla", "")},
        {"Campo": "Empleados", "Valor": len(datos_pila.get("empleados", []))},
    ])

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xl:
        df_resumen.to_excel(xl, sheet_name="Resumen", index=False)
        df_emp.to_excel(xl, sheet_name="Empleados", index=False)
        df_tot.to_excel(xl, sheet_name="Totales", index=False)
    return buf.getvalue()
