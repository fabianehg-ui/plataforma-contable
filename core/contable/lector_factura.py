"""
core/contable/lector_factura.py

Lectura de facturas para prellenar la Captura de INTEGRAL. Devuelve un dict
NORMALIZADO con los valores que interesan al asiento:

    {
        "formato": "xml" | "pdf" | "imagen",
        "nit": str, "nombre": str, "fecha": "YYYY-MM-DD", "numero": str,
        "base": int, "iva": int,
        "rete_fuente": int, "rete_iva": int, "rete_ica": int,
        "total": int, "moneda": str,
        "confianza": "alta" | "media" | "baja",
        "items": [ {descripcion, base, iva, iva_pct}, ... ],
        "advertencias": [str, ...],
    }

- XML  (UBL DIAN): reusa core/procesadores/procesador_dian_xml.parsear_xml_dian
                   → extracción exacta. confianza = alta.
- PDF  (representación gráfica): texto con pdfplumber + heurística. confianza media/baja.
- Imagen: OCR con pytesseract (si el servidor tiene tesseract) + misma heurística.
"""
from __future__ import annotations

import io
import re
from typing import Optional


# ============================================================
# Utilidades de números y fechas (formato colombiano)
# ============================================================

def _a_int(texto: str) -> int:
    """'1.234.567,89' o '1,234,567.89' → 1234567 (pesos, sin decimales)."""
    if texto is None:
        return 0
    s = str(texto).strip().replace("$", "").replace(" ", "")
    if not s:
        return 0
    # Quitar decimales: el último separador seguido de exactamente 2 dígitos
    s = re.sub(r"[.,](\d{2})$", "", s)
    # El resto de separadores son de miles
    s = s.replace(".", "").replace(",", "")
    m = re.search(r"-?\d+", s)
    return int(m.group()) if m else 0


_MESES = {
    "enero": "01", "febrero": "02", "marzo": "03", "abril": "04", "mayo": "05",
    "junio": "06", "julio": "07", "agosto": "08", "septiembre": "09",
    "setiembre": "09", "octubre": "10", "noviembre": "11", "diciembre": "12",
}


def _norm_fecha(texto: str) -> Optional[str]:
    """Intenta normalizar una fecha a 'YYYY-MM-DD'."""
    if not texto:
        return None
    s = str(texto).strip()
    m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", s)   # YYYY-MM-DD
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.search(r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})", s)   # DD/MM/YYYY
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    m = re.search(r"(\d{1,2})\s+de\s+([a-záéíóú]+)\s+de\s+(\d{4})", s, re.IGNORECASE)
    if m:
        mes = _MESES.get(m.group(2).lower())
        if mes:
            return f"{m.group(3)}-{mes}-{int(m.group(1)):02d}"
    return None


# ============================================================
# Régimen / responsabilidades fiscales del emisor (para sugerir retención)
# ============================================================

_RESP_NOMBRES = {
    "O-13": "Gran contribuyente",
    "O-15": "Autorretenedor",
    "O-23": "Agente de retención IVA",
    "O-47": "Régimen simple (RST)",
    "R-99-PN": "No responsable",
}


def _texto_regimen(reg: dict) -> str:
    partes = []
    if reg["iva"] == "responsable":
        partes.append("Responsable de IVA")
    elif reg["iva"] == "no_responsable":
        partes.append("No responsable de IVA")
    for code, flag in (("O-13", "gran_contribuyente"), ("O-15", "autorretenedor"),
                       ("O-23", "agente_retencion_iva"), ("O-47", "regimen_simple")):
        if reg.get(flag):
            partes.append(_RESP_NOMBRES[code])
    return " · ".join(partes) if partes else "Régimen no detectado"


