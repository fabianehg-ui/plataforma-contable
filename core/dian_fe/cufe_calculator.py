"""
core/dian_fe/cufe_calculator.py

Cálculo del CUFE (Código Único de Factura Electrónica) para facturas
electrónicas de venta DIAN.

Fórmula oficial (Anexo Técnico DIAN v1.9, Apéndice 7):

CUFE = SHA-384(
    NumFac     ||  # Número completo de factura (PrefijoFolio, ej. "SETP990000001")
    FecFac     ||  # Fecha emisión (YYYY-MM-DD)
    HorFac     ||  # Hora emisión (HH:MM:SS-05:00)
    ValFac     ||  # Valor sin tributos (subtotal sin impuestos, 2 decimales)
    CodImp1    ||  # "01" IVA
    ValImp1    ||  # Valor IVA total (2 decimales)
    CodImp2    ||  # "04" INC
    ValImp2    ||  # Valor INC total (2 decimales)
    CodImp3    ||  # "03" ICA
    ValImp3    ||  # Valor ICA total (2 decimales)
    ValTot     ||  # Valor total con tributos (PayableAmount, 2 decimales)
    NitOFE     ||  # NIT del emisor (sin DV, sin puntos)
    TipDocAdq  ||  # Tipo doc identificación del adquiriente (ej. "31")
    NumAdq     ||  # Número doc del adquiriente
    ClTec      ||  # Clave técnica (de la resolución de numeración)
    TipoAmb    ||  # "1"=producción, "2"=habilitación
)

CRÍTICO — diferencias con el CUDE de eventos:
  1. Para CUFE se usan los valores REALES de impuestos (no 0.00 como en eventos)
  2. La clave técnica viene de la RESOLUCIÓN, no del set de pruebas
  3. NumFac es el número COMPLETO con prefijo (no solo el folio)
  4. Si un impuesto no aplica, su valor es "0.00" pero su código IGUAL va

Formato exacto de números (importante para DIAN):
  - 2 decimales SIEMPRE (incluso para enteros: "100" → "100.00")
  - Punto decimal (no coma)
  - Sin separadores de miles
  - Sin signos de moneda

Si un solo byte está mal en la cadena, el CUFE no coincide y DIAN
rechaza el envío con error FAJ24 / FAK01 / similar.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional


# ════════════════════════════════════════════════════════════════════════
# Constantes
# ════════════════════════════════════════════════════════════════════════

TIPO_AMBIENTE_PRODUCCION = "1"
TIPO_AMBIENTE_HABILITACION = "2"

CODIGO_IVA = "01"
CODIGO_IC = "02"
CODIGO_ICA = "03"
CODIGO_INC = "04"


# ════════════════════════════════════════════════════════════════════════
# Estructura de entrada
# ════════════════════════════════════════════════════════════════════════

@dataclass
class DatosCUFE:
    """
    Datos necesarios para calcular el CUFE de una factura.

    Los valores monetarios son Decimal — DIAN exige precisión exacta.
    """
    # Número completo (PrefijoFolio)
    numero_factura: str               # Ej. "SETP990000001"

    # Fecha+hora de emisión
    fecha_emision: datetime           # Con timezone preferiblemente

    # Valores agregados
    valor_sin_impuestos: Decimal      # ValFac
    valor_total: Decimal              # ValTot (PayableAmount)

    # Impuestos: usar 0.00 si no aplica
    valor_iva: Decimal = Decimal("0.00")
    valor_inc: Decimal = Decimal("0.00")
    valor_ica: Decimal = Decimal("0.00")

    # Identificaciones
    nit_emisor: str = ""              # Solo dígitos, sin DV
    tipo_doc_adquiriente: str = "31"  # "31"=NIT, "13"=CC, etc.
    num_doc_adquiriente: str = ""

    # Clave técnica de la resolución
    clave_tecnica: str = ""

    # Ambiente
    tipo_ambiente: Literal["1", "2"] = "2"


# ════════════════════════════════════════════════════════════════════════
# Cálculo principal
# ════════════════════════════════════════════════════════════════════════

def calcular_cufe(datos: DatosCUFE) -> str:
    """
    Calcula el CUFE según fórmula DIAN.

    Args:
        datos: estructura con todos los campos.

    Returns:
        CUFE en hex lowercase (96 caracteres, SHA-384).

    Raises:
        ValueError: si algún campo crítico falta o está mal formado.
    """
    _validar(datos)
    cadena = _construir_cadena(datos)
    return hashlib.sha384(cadena.encode("utf-8")).hexdigest()


def _construir_cadena(datos: DatosCUFE) -> str:
    """
    Construye la cadena que se hashea.

    El orden y formato es CRÍTICO — un byte distinto y el CUFE no coincide.
    """
    fecha_str = datos.fecha_emision.strftime("%Y-%m-%d")
    hora_str = _formato_hora(datos.fecha_emision)

    cadena = (
        datos.numero_factura +
        fecha_str +
        hora_str +
        _formato_decimal(datos.valor_sin_impuestos) +
        CODIGO_IVA +
        _formato_decimal(datos.valor_iva) +
        CODIGO_INC +
        _formato_decimal(datos.valor_inc) +
        CODIGO_ICA +
        _formato_decimal(datos.valor_ica) +
        _formato_decimal(datos.valor_total) +
        datos.nit_emisor +
        datos.tipo_doc_adquiriente +
        datos.num_doc_adquiriente +
        datos.clave_tecnica +
        datos.tipo_ambiente
    )
    return cadena


def _formato_decimal(valor: Decimal) -> str:
    """
    Convierte un Decimal al formato DIAN: 2 decimales, punto, sin separadores.

    Ejemplos:
        Decimal("100") → "100.00"
        Decimal("100.5") → "100.50"
        Decimal("100.55") → "100.55"
        Decimal("100.555") → "100.56" (redondeo bancario, ROUND_HALF_EVEN)
    """
    if not isinstance(valor, Decimal):
        valor = Decimal(str(valor))
    # quantize a 2 decimales con redondeo HALF_EVEN (default Decimal)
    valor_redondeado = valor.quantize(Decimal("0.01"))
    return f"{valor_redondeado:.2f}"


def _formato_hora(fecha: datetime) -> str:
    """
    Devuelve la hora en formato HH:MM:SS-05:00 (zona Colombia).

    Si la fecha no tiene timezone, asume Colombia (-05:00).
    """
    base = fecha.strftime("%H:%M:%S")
    if fecha.tzinfo is not None:
        offset = fecha.strftime("%z")  # ±HHMM
        if offset:
            return f"{base}{offset[:3]}:{offset[3:]}"
    return f"{base}-05:00"


def _validar(datos: DatosCUFE) -> None:
    """Validaciones críticas antes de calcular el CUFE."""
    if not datos.numero_factura:
        raise ValueError("numero_factura es obligatorio")
    if not datos.fecha_emision:
        raise ValueError("fecha_emision es obligatoria")
    if not datos.nit_emisor or not datos.nit_emisor.isdigit():
        raise ValueError(f"nit_emisor inválido: {datos.nit_emisor!r}")
    if not datos.num_doc_adquiriente:
        raise ValueError("num_doc_adquiriente es obligatorio")
    if not datos.clave_tecnica:
        raise ValueError("clave_tecnica es obligatoria (de la resolución)")
    if datos.tipo_ambiente not in ("1", "2"):
        raise ValueError(f"tipo_ambiente debe ser '1' o '2'")
    if datos.valor_total < 0:
        raise ValueError(f"valor_total no puede ser negativo")


# ════════════════════════════════════════════════════════════════════════
# Helper de alto nivel
# ════════════════════════════════════════════════════════════════════════

def calcular_cufe_desde_factura(factura, ambiente: Literal["habilitacion", "produccion"] = "habilitacion") -> str:
    """
    Helper que extrae los datos de un objeto Factura (modelos.py) y calcula el CUFE.

    Args:
        factura: instancia de core.dian_fe.modelos.Factura (con totales ya calculados)
        ambiente: "habilitacion" o "produccion"

    Returns:
        CUFE hex lowercase.
    """
    if not factura.emisor or not factura.adquiriente:
        raise ValueError("La factura debe tener emisor y adquiriente")
    if not factura.resolucion:
        raise ValueError("La factura debe tener resolución asignada")

    # Sumar impuestos por código
    iva_total = Decimal("0.00")
    inc_total = Decimal("0.00")
    ica_total = Decimal("0.00")
    for it in factura.impuestos_totales:
        if it.codigo == CODIGO_IVA:
            iva_total += it.valor
        elif it.codigo == CODIGO_INC:
            inc_total += it.valor
        elif it.codigo == CODIGO_ICA:
            ica_total += it.valor

    tipo_amb = TIPO_AMBIENTE_PRODUCCION if ambiente == "produccion" else TIPO_AMBIENTE_HABILITACION

    # La clave técnica viene de la RESOLUCIÓN (no del software security code)
    datos = DatosCUFE(
        numero_factura=factura.numero_factura,
        fecha_emision=factura.fecha_emision,
        valor_sin_impuestos=factura.totales.line_extension,
        valor_total=factura.totales.payable,
        valor_iva=iva_total,
        valor_inc=inc_total,
        valor_ica=ica_total,
        nit_emisor=factura.emisor.numero_documento,
        tipo_doc_adquiriente=factura.adquiriente.tipo_documento_id,
        num_doc_adquiriente=factura.adquiriente.numero_documento,
        clave_tecnica=factura.resolucion.clave_tecnica,
        tipo_ambiente=tipo_amb,
    )

    return calcular_cufe(datos)


# ════════════════════════════════════════════════════════════════════════
# Test integrado con ejemplo de DIAN
# ════════════════════════════════════════════════════════════════════════
# El Anexo Técnico DIAN incluye un ejemplo "canónico" del cálculo CUFE.
# Si el módulo da el mismo CUFE para ese ejemplo, está correcto.
# Ejemplo Apéndice 7.2 del Anexo Técnico 1.8:
#
#   NumFac:    "FE15634"
#   FecFac:    "2019-04-25"
#   HorFac:    "11:43:11-05:00"
#   ValFac:    1500000.00
#   IVA:       285000.00
#   INC:       0.00
#   ICA:       0.00
#   ValTot:    1785000.00
#   NitOFE:    "700085371"
#   TipDocAdq: "31"
#   NumAdq:    "800199436"
#   ClTec:     "693ff6f2a553c3646a063436fd4dd9ded0311471"
#   TipoAmb:   "2"
#
# Resultado esperado:
#   CUFE: 8bb918b19ce33eee5cb2eaee2168f7a98549d3d8a517b09a311e2c4a47b91972f73a533a1adb406109b1da64aa20b067
#
# ⚠️ DIAN ha cambiado los ejemplos en diferentes versiones del anexo.
# Cuando saquen v1.10 hay que validar contra el ejemplo actualizado.

EJEMPLO_CANONICO_DIAN = {
    "numero_factura": "FE15634",
    "fecha_emision_str": "2019-04-25T11:43:11-05:00",
    "valor_sin_impuestos": Decimal("1500000.00"),
    "valor_iva": Decimal("285000.00"),
    "valor_inc": Decimal("0.00"),
    "valor_ica": Decimal("0.00"),
    "valor_total": Decimal("1785000.00"),
    "nit_emisor": "700085371",
    "tipo_doc_adquiriente": "31",
    "num_doc_adquiriente": "800199436",
    "clave_tecnica": "693ff6f2a553c3646a063436fd4dd9ded0311471",
    "tipo_ambiente": "2",
    "cufe_esperado": "8bb918b19ce33eee5cb2eaee2168f7a98549d3d8a517b09a311e2c4a47b91972f73a533a1adb406109b1da64aa20b067",
}


def validar_contra_ejemplo_dian() -> tuple[bool, str, str]:
    """
    Verifica el cálculo contra el ejemplo canónico del Anexo Técnico DIAN.

    Returns:
        (es_correcto, cufe_calculado, cufe_esperado)
    """
    ej = EJEMPLO_CANONICO_DIAN
    fecha = datetime.fromisoformat(ej["fecha_emision_str"])
    datos = DatosCUFE(
        numero_factura=ej["numero_factura"],
        fecha_emision=fecha,
        valor_sin_impuestos=ej["valor_sin_impuestos"],
        valor_total=ej["valor_total"],
        valor_iva=ej["valor_iva"],
        valor_inc=ej["valor_inc"],
        valor_ica=ej["valor_ica"],
        nit_emisor=ej["nit_emisor"],
        tipo_doc_adquiriente=ej["tipo_doc_adquiriente"],
        num_doc_adquiriente=ej["num_doc_adquiriente"],
        clave_tecnica=ej["clave_tecnica"],
        tipo_ambiente=ej["tipo_ambiente"],
    )
    calculado = calcular_cufe(datos)
    esperado = ej["cufe_esperado"]
    return (calculado == esperado, calculado, esperado)
