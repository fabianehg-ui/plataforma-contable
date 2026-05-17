"""
core/procesadores/lector_captura_dian.py

Lee el JSON generado por la extensión Chrome "DIAN Capturador" que contiene:
  - meta: configuración (fechas, tipos, etc.)
  - documentos: array con metadata completa de cada documento (CUFE, NIT, monto, etc.)
  - xmls: dict {cufe: <ZIP base64-encoded>} — cada ZIP contiene .xml + .pdf
  - fallidos: trackIds con error
  - log: histórico de la captura

FORMATO DEL XML EN EL JSON:
    Los XMLs vienen como base64. Al decodificar obtienes un ZIP. Dentro del ZIP
    hay un .xml y un .pdf con el mismo CUFE como nombre.

EXPONE:
    cargar_captura(ruta) -> dict          : carga el JSON
    iter_xmls(captura) -> iter[(cufe, xml_str, pdf_bytes)] : itera todos los XMLs
    obtener_xml(captura, cufe) -> str     : un XML específico
    generar_zip_xmls(captura) -> bytes    : reconstruye un ZIP "plano" con todos los XMLs
    filtrar_por_prefijo(captura, prefijo) -> dict
    filtrar_por_tipo(captura, tipo_code)  -> dict
"""
from __future__ import annotations

import base64
import io
import json
import zipfile
from pathlib import Path
from typing import Iterator, Optional, Union


def cargar_captura(ruta_o_bytes: Union[str, Path, bytes]) -> dict:
    """
    Carga el JSON de captura DIAN.

    Args:
        ruta_o_bytes: ruta al archivo .json o bytes ya leídos.

    Returns:
        dict con keys: meta, documentos, xmls, fallidos, log.
    """
    if isinstance(ruta_o_bytes, (str, Path)):
        with open(ruta_o_bytes, encoding="utf-8") as f:
            return json.load(f)
    elif isinstance(ruta_o_bytes, bytes):
        return json.loads(ruta_o_bytes.decode("utf-8"))
    elif isinstance(ruta_o_bytes, dict):
        return ruta_o_bytes  # ya está cargado
    else:
        raise TypeError(f"Tipo no soportado: {type(ruta_o_bytes)}")


def _decodificar_xml_b64(xml_b64: str) -> tuple[Optional[str], Optional[bytes]]:
    """
    Decodifica un XML base64 → (xml_str, pdf_bytes).
    El base64 viene de un ZIP que contiene un .xml y un .pdf.

    Returns:
        (xml_str, pdf_bytes) o (None, None) si falla.
    """
    try:
        zip_bytes = base64.b64decode(xml_b64)
        xml_str = None
        pdf_bytes = None
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for name in zf.namelist():
                if name.lower().endswith(".xml"):
                    xml_str = zf.read(name).decode("utf-8", errors="ignore")
                elif name.lower().endswith(".pdf"):
                    pdf_bytes = zf.read(name)
        return xml_str, pdf_bytes
    except Exception:
        return None, None


def iter_xmls(captura: dict) -> Iterator[tuple[str, str, Optional[bytes]]]:
    """
    Itera todos los XMLs decodificados.

    Yields:
        (cufe, xml_str, pdf_bytes_o_None)
    """
    xmls = captura.get("xmls", {})
    for cufe, b64 in xmls.items():
        xml_str, pdf_bytes = _decodificar_xml_b64(b64)
        if xml_str:
            yield cufe, xml_str, pdf_bytes


def obtener_xml(captura: dict, cufe: str) -> Optional[str]:
    """Devuelve el XML decodificado de un CUFE, o None si no existe."""
    xmls = captura.get("xmls", {})
    if cufe not in xmls:
        return None
    xml_str, _ = _decodificar_xml_b64(xmls[cufe])
    return xml_str


def generar_zip_xmls(captura: dict, incluir_pdf: bool = False) -> bytes:
    """
    Genera un ZIP plano (sin anidación) con todos los XMLs decodificados.
    Útil para que el usuario descargue los XMLs como archivos sueltos.

    Args:
        captura: dict del JSON cargado.
        incluir_pdf: si True, incluye también los PDFs.

    Returns:
        bytes del ZIP.
    """
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for cufe, xml_str, pdf_bytes in iter_xmls(captura):
            zf.writestr(f"{cufe}.xml", xml_str.encode("utf-8"))
            if incluir_pdf and pdf_bytes:
                zf.writestr(f"{cufe}.pdf", pdf_bytes)
    return out.getvalue()


def filtrar_por_prefijo(captura: dict, prefijo: str) -> list[dict]:
    """Devuelve documentos cuya 'Serie' coincide con el prefijo."""
    pref_u = prefijo.upper().strip()
    return [
        d for d in captura.get("documentos", [])
        if str(d.get("Serie", "")).upper().strip() == pref_u
    ]


def filtrar_por_tipo(captura: dict, type_id: str) -> list[dict]:
    """Filtra por DocumentTypeId: '01' factura, '05' DSE, '91' NC, '92' ND."""
    return [
        d for d in captura.get("documentos", [])
        if str(d.get("DocumentTypeId", "")) == str(type_id)
    ]


def filtrar_por_grupo(captura: dict, grupo: str, nit_empresa: str) -> list[dict]:
    """
    Filtra por 'emitido' (NIT empresa = SenderCode) o 'recibido' (NIT empresa = ReceiverCode).
    """
    import re
    nit_n = re.sub(r"\D", "", str(nit_empresa))
    g = grupo.lower()
    out = []
    for d in captura.get("documentos", []):
        sender = re.sub(r"\D", "", str(d.get("SenderCode", "")))
        receiver = re.sub(r"\D", "", str(d.get("ReceiverCode", "")))
        if g == "emitido" and sender == nit_n:
            out.append(d)
        elif g == "recibido" and receiver == nit_n:
            out.append(d)
    return out


def resumen_captura(captura: dict) -> dict:
    """Resumen útil para mostrar en UI."""
    docs = captura.get("documentos", [])
    xmls = captura.get("xmls", {})
    fallidos = captura.get("fallidos", [])
    meta = captura.get("meta", {})

    from collections import Counter
    tipos = Counter(d.get("DocumentTypeName", "?") for d in docs)
    prefijos = Counter(d.get("Serie", "?") for d in docs)

    return {
        "fecha_desde": meta.get("fechaDesde", ""),
        "fecha_hasta": meta.get("fechaHasta", ""),
        "total_documentos": len(docs),
        "xmls_descargados": len(xmls),
        "fallidos": len(fallidos),
        "tipos": dict(tipos),
        "prefijos_top10": dict(prefijos.most_common(10)),
        "tiempo_captura_seg": meta.get("tiempoSegundos", 0),
        "version_extension": meta.get("version", ""),
    }


def buscar_cufes_de_prefijo(captura: dict, prefijo: str) -> list[str]:
    """Devuelve los CUFEs (campo 'Id') de documentos con el prefijo dado."""
    pref_u = prefijo.upper().strip()
    out = []
    for d in captura.get("documentos", []):
        if str(d.get("Serie", "")).upper().strip() == pref_u:
            # El CUFE/key del XML está en el campo 'Id' del documento.
            # DocumentKey suele estar vacío; Identifier es otro hash distinto.
            cufe = d.get("Id")
            if cufe:
                out.append(cufe)
    return out
