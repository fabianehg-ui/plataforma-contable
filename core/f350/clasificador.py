"""
core/f350/clasificador.py — clasificación de cuentas PUC a conceptos del F350.

Estrategia (en orden de prioridad descendente):

  1. CÓDIGO PUC EXACTO  → la cuenta 23-65-XX del PUC colombiano tiene
     significado fijo definido por el Decreto 2650 de 1993. Es la
     fuente más confiable.

  2. PATRONES COMBINADOS → palabras que solo califican cuando aparecen
     junto a otras (ej: "VIGILANCIA FISCAL" es honorarios, mientras
     que "VIGILANCIA PRIVADA" es servicios).

  3. PALABRAS CLAVE INDIVIDUALES → la última red de seguridad cuando
     no hay código PUC o el nombre es ambiguo.

Cada regla devuelve además un nivel de confianza (alta/media/baja)
para que la UI pueda resaltar movimientos que probablemente requieran
revisión manual.

Para agregar reglas nuevas sin tocar el código: añade entradas a
REGLAS_CODIGO_PUC, REGLAS_PATRON_COMBINADO o REGLAS_PALABRA_CLAVE.

Extraído de BorradorFácil 350 v2.1.5 (incluye el patch v2.1.5 de mejoras).
"""


# =============================================================================
# 1. REGLAS POR CÓDIGO PUC
# =============================================================================
# Llave: prefijo de código (con o sin guiones).
# Valor: (concepto, confianza).
# Los prefijos más específicos (más largos) se evalúan primero.

REGLAS_CODIGO_PUC = {
    # Retenciones IVA (toda la cuenta 2367 / 23-67)
    "2367":     ("IVA", "alta"),
    "23-67":    ("IVA", "alta"),

    # Retenciones renta — cuenta 2365 / 23-65
    "236505":   ("Rentas de trabajo", "alta"),
    "23-65-05": ("Rentas de trabajo", "alta"),
    "236510":   ("Dividendos", "alta"),
    "23-65-10": ("Dividendos", "alta"),
    "236515":   ("Honorarios", "alta"),
    "23-65-15": ("Honorarios", "alta"),
    "236520":   ("Comisiones", "alta"),
    "23-65-20": ("Comisiones", "alta"),
    "236525":   ("Servicios", "alta"),
    "23-65-25": ("Servicios", "alta"),
    "236530":   ("Arrendamientos", "alta"),
    "23-65-30": ("Arrendamientos", "alta"),
    "236535":   ("Rendimientos financieros", "alta"),
    "23-65-35": ("Rendimientos financieros", "alta"),
    "236540":   ("Compras", "alta"),
    "23-65-40": ("Compras", "alta"),
    "236545":   ("Loterías rifas", "alta"),
    "23-65-45": ("Loterías rifas", "alta"),
    "236550":   ("Otros pagos", "alta"),  # Por pagos al exterior
    "23-65-50": ("Otros pagos", "alta"),
    "236555":   ("Otros pagos", "alta"),  # Por pagos al exterior renta
    "23-65-55": ("Otros pagos", "alta"),
    "236560":   ("Compras", "alta"),  # Compras de café
    "23-65-60": ("Compras", "alta"),
    "236565":   ("Honorarios", "alta"),  # Por enajenación propiedad raíz P.N.
    "23-65-65": ("Honorarios", "alta"),
    "236570":   ("Contratos construcción", "alta"),
    "23-65-70": ("Contratos construcción", "alta"),
    "236575":   ("Servicios", "alta"),  # Por pagos al exterior servicios técnicos
    "23-65-75": ("Servicios", "alta"),
    "236580":   ("Compras", "media"),
    "23-65-80": ("Compras", "media"),
    "236595":   ("Otros pagos", "media"),
    "23-65-95": ("Otros pagos", "media"),
    "236599":   ("Otros pagos", "baja"),
    "23-65-99": ("Otros pagos", "baja"),
}


