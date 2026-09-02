# -*- coding: utf-8 -*-
"""
Lector del "resumen de ventas por punto" (el cuadro NOMBRE | VALOR).

Sirve como fuente de valores para los Certificados de Ventas cuando la
informacion llega:
  - en imagen / pantallazo  -> OCR (tesseract), o
  - en Excel (dos columnas: nombre del punto + valor).

El cuadro trae dos secciones separadas por las filas "TOTAL SANTA LENA" y
"TOTAL MILAGROS"; por eso el mapeo al centro de costo se hace por SECCION
(familia 11xx = Santa Lena / JIPER, familia 12xx = Milagros), no solo por el
nombre.

IMPORTANTE: el OCR puede confundir digitos (1<->4, 6<->8). El resultado SIEMPRE
debe revisarse en una tabla editable antes de generar certificados.
"""
from __future__ import annotations

import io
import re
from typing import Dict, List, Optional

from openpyxl import load_workbook

from core.reportes.ventas_informe import _CATALOGO_CC, _norm_tokens


# ------------------------------------------------------------------ OCR
def ocr_disponible() -> bool:
    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def leer_imagen_texto(img_bytes: bytes) -> str:
    """OCR de la imagen del resumen. Escala la imagen para mejorar los digitos."""
    import pytesseract
    from PIL import Image
    img = Image.open(io.BytesIO(img_bytes)).convert("L")
    w, h = img.size
    factor = 3 if max(w, h) < 1600 else 2
    img = img.resize((w * factor, h * factor))
    return pytesseract.image_to_string(img, lang="spa+eng", config="--psm 6")


# ------------------------------------------------------------------ mapeo por familia
def cc_de_nombre_en_familia(nombre: str, familia: str) -> Optional[str]:
    """Mapea el nombre a un CC dentro de la familia dada ('11' o '12')."""
    toks = _norm_tokens(nombre)
    if not toks:
        return None
    candidatos = []
    for cod, nom_cat in _CATALOGO_CC.items():
        if not cod.startswith(familia):
            continue
        toks_cat = _norm_tokens(nom_cat)
        if toks == toks_cat or toks <= toks_cat or toks_cat <= toks:
            candidatos.append(cod)
    if len(candidatos) == 1:
        return candidatos[0]
    if candidatos:
        return max(candidatos, key=lambda c: len(toks & _norm_tokens(_CATALOGO_CC[c])))
    return None


# ------------------------------------------------------------------ helpers de parseo
_SALTAR = ("TOTAL", "CRECIMIENTO", "VENTAS ACUMULA", "VENTAS ACUMULADAS")


def _solo_numero(s: str) -> Optional[int]:
    digs = re.sub(r"[^\d]", "", s or "")
    return int(digs) if digs else None


def _fila_valida(nombre: str) -> bool:
    u = (nombre or "").strip().upper()
    if not u:
        return False
    for k in _SALTAR:
        if u.startswith(k):
            return False
    if u in ("VENTAS", "DAS", "$"):
        return False
    return True


def _cc_familia_por_seccion(nombre_upper: str, familia_actual: str) -> str:
    """Actualiza la familia segun las filas separadoras."""
    if "TOTAL SANTA" in nombre_upper or ("SANTA LE" in nombre_upper and "TOTAL" in nombre_upper):
        return "12"   # de aqui en adelante: Milagros
    return familia_actual


# ------------------------------------------------------------------ parseo de texto (OCR)
def parsear_texto(texto: str) -> List[Dict]:
    """Devuelve filas [{nombre, familia, cc4, valor}] a partir del texto OCR."""
    filas: List[Dict] = []
    familia = "11"
    detenido = False
    for linea in (texto or "").splitlines():
        up = linea.upper()
        if "TOTAL MILAGROS" in up or "TOTAL DIA" in up:
            detenido = True
        # cambio de seccion
        familia = _cc_familia_por_seccion(up, familia)
        if detenido:
            continue
        if "TOTAL" in up or "CRECIMIENTO" in up:
            continue
        # separar nombre y valor por el signo $
        m = re.match(r"^\s*(.*?)\$\s*([\d.,\s]+)", linea)
        if not m:
            continue
        nombre = re.sub(r"\s+", " ", m.group(1)).strip(" .:-|")
        valor = _solo_numero(m.group(2))
        if not _fila_valida(nombre) or not valor:
            continue
        cc4 = cc_de_nombre_en_familia(nombre, familia) or ""
        filas.append({"nombre": nombre, "familia": familia, "cc4": cc4, "valor": valor})
    return filas


# ------------------------------------------------------------------ parseo de Excel
def parsear_excel(xlsx_bytes: bytes) -> List[Dict]:
    """Lee el resumen desde un Excel de dos columnas (nombre + valor)."""
    wb = load_workbook(io.BytesIO(xlsx_bytes), read_only=True, data_only=True)
    filas: List[Dict] = []
    familia = "11"
    detenido = False
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            celdas = [c for c in row if c is not None]
            if not celdas:
                continue
            # nombre = primera celda de texto; valor = primer numero de la fila
            nombre = ""
            valor = None
            for c in celdas:
                if isinstance(c, str) and not nombre and c.strip():
                    nombre = c.strip()
                elif isinstance(c, (int, float)) and valor is None:
                    valor = int(round(c))
            up = (nombre or "").upper()
            if "TOTAL MILAGROS" in up or "TOTAL DIA" in up:
                detenido = True
            familia = _cc_familia_por_seccion(up, familia)
            if detenido:
                continue
            if not _fila_valida(nombre) or not valor:
                continue
            cc4 = cc_de_nombre_en_familia(nombre, familia) or ""
            filas.append({"nombre": nombre, "familia": familia, "cc4": cc4, "valor": valor})
    return filas


# ------------------------------------------------------------------ API principal
def leer_resumen(archivo_bytes: bytes, nombre_archivo: str = "") -> List[Dict]:
    """Detecta si es imagen o Excel y devuelve las filas [{nombre,familia,cc4,valor}]."""
    ext = (nombre_archivo or "").lower().rsplit(".", 1)[-1]
    if ext in ("xlsx", "xlsm", "xls"):
        return parsear_excel(archivo_bytes)
    if ext in ("png", "jpg", "jpeg", "tif", "tiff", "webp", "bmp"):
        if not ocr_disponible():
            raise RuntimeError(
                "OCR no disponible: el servidor no tiene tesseract instalado.")
        return parsear_texto(leer_imagen_texto(archivo_bytes))
    # sin extension: intentar imagen
    if not ocr_disponible():
        raise RuntimeError("Formato no reconocido y OCR no disponible.")
    return parsear_texto(leer_imagen_texto(archivo_bytes))


def filas_a_ventas(filas: List[Dict], mes_num: int) -> Dict:
    """Convierte filas revisadas en el dict de ventas {(cc4, mes): {'ventas': v}}."""
    out: Dict = {}
    for f in filas:
        cc4 = str(f.get("cc4") or "").strip()
        val = f.get("valor")
        if cc4 and val:
            out[(cc4, int(mes_num))] = {"ventas": float(val), "devol": 0.0}
    return out
