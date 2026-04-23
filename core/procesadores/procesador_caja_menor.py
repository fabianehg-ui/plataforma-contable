"""
Procesador de egresos de Caja Menor - versión web.

Adaptado del procesador_caja_menor.py del .exe original.

Cambios vs versión escritorio:
    - Recibe file-like objects (BytesIO) en vez de rutas de archivo
    - Recibe un objeto Configuracion explícito en vez de usar módulo global
    - Retorna DataFrame + log de texto, en vez de imprimir a stdout

Estructura del archivo esperado (RadGridExport de egresos):
  Col A = Consecutivo (ej: CEG4739)
  Col B = Cancela     (mismo CEG = Tipo 1, DSxxx = Tipo 2)
  Col C = Identificación (NIT/Cédula del beneficiario)
  Col D = Nombres      (nombre del beneficiario)
  Col E = Fecha        (dd/mm/yyyy)
  Col F = Sucursal
  Col G = Concepto
  Col H = Proyecto
  Col I = Valor        ($ 53.900)
"""
from __future__ import annotations
import io
import re
from typing import Optional, List, Dict, Tuple
import pandas as pd

from core.utils.configuracion_web import Configuracion


# ============================================================
# Utilidades (iguales que en la versión escritorio)
# ============================================================

def _normalizar(texto):
    if texto is None:
        return ""
    t = str(texto).strip().upper()
    for a, b in [("Á", "A"), ("É", "E"), ("Í", "I"), ("Ó", "O"),
                 ("Ú", "U"), ("Ñ", "N")]:
        t = t.replace(a, b)
    return re.sub(r"\s+", " ", t)


def _limpiar_valor(v):
    """Convierte '$ 53.900' en int (pesos colombianos)."""
    if v is None:
        return 0
    if isinstance(v, (int, float)):
        return int(round(v))
    s = str(v).replace("$", "").strip()
    if "," in s:
        entero, _, _dec = s.partition(",")
        s = entero.replace(".", "")
    else:
        s = s.replace(".", "")
    try:
        return int(s)
    except ValueError:
        return 0


def _formatear_fecha(fecha_str):
    """Convierte 'dd/mm/yyyy' a 'MM/DD/YYYY'."""
    if not fecha_str:
        return ""
    s = str(fecha_str).strip()
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        dia, mes, anio = m.groups()
        return f"{int(mes):02d}/{int(dia):02d}/{anio}"
    return s


# ============================================================
# Lector robusto de archivos (HTML disfrazado / xlsx)
# ============================================================

def _leer_archivo_caja_menor(archivo) -> pd.DataFrame:
    """Lee un archivo de caja menor. 'archivo' puede ser:
        - bytes (el contenido del archivo)
        - file-like (BytesIO, UploadedFile de Streamlit, etc.)

    Prueba varios métodos porque el archivo puede venir en HTML disfrazado
    (típico RadGrid), .xlsx real o .xls binario.
    """
    # Normalizar a bytes
    if hasattr(archivo, "read"):
        contenido = archivo.read()
        if hasattr(archivo, "seek"):
            archivo.seek(0)
    elif isinstance(archivo, (bytes, bytearray)):
        contenido = bytes(archivo)
    else:
        raise TypeError(f"Tipo de archivo no soportado: {type(archivo)}")

    # Detectar si es HTML mirando los primeros bytes
    primeros = contenido[:200].lower()
    es_html = (
        b"<html" in primeros
        or b"<!doctype" in primeros
        or b"<table" in primeros
    )

    # Método 1: HTML (RadGrid)
    if es_html:
        try:
            tablas = pd.read_html(io.BytesIO(contenido), header=0)
            if tablas:
                return tablas[0]
        except Exception:
            pass

    # Método 2: xlsx real con openpyxl
    try:
        return pd.read_excel(
            io.BytesIO(contenido), sheet_name=0, engine="openpyxl"
        )
    except Exception:
        pass

    # Método 3: read_excel sin engine
    try:
        return pd.read_excel(io.BytesIO(contenido), sheet_name=0)
    except Exception:
        pass

    # Método 4: último intento forzar HTML
    try:
        tablas = pd.read_html(io.BytesIO(contenido), header=0)
        if tablas:
            return tablas[0]
    except Exception:
        pass

    raise ValueError(
        "No se pudo leer el archivo de caja menor. "
        "Asegúrate de que sea un archivo Excel válido o un export RadGrid."
    )