# =============================================================================
# 0. PALABRAS CLAVE PRIORITARIAS (sobre el NOMBRE de la cuenta)
# =============================================================================
# Se revisan ANTES del código PUC. Sirven para ubicar el renglón correcto por
# el nombre de la cuenta cuando el código PUC apunta a otro concepto.
#
#   Caso real: la cuenta 23-65-70 en el PUC es "Contratos construcción", pero
#   una empresa la usa como "REGALIAS Y FRANQUICIAS 2.5%". El nombre manda.
#
# Orden = prioridad (la primera que coincida gana). Edita esta lista para
# agregar/ordenar palabras clave. Formato: (subcadena_en_MAYÚSCULAS, concepto).
REGLAS_NOMBRE_PRIORITARIO = [
    ("REGALIA",       "Regalías"),
    ("REGALÍA",       "Regalías"),
    ("FRANQUICIA",    "Regalías"),
    ("ARRENDAMIENT",  "Arrendamientos"),
    ("ALQUILER",      "Arrendamientos"),
    ("HONORARIO",     "Honorarios"),
    ("COMISION",      "Comisiones"),
    ("COMISIÓN",      "Comisiones"),
    ("DIVIDENDO",     "Dividendos"),
    ("FLETE",         "Servicios"),
    ("LICENCIAM",     "Servicios"),
    ("CONSTRUCCION",  "Contratos construcción"),
    ("CONSTRUCCIÓN",  "Contratos construcción"),
    ("LOTER",         "Loterías rifas"),
    ("RIFA",          "Loterías rifas"),
    ("SERVICIO",      "Servicios"),
    ("COMPRA",        "Compras"),
]


# =============================================================================
# 2. PATRONES COMBINADOS
# =============================================================================
# (palabra_principal, palabras_secundarias, concepto, confianza)
# Se evalúa: ¿está la palabra_principal Y al menos una de las secundarias?
# (lista vacía = solo necesita la principal)