def _extraer_regimen(xml_bytes: bytes) -> dict:
    """Lee régimen de IVA (48/49) y responsabilidades fiscales (O-13, O-15…)
    del emisor, desde cbc:TaxLevelCode (texto + atributo listName)."""
    reg = {
        "codigo_iva": "", "responsabilidades": [], "iva": "desconocido",
        "gran_contribuyente": False, "autorretenedor": False,
        "agente_retencion_iva": False, "regimen_simple": False, "texto": "",
    }
    try:
        import xml.etree.ElementTree as ET
        from core.procesadores.procesador_dian_xml import _find, _extraer_documento_anidado
        root = ET.fromstring(xml_bytes)
        interno = _extraer_documento_anidado(root)
        if interno is not None:
            root = interno
        tlc = _find(root, "cac:AccountingSupplierParty/cac:Party/"
                          "cac:PartyTaxScheme/cbc:TaxLevelCode")
        if tlc is None:
            return reg
        cod = (tlc.text or "").strip()
        listname = tlc.get("listName", "") or ""
        resp = [c.strip() for c in re.split(r"[;,|]", listname) if c.strip()]
        reg["codigo_iva"] = cod
        reg["responsabilidades"] = resp
        reg["gran_contribuyente"] = "O-13" in resp
        reg["autorretenedor"] = "O-15" in resp
        reg["agente_retencion_iva"] = "O-23" in resp
        reg["regimen_simple"] = "O-47" in resp
        if "48" in cod or "O-48" in resp:
            reg["iva"] = "responsable"
        elif "49" in cod or "R-99-PN" in (resp + [cod]) or "O-49" in resp:
            reg["iva"] = "no_responsable"
        reg["texto"] = _texto_regimen(reg)
    except Exception:
        pass
    return reg


# ============================================================
# XML — reusa el parser UBL entrante existente
# ============================================================

def leer_xml(xml_bytes: bytes, nombre: str = "") -> dict:
    from core.procesadores.procesador_dian_xml import parsear_xml_dian

    doc = parsear_xml_dian(xml_bytes, archivo_origen=nombre)
    numero = f"{(doc.prefijo or '').strip()}{(doc.numero or '').strip()}".strip()
    items = []
    for it in getattr(doc, "items", []) or []:
        items.append({
            "descripcion": getattr(it, "descripcion", ""),
            "base": _a_int(str(getattr(it, "valor_neto", 0))),
            "iva": _a_int(str(getattr(it, "iva_valor", 0))),
            "iva_pct": float(getattr(it, "iva_porcentaje", 0) or 0),
        })
    return {
        "formato": "xml",
        "nit": (doc.nit_emisor or "").strip(),
        "nombre": (doc.nombre_emisor or "").strip(),
        "fecha": _norm_fecha(doc.fecha_emision) or (doc.fecha_emision or None),
        "numero": numero,
        "base": _a_int(str(doc.valor_base_gravable)),
        "iva": _a_int(str(doc.iva_total)),
        "rete_fuente": _a_int(str(doc.rete_fuente)),
        "rete_iva": _a_int(str(doc.rete_iva)),
        "rete_ica": _a_int(str(doc.rete_ica)),
        "total": _a_int(str(doc.valor_total)),
        "moneda": doc.moneda or "COP",
        "confianza": "alta",
        "regimen": _extraer_regimen(xml_bytes),
        "bases_por_tarifa": _bases_por_tarifa(
            items, _a_int(str(doc.valor_base_gravable)), _a_int(str(doc.iva_total))),
        "items": items,
        "advertencias": list(getattr(doc, "advertencias", []) or []),
    }


def _bases_por_tarifa(items: list[dict], base_total: int, iva_total: int) -> list[dict]:
    """Agrupa las líneas por tarifa de IVA → [{tarifa, base, iva}] (desc).

    Sirve para separar bases cuando la factura trae tarifas diferenciales
    (19% + 5% + excluido). Si no hay detalle de líneas, devuelve un solo
    bucket a partir de los totales de cabecera.
    """
    buckets: dict = {}
    for it in items or []:
        tar = round(float(it.get("iva_pct") or 0), 2)
        b = buckets.setdefault(tar, {"tarifa": tar, "base": 0, "iva": 0})
        b["base"] += int(it.get("base") or 0)
        b["iva"] += int(it.get("iva") or 0)
    filas = [b for b in buckets.values() if b["base"] or b["iva"]]
    if not filas:
        tar = round(iva_total / base_total * 100, 2) if base_total else 0
        filas = [{"tarifa": tar, "base": base_total, "iva": iva_total}]
    filas.sort(key=lambda x: -x["tarifa"])
    return filas


# ============================================================
# Heurística sobre TEXTO (PDF y OCR)
# ============================================================

# Un monto: dígitos con separadores de miles (1.234.567[,89]) o 4+ dígitos seguidos.
_MONTO_RE = re.compile(r"\$?\s*(\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{2})?|\d{4,}(?:[.,]\d{2})?)")


