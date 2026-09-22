"""
22_Maestros.py — Maestros de INTEGRAL: Terceros, Plan de cuentas, Centros de costo.

Permite listar y CARGAR MASIVAMENTE desde un plano (.txt/.csv/.xlsx):
    - Terceros (NITs): NIT, NOMBRE, [TIPO, DV, RÉGIMEN, EMAIL, TEL, DIR, MUNICIPIO]
    - Plan de cuentas: CÓDIGO, NOMBRE, [NATURALEZA, TIPO, MANEJA NIT/CC/BASE]
    - Centros de costo: CÓDIGO, NOMBRE
Reconoce las columnas por su encabezado; si el plano no trae encabezados,
usa el orden posicional.
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import io

import streamlit as st
import pandas as pd

from auth.login import require_auth, sidebar_user_info
from auth.empresas import seleccionar_empresa_sidebar, require_rol
from db.supabase_client import get_supabase
from core.contable import servicio_contable as cont


require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()
emp = require_rol(["admin", "operador"])
sb = get_supabase()

st.title("🗂️ Maestros")
st.caption(f"Empresa activa: **{emp['razon_social']}** · Terceros, plan de cuentas y centros de costo")
st.markdown("---")


def _leer_terceros_contai(lineas) -> pd.DataFrame:
    """Parsea el export de TERCEROS de Contai (ANCHO FIJO, con relleno de bytes
    nulos). Extrae NIT y NOMBRE (razón social o nombres+apellidos) de cada
    registro. Devuelve columnas nit, nombre, tipo_persona."""
    import re
    LET = re.compile(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]{3,}")

    def limpiar(n: str) -> str:
        n = re.sub(r"\s+", " ", n).strip()
        n = re.sub(r"\b0?\d{4,5}S?N?\d{0,3}\b", "", n)   # códigos ciudad/municipio
        n = re.sub(r"\d{5,}", "", n)
        n = re.sub(r"\bSN\b", "", n)
        return re.sub(r"\s+", " ", n).strip(" -0")

    filas, vistos = [], set()
    for s in lineas[1:]:
        if "\t" in s:  # algunas filas vienen con tabs en vez de ancho fijo
            p = [x.strip() for x in s.split("\t") if x.strip()]
            if not p:
                continue
            nit = "".join(c for c in p[0].split()[0] if c.isdigit()) if p[0].split() else ""
            nombre, tipo = " ".join(p[1:]).strip(), ""
        else:
            nit = s[0:11].strip()
            razon = s[12:42].strip()
            pn, sn2, pa, sa = s[104:134].strip(), s[134:164].strip(), s[164:194].strip(), s[194:224].strip()
            persona = " ".join(x for x in (pn, sn2, pa, sa) if x).strip()
            if persona and not razon:
                nombre, tipo = persona, "N"
            else:
                nombre, tipo = razon, ""
        nitd = "".join(c for c in nit if c.isdigit())
        nombre = limpiar(nombre)
        if not nitd or len(nitd) < 4 or not LET.search(nombre):
            continue
        if nitd in vistos:
            continue
        vistos.add(nitd)
        filas.append({"nit": nitd, "nombre": nombre, "tipo_persona": tipo})
    return pd.DataFrame(filas)


def _leer_tabla(archivo) -> pd.DataFrame:
    """Lee un plano (.xlsx/.txt/.csv) a DataFrame (como texto). Tolera los
    archivos que se bajan de Contai: quita bytes nulos y reconoce el export
    de terceros en ancho fijo."""
    nombre = archivo.name.lower()
    if nombre.endswith((".xlsx", ".xls")):
        return pd.read_excel(archivo, dtype=str).fillna("")
    raw = archivo.read()
    if isinstance(raw, (bytes, bytearray)):
        raw = bytes(raw).replace(b"\x00", b"")        # Contai rellena con NUL
        texto = raw.decode("latin-1")
    else:
        texto = str(raw).replace("\x00", "")
    lineas = [l for l in texto.splitlines() if l.strip() and not l.lower().startswith("sep=")]
    if not lineas:
        return pd.DataFrame()
    cab = lineas[0]
    # ¿Export de TERCEROS de Contai (ancho fijo)? Encabezado con RAZON SOCIAL y
    # sin delimitador utilizable.
    if ("\t" not in cab and ";" not in cab) and "RAZON SOCIAL" in cab.upper():
        return _leer_terceros_contai(lineas)
    # Detectar delimitador por la primera línea
    delim = "\t" if "\t" in cab else (";" if ";" in cab else ("," if "," in cab else "\t"))
    filas = [l.split(delim) for l in lineas]
    df = pd.DataFrame(filas).fillna("")
    # ¿Primera fila es encabezado? (si contiene texto no numérico típico)
    primera = " ".join(str(x) for x in df.iloc[0]).upper()
    if any(k in primera for k in ("NIT", "NOMBRE", "CODIGO", "CÓDIGO", "CUENTA", "RAZON")):
        df.columns = [str(x).strip() for x in df.iloc[0]]
        df = df.iloc[1:].reset_index(drop=True)
    # quitar caracteres de control residuales en celdas de texto
    return df.applymap(lambda x: str(x).replace("\x00", "").strip() if isinstance(x, str) else x)


def _bloque_import(titulo, ayuda, key, fn_import):
    """UI genérica: subir archivo -> vista previa -> importar."""
    st.markdown(f"#### 📥 Importar {titulo} desde plano")
    st.caption(ayuda)
    archivo = st.file_uploader("Archivo (.txt / .csv / .xlsx)",
                               type=["txt", "csv", "xlsx", "xls"], key=f"up_{key}")
    if archivo is not None:
        try:
            df = _leer_tabla(archivo)
        except Exception as e:
            st.error(f"No se pudo leer el archivo: {e}")
            return
        st.markdown(f"**Vista previa** ({len(df)} filas)")
        st.dataframe(df.head(15), use_container_width=True, hide_index=True)
        if st.button(f"📥 Importar {titulo}", type="primary", key=f"btn_{key}"):
            try:
                with st.spinner("Importando…"):
                    n = fn_import(df)
                st.success(f"✅ {n} {titulo} importados/actualizados.")
                st.rerun()
            except Exception as e:
                st.error(f"No se pudo importar (¿permiso de admin?): {e}")


tab_ter, tab_cta, tab_cc = st.tabs([
    "👥 Terceros (NITs)",
    "📚 Plan de cuentas",
    "🏷️ Centros de costo",
])


# ---------------- Terceros ----------------
with tab_ter:
    st.markdown("### 👥 Terceros")
    q = st.text_input("Buscar por nombre", key="q_ter")
    terceros = cont.listar_terceros(sb, emp["id"], query=q or None)
    st.caption(f"{len(terceros)} terceros")
    if terceros:
        st.dataframe(
            pd.DataFrame([{
                "NIT": t["nit"], "Nombre": t["nombre"],
                "Tipo": t.get("tipo_persona") or "", "Régimen": t.get("regimen") or "",
            } for t in terceros]),
            use_container_width=True, hide_index=True, height=350,
        )
    st.markdown("---")
    _bloque_import(
        "terceros",
        "Columnas: NIT, NOMBRE y opcionales TIPO (N/J), DV, RÉGIMEN, EMAIL, "
        "TELÉFONO, DIRECCIÓN, MUNICIPIO. Sin encabezados asume: NIT, NOMBRE, TIPO.",
        "ter",
        lambda df: cont.importar_terceros(sb, emp["id"], df),
    )


# ---------------- Plan de cuentas ----------------
with tab_cta:
    st.markdown("### 📚 Plan de cuentas (PUC)")
    cuentas = cont.listar_plan_cuentas(sb, emp["id"])
    st.caption(f"{len(cuentas)} cuentas")
    if cuentas:
        st.dataframe(
            pd.DataFrame([{
                "Código": c["codigo"], "Nombre": c["nombre"],
                "Nat.": c.get("naturaleza") or "",
                "NIT": "S" if c.get("maneja_nit") else "",
                "CC": "S" if c.get("maneja_cc") else "",
            } for c in cuentas]),
            use_container_width=True, hide_index=True, height=350,
        )
    st.markdown("---")
    _bloque_import(
        "cuentas",
        "Columnas: CÓDIGO, NOMBRE y opcionales NATURALEZA (D/C), TIPO, "
        "MANEJA NIT, MANEJA CC, MANEJA BASE (S/N). Sin encabezados asume: "
        "CÓDIGO, NOMBRE, NATURALEZA.",
        "cta",
        lambda df: cont.importar_cuentas_desde_df(sb, emp["id"], df),
    )


# ---------------- Centros de costo ----------------
def _importar_cc(df):
    m = cont._mapear_columnas(df, {"codigo": "codigo", "cod": "codigo",
                                   "nombre": "nombre", "descripcion": "nombre"},
                              ["codigo", "nombre"])
    n = 0
    for _, r in m.iterrows():
        cod = str(r.get("codigo", "")).strip()
        nom = str(r.get("nombre", "")).strip()
        if cod and nom:
            cont.upsert_centro_costo(sb, emp["id"], cod, nom)
            n += 1
    return n


with tab_cc:
    st.markdown("### 🏷️ Centros de costo")
    ccs = cont.listar_centros_costo(sb, emp["id"])
    st.caption(f"{len(ccs)} centros de costo")
    if ccs:
        st.dataframe(
            pd.DataFrame([{"Código": c["codigo"], "Nombre": c["nombre"]} for c in ccs]),
            use_container_width=True, hide_index=True, height=300,
        )
    st.markdown("---")
    _bloque_import(
        "centros de costo",
        "Columnas: CÓDIGO, NOMBRE. Sin encabezados asume ese orden.",
        "cc",
        _importar_cc,
    )
