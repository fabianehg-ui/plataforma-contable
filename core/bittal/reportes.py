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
    # Reusa el procesador existente. OJO: requiere un objeto Configuracion de la
    # empresa. Hay que enlazarlo a tu cargador de config por NIT.
    raise NotImplementedError(
        "Caja menor reusa procesador_caja_menor, pero falta pasarle la "
        "Configuracion de la empresa. Lo enlazamos cuando definas el cargador."
    )


def _procesar_compras_ds(archivos: dict, log: list):
    raise NotImplementedError(
        "Falta el procesador de Documento Soporte (PurchaseDetailList). "
        "Definir producto->cuenta, cuenta proveedor (CxP), retefuente y comprobante."
    )


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
            "egresos": {"url": PEND, "opcional": False},  # URL de tesorería por capturar
        },
        "procesar": _procesar_caja_menor,
        "estado": "REUSA procesador_caja_menor (falta Configuracion empresa)",
    },
    "compras_ds": {
        "nombre": "Compras — documento soporte",
        "descargas": {
            "listado": {"url": f"{BASE}/Purchases/PurchaseDetailList.aspx",
                        "opcional": False},
        },
        "procesar": _procesar_compras_ds,
        "estado": "PENDIENTE procesador",
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
        xlsx = descargar_reporte(creds, url, fecha_ini, fecha_fin, headless=headless, log=log)
        archivos[rol] = io.BytesIO(xlsx)
    plano_bytes, resumen = inf["procesar"](archivos, log)
    return plano_bytes, log, resumen
