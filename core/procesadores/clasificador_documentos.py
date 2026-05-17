"""
core/procesadores/clasificador_documentos.py

Clasificador de documentos electrónicos DIAN.

Dado un set de documentos (cada uno = dict con 'raw_listing' = fila del API DIAN
y 'parsed_xml' = dict del parser XML), los clasifica en:

  - VENTAS POS         (NIT empresa = emisor, prefijo de sucursal POS)
  - VENTAS STL         (NIT empresa = emisor, prefijo STL = mayoristas)
  - VENTAS OTRAS       (NIT empresa = emisor, prefijo no reconocido)
  - NC POS / NC STL    (notas crédito asociadas a ventas)
  - ND emitidas        (notas débito emitidas)
  - DS emitidos        (doc soporte que JIPER emite a no obligados)
  - COMPRAS            (NIT empresa = receptor)
  - NC COMPRAS         (notas crédito recibidas de proveedores)
  - ND COMPRAS         (notas débito recibidas de proveedores)
  - DS RECIBIDOS       (raro: empresa recibe doc soporte)

La clasificación primaria es SENDER vs RECEIVER (¿lo emití o lo recibí?).
La sub-clasificación de ventas es por prefijo del folio.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# Categorías de salida
CAT_VENTA_POS    = "VENTA_POS"
CAT_VENTA_STL    = "VENTA_STL"
CAT_VENTA_OTRA   = "VENTA_OTRA"
CAT_NC_POS       = "NC_POS"
CAT_NC_STL       = "NC_STL"
CAT_NC_OTRA      = "NC_OTRA"
CAT_ND_EMITIDA   = "ND_EMITIDA"
CAT_DS_EMITIDO   = "DS_EMITIDO"
CAT_COMPRA       = "COMPRA"
CAT_NC_COMPRA    = "NC_COMPRA"
CAT_ND_COMPRA    = "ND_COMPRA"
CAT_DS_RECIBIDO  = "DS_RECIBIDO"
CAT_DESCONOCIDO  = "DESCONOCIDO"

CATEGORIAS = [
    CAT_VENTA_POS, CAT_VENTA_STL, CAT_VENTA_OTRA,
    CAT_NC_POS,    CAT_NC_STL,    CAT_NC_OTRA,
    CAT_ND_EMITIDA, CAT_DS_EMITIDO,
    CAT_COMPRA, CAT_NC_COMPRA, CAT_ND_COMPRA, CAT_DS_RECIBIDO,
    CAT_DESCONOCIDO,
]

# Prefijos especiales que NO son POS aunque sean ventas
PREFIJOS_STL_VENTAS = {"STL"}

# Las NCs de ventas STL salen con folios "NC2xxx" — el "NC" es el prefijo literal
# pero el patrón "NC seguido del dígito 2" las distingue de NCs POS (que tienen
# prefijo NCI, NCOVI, etc).
RX_FOLIO_NC_STL = re.compile(r"^NC2\d", re.IGNORECASE)


def _normalizar_nit(nit) -> str:
    """
    Limpia un NIT a solo dígitos.

    Si el NIT viene con dígito de verificación separado por guión (formato
    estándar Colombia: "901038325-7"), se elimina la parte del DV.
    Si viene como "9010383257" o "901038325" sin guión, se deja tal cual.
    """
    if nit is None:
        return ""
    s = str(nit).strip()
    if "-" in s:
        s = s.split("-", 1)[0]
    return re.sub(r"\D", "", s)


def _extraer_prefijo(folio: str) -> str:
    """De 'STL15808' o 'NCVI100' extrae 'STL' o 'NCVI'."""
    if not folio:
        return ""
    m = re.match(r"^([A-Z_]+)\d", str(folio).upper().strip())
    return m.group(1) if m else ""


@dataclass
class DocumentoClasificado:
    """Un documento DIAN ya clasificado y normalizado."""
    track_id: str
    folio: str            # SerieAndNumber, ej "STL15808"
    prefijo: str          # "STL", "MLA", etc
    tipo_dian: str        # '01' / '91' / '92' / '05'
    fecha: str            # YYYY-MM-DD
    nit_emisor: str
    nombre_emisor: str
    nit_receptor: str
    nombre_receptor: str
    valor_total: float
    categoria: str        # una de CATEGORIAS
    cc_sucursal: Optional[str] = None        # si pudo mapear prefijo→CC
    nombre_sucursal: Optional[str] = None
    raw_listing: Optional[dict] = None       # fila completa del API listing
    parsed_xml: Optional[dict] = None        # dict de parser_xml_stl.parsear_xml_dian


@dataclass
class ResultadoClasificacion:
    """Resultado agregado de clasificar una tanda de documentos."""
    documentos: List[DocumentoClasificado] = field(default_factory=list)
    por_categoria: Dict[str, List[DocumentoClasificado]] = field(default_factory=dict)
    prefijos_no_mapeados: Dict[str, int] = field(default_factory=dict)  # prefijo → conteo
    advertencias: List[str] = field(default_factory=list)

    def conteos(self) -> Dict[str, int]:
        return {cat: len(self.por_categoria.get(cat, [])) for cat in CATEGORIAS if self.por_categoria.get(cat)}

    def totales(self) -> Dict[str, float]:
        return {
            cat: sum(d.valor_total for d in docs)
            for cat, docs in self.por_categoria.items()
        }


def construir_mapeo_prefijos(sucursales: List[dict]) -> Dict[str, dict]:
    """
    A partir de datos_punto.json (lista de sucursales con 'prefijo_token' y
    'prefijo_token_nc') construye el dict de mapeo:

        { 'IND': {'cc': '001101', 'nombre': 'Indiana', 'tipo': 'venta'},
          'NCI': {'cc': '001101', 'nombre': 'Indiana', 'tipo': 'nc'},
          ... }

    Sucursales sin prefijo_token configurado se ignoran (no rompen).
    """
    mapeo = {}
    for s in sucursales:
        cc = s.get("cc", "")
        nombre = s.get("nombre_reporte") or s.get("sede") or cc
        pref_v = (s.get("prefijo_token") or "").strip().upper()
        pref_nc = (s.get("prefijo_token_nc") or "").strip().upper()
        if pref_v:
            mapeo[pref_v] = {"cc": cc, "nombre": nombre, "tipo": "venta"}
        if pref_nc:
            mapeo[pref_nc] = {"cc": cc, "nombre": nombre, "tipo": "nc"}
    return mapeo


def clasificar_documentos(
    documentos_raw: List[dict],
    nit_empresa: str,
    mapeo_prefijos: Optional[Dict[str, dict]] = None,
    parsed_xmls: Optional[Dict[str, dict]] = None,
) -> ResultadoClasificacion:
    """
    Clasifica una lista de documentos DIAN.

    Args:
        documentos_raw: lista de filas del API listing (lo que devuelve
            cliente_token_dian.listar_documentos).
        nit_empresa: NIT propio de la empresa (sin dígito de verificación).
        mapeo_prefijos: dict prefijo→{cc,nombre,tipo}. Opcional. Si falta,
            todos los prefijos quedan como "no mapeados" y van a VENTA_OTRA.
        parsed_xmls: dict trackId → dict del parser XML. Opcional. Si falta,
            la clasificación usa solo el listing.

    Returns:
        ResultadoClasificacion con docs categorizados.
    """
    nit_empresa = _normalizar_nit(nit_empresa)
    if not nit_empresa:
        raise ValueError("nit_empresa es obligatorio para clasificar.")

    mapeo_prefijos = mapeo_prefijos or {}
    parsed_xmls = parsed_xmls or {}

    resultado = ResultadoClasificacion()
    for cat in CATEGORIAS:
        resultado.por_categoria[cat] = []

    for fila in documentos_raw:
        # Datos básicos del listing
        track_id = fila.get("Id") or fila.get("DocumentKey") or fila.get("TrackId") or ""
        folio    = str(fila.get("SerieAndNumber") or "").upper().strip()
        prefijo  = _extraer_prefijo(folio)
        tipo     = str(fila.get("DocumentTypeId") or "").strip()
        emisor   = _normalizar_nit(fila.get("SenderCode"))
        receptor = _normalizar_nit(fila.get("ReceiverCode"))
        valor    = float(fila.get("TotalAmount") or 0)
        fecha_ms = _epoch_ms_de_fecha_dian(fila.get("EmissionDate"))
        fecha    = _ms_a_fecha_iso(fecha_ms) if fecha_ms else ""

        # Resolver sucursal por prefijo
        sucursal_info = mapeo_prefijos.get(prefijo)
        cc_sucursal  = sucursal_info["cc"] if sucursal_info else None
        nombre_sucursal = sucursal_info["nombre"] if sucursal_info else None

        # ── Decisión de categoría ────────────────────────────
        es_emisor = (emisor == nit_empresa)
        es_receptor = (receptor == nit_empresa)

        if es_emisor:
            # VENTAS / NC / ND / DS emitidos
            if tipo == "01":
                if prefijo in PREFIJOS_STL_VENTAS:
                    categoria = CAT_VENTA_STL
                elif sucursal_info and sucursal_info["tipo"] == "venta":
                    categoria = CAT_VENTA_POS
                else:
                    categoria = CAT_VENTA_OTRA
            elif tipo == "91":
                if RX_FOLIO_NC_STL.match(folio):
                    categoria = CAT_NC_STL
                elif sucursal_info and sucursal_info["tipo"] == "nc":
                    categoria = CAT_NC_POS
                else:
                    categoria = CAT_NC_OTRA
            elif tipo == "92":
                categoria = CAT_ND_EMITIDA
            elif tipo == "05":
                categoria = CAT_DS_EMITIDO
            else:
                categoria = CAT_DESCONOCIDO
        elif es_receptor:
            # COMPRAS / NC / ND / DS recibidos
            if tipo == "01":
                categoria = CAT_COMPRA
            elif tipo == "91":
                categoria = CAT_NC_COMPRA
            elif tipo == "92":
                categoria = CAT_ND_COMPRA
            elif tipo == "05":
                categoria = CAT_DS_RECIBIDO
            else:
                categoria = CAT_DESCONOCIDO
        else:
            # Ni emisor ni receptor: raro. Puede ser un doc compartido por ej.
            categoria = CAT_DESCONOCIDO
            resultado.advertencias.append(
                f"Doc {folio} (trackId {track_id[:12]}...) no tiene al NIT {nit_empresa} "
                f"ni como emisor ni receptor (emisor={emisor}, receptor={receptor})."
            )

        # Si es venta POS pero sin mapeo, anotar el prefijo para que el usuario
        # pueda configurar el mapeo después.
        if categoria == CAT_VENTA_OTRA and prefijo:
            resultado.prefijos_no_mapeados[prefijo] = (
                resultado.prefijos_no_mapeados.get(prefijo, 0) + 1
            )

        doc = DocumentoClasificado(
            track_id=track_id,
            folio=folio,
            prefijo=prefijo,
            tipo_dian=tipo,
            fecha=fecha,
            nit_emisor=emisor,
            nombre_emisor=str(fila.get("SenderName") or "").strip(),
            nit_receptor=receptor,
            nombre_receptor=str(fila.get("ReceiverName") or "").strip(),
            valor_total=valor,
            categoria=categoria,
            cc_sucursal=cc_sucursal,
            nombre_sucursal=nombre_sucursal,
            raw_listing=fila,
            parsed_xml=parsed_xmls.get(track_id),
        )
        resultado.documentos.append(doc)
        resultado.por_categoria[categoria].append(doc)

    return resultado


# ── Helpers de fechas ────────────────────────────────────────

def _epoch_ms_de_fecha_dian(s) -> Optional[int]:
    if not s:
        return None
    m = re.search(r"/Date\((\d+)\)", str(s))
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _ms_a_fecha_iso(ms: int) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
