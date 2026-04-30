"""
Motor de mapeo v0.3 — Plataforma Contable Silla Tres

Combina las 3 fuentes de información para asignar a cada XML su asiento contable:

  1. mapeo_nits.json (aprendido del Balance de Prueba)
       NIT → cuenta_default + cc_default + concepto_retencion + régimen

  2. direcciones_locales.json (curado por el usuario una sola vez)
       dirección_normalizada → CC

  3. retenciones.json (catálogo DIAN 2026)
       concepto → tarifa, base_minima, cuenta_db

Prioridad para el CC del asiento:
  (a) Si el XML trae Delivery con dirección catalogada → CC del catálogo
  (b) Si el NIT tiene cc_default con confianza ≥ 0.7 → cc_default
  (c) Sino → cc_default de empresa.json (GENERAL)
"""
from __future__ import annotations
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ═══════════════════════════════════════════════════════════════════
# Normalizadores
# ═══════════════════════════════════════════════════════════════════

def normalizar_nit(nit_raw) -> str:
    """Normaliza NIT a solo dígitos sin DV."""
    if not nit_raw:
        return ''
    s = str(nit_raw).strip().replace('.', '').replace(' ', '')
    if '-' in s:
        s = s.split('-')[0]
    return re.sub(r'\D', '', s)