REGLAS_PATRON_COMBINADO = [
    # === Pagos al exterior — tienen prioridad sobre todo lo demás ===
    ("EXTERIOR",        [],                                              "Otros pagos", "alta"),
    ("NO RESIDENTE",    [],                                              "Otros pagos", "alta"),
    ("EXTRANJERO",      ["PAGO", "RETENCION"],                           "Otros pagos", "alta"),

    # IVA — variantes de escritura
    ("RETEIVA",         [],                                              "IVA", "alta"),
    ("RETE IVA",        [],                                              "IVA", "alta"),
    ("RETENCION IVA",   [],                                              "IVA", "alta"),
    ("RETENCIÓN IVA",   [],                                              "IVA", "alta"),

    # Rentas de trabajo
    ("SALARIO",         [],                                              "Rentas de trabajo", "alta"),
    ("NOMINA",          ["RETENCION", "RETEFUENTE"],                     "Rentas de trabajo", "alta"),
    ("NÓMINA",          ["RETENCION", "RETEFUENTE"],                     "Rentas de trabajo", "alta"),
    ("LABORAL",         ["RETENCION", "PAGO"],                           "Rentas de trabajo", "alta"),
    ("TRABAJO",         ["RENTA", "RENTAS"],                             "Rentas de trabajo", "alta"),

    # Honorarios y profesionales
    ("HONORARIO",       [],                                              "Honorarios", "alta"),
    ("CONSULTORIA",     [],                                              "Honorarios", "alta"),
    ("CONSULTORÍA",     [],                                              "Honorarios", "alta"),
    ("ASESORIA",        ["TECNICA", "PROFESIONAL", "JURIDICA", "CONTABLE", "TRIBUTARIA", "FINANCIERA"], "Honorarios", "alta"),
    ("ASESORÍA",        ["TÉCNICA", "PROFESIONAL", "JURÍDICA", "CONTABLE", "TRIBUTARIA", "FINANCIERA"], "Honorarios", "alta"),
    ("REVISORIA",       ["FISCAL"],                                      "Honorarios", "alta"),
    ("REVISORÍA",       ["FISCAL"],                                      "Honorarios", "alta"),
    ("VIGILANCIA",      ["FISCAL"],                                      "Honorarios", "alta"),

    # Comisiones
    ("COMISION",        [],                                              "Comisiones", "alta"),
    ("COMISIÓN",        [],                                              "Comisiones", "alta"),
    ("INTERMEDIACION",  [],                                              "Comisiones", "media"),
    ("INTERMEDIACIÓN",  [],                                              "Comisiones", "media"),

    # Servicios
    ("SERVICIO",        [],                                              "Servicios", "alta"),
    ("ASEO",            [],                                              "Servicios", "alta"),
    ("VIGILANCIA",      ["PRIVADA", "SEGURIDAD"],                        "Servicios", "alta"),
    ("MANTENIMIENTO",   [],                                              "Servicios", "media"),
    ("REPARACION",      [],                                              "Servicios", "media"),
    ("REPARACIÓN",      [],                                              "Servicios", "media"),
    ("CAPACITACION",    [],                                              "Servicios", "alta"),
    ("CAPACITACIÓN",    [],                                              "Servicios", "alta"),
    ("FLETE",           [],                                              "Servicios", "alta"),
    ("TRANSPORTE",      ["CARGA", "MERCANCIA", "MERCANCÍA"],              "Servicios", "alta"),
    ("LICENCIAM",       [],                                              "Servicios", "alta"),
    ("HOSTING",         [],                                              "Servicios", "alta"),
    ("PUBLICIDAD",      [],                                              "Servicios", "alta"),
    ("VALLA",           ["PUBLICITARIA"],                                "Servicios", "alta"),

    # Arrendamientos
    ("ARRENDAMIENT",    [],                                              "Arrendamientos", "alta"),
    ("ALQUILER",        [],                                              "Arrendamientos", "alta"),
    ("CANON",           ["ARRENDAMIENTO"],                               "Arrendamientos", "alta"),

    # Regalías y franquicia
    ("REGALIA",         [],                                              "Regalías", "alta"),
    ("REGALÍA",         [],                                              "Regalías", "alta"),
    ("FRANQUICIA",      [],                                              "Regalías", "alta"),
    ("LICENCIA",        ["USO", "MARCA", "EXPLOTACION", "EXPLOTACIÓN"],  "Regalías", "alta"),
    ("PROPIEDAD",       ["INTELECTUAL", "INDUSTRIAL"],                   "Regalías", "alta"),

    # Dividendos
    ("DIVIDENDO",       [],                                              "Dividendos", "alta"),
    ("PARTICIPACION",   ["SOCIAL", "UTILIDAD"],                          "Dividendos", "media"),
    ("PARTICIPACIÓN",   ["SOCIAL", "UTILIDAD"],                          "Dividendos", "media"),

    # Construcción
    ("CONSTRUCCION",    [],                                              "Contratos construcción", "alta"),
    ("CONSTRUCCIÓN",    [],                                              "Contratos construcción", "alta"),
    ("OBRA",            ["CIVIL", "CONSTRUCCION", "CONSTRUCCIÓN"],       "Contratos construcción", "alta"),

    # Loterías y juegos
    ("LOTER",           [],                                              "Loterías rifas", "alta"),
    ("RIFA",            [],                                              "Loterías rifas", "alta"),
    ("APUEST",          [],                                              "Loterías rifas", "alta"),
    ("PREMIO",          ["JUEGO", "AZAR", "SORTEO"],                     "Loterías rifas", "alta"),

    # Rendimientos financieros
    ("RENDIMIENTO",     ["FINANCIERO"],                                  "Rendimientos financieros", "alta"),
    ("INTERES",         ["FINANCIERO", "CDT", "PRESTAMO", "PRÉSTAMO"],   "Rendimientos financieros", "alta"),
    ("INTERÉS",         ["FINANCIERO", "CDT", "PRESTAMO", "PRÉSTAMO"],   "Rendimientos financieros", "alta"),
    ("DESCUENTO",       ["FINANCIERO"],                                  "Rendimientos financieros", "alta"),

    # Compras
    ("COMPRA",          [],                                              "Compras", "alta"),
    ("ADQUISICION",     ["BIEN", "MERCANCIA", "MERCANCÍA"],              "Compras", "alta"),
    ("ADQUISICIÓN",     ["BIEN", "MERCANCIA", "MERCANCÍA"],              "Compras", "alta"),
    ("CAFE",            ["COMPRA"],                                      "Compras", "alta"),
    ("CAFÉ",            ["COMPRA"],                                      "Compras", "alta"),
]


# =============================================================================
# 3. PALABRAS CLAVE INDIVIDUALES (último recurso)
# =============================================================================

REGLAS_PALABRA_CLAVE = [
    ("HONORARIO",      "Honorarios", "media"),
    ("COMISION",       "Comisiones", "media"),
    ("COMISIÓN",       "Comisiones", "media"),
    ("ARRENDAMIENT",   "Arrendamientos", "media"),
    ("ALQUILER",       "Arrendamientos", "media"),
    ("SERVICIO",       "Servicios", "media"),
    ("COMPRA",         "Compras", "media"),
    ("DIVIDENDO",      "Dividendos", "media"),
    ("REGALIA",        "Regalías", "media"),
    ("REGALÍA",        "Regalías", "media"),
    ("CONSTRUCCION",   "Contratos construcción", "media"),
    ("CONSTRUCCIÓN",   "Contratos construcción", "media"),
    ("LOTER",          "Loterías rifas", "media"),
    ("RIFA",           "Loterías rifas", "media"),
    ("SALARIO",        "Rentas de trabajo", "media"),
    ("LABORAL",        "Rentas de trabajo", "media"),
    ("RENDIMIENTO",    "Rendimientos financieros", "media"),
    ("FINANCIERO",     "Rendimientos financieros", "baja"),
    ("EXTERIOR",       "Otros pagos", "media"),
]


