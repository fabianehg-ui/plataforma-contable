"""
Helpers de inferencia para enriquecimiento de terceros y bancos.

Provee:
  - inferir_dpto_municipio_desde_texto: detecta dpto/mun mencionado en direccion/ciudad
  - obtener_nit_banco: dado el nombre de la cuenta bancaria, devuelve el NIT del banco
  - DIRECCION_PREDETERMINADA: dirección genérica para personas naturales sin datos
"""

from __future__ import annotations
import re
import unicodedata
from typing import Optional


# ================================================================
# Constantes - Dirección predeterminada para fallback
# ================================================================
# Para personas naturales o cualquier tercero que no se pueda enriquecer,
# usar los datos de la empresa informante como predeterminados.
# Estos valores se sobreescriben en runtime con los datos de la empresa.
PAIS_COLOMBIA = '169'


# ================================================================
# 1) NITs de bancos colombianos (para F1012 cuentas 1110-1120)
# ================================================================
# Se mapea palabras clave del nombre de la cuenta al NIT del banco.
# Ej: si la cuenta se llama "BANCOLOMBIA AHORROS" → NIT 890903938
#
# NITs verificados en RUES (octubre 2025)

BANCOS_NITS = {
    # Bancos comerciales tradicionales
    'BANCOLOMBIA': {'nit': '890903938', 'dv': '8', 'razon_social': 'BANCOLOMBIA S.A.'},
    'BANCO BOGOTA': {'nit': '860002964', 'dv': '4', 'razon_social': 'BANCO DE BOGOTA S.A.'},
    'BANCO DE BOGOTA': {'nit': '860002964', 'dv': '4', 'razon_social': 'BANCO DE BOGOTA S.A.'},
    'DAVIVIENDA': {'nit': '860034313', 'dv': '7', 'razon_social': 'BANCO DAVIVIENDA S.A.'},
    'BBVA': {'nit': '860003020', 'dv': '1', 'razon_social': 'BBVA COLOMBIA S.A.'},
    'BANCO POPULAR': {'nit': '860007738', 'dv': '9', 'razon_social': 'BANCO POPULAR S.A.'},
    'BANCO OCCIDENTE': {'nit': '890300279', 'dv': '4', 'razon_social': 'BANCO DE OCCIDENTE S.A.'},
    'BANCO DE OCCIDENTE': {'nit': '890300279', 'dv': '4', 'razon_social': 'BANCO DE OCCIDENTE S.A.'},
    'SCOTIABANK COLPATRIA': {'nit': '860034594', 'dv': '1', 'razon_social': 'SCOTIABANK COLPATRIA S.A.'},
    'COLPATRIA': {'nit': '860034594', 'dv': '1', 'razon_social': 'SCOTIABANK COLPATRIA S.A.'},
    'AV VILLAS': {'nit': '860035827', 'dv': '5', 'razon_social': 'BANCO AV VILLAS S.A.'},
    'AVVILLAS': {'nit': '860035827', 'dv': '5', 'razon_social': 'BANCO AV VILLAS S.A.'},
    'CITIBANK': {'nit': '860051135', 'dv': '4', 'razon_social': 'CITIBANK COLOMBIA S.A.'},
    'GNB SUDAMERIS': {'nit': '860050750', 'dv': '1', 'razon_social': 'BANCO GNB SUDAMERIS S.A.'},
    'BANCO AGRARIO': {'nit': '800037800', 'dv': '8', 'razon_social': 'BANCO AGRARIO DE COLOMBIA S.A.'},
    'BANAGRARIO': {'nit': '800037800', 'dv': '8', 'razon_social': 'BANCO AGRARIO DE COLOMBIA S.A.'},
    'ITAU': {'nit': '860003107', 'dv': '9', 'razon_social': 'ITAU CORPBANCA COLOMBIA S.A.'},
    'CORPBANCA': {'nit': '860003107', 'dv': '9', 'razon_social': 'ITAU CORPBANCA COLOMBIA S.A.'},
    'BANCOOMEVA': {'nit': '900200960', 'dv': '5', 'razon_social': 'BANCOOMEVA S.A.'},
    'COOMEVA': {'nit': '900200960', 'dv': '5', 'razon_social': 'BANCOOMEVA S.A.'},
    'BANCO CAJA SOCIAL': {'nit': '860007335', 'dv': '4', 'razon_social': 'BANCO CAJA SOCIAL S.A.'},
    'CAJA SOCIAL': {'nit': '860007335', 'dv': '4', 'razon_social': 'BANCO CAJA SOCIAL S.A.'},
    'BCSC': {'nit': '860007335', 'dv': '4', 'razon_social': 'BANCO CAJA SOCIAL S.A.'},
    'BANCO PICHINCHA': {'nit': '890200450', 'dv': '4', 'razon_social': 'BANCO PICHINCHA S.A.'},
    'PICHINCHA': {'nit': '890200450', 'dv': '4', 'razon_social': 'BANCO PICHINCHA S.A.'},
    'BANCO FALABELLA': {'nit': '900047981', 'dv': '6', 'razon_social': 'BANCO FALABELLA S.A.'},
    'FALABELLA': {'nit': '900047981', 'dv': '6', 'razon_social': 'BANCO FALABELLA S.A.'},
    'BANCO MUNDO MUJER': {'nit': '900768302', 'dv': '4', 'razon_social': 'BANCO MUNDO MUJER S.A.'},
    'MUNDO MUJER': {'nit': '900768302', 'dv': '4', 'razon_social': 'BANCO MUNDO MUJER S.A.'},
    'BANCAMIA': {'nit': '900215071', 'dv': '7', 'razon_social': 'BANCAMIA S.A.'},
    'BANCO W': {'nit': '900378212', 'dv': '4', 'razon_social': 'BANCO W S.A.'},
    'COLTEFINANCIERA': {'nit': '890903937', 'dv': '0', 'razon_social': 'COLTEFINANCIERA S.A.'},
    'FINANDINA': {'nit': '860051894', 'dv': '6', 'razon_social': 'BANCO FINANDINA S.A.'},
    # Bancos digitales / Fintechs
    'NUBANK': {'nit': '901658107', 'dv': '0', 'razon_social': 'NU COLOMBIA COMPAÑIA DE FINANCIAMIENTO S.A.'},
    'NU COLOMBIA': {'nit': '901658107', 'dv': '0', 'razon_social': 'NU COLOMBIA COMPAÑIA DE FINANCIAMIENTO S.A.'},
    'LULO BANK': {'nit': '901423020', 'dv': '5', 'razon_social': 'LULO BANK S.A.'},
    'LULO': {'nit': '901423020', 'dv': '5', 'razon_social': 'LULO BANK S.A.'},
    'NEQUI': {'nit': '900628110', 'dv': '1', 'razon_social': 'COMPAÑIA DE FINANCIAMIENTO TUYA S.A.'},
    'DAVIPLATA': {'nit': '860034313', 'dv': '7', 'razon_social': 'BANCO DAVIVIENDA S.A.'},  # mismo que Davivienda
    # Cooperativas financieras y de crédito
    'CONFIAR': {'nit': '890981233', 'dv': '7', 'razon_social': 'CONFIAR COOPERATIVA FINANCIERA'},
    'COTRAFA': {'nit': '890900286', 'dv': '7', 'razon_social': 'COTRAFA COOPERATIVA FINANCIERA'},
    'COOFINEP': {'nit': '811007510', 'dv': '4', 'razon_social': 'COOFINEP COOPERATIVA FINANCIERA'},
    'JFK COOPERATIVA': {'nit': '860030552', 'dv': '4', 'razon_social': 'JFK COOPERATIVA FINANCIERA'},
    'JFK': {'nit': '860030552', 'dv': '4', 'razon_social': 'JFK COOPERATIVA FINANCIERA'},
    'COOPERATIVA FINANCIERA': None,  # placeholder, requiere especificidad
}


