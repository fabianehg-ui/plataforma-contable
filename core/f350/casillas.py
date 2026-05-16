"""
core/f350/casillas.py — mapeo de conceptos a casillas oficiales del F350.

Estos mapeos siguen el diseño actual del Formulario 350 DIAN. Si la DIAN
cambia la numeración, hay que actualizar este archivo y nada más.

Extraído de BorradorFácil 350 v2.1.5 sin modificaciones.
"""

# =============================================================================
# RETENCIONES A TERCEROS — sección "Retenciones a título de renta"
# =============================================================================
# Cada concepto del F350 tiene 4 casillas:
#   - PJ → (base, retención)  para Personas Jurídicas
#   - PN → (base, retención)  para Personas Naturales
#
# 'Rentas de trabajo' solo aplica a PN (no hay casilla PJ).

MAPEO_CASILLAS_F350 = {
    "Honorarios":              {"PJ": (29, 42),     "PN": (79, 95)},
    "Comisiones":              {"PJ": (30, 43),     "PN": (80, 96)},
    "Servicios":               {"PJ": (31, 44),     "PN": (81, 97)},
    "Rendimientos financieros":{"PJ": (32, 45),     "PN": (82, 98)},
    "Arrendamientos":          {"PJ": (33, 46),     "PN": (83, 99)},
    "Regalías":                {"PJ": (34, 47),     "PN": (84, 100)},
    "Dividendos":              {"PJ": (35, 48),     "PN": (85, 101)},
    "Compras":                 {"PJ": (36, 49),     "PN": (86, 102)},
    "Contratos construcción":  {"PJ": (38, 51),     "PN": (88, 104)},
    "Loterías rifas":          {"PJ": (39, 52),     "PN": (90, 106)},
    "Otros pagos":             {"PJ": (41, 54),     "PN": (92, 108)},
    "Rentas de trabajo":       {"PJ": (None, None), "PN": (77, 93)},
}


# =============================================================================
# AUTORRETENCIONES — sección "Autorretenciones a título de renta"
# =============================================================================
# Aquí cada concepto tiene 2 casillas: (base, retención).
# Solo se diligencia la columna "Personas Jurídicas".

AUTORRET_CASILLAS_F350 = {
    "Contribuyentes exonerados 114-1": (59, 68),
    "Ventas":                          (60, 69),
    "Honorarios":                      (61, 70),
    "Comisiones":                      (62, 71),
    "Servicios":                       (63, 72),
    "Rendimientos financieros":        (64, 73),
    "Otros conceptos":                 (67, 76),
}


# =============================================================================
# CONCEPTOS EN EL ORDEN VISUAL DEL F350
# =============================================================================
# Útil para la UI y para el PDF: muestra los conceptos en el orden en que
# aparecen en el formulario oficial.

CONCEPTOS_ORDEN_F350 = [
    "Rentas de trabajo",
    "Honorarios",
    "Comisiones",
    "Servicios",
    "Rendimientos financieros",
    "Arrendamientos",
    "Regalías",
    "Dividendos",
    "Compras",
    "Contratos construcción",
    "Loterías rifas",
    "Otros pagos",
]


def obtener_casillas_f350(concepto, tipo_tercero, es_extranjero=False):
    """
    Dado un concepto (ej. 'Servicios') y tipo ('Persona Jurídica' o
    'Persona Natural'), retorna tupla (casilla_base, casilla_retencion) del
    formulario 350.

    Para extranjeros se reportan en casillas 55/57 (otros pagos al exterior).
    """
    if es_extranjero:
        return (55, 57)

    tipo_key = "PN" if tipo_tercero == "Persona Natural" else "PJ"
    if concepto in MAPEO_CASILLAS_F350:
        return MAPEO_CASILLAS_F350[concepto][tipo_key]
    # Default si el concepto no existe: cae en "Otros pagos"
    return (41, 54) if tipo_key == "PJ" else (92, 108)


def mapear_cuenta_contai_a_casilla(cuenta_contai, nombre_cuenta):
    """
    DEPRECATED. Mantenido por compatibilidad con código antiguo del .exe.
    Para código nuevo, usar:
        concepto = clasificar_concepto_por_cuenta(cuenta, nombre)
        (cas_b, cas_r) = obtener_casillas_f350(concepto, tipo)
    """
    # Import diferido para evitar ciclos
    from core.f350.clasificador import clasificar_concepto_por_cuenta
    concepto = clasificar_concepto_por_cuenta(cuenta_contai, nombre_cuenta)
    cas_base, cas_ret = obtener_casillas_f350(concepto, "Persona Jurídica")
    return cas_ret if cas_ret else 54
