"""
Normalización de NITs.

Regla: un NIT debe quedar SIN puntos y SIN dígito de verificación (-X),
para que sea comparable en todo el flujo (lectura, matching, salida).

Ejemplos:
    '900.473.959-1'      → '900473959'
    '39.177.488-2'       → '39177488'
    '  800.180.687-2 '   → '800180687'
    '900473959'          → '900473959' (ya estaba limpio)
    '22.222.222.222-3'   → '22222222222' (CONSUMIDOR FINAL, 11 dígitos)
    '222222222'          → '222222222'   (GENÉRICO MENOR CUANTÍA, 9 dígitos)

NITs genéricos del sistema:
    NIT_CONSUMIDOR_FINAL = '22222222222'  → FE / PVFE (ventas al público)
    NIT_GENERICO_MENOR   = '222222222'    → GBF, DV, DV3, DW, CM
"""
import re


# NITs genéricos del sistema (ya están normalizados)
NIT_CONSUMIDOR_FINAL = "22222222222"   # 11 dígitos - ventas FE/POS
NIT_GENERICO_MENOR = "222222222"        # 9 dígitos - menor cuantía


def normalizar_nit(nit) -> str:
    """Quita puntos, espacios y dígito de verificación (-X).

    Retorna '' si la entrada es None o vacía.
    """
    if nit is None:
        return ""
    s = str(nit).strip()
    if not s:
        return ""
    # Quitar decimales sobrantes de Excel ("900473959.0")
    if s.endswith(".0"):
        s = s[:-2]
    # Quitar puntos y espacios
    s = s.replace(".", "").replace(" ", "")
    # Quitar dígito de verificación (-X donde X es 0-9)
    s = re.sub(r"-\d$", "", s)
    # Limpiar guiones sueltos
    s = s.replace("-", "")
    return s


def es_nit_generico(nit) -> bool:
    """True si el NIT es uno de los genéricos del sistema."""
    n = normalizar_nit(nit)
    return n in (NIT_CONSUMIDOR_FINAL, NIT_GENERICO_MENOR)