def _normalizar(texto: str) -> str:
    """Quita tildes, mayúsculas, símbolos, deja solo ASCII upper."""
    if not texto:
        return ''
    # Quitar acentos
    s = unicodedata.normalize('NFKD', str(texto))
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    # Mayúsculas
    s = s.upper()
    # Solo letras, dígitos y espacios
    s = re.sub(r'[^A-Z0-9 ]+', ' ', s)
    # Comprimir espacios
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def obtener_nit_banco(nombre_cuenta: str) -> Optional[dict]:
    """
    Dado el nombre de una cuenta bancaria, devuelve los datos del banco
    asociado (NIT, DV, razón social) si se puede identificar.

    Args:
        nombre_cuenta: ej. "Bancolombia Ahorros 12345" o "DAVIVIENDA CTA CTE"

    Returns:
        dict con 'nit', 'dv', 'razon_social' o None si no se puede identificar.

    Estrategia: buscar palabras clave en el nombre normalizado.
    Si hay múltiples matches, gana el más largo (más específico).

    Ejemplos:
        obtener_nit_banco("BANCOLOMBIA AHORROS 1234")
          → {'nit': '890903938', 'dv': '8', 'razon_social': 'BANCOLOMBIA S.A.'}

        obtener_nit_banco("Banco de Bogotá Cta Cte")
          → {'nit': '860002964', ...}

        obtener_nit_banco("Caja Menor Operativa")  # NO es un banco
          → None
    """
    if not nombre_cuenta:
        return None

    texto = _normalizar(nombre_cuenta)
    if not texto:
        return None

    # Buscar el match más específico (más largo)
    mejor_match: Optional[tuple[str, dict]] = None
    for keyword, datos in BANCOS_NITS.items():
        if datos is None:
            continue
        if keyword in texto:
            if mejor_match is None or len(keyword) > len(mejor_match[0]):
                mejor_match = (keyword, datos)

    return mejor_match[1] if mejor_match else None


