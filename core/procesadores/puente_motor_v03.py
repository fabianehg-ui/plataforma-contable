"""
Puente entre el procesador legacy y el motor v0.3 — VERSIÓN COMPLETA
====================================================================

Objetivo: que el plano contable salga con TODOS los recursos posibles:
- Cuenta + CC desde mapeo_nits.json (los 126 NITs aprendidos del BP)
- CC desde palabras clave en notas del XML (CTS1.=...)
- CC desde dirección de entrega del XML
- Heurísticas por descripción de item (10 reglas) para PENDIENTES
- Memoria de proveedores aprendida en runtime
- Retenciones (retefuente + reteIVA) calculadas según motor v0.3

Estrategia: monkey-patch al procesador legacy en TRES puntos:
1. Parser (parsear_xml_dian) → para extraer notas y dirección
2. aplicar_mapeo → para usar el motor v0.3
3. ResultadoProcesamiento → para post-procesar y agregar retenciones

USO:
    from core.procesadores import puente_motor_v03
    puente_motor_v03.activar()

    resultados, resumen = procesar_multiples_zips(...)  # ya usa motor v0.3
    resultados = puente_motor_v03.agregar_retenciones_a_resultados(
        resultados, ruta_empresas
    )
"""
from __future__ import annotations
import json
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

# Imports del procesador legacy
from core.procesadores import procesador_dian_xml as legacy
from core.procesadores.procesador_dian_xml import (
    DocumentoDIAN, ItemFactura, LineaPlano, ResultadoProcesamiento, _q
)

# Imports del motor v0.3
from core.procesadores.motor_mapeo_v03 import (
    CatalogoEmpresa,
    resolver_mapeo,
    calcular_retencion_renta,
    calcular_reteiva,
    normalizar_nit,
)


# ─────────────────────────────────────────────────────────────────
# REGLAS HEURÍSTICAS POR DESCRIPCIÓN DEL ITEM
# ─────────────────────────────────────────────────────────────────

REGLAS_HEURISTICAS_PENDIENTES = [
    {
        "nombre": "software_saas",
        "patrones_nombre": ["SIIGO", "MICROSOFT", "GOOGLE", "ZOOM", "ADOBE", "SOFTWARE",
                             "AWS", "AZURE", "DROPBOX"],
        "patrones_desc": ["LICENCIA", "SOFTWARE", "SUSCRIPCION", "SAAS", "SaaS",
                           "MENSUALIDAD SISTEMA", "PLAN MENSUAL", "CRÉDITO", "CREDITO"],
        "cuenta": "519515",
        "concepto": "Software / licenciamiento",
        "concepto_retencion": "software_3_5",
    },
    {
        "nombre": "hardware_computo",
        "patrones_nombre": ["TECH", "TECNOLOG", "COMPUTAC", "JAL"],
        "patrones_desc": ["TABLET", "LAPTOP", "COMPUTAD", "IMPRESORA", "LENOVO", "HP ", "DELL",
                           "MONITOR", "TECLADO", "MOUSE", "ESTUCHE", "VIDRIO TEMPLADO"],
        "cuenta": "152405",
        "concepto": "Equipo de cómputo",
        "concepto_retencion": "compras_2_5",
    },
    {
        "nombre": "aseo_limpieza",
        "patrones_nombre": ["ECOLAB", "QUIMICOS", "LIMPIEZA"],
        "patrones_desc": ["DETERGENTE", "DESINFECT", "JABON", "JABÓN", "CLORO", "ASEO",
                           "LIMPIEZA", "PRO CARE", "SCOUT", "BLANQUEADOR"],
        "cuenta": "519525",
        "concepto": "Productos de aseo y limpieza",
        "concepto_retencion": "compras_2_5",
    },
    {
        "nombre": "uniformes_dotacion",
        "patrones_nombre": ["CONFECCION", "TEXTIL", "UNIFORME"],
        "patrones_desc": ["DELANTAL", "CAMISETA", "JOGGER", "ZAPATO", "UNIFORME", "DOTACION",
                           "DOTACIÓN", "PANTALON", "BUZO"],
        "cuenta": "519520",
        "concepto": "Dotación / uniformes",
        "concepto_retencion": "compras_2_5",
    },
    {
        "nombre": "salud_ocupacional",
        "patrones_nombre": ["CENDIATRA", "SALUD", "MEDIC", "IPS", "CLINIC"],
        "patrones_desc": ["EXAMEN", "OSTEOMUSCULAR", "HEMOGRAMA", "GLUCOSA", "MEDICO",
                           "MÉDICO", "OCUPACIONAL", "LABORATORIO"],
        "cuenta": "519030",
        "concepto": "Salud ocupacional / exámenes médicos",
        "concepto_retencion": "servicios_salud_ips_2",
    },
    {
        "nombre": "publicidad",
        "patrones_nombre": ["PUBLICIDAD", "VISUAL", "MEDIOS", "MARKETING"],
        "patrones_desc": ["AVISO", "VINILO", "ACRILICO", "PLOTTER", "INSTALACION", "INSTALACIÓN",
                           "LOGO", "ROTULO", "RÓTULO", "LED"],
        "cuenta": "513025",
        "concepto": "Publicidad / avisos",
        "concepto_retencion": "compras_2_5",
    },
    {
        "nombre": "insumos_alimenticios",
        "patrones_nombre": ["ALIMENTOS", "PROVEEDORA", "DISTRIBUI"],
        "patrones_desc": ["TRIDENT", "GOMA", "DULCE", "SNACK", "BEBIDA", "ZUMO", "JUGO",
                           "CHICLE", "GALLETA", "CARNE", "POLLO", "VERDURA", "FRUTA",
                           "ARROZ", "PAN ", "QUESO", "LECHE"],
        "cuenta": "14350503",
        "concepto": "Insumos alimenticios",
        "concepto_retencion": "compras_2_5",
    },
    {
        "nombre": "papeleria",
        "patrones_desc": ["LAPICERO", "ESFERO", "PAPEL", "FOLDER", "CARPETA", "AGENDA",
                           "CUADERNO", "MARCADOR", "RESALTADOR"],
        "cuenta": "519530",
        "concepto": "Papelería / útiles oficina",
        "concepto_retencion": "compras_2_5",
    },
    {
        "nombre": "fletes_transporte",
        "patrones_desc": ["FLETE", "TRANSPORTE", "ENVIO", "ENVÍO", "DOMICILIO"],
        "cuenta": "513550",
        "concepto": "Flete / transporte",
        "concepto_retencion": "transporte_carga_1",
    },
    {
        "nombre": "honorarios_genericos",
        "patrones_nombre": ["S.A.S", "LTDA", "CIA", "SAS"],
        "patrones_desc": ["SERVICIO", "ASESOR", "CONSULT"],
        "cuenta": "511005",
        "concepto": "Servicios profesionales",
        "concepto_retencion": "servicios_4",
    },
]


