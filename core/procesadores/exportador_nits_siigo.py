"""
core/procesadores/exportador_nits_siigo.py

Exporta proveedores nuevos al formato de plantilla Siigo NITs (20 columnas).

ESTRUCTURA DE COLUMNAS (basada en plantilla real JIPER):
    0  NIT              - número sin DV
    1  C                - tipo de tercero (C=Cliente/Proveedor, A=Auxiliar, etc.)
    2  RAZON SOCIAL     - nombre completo del tercero
    3  DIRECCION        - dirección física
    4  CIUDAD           - ciudad texto
    5  TEL              - teléfono fijo
    6  MPIO             - código DANE municipio (5001=Medellín)
    7  V                - vigencia activo (S=Sí)
    8  R                - responsable IVA (S/N)
    9  CP               - código país (169=Colombia)
    10 PRIMER NOMBRE    - solo personas naturales
    11 SEGUNDO NOMBRE
    12 PRIMER APELLIDO
    13 SEGUNDO APELLIDO
    14 E-MAIL
    15 CELULAR
    16 PLAZO            - plazo de pago en días (0 por defecto)
    17 ACTIVIDAD ECONOMICA - código CIIU
    18 INDICATIVO       - código zona (vacío para JIPER)
    19 NATURALEZA       - J=jurídica, N=natural

FUENTE DE DATOS:
    Del `maestro_terceros.json` extraído de los XMLs descargados:
      - nit, nombre, ciudad, direccion, email, telefono
      - tax_level_principal (regimen)
"""
from __future__ import annotations

import io
import json
import re
from pathlib import Path
from typing import Optional

import pandas as pd


# Tabla DANE de ciudades principales (las que aparecen en JIPER)
CIUDAD_A_MPIO = {
    "MEDELLIN":  "5001",
    "MEDELLÍN":  "5001",
    "MEDELLIM":  "5001",
    "MEDELIN":   "5001",
    "BOGOTA":    "11001",
    "BOGOTÁ":    "11001",
    "BOGOTA D.C.": "11001",
    "BOGOTÁ D.C.": "11001",
    "CALI":      "76001",
    "BARRANQUILLA": "8001",
    "CARTAGENA": "13001",
    "BUCARAMANGA":  "68001",
    "CUCUTA":    "54001",
    "CÚCUTA":    "54001",
    "PEREIRA":   "66001",
    "MANIZALES": "17001",
    "IBAGUE":    "73001",
    "IBAGUÉ":    "73001",
    "SANTA MARTA":  "47001",
    "VILLAVICENCIO":"50001",
    "PASTO":     "52001",
    "NEIVA":     "41001",
    "ARMENIA":   "63001",
    "MONTERIA":  "23001",
    "MONTERÍA":  "23001",
    "ENVIGADO":  "5266",
    "BELLO":     "5088",
    "ITAGUI":    "5360",
    "ITAGÜÍ":    "5360",
    "RIONEGRO":  "5615",
    "SABANETA":  "5631",
    "LA ESTRELLA":  "5380",
    "COPACABANA":   "5212",
    "CALDAS":       "5129",
    "CHIA":         "25175",
    "CHÍA":         "25175",
    "SOACHA":       "25754",
    "TOLU":         "70820",
    "GIRARDOTA":    "5308",
    "CARTAGO":      "76147",
    "PALMIRA":      "76520",
    "FLORIDABLANCA":"68276",
    "POPAYAN":      "19001",
    "POPAYÁN":      "19001",
    "TUNJA":        "15001",
    "RIOHACHA":     "44001",
    "VALLEDUPAR":   "20001",
    "SINCELEJO":    "70001",
    "QUIBDO":       "27001",
    "QUIBDÓ":       "27001",
    "FUSAGASUGA":   "25290",
    "FUSAGASUGÁ":   "25290",
    "BARRANCABERMEJA":"68081",
    "BUGA":         "76111",
    "ARMENIA":      "63001",
    "GUARNE":       "5318",
    "MARINILLA":    "5440",
    "EL CARMEN DE VIBORAL": "5148",
    "LA CEJA":      "5376",
}


def codigo_municipio(ciudad: str) -> str:
    """Devuelve código DANE del municipio según el nombre."""
    if not ciudad:
        return ""
    c = str(ciudad).strip().upper()
    # Quitar acentos para hacer match
    c = c.replace("Á","A").replace("É","E").replace("Í","I").replace("Ó","O").replace("Ú","U").replace("Ñ","N")
    for nombre, codigo in CIUDAD_A_MPIO.items():
        nombre_norm = nombre.replace("Á","A").replace("É","E").replace("Í","I").replace("Ó","O").replace("Ú","U").replace("Ñ","N")
        if c == nombre_norm:
            return codigo
    return ""  # vacío si no se reconoce