# ================================================================
# 2) Inferencia geográfica desde texto
# ================================================================

# Capitales de departamento (la mayoría de direcciones referencian la capital)
# Mapeo: nombre normalizado → (codigo_dpto, codigo_mun)
# Los códigos siguen el estándar DANE oficial DIAN.
CIUDADES_CONOCIDAS = {
    'BOGOTA': ('11', '001'),
    'BOGOTA DC': ('11', '001'),
    'BOGOTÁ': ('11', '001'),
    'MEDELLIN': ('05', '001'),
    'MEDELLÍN': ('05', '001'),
    'CALI': ('76', '001'),
    'BARRANQUILLA': ('08', '001'),
    'CARTAGENA': ('13', '001'),
    'CARTAGENA DE INDIAS': ('13', '001'),
    'BUCARAMANGA': ('68', '001'),
    'PEREIRA': ('66', '001'),
    'IBAGUE': ('73', '001'),
    'IBAGUÉ': ('73', '001'),
    'SANTA MARTA': ('47', '001'),
    'VILLAVICENCIO': ('50', '001'),
    'CUCUTA': ('54', '001'),
    'CÚCUTA': ('54', '001'),
    'MANIZALES': ('17', '001'),
    'PASTO': ('52', '001'),
    'NEIVA': ('41', '001'),
    'POPAYAN': ('19', '001'),
    'POPAYÁN': ('19', '001'),
    'ARMENIA': ('63', '001'),
    'MONTERIA': ('23', '001'),
    'MONTERÍA': ('23', '001'),
    'SINCELEJO': ('70', '001'),
    'TUNJA': ('15', '001'),
    'VALLEDUPAR': ('20', '001'),
    'RIOHACHA': ('44', '001'),
    'QUIBDO': ('27', '001'),
    'QUIBDÓ': ('27', '001'),
    'FLORENCIA': ('18', '001'),
    'YOPAL': ('85', '001'),
    'MOCOA': ('86', '001'),
    'ARAUCA': ('81', '001'),
    'LETICIA': ('91', '001'),
    'MITU': ('97', '001'),
    'MITÚ': ('97', '001'),
    'PUERTO CARRENO': ('99', '001'),
    'PUERTO INIRIDA': ('94', '001'),
    'SAN ANDRES': ('88', '001'),
    'SAN ANDRÉS': ('88', '001'),
    'SAN JOSE DEL GUAVIARE': ('95', '001'),
    'ENVIGADO': ('05', '266'),
    'ITAGUI': ('05', '360'),
    'BELLO': ('05', '088'),
    'SABANETA': ('05', '631'),
    'RIONEGRO': ('05', '615'),
    'SOACHA': ('25', '754'),
    'CHIA': ('25', '175'),
    'ZIPAQUIRA': ('25', '899'),
    'PALMIRA': ('76', '520'),
    'BUENAVENTURA': ('76', '109'),
    'TULUA': ('76', '834'),
    'SOLEDAD': ('08', '758'),
    'MALAMBO': ('08', '433'),
    'GIRON': ('68', '307'),
    'FLORIDABLANCA': ('68', '276'),
    'PIEDECUESTA': ('68', '547'),
    'DOSQUEBRADAS': ('66', '170'),
}