def _detectar_cuenta_heuristica(
    nombre_emisor: str,
    descripciones: list[str],
) -> dict | None:
    """Aplica las reglas heurísticas. Devuelve dict con cuenta/concepto/regla o None."""
    nombre_norm = (nombre_emisor or "").upper()
    descs_norm = " | ".join((d or "").upper() for d in descripciones if d)

    for regla in REGLAS_HEURISTICAS_PENDIENTES:
        patrones_nombre = regla.get("patrones_nombre", [])
        patrones_desc = regla.get("patrones_desc", [])

        match_nombre = (not patrones_nombre) or any(
            p in nombre_norm for p in patrones_nombre
        )
        match_desc = (not patrones_desc) or any(
            p in descs_norm for p in patrones_desc
        )

        if match_nombre and match_desc:
            return {
                "cuenta": regla["cuenta"],
                "concepto": regla["concepto"],
                "concepto_retencion": regla.get("concepto_retencion", "compras_2_5"),
                "regla": regla["nombre"],
            }

    return None


# ─────────────────────────────────────────────────────────────────
# MEMORIA DE PROVEEDORES (aprendizaje runtime)
# ─────────────────────────────────────────────────────────────────
# Cuando la heurística clasifica un NIT, lo guardamos para que el siguiente
# documento del mismo NIT en la sesión vaya directo al match aprendido.

_memoria_proveedores: dict[str, dict] = {}


def memoria_aprender(nit: str, info: dict) -> None:
    """Guarda en memoria que <nit> debe ir a info['cuenta'] / info['concepto_retencion']."""
    nit_norm = normalizar_nit(nit)
    if nit_norm and nit_norm not in _memoria_proveedores:
        _memoria_proveedores[nit_norm] = info


def memoria_consultar(nit: str) -> dict | None:
    return _memoria_proveedores.get(normalizar_nit(nit))


def memoria_clear() -> None:
    _memoria_proveedores.clear()


# ─────────────────────────────────────────────────────────────────
# CACHÉ DE CATÁLOGOS DEL MOTOR v0.3
# ─────────────────────────────────────────────────────────────────
_cache_catalogos: dict[str, CatalogoEmpresa] = {}


def _cargar_catalogo_motor(empresa_id: str, ruta_empresas: Path) -> CatalogoEmpresa | None:
    if empresa_id in _cache_catalogos:
        return _cache_catalogos[empresa_id]
    for p in Path(ruta_empresas).iterdir():
        if not p.is_dir() or p.name.startswith("_"):
            continue
        if p.name.startswith(f"{empresa_id}_") or p.name == empresa_id:
            try:
                cat = CatalogoEmpresa.cargar(p)
                _cache_catalogos[empresa_id] = cat
                return cat
            except Exception:
                return None
    return None


# ─────────────────────────────────────────────────────────────────
# MONKEY-PATCH 1: PARSER (extraer notas y dirección)
# ─────────────────────────────────────────────────────────────────
_parsear_xml_original = legacy.parsear_xml_dian