# ============================================================
# Resolución de cuenta por beneficiario / DS
# ============================================================

def _cuenta_por_beneficiario(nombre: str, cfg: Configuracion) -> Optional[str]:
    if not nombre:
        return None
    nombre_norm = _normalizar(nombre)
    for regla in cfg.caja_menor_beneficiarios():
        palabra = _normalizar(regla["palabra_clave"])
        if palabra and palabra in nombre_norm:
            return regla["cuenta"]
    return None


def _cargar_mapeo_ds(archivo_compras) -> Dict[str, str]:
    """Si hay archivo de compras del mes, extrae el mapeo DSxxx → cuenta.

    NOTA: La lógica original usa procesador_compras que aún no está migrado.
    Por ahora retornamos un dict vacío; cuando migres procesador_compras,
    lo enganchas aquí.
    """
    if archivo_compras is None:
        return {}
    # TODO: cuando migres procesador_compras, importarlo aquí y delegarle
    # el parseo para devolver el mapeo DS → cuenta contrapartida.
    return {}


# ============================================================
# Función principal
# ============================================================

def procesar_caja_menor(
    archivo_caja_menor,
    cfg: Configuracion,
    archivo_compras=None,
) -> Tuple[pd.DataFrame, List[str]]:
    """Procesa el archivo de caja menor y genera el DataFrame plano.

    Args:
        archivo_caja_menor: file-like o bytes del Excel de egresos
        cfg: Configuracion de la empresa
        archivo_compras: (opcional) archivo de compras del mes para resolver
                         cuentas de egresos Tipo 2 (CEG que cancela DSxxx)

    Returns:
        (df_plano, log_mensajes)
        df_plano: DataFrame con las columnas del plano contable
        log_mensajes: lista de strings para mostrar al usuario
    """
    log: List[str] = []

    COMPROBANTE = cfg.codigo_comprobante("CM", "13")
    CC_DEFAULT = cfg.parametro("CENTRO_COSTOS_DEFAULT", "PRINCIPAL")
    CUENTA_CAJA = cfg.parametro("CUENTA_CAJA_MENOR_EGRESO", "11050500")
    CUENTA_T1 = cfg.parametro("CUENTA_CAJA_MENOR_DEFAULT_T1", "23359501")
    CUENTA_T2 = cfg.parametro("CUENTA_CAJA_MENOR_DEFAULT_T2", "22050501")

    df = _leer_archivo_caja_menor(archivo_caja_menor)
    df.columns = [str(c).strip() for c in df.columns]

    cols_norm = {_normalizar(c): c for c in df.columns}

    def col(nombre):
        return cols_norm.get(_normalizar(nombre))

    col_consec = col("Consecutivo")
    col_cancela = col("Cancela")
    col_ident = col("Identificación") or col("Identificacion")
    col_nombre = col("Nombres")
    col_fecha = col("Fecha")
    col_sucursal = col("Sucursal")
    col_valor = col("Valor")

    faltantes = [
        n for n, c in [
            ("Consecutivo", col_consec),
            ("Cancela", col_cancela),
            ("Identificación", col_ident),
            ("Nombres", col_nombre),
            ("Fecha", col_fecha),
            ("Valor", col_valor),
        ] if c is None
    ]
    if faltantes:
        raise ValueError(
            f"El archivo de caja menor no tiene las columnas esperadas. "
            f"Faltan: {faltantes}"
        )

    mapeo_ds = _cargar_mapeo_ds(archivo_compras)
    if mapeo_ds:
        log.append(f"Mapeo DS cargado: {len(mapeo_ds)} documentos soporte")

    filas_salida = []
    stats = {"tipo1": 0, "tipo2": 0, "tipo2_nf": 0, "sin_mapeo_t1": 0}
    advertencias = []

    for _, fila in df.iterrows():
        consec = str(fila[col_consec]).strip() if pd.notna(fila[col_consec]) else ""
        cancela = str(fila[col_cancela]).strip() if pd.notna(fila[col_cancela]) else ""
        nit = str(fila[col_ident]).strip() if pd.notna(fila[col_ident]) else ""
        nombre = str(fila[col_nombre]).strip() if pd.notna(fila[col_nombre]) else ""
        fecha = _formatear_fecha(str(fila[col_fecha])) if pd.notna(fila[col_fecha]) else ""
        valor = _limpiar_valor(fila[col_valor])

        if nit.endswith(".0"):
            nit = nit[:-2]

        if not consec or valor == 0:
            continue

        sucursal_val = ""
        if col_sucursal and pd.notna(fila[col_sucursal]):
            sucursal_val = str(fila[col_sucursal]).strip()
        centro = sucursal_val if sucursal_val else CC_DEFAULT

        es_tipo_2 = cancela.upper().startswith("DS")

        if es_tipo_2:
            stats["tipo2"] += 1
            cuenta_debito = mapeo_ds.get(cancela)
            if cuenta_debito is None:
                stats["tipo2_nf"] += 1
                cuenta_debito = CUENTA_T2
                advertencias.append(
                    f"[{consec}] Cancela '{cancela}' no está en archivo de compras. "
                    f"Se usó cuenta por defecto {CUENTA_T2}."
                )
            doc_ref = cancela
        else:
            stats["tipo1"] += 1
            cuenta_debito = _cuenta_por_beneficiario(nombre, cfg)
            if cuenta_debito is None:
                stats["sin_mapeo_t1"] += 1
                cuenta_debito = CUENTA_T1
                if nombre:
                    advertencias.append(
                        f"[{consec}] Beneficiario '{nombre}' sin regla de mapeo. "
                        f"Se usó {CUENTA_T1}."
                    )
            doc_ref = consec

        detalle = nombre.upper() if nombre else f"EGRESO {consec}"

        base_fila = {
            "COMPROBANTE": COMPROBANTE,
            "FECHA": fecha,
            "DOCUMENTO": consec,
            "DOCUMENTO REFERENCIA": doc_ref,
            "NIT": nit,
            "CENTRO DE COSTOS": centro,
        }

        # Débito a la cuenta destino
        filas_salida.append({
            **base_fila,
            "CUENTA": cuenta_debito,
            "DETALLE": detalle,
            "TIPO DE TRANSACCION": "1",
            "VALOR": str(-valor),
            "BASE DE IMPUESTOS": "0",
        })
        # Crédito a caja
        filas_salida.append({
            **base_fila,
            "CUENTA": CUENTA_CAJA,
            "DETALLE": detalle,
            "TIPO DE TRANSACCION": "2",
            "VALOR": str(valor),
            "BASE DE IMPUESTOS": "0",
        })

    log.append(
        f"Egresos procesados: {stats['tipo1']} tipo 1 + {stats['tipo2']} tipo 2 "
        f"= {stats['tipo1'] + stats['tipo2']} total"
    )
    if stats["tipo2_nf"]:
        log.append(f"⚠️ Tipo 2 sin DS en compras: {stats['tipo2_nf']}")
    if stats["sin_mapeo_t1"]:
        log.append(f"⚠️ Tipo 1 sin regla de mapeo: {stats['sin_mapeo_t1']}")

    # Convertir a DataFrame con las columnas en orden
    columnas = [
        "CUENTA", "COMPROBANTE", "FECHA", "DOCUMENTO", "DOCUMENTO REFERENCIA",
        "NIT", "DETALLE", "TIPO DE TRANSACCION", "VALOR", "BASE DE IMPUESTOS",
        "CENTRO DE COSTOS",
    ]
    df_salida = pd.DataFrame(filas_salida, columns=columnas)

    return df_salida, log + ([""] + ["Advertencias:"] + advertencias if advertencias else [])


# ============================================================
# Generar TSV (plano final)
# ============================================================

def dataframe_a_plano_tsv(df: pd.DataFrame, incluir_encabezado_excel: bool = True) -> bytes:
    """Convierte el DataFrame plano a bytes TSV para descarga.

    Args:
        incluir_encabezado_excel: si True, agrega 'sep=\\t' al inicio para que
                                   Excel abra el archivo correctamente.
    """
    buf = io.StringIO()
    if incluir_encabezado_excel:
        buf.write("sep=\t\n")
    df.to_csv(buf, sep="\t", index=False)
    return buf.getvalue().encode("utf-8-sig")
