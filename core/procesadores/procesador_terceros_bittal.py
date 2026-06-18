"""
core/procesadores/procesador_terceros_bittal.py

Convierte el export de Terceros de bittal (ThirdParties/General/List.aspx) al
formato NITS de Contai (20 columnas), reusando el motor de exportador_nits_siigo.

Reglas:
- El NIT/cédula se limpia con normalizar_nit (sin puntos, sin DV, sin guiones).
- La naturaleza (N/J) y el tipo de documento (C/A) se deciden por la regla de
  DÍGITOS del NIT (es_persona_natural), NO por el 'Tipo Persona' de bittal, que
  es poco confiable (p. ej. marca empresas como 'Persona Natural').
- Se eliminan filas sin NIT válido y duplicados por NIT normalizado.
- Si bittal trae los nombres ya descompuestos y el tercero es natural, se
  prefieren esos sobre la heurística de descomposición.
"""
from __future__ import annotations

import pandas as pd

from core.procesadores.exportador_nits_siigo import (
    construir_fila_siigo, normalizar_nit, generar_excel_nits_siigo,
    es_persona_natural,
)

# Columnas del export de bittal (con sus tildes / typos reales).
COL = {
    "id": "Identificación",
    "razon": "Razón Social Compania",
    "nombre": "Nombre",
    "otro_nombre": "Otro Nombre",
    "apellido": "Apellido",
    "segundo_apellido": "Segundo Apellido",
    "direccion": "Dirección",
    "ciudad": "Ciudad",
    "telefono": "Télefono",
    "celular": "Celular",
    "email": "Correo Electrónico",
    "regimen": "Responsabilidad Tributaria",
}

COLUMNAS_NITS = [
    "NIT", "C", "RAZON SOCIAL", "DIRECCION", "CIUDAD", "TEL", "MPIO",
    "V", "R", "CP",
    "PRIMER NOMBRE", "SEGUNDO NOMBRE", "PRIMER APELLIDO", "SEGUNDO APELLIDO",
    "E-MAIL", "CELULAR", "PLAZO", "ACTIVIDAD ECONOMICA",
    "INDICATIVO", "NATURALEZA",
]


def _col(df: pd.DataFrame, key: str) -> pd.Series:
    """Serie de la columna pedida; tolera variantes de tildes/espacios y ausencia."""
    nombre = COL[key]
    if nombre in df.columns:
        return df[nombre].fillna("")
    objetivo = nombre.lower().replace(" ", "")
    for c in df.columns:
        if str(c).lower().replace(" ", "") == objetivo:
            return df[c].fillna("")
    return pd.Series([""] * len(df), index=df.index)


def _nombre_tercero(rs, nom, otro, ape, ape2) -> str:
    """Reconstruye el nombre completo. Si hay Razón Social, se usa; si no, se
    arma con los nombres/apellidos de bittal (que vienen en campos desordenados)
    y se limpia para que la heurística de descomposición lo parta bien."""
    rs = (rs or "").strip()
    if rs:
        full = rs
    else:
        full = " ".join(p.strip() for p in (nom, otro, ape, ape2) if (p or "").strip())
    full = full.replace("/", " ").replace("\\", " ")
    return " ".join(full.split())


def procesar_terceros_bittal(archivo):
    """Lee el xlsx de Terceros de bittal y devuelve (xlsx_bytes, resumen)."""
    df = pd.read_excel(archivo, dtype=str).fillna("")

    s_id, s_rs = _col(df, "id"), _col(df, "razon")
    s_nom, s_otro = _col(df, "nombre"), _col(df, "otro_nombre")
    s_ape, s_ape2 = _col(df, "apellido"), _col(df, "segundo_apellido")
    s_dir, s_ciu = _col(df, "direccion"), _col(df, "ciudad")
    s_tel, s_cel = _col(df, "telefono"), _col(df, "celular")
    s_mail, s_reg = _col(df, "email"), _col(df, "regimen")

    filas, vistos = [], set()
    sin_nit = duplicados = 0
    for i in df.index:
        nit = normalizar_nit(s_id[i])
        if not nit:
            sin_nit += 1
            continue

        nombre = _nombre_tercero(s_rs[i], s_nom[i], s_otro[i], s_ape[i], s_ape2[i])

        # Jurídica con DV pegado al final (10 díg): recortar el último dígito
        # para dejar la base de 9. Las formas con guion (-3, -) ya las limpia
        # normalizar_nit. La naturaleza se decide por dígitos del NIT.
        es_juridica = not es_persona_natural(nombre, s_reg[i], nit)
        if es_juridica and len(nit) == 10:
            nit = nit[:-1]

        if nit in vistos:
            duplicados += 1
            continue
        vistos.add(nit)

        # construir_fila_siigo arma las 20 columnas y, si es natural, descompone
        # el nombre en Primer/Segundo Nombre y Primer/Segundo Apellido.
        fila = construir_fila_siigo(
            nit=nit, nombre=nombre,
            direccion=s_dir[i], ciudad=s_ciu[i],
            telefono=s_tel[i], email=s_mail[i], celular=s_cel[i],
            regimen=s_reg[i],
        )
        filas.append(fila)

    out = pd.DataFrame(filas, columns=COLUMNAS_NITS)
    xlsx = generar_excel_nits_siigo(out)
    resumen = {
        "terceros": len(out),
        "juridicas": int((out["NATURALEZA"] == "J").sum()),
        "naturales": int((out["NATURALEZA"] == "N").sum()),
        "duplicados": duplicados,
        "sin_nit": sin_nit,
    }
    return xlsx, resumen