def _extraer_notas_y_direccion(xml_bytes: bytes) -> tuple[list[str], str, list[list[str]]]:
    """Parsea el XML para extraer:
    - notas a nivel raíz (cbc:Note)
    - dirección de entrega (cac:Delivery / cac:DeliveryAddress)
    - notas por línea (cbc:Note dentro de cada InvoiceLine)
    """
    NS = {
        "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
        "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    }
    notas: list[str] = []
    direccion = ""
    notas_por_linea: list[list[str]] = []

    try:
        root = ET.fromstring(xml_bytes)
    except Exception:
        return ([], "", [])

    # Si es AttachedDocument, extraer doc interno
    tag_root = root.tag.split("}")[-1] if "}" in root.tag else root.tag
    if tag_root == "AttachedDocument":
        for desc in root.iter(f"{{{NS['cbc']}}}Description"):
            if desc.text and ("<Invoice" in desc.text or "<CreditNote" in desc.text
                               or "<DebitNote" in desc.text):
                try:
                    root = ET.fromstring(desc.text)
                except Exception:
                    pass
                break

    # 1) Notas a nivel raíz
    for note in root.findall(f"{{{NS['cbc']}}}Note"):
        if note.text:
            notas.append(note.text.strip())

    # 2) Dirección de entrega - varios paths posibles
    delivery_paths = [
        "cac:Delivery/cac:DeliveryAddress/cac:AddressLine/cbc:Line",
        "cac:Delivery/cac:DeliveryLocation/cac:Address/cac:AddressLine/cbc:Line",
        "cac:Delivery/cac:DeliveryAddress/cbc:StreetName",
        "cac:Delivery/cac:DeliveryLocation/cac:Address/cbc:StreetName",
    ]
    for path in delivery_paths:
        # Convertir path con namespaces
        partes = path.split("/")
        actual = root
        for parte in partes:
            if ":" in parte:
                pre, tag = parte.split(":")
                ns = NS.get(pre, "")
                elem = actual.find(f"{{{ns}}}{tag}")
            else:
                elem = actual.find(parte)
            if elem is None:
                actual = None
                break
            actual = elem
        if actual is not None and actual.text:
            direccion = actual.text.strip()
            break

    # Si no se encontró por paths estándar, buscar AddressLine en cualquier parte
    if not direccion:
        for line_elem in root.iter(f"{{{NS['cbc']}}}Line"):
            txt = (line_elem.text or "").strip()
            if txt and len(txt) > 5:
                direccion = txt
                break

    # 3) Notas por línea (InvoiceLine, CreditNoteLine, DebitNoteLine)
    for line_tag in ("InvoiceLine", "CreditNoteLine", "DebitNoteLine"):
        for line in root.findall(f"{{{NS['cac']}}}{line_tag}"):
            notas_linea = []
            for note in line.findall(f"{{{NS['cbc']}}}Note"):
                if note.text:
                    notas_linea.append(note.text.strip())
            notas_por_linea.append(notas_linea)

    return (notas, direccion, notas_por_linea)


def parsear_xml_dian_extendido(xml_bytes: bytes, archivo_origen: str = "") -> DocumentoDIAN:
    """Parser extendido: usa el legacy y le agrega notas + dirección."""
    doc = _parsear_xml_original(xml_bytes, archivo_origen)
    notas, direccion, notas_por_linea = _extraer_notas_y_direccion(xml_bytes)
    # Inyectar atributos extra (aunque no estén en el dataclass, Python los acepta)
    doc.notas = notas
    doc.direccion_entrega = direccion
    doc.notas_por_linea = notas_por_linea
    return doc


# ─────────────────────────────────────────────────────────────────
# MONKEY-PATCH 2: aplicar_mapeo
# ─────────────────────────────────────────────────────────────────
_aplicar_mapeo_original = legacy.aplicar_mapeo


def aplicar_mapeo_v03(doc: DocumentoDIAN, bundle_empresa: dict) -> DocumentoDIAN:
    """Reemplazo de aplicar_mapeo() que usa el motor v0.3 + memoria + heurísticas."""
    empresa = bundle_empresa.get("empresa", {})
    empresa_id = empresa.get("id") or empresa.get("nit") or ""
    ruta_empresas = bundle_empresa.get("_ruta_empresas") or Path("core/data/empresas")

    catalogo = _cargar_catalogo_motor(str(empresa_id), Path(ruta_empresas))
    if catalogo is None:
        return _aplicar_mapeo_original(doc, bundle_empresa)

    # Recolectar TODA la información disponible del documento
    nit_emi = normalizar_nit(doc.nit_emisor)
    direccion = getattr(doc, "direccion_entrega", "") or ""
    notas_doc = getattr(doc, "notas", []) or []
    notas_por_linea = getattr(doc, "notas_por_linea", []) or []

    # Concatenar TODAS las notas: doc + por línea
    notas_todas: list[str] = list(notas_doc)
    for nl in notas_por_linea:
        notas_todas.extend(nl)

    descripciones = [it.descripcion or "" for it in doc.items]

    # Resolver con motor v0.3
    resolucion = resolver_mapeo(
        catalogo,
        nit_emisor=nit_emi,
        nombre_emisor=doc.nombre_emisor or "",
        direccion_entrega=direccion,
        items_descripcion=" || ".join(descripciones[:30]),
        items_descripciones_lista=descripciones,
        notas_xml=notas_todas,
    )

    # ── Caso 1: NIT catalogado en mapeo_nits.json (NO es pendiente) ─────
    if not resolucion.es_pendiente_revision:
        cuenta_doc = resolucion.cuenta
        cc_doc = resolucion.cc
        concepto_doc = doc.nombre_emisor or ""
        concepto_ret = resolucion.concepto_retencion or "compras_2_5"
        regla = f"MOTOR_V03:{resolucion.fuente_cuenta}/{resolucion.fuente_cc}"

    # ── Caso 2: NIT NO catalogado pero SÍ está en memoria de proveedores ─
    elif (memoria := memoria_consultar(nit_emi)):
        cuenta_doc = memoria["cuenta"]
        cc_doc = "10-10"  # General
        concepto_doc = memoria["concepto"]
        concepto_ret = memoria["concepto_retencion"]
        regla = f"MEMORIA_PROVEEDOR:{memoria['regla']}"
        doc.advertencias.append(
            f"ℹ NIT {nit_emi} resuelto desde memoria de proveedores ({memoria['regla']})"
        )

    # ── Caso 3: PENDIENTE → aplicar reglas heurísticas por descripción ───
    else:
        heuristica = _detectar_cuenta_heuristica(doc.nombre_emisor or "", descripciones)
        if heuristica:
            cuenta_doc = heuristica["cuenta"]
            cc_doc = "10-10"  # General
            concepto_doc = heuristica["concepto"]
            concepto_ret = heuristica["concepto_retencion"]
            regla = f"HEURISTICA:{heuristica['regla']}"
            # Aprender para futuros XMLs en la misma sesión
            memoria_aprender(nit_emi, heuristica)
            doc.advertencias.append(
                f"⚠ NIT no catalogado — cuenta sugerida heurística: "
                f"{heuristica['cuenta']} ({heuristica['concepto']}) - regla: {heuristica['regla']}"
            )
        else:
            cuenta_doc = catalogo.empresa_json.get("cuenta_pendiente_revision", "519095")
            cc_doc = "10-10"  # General
            concepto_doc = "PENDIENTE DE MAPEO"
            concepto_ret = "sin_retencion"
            regla = "FALLBACK_PENDIENTE"
            doc.pendiente_revision = True
            doc.razon_pendiente = (
                f"NIT {nit_emi} ({doc.nombre_emisor}) sin mapeo, sin memoria, "
                f"y descripción no matcheó ninguna regla heurística"
            )
            doc.advertencias.append(doc.razon_pendiente)

    # Refinar cuenta de inventario por tarifa de IVA si aplica
    cuentas_inv_tarifa = catalogo.empresa_json.get("cuentas_inventario_por_tarifa_iva", {})

    for it in doc.items:
        cuenta_item = cuenta_doc
        if cuentas_inv_tarifa and cuenta_doc.startswith("14350"):
            tarifa_key = str(int(it.iva_porcentaje or 0))
            cuenta_por_tarifa = cuentas_inv_tarifa.get(tarifa_key)
            if cuenta_por_tarifa:
                cuenta_item = cuenta_por_tarifa

        it.cuenta = cuenta_item
        it.centro_costo = cc_doc
        it.concepto = concepto_doc
        it.regla_aplicada = regla

    # Guardar info para post-procesado de retenciones
    doc._motor_v03_concepto_retencion = concepto_ret
    doc._motor_v03_regimen_emisor = resolucion.regimen_emisor
    doc._motor_v03_autorretenedor = resolucion.autorretenedor_renta
    doc._motor_v03_resolucion = resolucion

    return doc


# ─────────────────────────────────────────────────────────────────
# ORDENAMIENTO POR FECHA + RENUMERACIÓN DE CONSECUTIVOS
# ─────────────────────────────────────────────────────────────────

def _orden_linea_intra_doc(linea: LineaPlano) -> int:
    """Devuelve un peso para ordenar líneas DENTRO de un mismo documento.
    Orden deseado:
      1. Gasto / inventario / costo
      2. IVA descontable (240810xx, 240813xx, o 24080xxx)
      3. Impuestos al consumo (IBUA/ICUI en 14359xxx; INC en 52159xxx)
      4. Retenciones (retefuente, reteIVA, reteICA)
      5. Proveedor (CxP) al final, como contrapartida que cuadra el doc.
    """
    cta = linea.cuenta or ""
    desc = (linea.descripcion or "").upper()

    # 5. Cuenta del proveedor (CxP) al final
    if cta.startswith("2205"):
        return 90

    # 4. Retenciones de renta/IVA/ICA: 2365xx, 2367xx, 2368xx
    if cta.startswith("2365") or cta.startswith("2367") or cta.startswith("2368"):
        return 80
    if "RETEFUENTE" in desc or "RETEIVA" in desc or "RETEICA" in desc:
        return 80

    # 3. Impuestos al consumo / saludables / bolsas
    #    - IBUA/ICUI (saludables) van al inventario 14359xxx (tras Silla Tres)
    #    - INC y telefónico van al gasto 52159xxx
    #    Ambos casos van DESPUÉS del IVA en el orden de impresión.
    if cta.startswith("14359"):
        return 40   # IBUA / ICUI / saludable / consumo al inventario
    if cta.startswith("521595"):
        return 42   # INC / telefónico / consumo al gasto
    if "IBUA" in desc or "ICUI" in desc or "BEBIDA AZUC" in desc or "ULTRA" in desc:
        return 40
    if "(INC)" in desc or "IMPUESTO AL CONSUMO" in desc or "TELEFONIC" in desc:
        return 42

    # 2. IVA descontable: 240810 (compras) o 240813 (servicios), o 24080x (legacy)
    if cta.startswith("240810") or cta.startswith("240813"):
        return 30
    if cta.startswith("2408"):
        return 30

    # 1. Gasto / inventario / costo (1xxx, 5xxx, 6xxx, 7xxx) — primero
    return 10


def _ordenar_y_renumerar_plano(
    lineas: list[LineaPlano],
    consecutivos_iniciales: dict[str, int] | int | None = None,
) -> list[LineaPlano]:
    """Ordena el plano contable por fecha de emisión ascendente y renumera
    consecutivos para que las facturas más antiguas tengan los números menores.

    Reglas:
    - Las líneas se agrupan por documento (consecutivo + documento_referencia).
    - Los grupos se ordenan por (fecha ASC, consecutivo_original ASC).
    - Se asigna un nuevo consecutivo correlativo por (comprobante, fecha).
      Cada comprobante (3=causación, 7=ND, 12=NC) lleva su propia secuencia
      independiente.

    Parámetro `consecutivos_iniciales` admite tres formas:
    - dict como {"3": 100, "7": 50, "12": 200}: número inicial por comprobante
    - int único (ej. 1000): mismo número inicial para todos los comprobantes
    - None: por defecto cada comprobante arranca en 1
    """
    if not lineas:
        return lineas

    # Normalizar `consecutivos_iniciales` a dict
    if consecutivos_iniciales is None:
        iniciales: dict[str, int] = {}
        default_inicial = 1
    elif isinstance(consecutivos_iniciales, int):
        iniciales = {}
        default_inicial = consecutivos_iniciales
    else:
        # Asegurar claves como str y valores como int
        iniciales = {str(k): int(v) for k, v in consecutivos_iniciales.items()}
        default_inicial = 1

    # Agrupar por (consecutivo_original, documento_referencia)
    grupos: dict[tuple[str, str], list[LineaPlano]] = defaultdict(list)
    for l in lineas:
        grupos[(l.consecutivo, l.documento_referencia)].append(l)

    # Lista de docs con su clave de orden
    docs_ordenables = []
    for (consec_orig, doc_ref), lns in grupos.items():
        primera = lns[0]
        # Intentar parsear consecutivo original como int para orden numérico estable
        try:
            consec_num = int(str(consec_orig).strip())
        except (ValueError, TypeError):
            consec_num = 0
        docs_ordenables.append({
            "fecha": primera.fecha,
            "consec_num": consec_num,
            "consec_orig": consec_orig,
            "doc_ref": doc_ref,
            "comprobante": primera.comprobante,
            "lineas": lns,
        })

    # Ordenar por fecha ASC, luego consecutivo original ASC (estable)
    docs_ordenables.sort(key=lambda d: (d["fecha"], d["consec_num"], d["consec_orig"]))

    # Renumerar: cada COMPROBANTE lleva su propia secuencia, arrancando
    # desde el número que indique el dict (o default_inicial)
    contadores: dict[str, int] = {}
    for d in docs_ordenables:
        comp = str(d["comprobante"])
        if comp not in contadores:
            inicial = iniciales.get(comp, default_inicial)
            contadores[comp] = inicial - 1
        contadores[comp] += 1
        nuevo_consec = str(contadores[comp])
        # Aplicar nuevo consecutivo a todas las líneas del doc
        for l in d["lineas"]:
            l.consecutivo = nuevo_consec
        # Ordenar líneas dentro del doc
        d["lineas"].sort(key=_orden_linea_intra_doc)

    # Devolver lista plana en el nuevo orden
    resultado: list[LineaPlano] = []
    for d in docs_ordenables:
        resultado.extend(d["lineas"])
    return resultado


# ─────────────────────────────────────────────────────────────────
# REMAPEO DE CUENTAS POR PUC DE EMPRESA
# ─────────────────────────────────────────────────────────────────
# El procesador legacy asigna cuentas IVA y de impuestos al consumo
# usando códigos genéricos del PUC (24080201, 24080203, etc.) que NO
# corresponden con el catálogo real de cada empresa. Esta función
# reemplaza esas cuentas por las correctas del PUC, según el contexto
# (compras vs servicios, inventario vs gasto, telefonía vs otros).

# Sufijos que identifican cuentas de inventario en el plano (vienen
# del legacy o del motor v0.3 antes del remapeo).
_PREFIJOS_INVENTARIO = ("1435", "14")

# Listas de palabras clave para identificar telefonía/comunicaciones
_NOMBRES_TELEFONIA = (
    "COLOMBIA MOVIL", "TIGO", "CLARO", "MOVISTAR", "ETB",
    "TELEFONICA", "COMUNICACIONES", "AVANTEL", "WOM",
    "COMCEL", "TELMEX", "UNE EPM", "DIRECTV",
)


def _es_proveedor_telefonia(nombre_emisor: str) -> bool:
    """Detecta si el emisor es una empresa de telecomunicaciones, para
    redirigir el INC al impuesto telefónico."""
    if not nombre_emisor:
        return False
    n = nombre_emisor.upper()
    return any(t in n for t in _NOMBRES_TELEFONIA)


# ─────────────────────────────────────────────────────────────────
# CONFIGURACIONES PRE-DEFINIDAS POR EMPRESA
# ─────────────────────────────────────────────────────────────────
# Cada empresa tiene su propio PUC. Las claves del config son las
# mismas para todas las empresas; cambian los códigos de cuenta.
#
# En el FUTURO (Fase 2) estas configs vivirán en empresa.json en
# Supabase Storage y se leerán dinámicamente. Por ahora están en
# código para no romper la compatibilidad.

CONFIG_SILLA_TRES = {
    "_descripcion": "SILLA TRES S.A.S — NIT 900451388",
    # IVA descontable
    "iva_compras_19":    "24081007",
    "iva_compras_5":     "24081006",
    "iva_servicios_19":  "24081303",
    "iva_servicios_5":   "24081303",   # mismo, no hay 5% servicios separado

    # Impuesto saludable (al inventario): IBUA, ICUI, y consumo cuando
    # el ítem es para inventario
    "saludable_inventario": "14359505",

    # Impuestos como gasto (cuando NO hay inventario en la factura)
    "consumo_gasto":     "52159501",   # INC general
    "consumo_telefonia": "52159502",   # INC telefonía

    # Mapeos de cuentas legacy → cuenta destino (para detectar y reemplazar)
    "mapa_iva_legacy_a_concepto": {
        "24080201": ("compras",  "19"),
        "24080203": ("compras",  "5"),
        "24080308": ("servicios","19"),
    },
    "mapa_consumo_legacy": {
        "24080540": "saludable",   # IBUA antiguo → saludable inventario
        "24080515": "saludable",   # ICUI antiguo → saludable inventario
        "24080530": "consumo",     # INC antiguo → gasto/inventario según contexto
    },
}


# Diccionario: NIT (sin guion, sin DV) → config de remapeo
# Cuando se agregue una empresa nueva, basta con añadir su entrada acá.
# En Fase 2 esto se reemplazará por una lectura dinámica de empresa.json.
CONFIGS_POR_NIT: dict[str, dict] = {
    "900451388": CONFIG_SILLA_TRES,
}


def obtener_config_empresa(
    nit_empresa: str,
    config_override: dict | None = None,
) -> dict | None:
    """Devuelve el config de remapeo para la empresa dada.

    Args:
        nit_empresa: NIT de la empresa (con o sin guion).
        config_override: dict explícito que toma precedencia sobre el
            registro interno. Útil cuando el config viene de Supabase.

    Returns:
        dict con el config, o None si la empresa no tiene config (en cuyo
        caso el remapeo no se aplicará).
    """
    if config_override is not None:
        return config_override
    nit_norm = normalizar_nit(nit_empresa)
    return CONFIGS_POR_NIT.get(nit_norm)


def remapear_cuentas_por_empresa(
    resultados: list[ResultadoProcesamiento],
    config_override: dict | None = None,
) -> list[ResultadoProcesamiento]:
    """Reemplaza las cuentas que asignó el procesador legacy por las
    correctas del PUC de cada empresa, según contexto.

    Para cada empresa en `resultados`, busca su config en `CONFIGS_POR_NIT`
    usando el NIT de la empresa. Si no encuentra config, no hace nada
    (la empresa pasa intacta).

    Reglas aplicadas (todas configurables en config_override):

    A) IVA DESCONTABLE — distinguir compras vs servicios y por tarifa.
       Si la línea de IVA está acompañada de líneas con cuenta `1435xx`
       (inventario) → es COMPRA. Si no, es SERVICIO.

    B) IMPUESTOS AL CONSUMO (INC, telefónico, bolsas):
       - Si el documento tiene líneas de inventario (1435xx) →
         el impuesto va al inventario (saludable_inventario).
       - Si el documento es de gasto/servicio:
            - Telefonía (Tigo/Claro/Movistar/...) → consumo_telefonia
            - Otros → consumo_gasto

    C) IBUA / ICUI (impuestos saludables):
       Siempre van a saludable_inventario, sin importar el contexto.

    Args:
        resultados: lista de ResultadoProcesamiento (uno por empresa).
        config_override: si se da, se aplica este config a TODAS las empresas
            de `resultados`, ignorando el NIT. Útil para test o para
            forzar una empresa específica.
    """
    for res in resultados:
        if not res.lineas_plano:
            continue

        # Determinar el config aplicable para ESTA empresa
        cfg = obtener_config_empresa(
            nit_empresa=getattr(res, "empresa_nit", "") or res.empresa_id,
            config_override=config_override,
        )
        if cfg is None:
            # Empresa sin config registrada: no remapear, pasa intacta
            continue

        _aplicar_remapeo_a_resultado(res, cfg)

    return resultados


def _aplicar_remapeo_a_resultado(res: ResultadoProcesamiento, cfg: dict) -> None:
    """Aplica el remapeo de cuentas a un resultado individual.
    Extraído para que la lógica sea testeable sin la lista de resultados."""
    # Indexar líneas por documento para tener contexto
    lineas_por_doc: dict[tuple[str, str], list[LineaPlano]] = defaultdict(list)
    for l in res.lineas_plano:
        lineas_por_doc[(l.consecutivo, l.documento_referencia)].append(l)

    # Mapa NIT → nombre del emisor para detectar telefonía
    nit_a_nombre: dict[str, str] = {}
    for d in res.documentos:
        nit_a_nombre[normalizar_nit(d.nit_emisor)] = d.nombre_emisor or ""

    # Configs con defaults seguros
    mapa_iva = cfg.get("mapa_iva_legacy_a_concepto", {})
    mapa_consumo = cfg.get("mapa_consumo_legacy", {})

    for clave, lineas_doc in lineas_por_doc.items():
        # ¿El documento tiene líneas de INVENTARIO (1435xx)?
        tiene_inventario = any(
            l.cuenta.startswith("1435") for l in lineas_doc
        )
        # NIT del proveedor (de cualquier línea con nit_tercero)
        nit_proveedor = ""
        for l in lineas_doc:
            if l.nit_tercero:
                nit_proveedor = normalizar_nit(l.nit_tercero)
                break
        es_telefonia = _es_proveedor_telefonia(nit_a_nombre.get(nit_proveedor, ""))

        for l in lineas_doc:
            cta_actual = l.cuenta or ""
            desc = (l.descripcion or "").upper()

            # ── A) IVA DESCONTABLE ─────────────────────────
            mapeo_iva = mapa_iva.get(cta_actual)
            if mapeo_iva is not None:
                _, tarifa = mapeo_iva
                concepto = "compras" if tiene_inventario else "servicios"
                nueva_cta = cfg.get(f"iva_{concepto}_{tarifa}")
                if nueva_cta:
                    l.cuenta = nueva_cta

            # ── B/C) IMPUESTOS AL CONSUMO / SALUDABLES ─────
            tag_consumo = mapa_consumo.get(cta_actual)
            if tag_consumo == "saludable" or "IBUA" in desc or "ICUI" in desc:
                cta_dest = cfg.get("saludable_inventario")
                if cta_dest:
                    l.cuenta = cta_dest
            elif tag_consumo == "consumo" or "(INC)" in desc:
                if tiene_inventario:
                    cta_dest = cfg.get("saludable_inventario")
                elif es_telefonia:
                    cta_dest = cfg.get("consumo_telefonia")
                else:
                    cta_dest = cfg.get("consumo_gasto")
                if cta_dest:
                    l.cuenta = cta_dest


# ─────────────────────────────────────────────────────────────────
# COMPATIBILIDAD HACIA ATRÁS
# ─────────────────────────────────────────────────────────────────
# La función original se llamaba `remapear_cuentas_silla_tres`. Mantenemos
# el alias para que cualquier código que la importe siga funcionando.
# DEPRECADO: usar `remapear_cuentas_por_empresa()`.

def remapear_cuentas_silla_tres(
    resultados: list[ResultadoProcesamiento],
    cuentas_override: dict | None = None,
) -> list[ResultadoProcesamiento]:
    """[DEPRECADO] Alias de `remapear_cuentas_por_empresa` que fuerza la
    config de Silla Tres. Mantenido para compatibilidad con código que
    importa esta función directamente. Se eliminará en una versión futura.
    """
    cfg = CONFIG_SILLA_TRES.copy()
    if cuentas_override:
        cfg.update(cuentas_override)
    return remapear_cuentas_por_empresa(resultados, config_override=cfg)


# ─────────────────────────────────────────────────────────────────
# POST-PROCESADO: agregar líneas de retenciones
# ─────────────────────────────────────────────────────────────────

def agregar_retenciones_a_resultados(
    resultados: list[ResultadoProcesamiento],
    ruta_empresas: Path | str,
    consecutivos_iniciales: dict[str, int] | int | None = None,
) -> list[ResultadoProcesamiento]:
    """Agrega líneas de retefuente y reteIVA al plano contable, ajustando
    el cuadre del proveedor. Al final ordena por fecha de emisión ASC y
    renumera consecutivos por comprobante.

    `consecutivos_iniciales` puede ser:
    - dict {"3": 100, "7": 50, "12": 200}: número inicial por comprobante
    - int único: mismo número inicial para todos los comprobantes
    - None: cada comprobante arranca en 1
    """
    ruta_emp = Path(ruta_empresas)

    for res in resultados:
        catalogo = _cargar_catalogo_motor(res.empresa_id, ruta_emp)
        if catalogo is None:
            continue

        cuenta_proveedor_default = catalogo.empresa_json.get(
            "cuentas_proveedores", {}
        ).get("default", "22050501")

        # Indexar líneas por (consecutivo, doc_ref) para encontrarlas rápido
        lineas_por_doc: dict[tuple[str, str], list[LineaPlano]] = defaultdict(list)
        for l in res.lineas_plano:
            lineas_por_doc[(l.consecutivo, l.documento_referencia)].append(l)

        # Recorrer documentos
        nuevas_lineas: list[LineaPlano] = []
        ya_agregadas: set[tuple[str, str]] = set()

        for doc in res.documentos:
            doc_ref = f"{doc.prefijo}{doc.numero}"
            # Buscar la(s) líneas del doc en el plano
            clave_match = None
            for clave, lineas in lineas_por_doc.items():
                if clave[1] == doc_ref:
                    clave_match = clave
                    break
            if clave_match is None:
                continue

            lineas_doc = lineas_por_doc[clave_match]
            ya_agregadas.add(clave_match)

            # Datos comunes
            primera = lineas_doc[0]
            consec = primera.consecutivo
            comp = primera.comprobante
            fecha = primera.fecha
            nit_terc = primera.nit_tercero

            # Determinar CC dominante del documento (el que más se repite en líneas no-proveedor)
            cc_dominante = primera.centro_costo
            cc_count: dict[str, int] = {}
            for l in lineas_doc:
                if not (l.cuenta.startswith("2205") or l.cuenta == cuenta_proveedor_default):
                    cc_count[l.centro_costo] = cc_count.get(l.centro_costo, 0) + 1
            if cc_count:
                cc_dominante = max(cc_count.items(), key=lambda x: x[1])[0]

            cc_doc = cc_dominante  # CC para nuevas líneas de retención

            # Reemplazar CC en líneas de proveedor: si quedaron como ADMIN o default,
            # ponerles el CC dominante del documento
            cc_default_legacy = catalogo.empresa_json.get("centro_costo_default", "ADMIN")
            for l in lineas_doc:
                if (l.cuenta.startswith("2205") or l.cuenta == cuenta_proveedor_default):
                    if l.centro_costo in ("ADMIN", "", cc_default_legacy):
                        l.centro_costo = cc_dominante

            # Obtener concepto_retencion
            concepto_ret = getattr(doc, "_motor_v03_concepto_retencion", "sin_retencion")
            regimen = getattr(doc, "_motor_v03_regimen_emisor", "ordinario")
            autorret = getattr(doc, "_motor_v03_autorretenedor", False)

            es_nc = doc.tipo_codigo == "91"
            base_neta = _q(doc.valor_base_gravable if doc.valor_base_gravable
                           else (doc.valor_total - doc.iva_total))
            iva = _q(doc.iva_total)

            # Calcular retenciones
            total_retenciones = Decimal(0)
            lineas_retencion: list[LineaPlano] = []

            # Retefuente
            if concepto_ret and concepto_ret != "sin_retencion":
                ret = calcular_retencion_renta(catalogo, concepto_ret, float(base_neta),
                                                regimen, autorret)
                if ret and ret.aplicada and ret.valor > 0:
                    valor_ret = _q(Decimal(str(ret.valor)))
                    if not es_nc:
                        lineas_retencion.append(LineaPlano(
                            fecha=fecha, comprobante=comp, consecutivo=consec,
                            cuenta=ret.cuenta, centro_costo=cc_doc, nit_tercero=nit_terc,
                            descripcion=f"Retefuente {ret.tarifa*100:.2f}% ({concepto_ret})",
                            documento_referencia=doc_ref,
                            debito=Decimal(0), credito=valor_ret,
                            base=base_neta, porcentaje=Decimal(str(ret.tarifa * 100)),
                        ))
                        total_retenciones += valor_ret
                    else:
                        # NC: invierte sentido
                        lineas_retencion.append(LineaPlano(
                            fecha=fecha, comprobante=comp, consecutivo=consec,
                            cuenta=ret.cuenta, centro_costo=cc_doc, nit_tercero=nit_terc,
                            descripcion=f"Reverso Retefuente NC ({concepto_ret})",
                            documento_referencia=doc_ref,
                            debito=valor_ret, credito=Decimal(0),
                            base=base_neta, porcentaje=Decimal(str(ret.tarifa * 100)),
                        ))
                        total_retenciones -= valor_ret

            # ReteIVA
            ret_iva = calcular_reteiva(catalogo, float(iva), regimen, float(base_neta))
            if ret_iva and ret_iva.aplicada and ret_iva.valor > 0:
                valor_iva = _q(Decimal(str(ret_iva.valor)))
                # Forzar cuenta de reteIVA del PUC Silla Tres (regimen simple 15%)
                # Si el catálogo tiene una cuenta distinta para reteIVA, esta
                # línea la sobreescribe.
                cuenta_reteiva = (
                    catalogo.empresa_json.get("cuentas_reteiva", {}).get("default")
                    or "23670515"
                )
                if not es_nc:
                    lineas_retencion.append(LineaPlano(
                        fecha=fecha, comprobante=comp, consecutivo=consec,
                        cuenta=cuenta_reteiva, centro_costo=cc_doc, nit_tercero=nit_terc,
                        descripcion=f"ReteIVA 15%",
                        documento_referencia=doc_ref,
                        debito=Decimal(0), credito=valor_iva,
                        base=iva, porcentaje=Decimal("15"),
                    ))
                    total_retenciones += valor_iva
                else:
                    lineas_retencion.append(LineaPlano(
                        fecha=fecha, comprobante=comp, consecutivo=consec,
                        cuenta=cuenta_reteiva, centro_costo=cc_doc, nit_tercero=nit_terc,
                        descripcion=f"Reverso ReteIVA NC",
                        documento_referencia=doc_ref,
                        debito=valor_iva, credito=Decimal(0),
                        base=iva, porcentaje=Decimal("15"),
                    ))
                    total_retenciones -= valor_iva

            # Ajustar línea del proveedor (CR menor por las retenciones)
            if total_retenciones != 0:
                for l in lineas_doc:
                    if l.cuenta.startswith("2205") or l.cuenta == cuenta_proveedor_default:
                        if not es_nc and l.credito > 0:
                            l.credito = _q(l.credito - total_retenciones)
                        elif es_nc and l.debito > 0:
                            l.debito = _q(l.debito - abs(total_retenciones))
                        break

            # Agregar líneas: primero las originales del doc, después las retenciones
            nuevas_lineas.extend(lineas_doc)
            nuevas_lineas.extend(lineas_retencion)

        # Líneas que no estaban indexadas (raro, pero por si acaso)
        for clave, lineas in lineas_por_doc.items():
            if clave not in ya_agregadas:
                nuevas_lineas.extend(lineas)

        # Recalcular cuadre
        cuadre_db = sum((l.debito for l in nuevas_lineas), Decimal(0))
        cuadre_cr = sum((l.credito for l in nuevas_lineas), Decimal(0))

        # Asignar las líneas al res ANTES del remapeo para que la función
        # de remapeo pueda iterar por documento.
        res.lineas_plano = nuevas_lineas

        # Remapear cuentas de IVA, IBUA, ICUI, INC al PUC real de la empresa.
        # `remapear_cuentas_por_empresa` busca el config en `CONFIGS_POR_NIT`
        # según el NIT de la empresa. Si no hay config, no hace nada.
        # En Fase 2 esto se reemplazará por config dinámico desde Supabase.
        remapear_cuentas_por_empresa([res])

        # Ordenar por fecha de emisión ASC y renumerar consecutivos:
        # facturas más antiguas → consecutivos menores. Cada comprobante
        # (3, 7, 12) lleva su propia secuencia, arrancando desde lo que
        # indique consecutivos_iniciales (o desde 1 por defecto).
        nuevas_lineas = _ordenar_y_renumerar_plano(
            res.lineas_plano, consecutivos_iniciales=consecutivos_iniciales,
        )

        res.lineas_plano = nuevas_lineas
        res.cuadre_db = cuadre_db
        res.cuadre_cr = cuadre_cr
        res.cuadrado = (cuadre_db == cuadre_cr)

    return resultados


# ─────────────────────────────────────────────────────────────────
# ACTIVACIÓN / DESACTIVACIÓN
# ─────────────────────────────────────────────────────────────────
_activo = False


def activar(ruta_empresas: Path | str = "core/data/empresas") -> None:
    """Aplica los monkey-patches al procesador legacy."""
    global _activo
    if _activo:
        return

    # Patch 1: parser
    legacy.parsear_xml_dian = parsear_xml_dian_extendido

    # Patch 2: aplicar_mapeo
    legacy.aplicar_mapeo = aplicar_mapeo_v03

    # Patch 3: cargar() para que el bundle lleve la ruta
    if hasattr(legacy, "RegistryEmpresas"):
        original_cargar = legacy.RegistryEmpresas.cargar
        ruta = Path(ruta_empresas)

        def cargar_con_ruta(self, empresa_id: str) -> dict:
            bundle = original_cargar(self, empresa_id)
            bundle["_ruta_empresas"] = ruta
            return bundle

        legacy.RegistryEmpresas.cargar = cargar_con_ruta

    _activo = True


def desactivar() -> None:
    global _activo
    if not _activo:
        return
    legacy.parsear_xml_dian = _parsear_xml_original
    legacy.aplicar_mapeo = _aplicar_mapeo_original
    _activo = False
    _cache_catalogos.clear()
    memoria_clear()
