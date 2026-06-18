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

import csv
import io

import pandas as pd

from core.procesadores.exportador_nits_siigo import (
    construir_fila_siigo, normalizar_nit, descomponer_nombre_persona,
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

# Sufijos societarios inequívocos: fuerzan "jurídica" aunque el NIT parezca
# cédula (cubre empresas con NIT mal digitado en el origen).
_SUFIJOS_JURIDICA = ("SAS", "S.A.S", "S A S", "LTDA", "S.A.", "& CIA", "S EN C")


def _es_natural(nit: str, nombre: str) -> bool:
    """Decide natural vs jurídica priorizando los DÍGITOS del NIT (no el texto
    del informe de bittal, que viene mal): jurídica = NIT de 9 dígitos que
    empieza en 8 o 9; el resto (cédulas de 6-10 dígitos) es natural. Un sufijo
    societario inequívoco en el nombre fuerza jurídica."""
    rs = (nombre or "").upper().strip()
    for s in _SUFIJOS_JURIDICA:
        if rs.endswith(s) or rs.endswith(s + "."):
            return False
    return not (len(nit) == 9 and nit[:1] in ("8", "9"))


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
    sin_nit = duplicados = sin_nombre = 0
    for i in df.index:
        nit = normalizar_nit(s_id[i])
        if not nit:
            sin_nit += 1
            continue

        nombre = _nombre_tercero(s_rs[i], s_nom[i], s_otro[i], s_ape[i], s_ape2[i])
        if not nombre.strip():
            # Sin nombre en el origen (bittal) -> se omite.
            sin_nombre += 1
            continue

        # DV pegado en jurídicas de 10 díg que empiezan en 8/9 -> base de 9.
        if len(nit) == 10 and nit[:1] in ("8", "9"):
            nit = nit[:-1]

        natural = _es_natural(nit, nombre)

        # Si quedó jurídica (p. ej. por sufijo societario) y aún tiene 10 díg,
        # también se le recorta el DV para dejar la base de 9.
        if not natural and len(nit) == 10:
            nit = nit[:-1]

        if nit in vistos:
            duplicados += 1
            continue
        vistos.add(nit)

        fila = construir_fila_siigo(
            nit=nit, nombre=nombre,
            direccion=s_dir[i], ciudad=s_ciu[i],
            telefono=s_tel[i], email=s_mail[i], celular=s_cel[i],
            regimen=s_reg[i],
        )
        # La clasificación manda por DÍGITOS del NIT (no por lo que diga bittal).
        fila["NATURALEZA"] = "N" if natural else "J"
        fila["C"] = "C" if natural else "A"
        if natural:
            p1, p2, a1, a2 = descomponer_nombre_persona(nombre)
            fila["PRIMER NOMBRE"], fila["SEGUNDO NOMBRE"] = p1, p2
            fila["PRIMER APELLIDO"], fila["SEGUNDO APELLIDO"] = a1, a2
        else:
            fila["PRIMER NOMBRE"] = fila["SEGUNDO NOMBRE"] = ""
            fila["PRIMER APELLIDO"] = fila["SEGUNDO APELLIDO"] = ""
        filas.append(fila)

    out = pd.DataFrame(filas, columns=COLUMNAS_NITS)
    # Código DANE de municipio con cero a la izquierda (05001 = Medellín). Al
    # entregar TXT no se pierde, a diferencia de re-guardar el xlsx en Excel.
    out["MPIO"] = out["MPIO"].apply(
        lambda x: str(x).zfill(5) if str(x).strip().isdigit() else x
    )
    txt = _df_a_txt_tab(out)
    resumen = {
        "terceros": len(out),
        "juridicas": int((out["NATURALEZA"] == "J").sum()),
        "naturales": int((out["NATURALEZA"] == "N").sum()),
        "duplicados": duplicados,
        "sin_nit": sin_nit,
        "sin_nombre": sin_nombre,
    }
    return txt, resumen


def _df_a_txt_tab(df: pd.DataFrame) -> bytes:
    """Genera TXT delimitado por tabulaciones (UTF-8, CRLF). Se entrega como
    texto para que Contai no pierda los ceros a la izquierda de los códigos."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter="\t", lineterminator="\r\n")
    w.writerow(list(df.columns))
    for _, row in df.iterrows():
        w.writerow(["" if pd.isna(v) else str(v) for v in row])
    return buf.getvalue().encode("utf-8")