def normalizar_direccion(d: str) -> str:
    """Normaliza una dirección colombiana para fuzzy match."""
    if not d:
        return ''
    s = d.upper().strip()
    s = re.sub(r'\bCARRERA\b|\bKARRERA\b|\bCRA\b|\bKRA\b|\bCRR\b', 'CR', s)
    s = re.sub(r'\bCALLE\b|\bCLL\b', 'CL', s)
    s = re.sub(r'\bDIAGONAL\b|\bDIAG\b', 'DG', s)
    s = re.sub(r'\bAVENIDA\b|\bAVE\b', 'AV', s)
    s = re.sub(r'[#\.\-]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def fingerprint_direccion(d: str) -> str:
    """
    Crea una huella robusta de la dirección extrayendo SOLO los números clave.
    Permite matchear 'CR 20 2B SUR 185' con 'CR 20 2 SUR 185' (mismo lugar, espaciado distinto).
    """
    nd = normalizar_direccion(d)
    if not nd:
        return ''
    # Extraer tipo de vía (CR/CL/DG/AV) y los grupos numéricos principales
    tokens = nd.split()
    if not tokens:
        return ''
    tipo = tokens[0] if tokens[0] in {'CR', 'CL', 'DG', 'AV'} else 'X'
    # Tomar los primeros 4-5 tokens significativos (los números clave)
    nums = []
    for t in tokens[1:]:
        # Solo guardar tokens cortos (números o sufijos cortos como A,B,C, BIS)
        if len(t) <= 4 or t.isdigit() or t in {'BIS', 'SUR', 'NORTE'}:
            nums.append(t)
        if len(nums) >= 6:
            break
    return f"{tipo} {' '.join(nums)}".strip()


def normalizar_texto_pista(t: str) -> str:
    """Normaliza un texto libre quitando acentos, encoding raro y espacios."""
    if not t:
        return ''
    s = t
    # Encoding mal interpretado (caso típico: utf-8 leído como latin-1)
    # Hacemos los reemplazos ANTES de upper() porque algunos son sensibles a mayúsculas
    encoding_fixes = [
        ('Ã©', 'é'), ('Ã³', 'ó'), ('Ã­', 'í'), ('Ãº', 'ú'), ('Ã¡', 'á'),
        ('Ã‰', 'É'), ('Ã"', 'Ó'), ('Ã', 'Í'),  # éste último captura Ã solo
        ('Ã±', 'ñ'), ('Ã'+'\x91', 'Ñ'),
    ]
    for bad, good in encoding_fixes:
        s = s.replace(bad, good)
    # Ahora upper
    s = s.upper()
    # Acentos → sin acento
    accent_map = {'Á':'A','É':'E','Í':'I','Ó':'O','Ú':'U','Ñ':'N','Ü':'U'}
    for a, b in accent_map.items():
        s = s.replace(a, b)
    # Quitar puntuación, dejar solo letras+números+espacios
    s = re.sub(r'[^\w\s]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def formato_cc_salida(cc: str, formato: str = 'sin_guion') -> str:
    """
    Convierte un CC interno a su formato de salida.

    formato='sin_guion'  : '10-04' → '1004'  (Silla Tres)
    formato='con_guion'  : '10-04' → '10-04' (formato del BP original)
    formato='primer_grupo': '10-04' → '10'   (solo grupo principal)
    """
    if not cc:
        return ''
    if formato == 'sin_guion':
        return cc.replace('-', '').replace('.', '')
    elif formato == 'con_guion':
        return cc
    elif formato == 'primer_grupo':
        return cc.split('-')[0] if '-' in cc else cc
    return cc


# ═══════════════════════════════════════════════════════════════════
# Carga de catálogos
# ═══════════════════════════════════════════════════════════════════

@dataclass
class CatalogoEmpresa:
    """Conjunto de catálogos cargados en memoria para una empresa."""
    nit: str
    empresa_json: dict
    mapeo_nits: dict
    direcciones_locales: dict
    retenciones: dict
    centros_costo: dict
    palabras_clave_cc: dict = field(default_factory=dict)

    # Índice precomputado: fingerprint → CC
    _idx_direcciones: dict = field(default_factory=dict)

    @classmethod
    def cargar(cls, ruta_carpeta: str | Path) -> 'CatalogoEmpresa':
        carp = Path(ruta_carpeta)
        empresa = json.loads((carp / 'empresa.json').read_text(encoding='utf-8'))
        mapeo = json.loads((carp / 'mapeo_nits.json').read_text(encoding='utf-8'))
        direcciones = json.loads((carp / 'direcciones_locales.json').read_text(encoding='utf-8'))
        retenciones = json.loads((carp / 'retenciones.json').read_text(encoding='utf-8'))
        centros = json.loads((carp / 'centros_costo.json').read_text(encoding='utf-8'))

        # palabras_clave_cc.json es opcional (compatibilidad hacia atrás)
        pkw_path = carp / 'palabras_clave_cc.json'
        palabras = json.loads(pkw_path.read_text(encoding='utf-8')) if pkw_path.exists() else {}

        cat = cls(
            nit=empresa['nit'],
            empresa_json=empresa,
            mapeo_nits=mapeo,
            direcciones_locales=direcciones,
            retenciones=retenciones,
            centros_costo=centros,
            palabras_clave_cc=palabras
        )
        cat._construir_indice_direcciones()
        return cat

    def _construir_indice_direcciones(self):
        """Pre-calcula fingerprints de todas las direcciones del catálogo."""
        direcciones = self.direcciones_locales.get('direcciones', {})
        for direc_norm, info in direcciones.items():
            fp = fingerprint_direccion(direc_norm)
            if fp:
                self._idx_direcciones[fp] = info.get('cc', '')


# ═══════════════════════════════════════════════════════════════════
# Resolución
# ═══════════════════════════════════════════════════════════════════

@dataclass
class ResolucionMapeo:
    """Resultado de resolver el mapeo para un XML/línea."""
    cuenta: str
    cc: str
    concepto_retencion: str
    regimen_emisor: str
    autorretenedor_renta: bool
    es_pendiente_revision: bool
    fuente_cc: str  # 'palabra_clave' | 'direccion_xml' | 'nit_default_alta_conf' | 'nit_default_baja_conf' | 'empresa_default'
    fuente_cuenta: str  # 'mapeo_nit' | 'auto_insumos' | 'pendiente'
    advertencias: list = field(default_factory=list)
    pista_palabra_clave: str = ''  # qué texto de la nota matcheó (para auditoría)


def resolver_cc_por_palabras_clave(
    catalogo: CatalogoEmpresa,
    notas: list,
    descripciones: list
) -> tuple[str, str]:
    """
    Intenta resolver el CC usando el catálogo de palabras clave.

    Estrategia: evalúa cada nota INDIVIDUALMENTE para no mezclar texto de
    distintos contextos. Una factura puede tener 10+ notas (info legal del
    proveedor, info DIAN, info del producto, y la pista CTS de CC).
    Si una sola nota matchea una regla, devuelve ese CC.

    Returns: (cc_resuelto, texto_que_matcheo) o ('', '') si no hay match.
    """
    reglas = catalogo.palabras_clave_cc.get('reglas_por_prioridad', [])
    if not reglas:
        return ('', '')

    def limpiar_sufijos(texto: str) -> str:
        """Limpia sufijos comunes que aparecen en TODAS las notas del mismo proveedor.
        Ej: 'CTS1.-DE LOLITA ROSARIO POBLADO SILLA TRES S.A.S - DE LOLITA TORRE MEDICA CLINCA AMERI'
            → 'CTS1 DE LOLITA ROSARIO POBLADO'
        """
        # Cortar todo lo que venga después de 'SILLA TRES' (el sufijo común)
        idx = texto.find('SILLA TRES')
        if idx > 5:  # solo si SILLA TRES no está al principio
            texto = texto[:idx].strip()
        # Cortar también si encuentra ' SILLA 3 '
        idx = texto.find('SILLA 3')
        if idx > 5:
            texto = texto[:idx].strip()
        return texto

    # Lista de textos a evaluar individualmente
    textos_individuales = []
    for t in (notas or []):
        if t:
            t_norm = normalizar_texto_pista(t)
            t_clean = limpiar_sufijos(t_norm)
            if t_clean:
                textos_individuales.append(('NOTE', t_clean))
    for t in (descripciones or []):
        if t:
            t_norm = normalizar_texto_pista(t)
            if t_norm:
                textos_individuales.append(('DESC', t_norm))

    if not textos_individuales:
        return ('', '')

    # Filtrar textos que claramente no aportan info de CC
    textos_filtrados = []
    for tipo, t in textos_individuales:
        # Saltar notas que SOLO contienen info legal del proveedor
        if 'AUTORRETENEDORES' in t and 'RESOLUCION' in t:
            continue
        if 'NUMFAC' in t and ('CUFE' in t or 'FECFAC' in t):
            continue
        if 'CREDITO' in t and 'DIAS' in t:
            continue
        if t.startswith('ITE '):
            continue
        if t.startswith('NTI ') or t.startswith('NTI_'):
            continue
        if t.startswith('MD '):
            continue
        if 'DIAN SE UTILIZARA' in t or 'EJEMPLAR QUE RECIBA' in t:
            continue
        if 'LEY 1231' in t:
            continue
        if 'BANCOLOMBIA' in t and 'CONSIGNACION' in t:
            continue
        if len(t) < 3:
            continue
        textos_filtrados.append((tipo, t))

    # Evaluar cada texto contra cada regla EN ORDEN
    for regla in reglas:
        patrones_todos = [normalizar_texto_pista(p) for p in regla.get('patrones_todos', [])]
        patrones_cualquiera = [normalizar_texto_pista(p) for p in regla.get('patrones_cualquiera', [])]

        for tipo, texto in textos_filtrados:
            match_todos = all(p in texto for p in patrones_todos) if patrones_todos else True
            if patrones_cualquiera:
                match_alguno = any(p in texto for p in patrones_cualquiera)
            else:
                match_alguno = True

            if match_todos and match_alguno:
                cc = regla.get('cc', '')
                if cc:
                    return (cc, f"[{tipo}] {texto[:120]}")

    return ('', '')


def resolver_mapeo(
    catalogo: CatalogoEmpresa,
    nit_emisor: str,
    nombre_emisor: str = '',
    direccion_entrega: str = '',
    items_descripcion: str = '',
    notas_xml: list | None = None,
    items_descripciones_lista: list | None = None
) -> ResolucionMapeo:
    """
    Resuelve cuenta y CC para un documento XML.

    Args:
      nit_emisor: NIT bruto del XML (puede traer puntos/guiones)
      nombre_emisor: razón social del emisor
      direccion_entrega: línea de Delivery del XML
      items_descripcion: descripciones concatenadas para auto-detección de insumos
      notas_xml: lista de cbc:Note del XML (para detectar pistas de CC tipo "CTS1.=...")
      items_descripciones_lista: lista de descripciones de ítems individuales
    """
    nit_n = normalizar_nit(nit_emisor)
    advertencias = []

    # ── Resolver CC (en orden de prioridad) ───────────────────────
    cc_resuelto = ''
    fuente_cc = ''
    pista_match = ''

    # (a) PISTA EXPLÍCITA en notas o descripciones (máxima prioridad)
    cc_resuelto, pista_match = resolver_cc_por_palabras_clave(
        catalogo,
        notas=notas_xml or [],
        descripciones=items_descripciones_lista or []
    )
    if cc_resuelto:
        fuente_cc = 'palabra_clave'

    # (b) Por dirección XML (Delivery)
    if not cc_resuelto and direccion_entrega:
        fp_xml = fingerprint_direccion(direccion_entrega)
        if fp_xml and fp_xml in catalogo._idx_direcciones:
            cc_resuelto = catalogo._idx_direcciones[fp_xml]
            if cc_resuelto:
                fuente_cc = 'direccion_xml'

    # (c) Por NIT default (del BP aprendido)
    if not cc_resuelto and nit_n in catalogo.mapeo_nits:
        info = catalogo.mapeo_nits[nit_n]
        cc_default = info.get('cc_default', '')
        confianza = info.get('confianza_cc', 0)
        if cc_default and confianza >= 0.7:
            cc_resuelto = cc_default
            fuente_cc = 'nit_default_alta_conf'
        elif cc_default:
            cc_resuelto = cc_default
            fuente_cc = 'nit_default_baja_conf'
            advertencias.append(
                f"CC asignado con baja confianza ({confianza:.0%}). "
                f"Proveedor distribuye en {len(info.get('ccs_vistos', []))} CCs."
            )

    # (d) Default de empresa
    if not cc_resuelto:
        cc_resuelto = catalogo.empresa_json.get('cc_default', '')
        fuente_cc = 'empresa_default'

    # ── Resolver cuenta ────────────────────────────────────────────
    cuenta_resuelta = ''
    concepto_ret = 'sin_retencion'
    regimen = 'ordinario'
    autorret = False
    fuente_cuenta = ''
    es_pendiente = False

    if nit_n in catalogo.mapeo_nits:
        info = catalogo.mapeo_nits[nit_n]
        cuenta_resuelta = info.get('cuenta_default', '')
        concepto_ret = info.get('concepto_retencion', 'sin_retencion')
        regimen = info.get('regimen', 'ordinario')
        autorret = info.get('autorretenedor_renta', False)
        fuente_cuenta = 'mapeo_nit'

        confianza_cuenta = info.get('confianza_cuenta', 0)
        if confianza_cuenta < 0.6:
            advertencias.append(
                f"Cuenta asignada con baja confianza ({confianza_cuenta:.0%}). "
                f"Cuentas vistas: {info.get('cuentas_vistas', [])}"
            )
    else:
        # Auto-detección de insumos alimenticios (si activa)
        flag_auto = catalogo.empresa_json.get('auto_insumos_alimenticios', {}).get('activo', False)
        if flag_auto and _es_insumo_alimenticio(nombre_emisor, items_descripcion):
            cuenta_resuelta = '14350503'  # mercancía no gravada (default conservador)
            concepto_ret = 'compras_2_5'
            fuente_cuenta = 'auto_insumos'
            advertencias.append(
                'NIT no catalogado. Auto-detectado como insumo alimenticio. '
                'Considere agregarlo formalmente a mapeo_nits.json'
            )
        else:
            # Pendiente
            cuenta_resuelta = catalogo.empresa_json.get('cuenta_pendiente_revision', '519095')
            concepto_ret = 'sin_retencion'
            fuente_cuenta = 'pendiente'
            es_pendiente = True
            advertencias.append('NIT no catalogado. Requiere catalogación manual.')

    return ResolucionMapeo(
        cuenta=cuenta_resuelta,
        cc=cc_resuelto,
        concepto_retencion=concepto_ret,
        regimen_emisor=regimen,
        autorretenedor_renta=autorret,
        es_pendiente_revision=es_pendiente,
        fuente_cc=fuente_cc,
        fuente_cuenta=fuente_cuenta,
        advertencias=advertencias,
        pista_palabra_clave=pista_match
    )


# ═══════════════════════════════════════════════════════════════════
# Auto-detección insumos (heredado de v0.2.2 + mejorado)
# ═══════════════════════════════════════════════════════════════════

PATRONES_NOMBRE_ALIMENTOS = [
    r'\bPOSTOBON\b', r'\bCOCA[\s-]*COLA\b', r'\bBAVARIA\b', r'\bFEMSA\b',
    r'\bFRITO[\s-]*LAY\b', r'\bNUTRESA\b',
    r'\bCOLANTA\b', r'\bALPINA\b', r'\bALQUERIA\b', r'\bPARMALAT\b',
    r'\bCARNES?\b', r'\bFRIGOR[ÍI]FIC', r"\bD[' ]?CARNES\b",
    r'\bNUTRIENTES?\b', r'\bCONCENTRADOS?\b', r'\bPURINA\b', r'\bSOLLA\b',
    r'\bATLANTIC[\s]+FS\b', r'\bCOMERCIALIZADORA[\s]+DE[\s]+ALIMENTOS\b',
    r'\bFRUVER\b', r'\bPANIFICADORA\b', r'\bMOLINOS\b',
    r'\bPESCADER[ÍI]A', r'\bAVES?\b', r'\bAVICOLA',
    r'\bDISTRIBUCIONES\b'  # Juan D. Hoyos Distribuciones
]

PATRONES_DESCRIPCION_ALIMENTOS = [
    r'\bCARNE\b', r'\bPOLLO\b', r'\bPESCADO\b', r'\bRES\b', r'\bCERDO\b',
    r'\bLECHE\b', r'\bQUESO\b', r'\bYOGUR', r'\bHUEVOS?\b', r'\bMANTEQUILLA\b',
    r'\bARROZ\b', r'\bFR[IÍ]JOL', r'\bHARINA\b', r'\bACEITE\b', r'\bAZ[UÚ]CAR\b',
    r'\bTOMATE\b', r'\bCEBOLLA\b', r'\bPAPA\b', r'\bFRUTAS?\b', r'\bVERDURAS?\b',
    r'\bREFRESCO\b', r'\bGASEOSA\b', r'\bJUGO\b', r'\bCAF[EÉ]\b',
    r'\bCONCENTRADO\b', r'\bFORRAJE\b', r'\bALIMENTO\b', r'\bMATERIA[\s]+PRIMA\b',
    r'\bSALCHICH', r'\bJAM[OÓ]N\b', r'\bCHORIZO\b', r'\bMORTADELA\b',
]


def _es_insumo_alimenticio(nombre_emisor: str, descripciones: str) -> bool:
    """Heurística: ¿este proveedor o sus ítems son alimentos?"""
    txt_emi = (nombre_emisor or '').upper()
    txt_des = (descripciones or '').upper()

    for p in PATRONES_NOMBRE_ALIMENTOS:
        if re.search(p, txt_emi):
            return True
    for p in PATRONES_DESCRIPCION_ALIMENTOS:
        if re.search(p, txt_des):
            return True
    return False


# ═══════════════════════════════════════════════════════════════════
# Cálculo de retenciones
# ═══════════════════════════════════════════════════════════════════

@dataclass
class Retencion:
    concepto: str
    cuenta: str
    base: float
    tarifa: float
    valor: float
    aplicada: bool
    motivo_no_aplicada: str = ''


def calcular_retencion_renta(
    catalogo: CatalogoEmpresa,
    concepto_retencion: str,
    base_imponible: float,
    regimen_emisor: str,
    autorretenedor: bool
) -> Optional[Retencion]:
    """
    Calcula retención en la fuente para renta según concepto y régimen del emisor.
    Devuelve None si no aplica o si el concepto no existe.
    """
    catalogo_ret = catalogo.retenciones.get('conceptos', {})
    if concepto_retencion not in catalogo_ret:
        return None

    info = catalogo_ret[concepto_retencion]

    # Concepto sin retención
    if info.get('no_aplicar'):
        return Retencion(
            concepto=concepto_retencion,
            cuenta='',
            base=base_imponible,
            tarifa=0,
            valor=0,
            aplicada=False,
            motivo_no_aplicada=info.get('razon', 'Concepto sin retención')
        )

    # Validar régimen del emisor
    no_aplica = info.get('no_aplica_si_emisor_es', [])
    if 'RST' in no_aplica and regimen_emisor in ('RST', 'simple_RST', 'regimen_simple'):
        return Retencion(
            concepto=concepto_retencion, cuenta=info.get('cuenta_db_proveedor', ''),
            base=base_imponible, tarifa=info['tarifa'], valor=0,
            aplicada=False, motivo_no_aplicada='Emisor pertenece al Régimen Simple (RST)'
        )
    if autorretenedor and 'autorretenedor_renta' in no_aplica:
        return Retencion(
            concepto=concepto_retencion, cuenta=info.get('cuenta_db_proveedor', ''),
            base=base_imponible, tarifa=info['tarifa'], valor=0,
            aplicada=False, motivo_no_aplicada='Emisor es autorretenedor de renta'
        )

    # Validar base mínima
    base_min = info.get('base_minima_pesos', 0)
    if base_imponible < base_min and base_min > 0:
        return Retencion(
            concepto=concepto_retencion, cuenta=info.get('cuenta_db_proveedor', ''),
            base=base_imponible, tarifa=info['tarifa'], valor=0,
            aplicada=False,
            motivo_no_aplicada=f'Base ${base_imponible:,.0f} < base mínima ${base_min:,.0f}'
        )

    # Calcular
    valor = round(base_imponible * info['tarifa'])
    return Retencion(
        concepto=concepto_retencion,
        cuenta=info.get('cuenta_db_proveedor', ''),
        base=base_imponible,
        tarifa=info['tarifa'],
        valor=valor,
        aplicada=True
    )


def calcular_reteiva(
    catalogo: CatalogoEmpresa,
    iva_factura: float,
    regimen_emisor: str,
    base_imponible: float,
    es_servicio: bool = False
) -> Optional[Retencion]:
    """
    Calcula reteIVA. Soporta dos modos según configuración de la empresa:
      - 'estandar' (default): retiene a régimen ordinario, NO retiene a RST
      - 'solo_a_RST': retiene SOLO cuando el emisor es RST (caso Silla Tres)
    """
    cfg = catalogo.retenciones.get('reteiva', {})
    if not cfg:
        return None

    modo = cfg.get('modo_aplicacion', 'estandar')
    es_rst = regimen_emisor in ('RST', 'simple_RST', 'regimen_simple')

    if modo == 'solo_a_RST':
        # Lógica INVERSA: solo se retiene si emisor es RST
        if not es_rst:
            return Retencion(
                concepto='reteiva', cuenta=cfg.get('cuenta_db_proveedor', ''),
                base=iva_factura, tarifa=cfg.get('tarifa_compras', 0.15), valor=0,
                aplicada=False,
                motivo_no_aplicada='Empresa solo retiene IVA a emisores del Régimen Simple (RST)'
            )
    else:
        # Lógica estándar: NO retener si emisor es RST
        if es_rst:
            return Retencion(
                concepto='reteiva', cuenta=cfg.get('cuenta_db_proveedor', ''),
                base=iva_factura, tarifa=cfg.get('tarifa_compras', 0.15), valor=0,
                aplicada=False, motivo_no_aplicada='Emisor RST - no se practica reteIVA'
            )

    if iva_factura <= 0:
        return None

    # Selección de tarifa y base mínima según operación
    if es_servicio:
        tarifa = cfg.get('tarifa_servicios', 0.15)
        base_min = cfg.get('base_minima_pesos_servicios', 104748)
    else:
        tarifa = cfg.get('tarifa_compras', 0.15)
        base_min = cfg.get('base_minima_pesos_compras', 523740)

    if base_imponible < base_min:
        return Retencion(
            concepto='reteiva', cuenta=cfg.get('cuenta_db_proveedor', ''),
            base=iva_factura, tarifa=tarifa, valor=0,
            aplicada=False,
            motivo_no_aplicada=f'Base ${base_imponible:,.0f} < base mín ${base_min:,.0f}'
        )

    valor = round(iva_factura * tarifa)
    return Retencion(
        concepto='reteiva', cuenta=cfg.get('cuenta_db_proveedor', ''),
        base=iva_factura, tarifa=tarifa,
        valor=valor, aplicada=True
    )


def calcular_reteica(
    catalogo: CatalogoEmpresa,
    base_imponible: float,
    actividad: str = 'servicios',
    regimen_emisor: str = 'ordinario'
) -> Optional[Retencion]:
    """
    Calcula reteICA si la empresa está habilitada como agente retenedor.
    Devuelve None si la empresa no está habilitada.
    """
    cfg = catalogo.retenciones.get('reteica', {})
    if not cfg or not cfg.get('habilitado', False):
        # Empresa no es agente retenedor de ICA
        return None

    # Lógica original (legacy reteica_medellin) — solo si está habilitado
    cfg_med = catalogo.retenciones.get('reteica_medellin', {})

    # No aplica si emisor es RST
    if regimen_emisor in ('RST', 'simple_RST', 'regimen_simple'):
        return Retencion(
            concepto='reteica', cuenta=cfg_med.get('cuenta_db_proveedor', ''),
            base=base_imponible, tarifa=0, valor=0,
            aplicada=False, motivo_no_aplicada='Emisor RST - no se practica reteICA'
        )

    tarifas = cfg_med.get('tarifas_por_actividad', {})
    tarifa = tarifas.get(actividad, cfg_med.get('tarifa_default', 0.00966))

    uvt = catalogo.retenciones.get('_uvt_2026', 52374)
    base_min = cfg_med.get('base_minima_uvt', 27) * uvt
    if base_imponible < base_min:
        return Retencion(
            concepto='reteica', cuenta=cfg_med.get('cuenta_db_proveedor', ''),
            base=base_imponible, tarifa=tarifa, valor=0,
            aplicada=False,
            motivo_no_aplicada=f'Base ${base_imponible:,.0f} < base mín ${base_min:,.0f}'
        )

    valor = round(base_imponible * tarifa)
    return Retencion(
        concepto='reteica', cuenta=cfg_med.get('cuenta_db_proveedor', ''),
        base=base_imponible, tarifa=tarifa, valor=valor, aplicada=True
    )