def es_persona_natural(razon_social: str, regimen: str = "", nit: str = "") -> bool:
    """
    Heurística para decidir si un tercero es persona natural.

    Reglas en orden de prioridad:
    1. Si la razón social contiene S.A.S, LTDA, SAS, etc → JURÍDICA (no natural)
    2. Si el NIT tiene 9-10 dígitos y empieza con 9, 8 o 7 → típicamente JURÍDICA
       (NITs colombianos de empresas usualmente empiezan con 8 o 9)
    3. Si el NIT tiene 6-10 dígitos y NO empieza con 8 o 9 → cédula (persona natural)
       (cédulas colombianas suelen ser de 7-10 dígitos pero NO empiezan con 8/9)
    4. Si la razón social parece nombre propio (3-4 palabras sin términos jurídicos) → NATURAL
    """
    # Regla 1: palabras jurídicas inequívocas
    rs = (razon_social or "").upper()
    palabras_juridicas = [
        "S.A.S", " SAS", "SAS.", "LTDA", "S.A.", "S.A ", "& CIA", "SEN C",
        "S EN C", "EMPRESA", "GRUPO", "FUNDACION", "FUNDACIÓN",
        "CORPORACION", "CORPORACIÓN", "ASOCIACION", "ASOCIACIÓN",
        "COOPERATIVA", "SOCIEDAD", "COMERCIALIZADORA", "DISTRIBUIDORA",
        "INVERSIONES", "INDUSTRIAS", "COMERCIAL", "S A S", "ZOMAC",
        "SERVICIOS", "COMPAÑIA", "COMPAÑÍA", "ADMINISTRADORA",
    ]
    for p in palabras_juridicas:
        if p in rs:
            return False
    # Detecta "XXXX SAS" o "XXXX S A S" al final
    if rs.endswith(" SAS") or rs.endswith(" S A S") or rs.endswith(" S.A.S"):
        return False

    # Regla 2: si NIT empieza con 9 (típico de jurídicas creadas después de 2010)
    nit_limpio = re.sub(r"\D", "", str(nit or "").split("-")[0])
    if len(nit_limpio) >= 9 and nit_limpio.startswith("9"):
        # Salvo que sea claramente nombre propio
        if not _parece_nombre_propio(rs):
            return False
        # Si parece nombre propio pero empieza con 9, dudoso → asumir jurídica
        return False

    # Regla 3: NIT empieza con 8 + 9-10 dígitos = empresa antigua
    if len(nit_limpio) >= 9 and nit_limpio.startswith("8"):
        if not _parece_nombre_propio(rs):
            return False
        return False

    # Regla 4: NIT corto (5-10 dígitos) sin empezar por 8 o 9 = cédula
    if 5 <= len(nit_limpio) <= 10 and not nit_limpio.startswith(("8", "9")):
        return True

    # Regla 5: si régimen es R-99-PN (no responsable / persona natural)
    if regimen and regimen.upper() == "R-99-PN":
        if _parece_nombre_propio(rs):
            return True

    # Por defecto: si tiene nombre que parece propio → natural
    return _parece_nombre_propio(rs)


def _parece_nombre_propio(rs: str) -> bool:
    """Heurística: 2-5 palabras, todas letras, sin números ni términos jurídicos."""
    if not rs:
        return False
    rs = rs.strip()
    partes = re.split(r"\s+", rs)
    if not (2 <= len(partes) <= 5):
        return False
    # Sin números y sin caracteres raros
    if any(re.search(r"\d", p) for p in partes):
        return False
    return True


def descomponer_nombre_persona(razon_social: str) -> tuple[str, str, str, str]:
    """
    Descompone 'JUAN DAVID PEREZ GOMEZ' en (primer_nombre, segundo_nombre, primer_apellido, segundo_apellido).
    Asume 4 palabras: 2 nombres y 2 apellidos. Si hay menos, deja vacío lo que falta.
    """
    if not razon_social:
        return ("", "", "", "")
    partes = re.split(r"\s+", razon_social.strip().upper())
    partes = [p for p in partes if p]  # quitar vacíos

    if len(partes) == 1:
        return (partes[0], "", "", "")
    if len(partes) == 2:
        return (partes[0], "", partes[1], "")
    if len(partes) == 3:
        return (partes[0], "", partes[1], partes[2])
    if len(partes) == 4:
        return (partes[0], partes[1], partes[2], partes[3])
    # Más de 4: tomar 2 primeras como nombres, 2 últimas como apellidos
    return (partes[0], partes[1], partes[-2], partes[-1])


def normalizar_nit(nit: str) -> str:
    """Quita DV y caracteres no numéricos."""
    if not nit:
        return ""
    s = str(nit).strip()
    # Si tiene formato NIT-DV, quedarse solo con el NIT
    s = s.split("-")[0]
    s = re.sub(r"\D", "", s)
    return s