def _buscar_monto(texto: str, etiquetas: list[str]) -> int:
    """Monto asociado a una etiqueta: toma el ÚLTIMO monto de la línea que la
    contiene, ignorando porcentajes (p.ej. el '19%' de 'IVA 19%: 380.000')."""
    for et in etiquetas:
        etre = re.compile(et, re.IGNORECASE)
        for linea in texto.splitlines():
            if not etre.search(linea):
                continue
            candidatos = []
            for m in _MONTO_RE.finditer(linea):
                if linea[m.end():m.end() + 1] == "%":   # es una tarifa, no un valor
                    continue
                val = _a_int(m.group(1))
                if val:
                    candidatos.append(val)
            if candidatos:
                return candidatos[-1]
    return 0


def _buscar_nit(texto: str) -> str:
    # "NIT: 900.123.456-7" o "NIT 900123456"
    m = re.search(r"NIT[.:\s]*([\d][\d.\s]{5,15}\d)(?:\s*-?\s*(\d))?", texto, re.IGNORECASE)
    if m:
        nit = re.sub(r"\D", "", m.group(1))
        return nit
    return ""


def _buscar_numero(texto: str) -> str:
    m = re.search(r"(?:factura|documento|fact\.?|no\.?|n[°º])[^\w]{0,4}"
                  r"([A-Z]{0,6}[-\s]?\d{1,12})", texto, re.IGNORECASE)
    if m:
        return re.sub(r"\s", "", m.group(1)).strip("-")
    return ""


def _buscar_fecha(texto: str) -> Optional[str]:
    for linea in texto.splitlines():
        if re.search(r"fecha", linea, re.IGNORECASE):
            f = _norm_fecha(linea)
            if f:
                return f
    return _norm_fecha(texto)


def _buscar_nombre(texto: str) -> str:
    """Primera línea 'razonable' (mayúsculas / con SAS/LTDA) como razón social."""
    for linea in texto.splitlines()[:15]:
        l = linea.strip()
        if len(l) < 4:
            continue
        if re.search(r"\b(S\.?A\.?S|LTDA|S\.?A\.?|E\.?U|SAS|S EN C)\b", l, re.IGNORECASE):
            return l[:120]
    return ""


def extraer_de_texto(texto: str, formato: str) -> dict:
    """Extrae los campos de una factura desde texto plano (PDF/OCR)."""
    texto = texto or ""
    base = _buscar_monto(texto, ["subtotal", "base gravable", "base grav", "valor bruto"])
    iva = _buscar_monto(texto, ["iva", "i\\.v\\.a", "impuesto"])
    total = _buscar_monto(texto, ["total a pagar", "valor total", "total factura",
                                  "total neto", "total"])
    rfte = _buscar_monto(texto, ["reten.*fuente", "rete.?fuente", "retefuente"])
    riva = _buscar_monto(texto, ["reteiva", "reten.*iva"])
    rica = _buscar_monto(texto, ["reteica", "reten.*ica", "rete.?ica"])

    advert = []
    if not total and not base:
        advert.append("No se detectaron montos; revisa/edita manualmente.")
    # Reconciliación: total ≈ base + IVA − retenciones. Si la base detectada no
    # calza (típico cuando el 'total' ya trae el IVA incluido), se recalcula.
    if total and iva:
        esperado = base + iva - rfte - riva - rica
        if abs(esperado - total) > max(2, int(total * 0.02)):
            base_rec = total - iva + rfte + riva + rica
            if base_rec > 0:
                base = base_rec
                advert.append("Base recalculada desde total e IVA; verifica.")

    confianza = "media" if (total or base) else "baja"
    if formato == "imagen":
        confianza = "baja"  # OCR siempre requiere revisión

    base_final = base or (total - iva if total and iva else total)
    tar = round(iva / base_final * 100, 2) if base_final else 0
    return {
        "formato": formato,
        "nit": _buscar_nit(texto),
        "nombre": _buscar_nombre(texto),
        "fecha": _buscar_fecha(texto),
        "numero": _buscar_numero(texto),
        "base": base_final,
        "iva": iva,
        "rete_fuente": rfte, "rete_iva": riva, "rete_ica": rica,
        "total": total,
        "moneda": "COP",
        "confianza": confianza,
        "regimen": None,
        "bases_por_tarifa": [{"tarifa": tar, "base": base_final, "iva": iva}] if base_final else [],
        "items": [],
        "advertencias": advert,
    }


# ============================================================
# PDF
# ============================================================

