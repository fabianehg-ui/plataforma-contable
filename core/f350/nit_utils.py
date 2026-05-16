"""
core/f350/nit_utils.py — utilidades para el NIT colombiano.

Funciones:
    inferir_tipo_persona(nit) — clasifica un NIT en PN/PJ/extranjero según
                                los rangos oficiales DIAN
    calcular_dv(nit)          — calcula el dígito de verificación oficial
    formato_nit(nit)          — formatea como "900.451.388-1"
    formato_moneda(valor)     — formato colombiano "$1.234.567"

Extraído de BorradorFácil 350 v2.1.5 sin modificaciones de lógica.
"""


def inferir_tipo_persona(nit_str):
    """
    Aplica la regla oficial del NIT colombiano.

    Retorna: (tipo, es_extranjero, es_valido, rango)
        - tipo: 'Persona Natural' | 'Persona Jurídica' | 'REVISAR'
        - es_extranjero: bool
        - es_valido: bool
        - rango: descripción del rango usado

    Rangos según numeración oficial DIAN:
        10.000 – 99.999.999       → Cédula antigua (PN)
        600.000.000 – 799.999.999 → NIT DIAN extranjero (PN)
        800.000.000 – 999.999.999 → NIT DIAN empresa (PJ)
        1.000.000.000 – 1.999.999.999 → Cédula moderna (PN)
    """
    try:
        nit_limpio = ''.join(c for c in str(nit_str) if c.isdigit())
        nit = int(nit_limpio)
    except (ValueError, TypeError):
        return ("REVISAR", False, False, "NIT inválido")

    if 10_000 <= nit <= 99_999_999:
        return ("Persona Natural", False, True, "Cédula antigua")
    if 600_000_000 <= nit <= 799_999_999:
        return ("Persona Natural", True, True, "NIT DIAN extranjero")
    if 800_000_000 <= nit <= 999_999_999:
        return ("Persona Jurídica", False, True, "NIT DIAN empresa")
    if 1_000_000_000 <= nit <= 1_999_999_999:
        return ("Persona Natural", False, True, "Cédula moderna")

    return ("REVISAR", False, False, "Fuera de rangos conocidos")


def calcular_dv(nit_str):
    """
    Calcula el dígito de verificación del NIT colombiano (algoritmo oficial DIAN).

    Pasos:
      1. Limpiar el NIT (solo dígitos).
      2. Invertir y multiplicar cada dígito por los factores fijos.
      3. Sumar todo.
      4. Tomar el residuo mod 11.
      5. Si residuo < 2 → DV = residuo. Si no → DV = 11 - residuo.
    """
    try:
        nit_limpio = ''.join(c for c in str(nit_str) if c.isdigit())
        if not nit_limpio:
            return ""
        factores = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]
        suma = 0
        nit_invertido = nit_limpio[::-1]
        for i, digito in enumerate(nit_invertido):
            if i < len(factores):
                suma += int(digito) * factores[i]
        residuo = suma % 11
        if residuo < 2:
            return str(residuo)
        return str(11 - residuo)
    except Exception:
        return ""


def formato_nit(nit_str):
    """Formato colombiano: 900.451.388-1"""
    try:
        nit_limpio = ''.join(c for c in str(nit_str) if c.isdigit())
        if len(nit_limpio) < 4:
            return nit_str
        dv = calcular_dv(nit_limpio)
        num = int(nit_limpio)
        formateado = f"{num:,}".replace(",", ".")
        return f"{formateado}-{dv}"
    except Exception:
        return nit_str


def formato_moneda(valor):
    """Formato colombiano: $1.234.567"""
    try:
        num = int(round(float(valor)))
        return f"${num:,}".replace(",", ".")
    except (ValueError, TypeError):
        return "$0"
