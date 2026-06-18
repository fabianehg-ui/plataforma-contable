"""
core/bittal/reportes.py

Registro de informes de bittal + orquestador.
Agregar un informe = una entrada en INFORMES (URL(s) + procesador).
Un informe puede requerir varias descargas; cada una puede ser opcional.
"""
from __future__ import annotations

import io
from datetime import date
from typing import Optional

from .cliente_bittal import BittalCreds, descargar_reporte

BASE = "https://e4.portal.bittal.co/Systems/Company"
PEND = "<<PENDIENTE>>"   # URL aún no capturada


def _limpiar_plano(data: bytes) -> bytes:
    """Quita el BOM inicial y la línea 'sep=\\t' (pista de Excel) que Contai no
    necesita. Aplica a todos los informes."""
    if data[:3] == b"\xef\xbb\xbf":
        data = data[3:]
    for pref in (b"sep=\t\r\n", b"sep=\t\n", b"sep=\t\r"):
        if data.startswith(pref):
            return data[len(pref):]
    return data


# ---------- procesadores por informe (envuelven los del repo) ----------

def _procesar_ventas(archivos: dict, log: list):
    from core.procesadores.procesador_ventas_c13 import (
        procesar_ventas_c13, dataframe_a_plano_tsv,
    )
    df, log_p, resumen = procesar_ventas_c13(
        archivos["detalle"], archivos.get("notas")  # notas es opcional
    )
    log.extend(log_p)
    return dataframe_a_plano_tsv(df), resumen


def _procesar_recaudos(archivos: dict, log: list):
    from core.procesadores.procesador_recaudos import (
        procesar_recaudos, dataframe_a_plano_tsv,
    )
    df, log_p, resumen = procesar_recaudos(archivos["documentos"])
    log.extend(log_p)
    return dataframe_a_plano_tsv(df), resumen


def _procesar_caja_menor(archivos: dict, log: list):
    import pandas as pd
    from core.utils.configuracion_web import Configuracion
    from core.procesadores.procesador_caja_menor import (
        procesar_caja_menor, dataframe_a_plano_tsv,
    )
    # Igual que la pagina de Caja Menor del repo: config vacia (cuentas por defecto).
    cfg = Configuracion.vacia()
    df, log_p = procesar_caja_menor(archivos["egresos"], cfg)
    log.extend(log_p)

    # Este procesador entrega VALOR con signo (tipo 1 negativo / tipo 2 positivo),
    # asi que el cuadre se verifica como neto == 0.
    v = pd.to_numeric(df["VALOR"], errors="coerce").fillna(0)
    neto = int(v.sum())
    log.append(f"🧮 Caja menor: {len(df)} líneas. Neto (debe ser 0): ${neto:,}")
    log.append("   ✅ Cuadra (neto 0)" if neto == 0 else f"   ⚠️ Neto distinto de 0: {neto}")
    # VALOR sin signo: Contai usa TIPO DE TRANSACCION (1=Db / 2=Cr) para el signo.
    df = df.copy()
    df["VALOR"] = v.abs().astype("int64")
    resumen = {"lineas": len(df), "neto": neto}
    return dataframe_a_plano_tsv(df), resumen


def _procesar_compras_ds(archivos: dict, log: list):
    import pandas as pd
    from core.procesadores.procesador_compras_egresos import (
        _leer_documentos_soporte, cargar_catalogo, _generar_asientos_ds,
        dataframe_a_plano_tsv, COLUMNAS_PLANO, COMPROBANTE_DS,
    )
    docs = _leer_documentos_soporte(archivos["listado"])
    log.append(f"📄 Documento Soporte: {len(docs)} documentos válidos.")
    cat = cargar_catalogo()
    base_min = int(cat["uvt"]) * int(cat["base_servicios_uvt"])
    log.append(
        f"   UVT ${cat['uvt']:,} × {cat['base_servicios_uvt']} = base retefuente "
        f"servicios ${base_min:,}"
    )
    filas, _mapa, advert = _generar_asientos_ds(docs, cat["productos"], base_min)
    for a in advert:
        log.append(a)

    df = pd.DataFrame(filas, columns=COLUMNAS_PLANO)
    v = pd.to_numeric(df["VALOR"], errors="coerce").fillna(0)
    db = int(v[df["TR"].astype(str) == "1"].sum())
    cr = int(v[df["TR"].astype(str) == "2"].sum())
    log.append(
        f"🧮 Comp {COMPROBANTE_DS}: {len(docs)} docs, {len(df)} líneas. "
        f"Db=${db:,} Cr=${cr:,}"
    )
    log.append("   ✅ Cuadre Db = Cr" if db == cr else f"   ⚠️ Descuadre: {db - cr}")
    resumen = {
        "documentos": len(docs),
        "lineas": len(df),
        "total_db": db,
        "total_cr": cr,
        "productos_sin_catalogo": len(advert),
    }
    return dataframe_a_plano_tsv(df), resumen