def leer_pdf(pdf_bytes: bytes, nombre: str = "") -> dict:
    try:
        import pdfplumber
    except ImportError:
        raise RuntimeError("pdfplumber no está instalado (requirements.txt lo incluye).")
    partes = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            partes.append(page.extract_text() or "")
    texto = "\n".join(partes)
    if not texto.strip():
        res = extraer_de_texto("", "pdf")
        res["advertencias"].append(
            "El PDF no tiene texto extraíble (parece escaneado). "
            "Súbelo como imagen para intentar OCR, o digita los valores.")
        res["confianza"] = "baja"
        return res
    return extraer_de_texto(texto, "pdf")


# ============================================================
# Imagen (OCR) — mejor esfuerzo, requiere tesseract en el servidor
# ============================================================

def ocr_disponible() -> bool:
    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def leer_imagen(img_bytes: bytes, nombre: str = "") -> dict:
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        raise RuntimeError(
            "OCR no disponible: falta pytesseract/Pillow. Agrega 'pytesseract' y "
            "'Pillow' a requirements.txt y el binario 'tesseract-ocr' al servidor.")
    try:
        pytesseract.get_tesseract_version()
    except Exception:
        raise RuntimeError(
            "OCR no disponible: el binario 'tesseract' no está instalado en el "
            "servidor. (En Docker: apt-get install -y tesseract-ocr tesseract-ocr-spa.)")
    img = Image.open(io.BytesIO(img_bytes))
    texto = pytesseract.image_to_string(img, lang="spa+eng")
    return extraer_de_texto(texto, "imagen")


# ============================================================
# ZIP (paquete de facturas: XML de la DIAN, o PDFs)
# ============================================================

def leer_zip(zip_bytes: bytes, nombre: str = "") -> list[dict]:
    """Extrae y lee todas las facturas de un ZIP (incluye sub-ZIPs del
    bookmarklet DIAN). Prioriza XML; si no hay, intenta PDFs."""
    out: list[dict] = []
    try:
        from core.procesadores.procesador_dian_xml import extraer_xmls_de_zip_maestro
        for nom, xb in extraer_xmls_de_zip_maestro(zip_bytes):
            try:
                out.append(leer_xml(xb, nom))
            except Exception:
                pass
    except Exception:
        pass
    if not out:
        try:
            import zipfile
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
                for nom in z.namelist():
                    low = nom.lower()
                    if low.endswith(".xml") and not nom.split("/")[-1].startswith("_"):
                        try:
                            out.append(leer_xml(z.read(nom), nom))
                        except Exception:
                            pass
                if not out:
                    for nom in z.namelist():
                        if nom.lower().endswith(".pdf"):
                            try:
                                out.append(leer_pdf(z.read(nom), nom))
                            except Exception:
                                pass
        except Exception:
            pass
    return out


# ============================================================
# Dispatcher
# ============================================================

def _es_zip(nombre: str, cab: bytes) -> bool:
    return (nombre or "").lower().endswith(".zip") or cab[:2] == b"PK"


def leer_facturas(nombre: str, contenido: bytes) -> list[dict]:
    """Lee una o varias facturas. ZIP → lista con todas; otro → lista de 1."""
    cab = contenido[:8] if contenido else b""
    if _es_zip(nombre, cab):
        return leer_zip(contenido, nombre)
    return [leer_factura(nombre, contenido)]


def leer_factura(nombre: str, contenido: bytes) -> dict:
    """Detecta el formato por extensión/contenido y lee UNA factura."""
    n = (nombre or "").lower()
    cab = contenido[:200].lstrip() if contenido else b""
    if _es_zip(nombre, contenido[:8] if contenido else b""):
        facs = leer_zip(contenido, nombre)
        if facs:
            return facs[0]
        raise RuntimeError("El ZIP no contiene facturas legibles (XML/PDF).")
    es_xml = n.endswith(".xml") or cab[:5].lower() == b"<?xml" or cab[:1] == b"<"
    if es_xml:
        return leer_xml(contenido, nombre)
    if n.endswith(".pdf") or cab[:4] == b"%PDF":
        return leer_pdf(contenido, nombre)
    if n.endswith((".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp")):
        return leer_imagen(contenido, nombre)
    # último recurso: intentar XML, luego PDF
    try:
        return leer_xml(contenido, nombre)
    except Exception:
        return leer_pdf(contenido, nombre)