def construir_fila_siigo(
    nit: str,
    nombre: str,
    direccion: str = "",
    ciudad: str = "",
    telefono: str = "",
    email: str = "",
    celular: str = "",
    regimen: str = "",
    actividad_economica: str = "",
    codigo_ciudad: str = "",
) -> dict:
    """
    Construye una fila con las 20 columnas del formato Siigo NITs.

    `codigo_ciudad`: si se pasa el código DANE directamente (extraído del XML),
    se usa con prioridad sobre la búsqueda heurística por nombre de ciudad.
    """
    nit_clean = normalizar_nit(nit)
    es_pn = es_persona_natural(nombre, regimen, nit_clean)

    # Descomponer nombre si es persona natural
    p1, p2, a1, a2 = ("", "", "", "")
    if es_pn:
        p1, p2, a1, a2 = descomponer_nombre_persona(nombre)

    # Responsable de IVA: S si es régimen distinto a R-99-PN
    r_iva = "S" if regimen and regimen.upper() not in ("R-99-PN", "") else "N"

    # Naturaleza
    naturaleza = "N" if es_pn else "J"

    # Columna C (tipo documento Siigo):
    #   A = NIT jurídica (empresa)
    #   C = Cédula (persona natural)
    tipo_doc = "C" if es_pn else "A"

    # Código DANE: priorizar el del XML (confiable) sobre la heurística por nombre
    mpio_cod = ""
    if codigo_ciudad:
        # Limpiar: solo dígitos, dejar tal cual (5 o 6 caracteres válidos)
        cod_limpio = re.sub(r"\D", "", str(codigo_ciudad))
        if cod_limpio:
            mpio_cod = cod_limpio
    if not mpio_cod:
        mpio_cod = codigo_municipio(ciudad)

    return {
        "NIT":                nit_clean,
        "C":                  tipo_doc,
        "RAZON SOCIAL":       (nombre or "").upper().strip(),
        "DIRECCION":          (direccion or "").upper().strip(),
        "CIUDAD":             (ciudad or "").upper().strip(),
        "TEL":                str(telefono or "").strip(),
        "MPIO":               mpio_cod,
        "V":                  "S",   # activo
        "R":                  r_iva,
        "CP":                 "169", # Colombia
        "PRIMER NOMBRE":      p1,
        "SEGUNDO NOMBRE":     p2,
        "PRIMER APELLIDO":    a1,
        "SEGUNDO APELLIDO":   a2,
        "E-MAIL":             (email or "").strip().lower(),
        "CELULAR":            str(celular or "").strip(),
        "PLAZO":              "0",
        "ACTIVIDAD ECONOMICA": str(actividad_economica or "").strip(),
        "INDICATIVO":         "",
        "NATURALEZA":         naturaleza,
    }


def exportar_nits_desde_maestro(
    maestro: dict,
    nits_filtrar: Optional[set] = None,
) -> pd.DataFrame:
    """
    Convierte el maestro de terceros al formato Siigo de 20 columnas.

    Args:
        maestro: dict con 'terceros' (extraído de XMLs)
        nits_filtrar: si se pasa, SOLO incluye los NITs en este set
                      (típicamente los proveedores nuevos que no están en Siigo)

    Returns:
        DataFrame con 20 columnas listo para guardar como Excel/TSV
    """
    filas = []
    for nit, datos in (maestro.get("terceros", {}) or {}).items():
        nit_norm = normalizar_nit(nit)
        if nits_filtrar is not None and nit_norm not in nits_filtrar:
            continue

        fila = construir_fila_siigo(
            nit=nit_norm,
            nombre=datos.get("nombre", ""),
            direccion=datos.get("direccion", ""),
            ciudad=datos.get("ciudad", ""),
            telefono=datos.get("telefono", ""),
            email=datos.get("email", ""),
            celular=datos.get("celular", "") or datos.get("telefono", ""),
            regimen=datos.get("tax_level_principal", ""),
            actividad_economica=datos.get("actividad_economica", ""),
            codigo_ciudad=datos.get("codigo_ciudad", ""),
        )
        filas.append(fila)

    cols = [
        "NIT", "C", "RAZON SOCIAL", "DIRECCION", "CIUDAD", "TEL", "MPIO",
        "V", "R", "CP",
        "PRIMER NOMBRE", "SEGUNDO NOMBRE", "PRIMER APELLIDO", "SEGUNDO APELLIDO",
        "E-MAIL", "CELULAR", "PLAZO", "ACTIVIDAD ECONOMICA",
        "INDICATIVO", "NATURALEZA",
    ]
    df = pd.DataFrame(filas, columns=cols)
    return df


def generar_excel_nits_siigo(df: pd.DataFrame) -> bytes:
    """Genera bytes de Excel con el formato Siigo (sin headers especiales)."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, sheet_name="nits jiper", index=False)
    return buf.getvalue()