# =============================================================================
# FUNCIONES DE CLASIFICACIÓN
# =============================================================================

def _normalizar_codigo(codigo):
    """Devuelve el código sin guiones para comparaciones por prefijo."""
    if not codigo:
        return ""
    return str(codigo).replace("-", "").replace(".", "").strip()


def _coincide_prefijo_puc(codigo_sin_guiones, prefijo):
    """¿El código empieza con el prefijo (también sin guiones)?"""
    prefijo_limpio = _normalizar_codigo(prefijo)
    return prefijo_limpio and codigo_sin_guiones.startswith(prefijo_limpio)


def clasificar_concepto_detallado(cuenta_contai, nombre_cuenta):
    """
    Versión extendida que devuelve la regla aplicada y un nivel de confianza.

    Retorna dict con:
      - 'concepto'   : str (uno de los conceptos del F350)
      - 'confianza'  : 'alta' | 'media' | 'baja'
      - 'origen'     : 'codigo_puc' | 'patron_combinado' | 'palabra_clave' | 'default'
      - 'regla'      : str descriptiva de la regla que disparó la clasificación
    """
    nombre_upper = (nombre_cuenta or "").upper()
    codigo_limpio = _normalizar_codigo(cuenta_contai)

    # ---- 0. Palabras clave PRIORITARIAS sobre el nombre ----
    # Corren antes del código PUC: si el nombre de la cuenta dice claramente el
    # concepto (REGALIAS, ARRENDAMIENT, SERVICIO…), manda el nombre aunque el
    # código apunte a otra cosa. Así "23-65-70 REGALIAS…" no cae en construcción.
    for palabra, concepto in REGLAS_NOMBRE_PRIORITARIO:
        if palabra in nombre_upper:
            return {
                "concepto":  concepto,
                "confianza": "alta",
                "origen":    "nombre_prioritario",
                "regla":     f"Palabra clave prioritaria '{palabra}' en el nombre",
            }

    # ---- 1. Reglas por código PUC (prefijos más largos primero) ----
    if codigo_limpio:
        prefijos_ordenados = sorted(
            REGLAS_CODIGO_PUC.keys(),
            key=lambda k: -len(_normalizar_codigo(k)),
        )
        for prefijo in prefijos_ordenados:
            if _coincide_prefijo_puc(codigo_limpio, prefijo):
                concepto, conf = REGLAS_CODIGO_PUC[prefijo]
                return {
                    "concepto":  concepto,
                    "confianza": conf,
                    "origen":    "codigo_puc",
                    "regla":     f"Código PUC {prefijo}",
                }

    # ---- 2. Patrones combinados (palabra principal + secundarias) ----
    for principal, secundarias, concepto, conf in REGLAS_PATRON_COMBINADO:
        if principal in nombre_upper:
            if not secundarias:
                return {
                    "concepto":  concepto,
                    "confianza": conf,
                    "origen":    "patron_combinado",
                    "regla":     f"Nombre contiene '{principal}'",
                }
            for sec in secundarias:
                if sec in nombre_upper:
                    return {
                        "concepto":  concepto,
                        "confianza": conf,
                        "origen":    "patron_combinado",
                        "regla":     f"Nombre contiene '{principal}' + '{sec}'",
                    }

    # ---- 3. Palabras clave individuales ----
    for palabra, concepto, conf in REGLAS_PALABRA_CLAVE:
        if palabra in nombre_upper:
            return {
                "concepto":  concepto,
                "confianza": conf,
                "origen":    "palabra_clave",
                "regla":     f"Palabra clave '{palabra}'",
            }

    # ---- 4. Default: Otros pagos con confianza baja ----
    return {
        "concepto":  "Otros pagos",
        "confianza": "baja",
        "origen":    "default",
        "regla":     "Sin coincidencias — clasificado por defecto",
    }


def clasificar_concepto_por_cuenta(cuenta_contai, nombre_cuenta):
    """
    Versión simple: solo devuelve el concepto (string).
    Para más detalle (confianza, regla aplicada), usar clasificar_concepto_detallado().
    """
    return clasificar_concepto_detallado(cuenta_contai, nombre_cuenta)["concepto"]