def inferir_dpto_municipio_desde_texto(*textos: str) -> Optional[tuple[str, str]]:
    """
    Intenta inferir (codigo_dpto, codigo_municipio) desde uno o varios textos
    libres (ej. dirección, ciudad, razón social).

    Args:
        *textos: varios strings opcionales (direccion, ciudad, etc.)

    Returns:
        Tupla (codigo_dpto, codigo_municipio) o None si no se puede inferir.

    Estrategia: busca el nombre de ciudad más específico mencionado.
    Si hay múltiples, gana el más largo (más específico).

    Ejemplos:
        inferir_dpto_municipio_desde_texto("CALLE 100 #20-30 MEDELLIN ANTIOQUIA")
          → ('05', '001')

        inferir_dpto_municipio_desde_texto("Calle 50 N° 10-20", "Envigado")
          → ('05', '266')

        inferir_dpto_municipio_desde_texto("Cra 7 # 11-50")  # sin ciudad
          → None
    """
    texto_completo = ' '.join(_normalizar(t) for t in textos if t)
    if not texto_completo:
        return None

    mejor_match: Optional[tuple[str, tuple[str, str]]] = None
    for nombre, codigos in CIUDADES_CONOCIDAS.items():
        nombre_norm = _normalizar(nombre)
        # Buscar como palabra completa (con bordes)
        # ej. "MEDELLIN" en "CALLE 100 MEDELLIN" pero NO en "MEDELLINENSE"
        pattern = rf'\b{re.escape(nombre_norm)}\b'
        if re.search(pattern, texto_completo):
            if mejor_match is None or len(nombre_norm) > len(mejor_match[0]):
                mejor_match = (nombre_norm, codigos)

    return mejor_match[1] if mejor_match else None


# ================================================================
# 3) Validación de completitud para formatos que requieren ubicación
# ================================================================

# Formatos donde DIAN exige dirección + dpto + municipio
# F2276 también se incluye porque aunque el XSD lo deja opcional, DIAN
# rechaza el envío si falta la ubicación del beneficiario.
FORMATOS_REQUIEREN_UBICACION = {'1001', '1003', '1008', '1009', '1647', '2276'}


def validar_tercero_completo(
    tercero_dict: dict,
    formato: str,
) -> list[str]:
    """
    Valida que el tercero tenga los campos obligatorios para un formato dado.

    Args:
        tercero_dict: dict con datos del tercero (de exogena_terceros)
        formato: '1001', '1003', etc.

    Returns:
        Lista de mensajes de error. Vacía si el tercero está completo.
    """
    errores = []

    # Campo identidad mínimo
    if not (tercero_dict.get('razon_social') or
            (tercero_dict.get('primer_nombre') and tercero_dict.get('primer_apellido'))):
        errores.append("Sin razón social ni nombres/apellidos")

    # Ubicación obligatoria para ciertos formatos
    if formato in FORMATOS_REQUIEREN_UBICACION:
        if not (tercero_dict.get('direccion') or '').strip():
            errores.append("Sin dirección")
        if not (tercero_dict.get('codigo_dpto') or '').strip():
            errores.append("Sin código departamento")
        if not (tercero_dict.get('codigo_municipio') or '').strip():
            errores.append("Sin código municipio")

    return errores


def es_persona_natural(tercero_dict: dict) -> bool:
    """Heurística: persona natural si tipo_documento es 13 (CC), 22 (CE), etc."""
    tipo = tercero_dict.get('tipo_documento')
    if isinstance(tipo, str) and tipo.isdigit():
        tipo = int(tipo)
    # 31 = NIT (jurídica), 43 = nex (sin doc, ej. cuantías menores)
    # 13 CC, 22 CE, 41 pasaporte, 42 tipo ext, 50 NIT extranjería
    return tipo in (13, 22, 41, 42, 11, 12, 15)


# ================================================================
# 4) Aplicar fallback de empresa informante
# ================================================================

def aplicar_fallback_empresa(
    tercero_dict: dict,
    info_empresa: dict,
) -> dict:
    """
    Rellena los campos faltantes del tercero con los de la empresa informante.
    Útil para personas naturales que no se pueden enriquecer.

    Args:
        tercero_dict: tercero con datos incompletos
        info_empresa: {direccion, codigo_dpto, codigo_municipio, codigo_pais}

    Returns:
        Copia del tercero con los campos faltantes rellenados.
    """
    out = dict(tercero_dict)
    campos_a_rellenar = ['direccion', 'codigo_dpto', 'codigo_municipio', 'codigo_pais']
    for campo in campos_a_rellenar:
        if not (out.get(campo) or '').strip():
            valor_empresa = info_empresa.get(campo)
            if valor_empresa:
                out[campo] = valor_empresa
    return out
