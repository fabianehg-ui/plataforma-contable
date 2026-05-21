"""
core/dian_pt/cude_calculator.py

Cálculo del CUDE (Código Único de Documento Electrónico) para eventos
RADIAN/Recepción Electrónica ante DIAN.

Aplica a:
  - Evento 030: Acuse de recibo de factura electrónica
  - Evento 031: Reclamo
  - Evento 032: Recibo del bien o prestación del servicio
  - Evento 033: Aceptación expresa
  - Evento 034: Aceptación tácita (automático, no se envía)

Fórmula (Anexo Técnico DIAN v1.9, sección "Generación del CUDE"):

CUDE = SHA-384(
    NumFac     ||  # ID del evento (consecutivo del emisor)
    FecFac     ||  # Fecha emisión (YYYY-MM-DD)
    HorFac     ||  # Hora emisión (HH:MM:SS-05:00)
    ValFac     ||  # Valor sin tributos (siempre 0.00 para eventos)
    CodImp1    ||  # 01 IVA
    ValImp1    ||  # 0.00
    CodImp2    ||  # 04 INC
    ValImp2    ||  # 0.00
    CodImp3    ||  # 03 ICA
    ValImp3    ||  # 0.00
    ValTot     ||  # Valor total (0.00 para eventos)
    NitOFE     ||  # NIT del emisor del evento (adquiriente)
    NumAdq     ||  # NIT del receptor del evento (proveedor original)
    ClTec      ||  # Clave técnica de software (asignada por DIAN)
    TipoAmb    ||  # 1=producción, 2=habilitación
)

Importante:
  - Los valores numéricos van con punto decimal y 2 decimales.
  - SIN espacios, SIN separadores entre campos.
  - El hash final se devuelve en lowercase hexadecimal.

Referencia: Anexo Técnico de Factura Electrónica de Venta, Resolución
000165 de 2023, Apéndice 7 - Algoritmo CUDE/CUFE.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Literal


# ════════════════════════════════════════════════════════════════════════
# Constantes
# ════════════════════════════════════════════════════════════════════════

TIPO_AMBIENTE_PRODUCCION = "1"
TIPO_AMBIENTE_HABILITACION = "2"

# Códigos de impuesto (DIAN tabla 6.4.1)
CODIGO_IVA = "01"
CODIGO_INC = "04"
CODIGO_ICA = "03"


# ════════════════════════════════════════════════════════════════════════
# Estructura para entrada del CUDE
# ════════════════════════════════════════════════════════════════════════

@dataclass
class DatosCUDEEvento:
    """
    Datos necesarios para calcular el CUDE de un evento RADIAN.

    Para eventos (030/032/033) los valores monetarios son siempre 0.00 —
    pero igual van en el hash con esa cifra.
    """
    num_evento: str                              # Consecutivo del evento (ej. "1", "2", ...)
    fecha_emision: datetime                      # Fecha+hora de emisión del EVENTO
    nit_emisor_evento: str                       # NIT del adquiriente (quien acusa)
    nit_receptor_evento: str                     # NIT del proveedor (emisor de la factura)
    clave_tecnica: str                           # Clave técnica del software (asignada por DIAN)
    tipo_ambiente: Literal["1", "2"] = "2"       # "1"=producción, "2"=habilitación


# ════════════════════════════════════════════════════════════════════════
# Cálculo principal
# ════════════════════════════════════════════════════════════════════════

def calcular_cude_evento(datos: DatosCUDEEvento) -> str:
    """
    Calcula el CUDE de un evento RADIAN según fórmula DIAN.

    Args:
        datos: estructura con todos los campos requeridos.

    Returns:
        CUDE en formato hex lowercase (96 caracteres, SHA-384).

    Raises:
        ValueError: si algún campo obligatorio está vacío o mal formado.
    """
    # Validar entrada
    _validar(datos)

    # Construir cadena base según fórmula DIAN
    cadena = _construir_cadena(datos)

    # SHA-384
    h = hashlib.sha384(cadena.encode("utf-8"))
    return h.hexdigest()


def _construir_cadena(datos: DatosCUDEEvento) -> str:
    """
    Concatena los campos en el orden EXACTO definido por DIAN.

    Para eventos RADIAN, todos los valores monetarios son 0.00 porque
    el evento no tiene valor económico propio (solo refiere a una factura).
    """
    # Fecha en formato YYYY-MM-DD
    fecha_str = datos.fecha_emision.strftime("%Y-%m-%d")

    # Hora en formato HH:MM:SS-05:00 (timezone Colombia)
    # Si la fecha viene con timezone, usa esa; si no, asume Bogotá
    if datos.fecha_emision.tzinfo is not None:
        hora_str = datos.fecha_emision.strftime("%H:%M:%S")
        offset = datos.fecha_emision.strftime("%z")  # ±HHMM
        # Convertir a formato -05:00
        if offset:
            hora_str = f"{hora_str}{offset[:3]}:{offset[3:]}"
        else:
            hora_str = f"{hora_str}-05:00"
    else:
        hora_str = datos.fecha_emision.strftime("%H:%M:%S") + "-05:00"

    # Valor 0.00 con 2 decimales (formato DIAN obligatorio)
    valor_cero = "0.00"

    # Concatenación EXACTA en el orden de DIAN (sin separadores)
    cadena = (
        datos.num_evento +
        fecha_str +
        hora_str +
        valor_cero +              # ValFac (sin tributos)
        CODIGO_IVA +
        valor_cero +              # ValImp1 (IVA)
        CODIGO_INC +
        valor_cero +              # ValImp2 (INC)
        CODIGO_ICA +
        valor_cero +              # ValImp3 (ICA)
        valor_cero +              # ValTot
        datos.nit_emisor_evento +
        datos.nit_receptor_evento +
        datos.clave_tecnica +
        datos.tipo_ambiente
    )
    return cadena


def _validar(datos: DatosCUDEEvento) -> None:
    """Valida que los campos críticos estén presentes y bien formados."""
    if not datos.num_evento:
        raise ValueError("num_evento es obligatorio")
    if not datos.fecha_emision:
        raise ValueError("fecha_emision es obligatoria")
    if not datos.nit_emisor_evento or not datos.nit_emisor_evento.isdigit():
        raise ValueError(f"nit_emisor_evento inválido: {datos.nit_emisor_evento!r}")
    if not datos.nit_receptor_evento or not datos.nit_receptor_evento.isdigit():
        raise ValueError(f"nit_receptor_evento inválido: {datos.nit_receptor_evento!r}")
    if not datos.clave_tecnica:
        raise ValueError("clave_tecnica es obligatoria (la asigna DIAN al PT)")
    if datos.tipo_ambiente not in ("1", "2"):
        raise ValueError(f"tipo_ambiente debe ser '1' o '2', recibí {datos.tipo_ambiente!r}")


# ════════════════════════════════════════════════════════════════════════
# Helpers de conveniencia
# ════════════════════════════════════════════════════════════════════════

def calcular_cude_evento_simple(
    num_evento: str,
    fecha_emision: datetime,
    nit_adquiriente: str,
    nit_proveedor: str,
    clave_tecnica: str,
    ambiente: Literal["produccion", "habilitacion"] = "habilitacion",
) -> str:
    """
    Versión simplificada para uso directo sin construir el dataclass.

    Args:
        num_evento: consecutivo del evento (string).
        fecha_emision: datetime de emisión del evento.
        nit_adquiriente: NIT de la empresa que emite el evento (el cliente).
        nit_proveedor: NIT del proveedor que emitió la factura original.
        clave_tecnica: clave técnica asignada por DIAN al PT.
        ambiente: "produccion" o "habilitacion" (sandbox DIAN).

    Returns:
        CUDE hex lowercase (96 chars).
    """
    tipo = TIPO_AMBIENTE_PRODUCCION if ambiente == "produccion" else TIPO_AMBIENTE_HABILITACION
    datos = DatosCUDEEvento(
        num_evento=num_evento,
        fecha_emision=fecha_emision,
        nit_emisor_evento=nit_adquiriente,
        nit_receptor_evento=nit_proveedor,
        clave_tecnica=clave_tecnica,
        tipo_ambiente=tipo,
    )
    return calcular_cude_evento(datos)