def _procesar_terceros(archivos: dict, log: list):
    from core.procesadores.procesador_terceros_bittal import procesar_terceros_bittal
    xlsx, resumen = procesar_terceros_bittal(archivos["listado"])
    log.append(
        f"👥 Terceros: {resumen['terceros']} "
        f"(jurídicas={resumen['juridicas']}, naturales={resumen['naturales']}); "
        f"{resumen['duplicados']} duplicados y {resumen['sin_nit']} sin NIT descartados."
    )
    log.append("   Naturaleza/tipo decididos por dígitos del NIT (no por 'Tipo Persona').")
    return xlsx, resumen


INFORMES = {
    "ventas": {
        "nombre": "Ventas — detalle por cuentas (+ notas crédito opcional)",
        "descargas": {
            "detalle": {"url": f"{BASE}/Sales/Lists/InvoiceTransactionByTaxDetail.aspx",
                        "opcional": False},
            "notas":   {"url": PEND, "opcional": True},  # solo enriquece DOC REFERENCIA
        },
        "procesar": _procesar_ventas,
        "estado": "VALIDADO",
    },
    "recaudos": {
        "nombre": "Recaudos / ingresos de tesorería (por medio de pago)",
        "descargas": {
            "documentos": {"url": f"{BASE}/Treasury/Documents/List.aspx",  # confirmar
                           "opcional": False},
        },
        "procesar": _procesar_recaudos,
        "estado": "VALIDADO (faltan cuentas Cr/comprobante en recaudos.json)",
    },
    "caja_menor": {
        "nombre": "Egresos de caja menor (CEG)",
        "descargas": {
            "egresos": {"url": f"{BASE}/Treasury/MovementsTreasuryDocumentDetail.aspx?DocumentType=8",
                        "opcional": False, "arg_exportar": "1:0"},
        },
        "procesar": _procesar_caja_menor,
        "estado": "VALIDADO (config vacía; cuentas por defecto Comp 13)",
    },
    "compras_ds": {
        "nombre": "Compras — documento soporte",
        "descargas": {
            "listado": {"url": f"{BASE}/Purchases/PurchaseDetailList.aspx",
                        "opcional": False, "arg_exportar": "0:0"},
        },
        "procesar": _procesar_compras_ds,
        "estado": "VALIDADO (catálogo: SERV017 cae a default si no se agrega)",
    },
    "terceros": {
        "nombre": "Terceros (NITs) → formato Contai",
        "descargas": {
            "listado": {
                "url": "https://e4.portal.bittal.co/Systems/ThirdParties/General/List.aspx",
                "opcional": False, "arg_exportar": "1:0", "refrescar": False,
            },
        },
        "procesar": _procesar_terceros,
        "salida": {
            "ext": "xlsx",
            "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "nombre": "nits_contai",
        },
        "estado": "VALIDADO",
    },
}


def generar_plano(
    informe_key: str,
    fecha_ini: date,
    fecha_fin: date,
    *,
    creds: Optional[BittalCreds] = None,
    headless: bool = True,
):
    """Descarga el/los archivo(s) del informe y devuelve (plano_bytes, log, resumen)."""
    creds = creds or BittalCreds.desde_entorno()
    inf = INFORMES[informe_key]
    log: list = []
    archivos: dict = {}
    for rol, cfg in inf["descargas"].items():
        url = cfg["url"]
        if url == PEND:
            if cfg.get("opcional"):
                log.append(f"⏭️ Rol opcional '{rol}' sin URL: se omite.")
                continue
            raise RuntimeError(
                f"Falta la URL del rol obligatorio '{rol}' en el informe '{informe_key}'."
            )
        kw = {"headless": headless, "log": log}
        if cfg.get("arg_exportar"):
            kw["arg_exportar"] = cfg["arg_exportar"]
        if "refrescar" in cfg:
            kw["refrescar"] = cfg["refrescar"]
        xlsx = descargar_reporte(creds, url, fecha_ini, fecha_fin, **kw)
        archivos[rol] = io.BytesIO(xlsx)
    plano_bytes, resumen = inf["procesar"](archivos, log)
    # Los planos de texto llevan limpieza (BOM / sep=); las salidas binarias no.
    if (inf.get("salida") or {}).get("ext") != "xlsx":
        plano_bytes = _limpiar_plano(plano_bytes)
    return plano_bytes, log, resumen
