"""
core/dian_fe — Módulo Facturación Electrónica DIAN.

Cubre emisión de facturas electrónicas de venta (FE) bajo el modo
"Software propio" de DIAN.

Estado actual: BASE FUNCIONAL para iteración.

Módulos:
  - modelos.py          → Modelos de datos (Factura, Línea, Parte, etc.)
  - cufe_calculator.py  → Cálculo del CUFE
  - xml_factura.py      → Generación XML UBL 2.1

Integración con módulos existentes:
  - firmador_xades.py   (del módulo dian_pt) → firma del XML
  - cliente_dian_soap.py (del módulo dian_pt) → envío SOAP a DIAN
  - vault.py            (del módulo dian_pt) → credenciales

Ejemplo de uso:

    from core.dian_fe import (
        Factura, LineaFactura, ParteFE, Resolucion, MedioPago, ImpuestoLinea,
        calcular_cufe_desde_factura, generar_xml_factura,
    )
    from core.dian_pt import cargar_p12, firmar_xml, ClienteDIAN

    # 1) Construir factura
    factura = Factura(...)
    factura.calcular_totales()
    factura.cufe = calcular_cufe_desde_factura(factura)

    # 2) Generar XML
    xml = generar_xml_factura(factura)

    # 3) Firmar
    cert = cargar_p12("jiper.p12", "pass")
    xml_firmado = firmar_xml(xml, cert)

    # 4) Enviar (cuando esté listo el set y certificado real)
    cliente = ClienteDIAN(cert, ambiente="habilitacion")
    # ⚠️ El método específico para enviar facturas (no eventos) es
    # SendBillSync, no SendEventUpdateStatus. Hay que extender el
    # cliente SOAP cuando se llegue a este paso.
"""

from .modelos import (
    # Clases principales
    Factura,
    LineaFactura,
    ParteFE,
    Resolucion,
    MedioPago,
    Retencion,
    Descuento,
    ImpuestoLinea,
    ImpuestoTotal,
    TotalesFE,
    # Constantes tipo identificación
    TIPO_DOC_NIT, TIPO_DOC_CC, TIPO_DOC_CE, TIPO_DOC_PASAPORTE,
    TIPO_DOC_RC, TIPO_DOC_TI,
    # Constantes organización
    ORG_JURIDICA, ORG_NATURAL,
    # Constantes responsabilidades
    RESP_IVA, RESP_NO_IVA, RESP_GRAN_CONTRIB,
    # Constantes tributos
    TRIBUTO_IVA, TRIBUTO_INC, TRIBUTO_ICA, TRIBUTO_IC,
    # Constantes tipo factura
    TIPO_FACTURA_VENTA, TIPO_FACTURA_EXPORTACION,
    # Constantes pago
    FORMA_PAGO_CONTADO, FORMA_PAGO_CREDITO,
    MEDIO_PAGO_EFECTIVO, MEDIO_PAGO_TARJETA_DEBITO,
    MEDIO_PAGO_TARJETA_CREDITO, MEDIO_PAGO_TRANSFERENCIA,
    # Unidades
    UNIDAD_UNIDAD, UNIDAD_KILOGRAMO, UNIDAD_LITRO,
)

from .cufe_calculator import (
    calcular_cufe,
    calcular_cufe_desde_factura,
    DatosCUFE,
    validar_contra_ejemplo_dian,
    TIPO_AMBIENTE_PRODUCCION,
    TIPO_AMBIENTE_HABILITACION,
)

from .xml_factura import (
    generar_xml_factura,
)

__all__ = [
    # Modelos
    "Factura", "LineaFactura", "ParteFE", "Resolucion",
    "MedioPago", "Retencion", "Descuento",
    "ImpuestoLinea", "ImpuestoTotal", "TotalesFE",
    # Constantes
    "TIPO_DOC_NIT", "TIPO_DOC_CC", "TIPO_DOC_CE", "TIPO_DOC_PASAPORTE",
    "TIPO_DOC_RC", "TIPO_DOC_TI",
    "ORG_JURIDICA", "ORG_NATURAL",
    "RESP_IVA", "RESP_NO_IVA", "RESP_GRAN_CONTRIB",
    "TRIBUTO_IVA", "TRIBUTO_INC", "TRIBUTO_ICA", "TRIBUTO_IC",
    "TIPO_FACTURA_VENTA", "TIPO_FACTURA_EXPORTACION",
    "FORMA_PAGO_CONTADO", "FORMA_PAGO_CREDITO",
    "MEDIO_PAGO_EFECTIVO", "MEDIO_PAGO_TARJETA_DEBITO",
    "MEDIO_PAGO_TARJETA_CREDITO", "MEDIO_PAGO_TRANSFERENCIA",
    "UNIDAD_UNIDAD", "UNIDAD_KILOGRAMO", "UNIDAD_LITRO",
    # CUFE
    "calcular_cufe", "calcular_cufe_desde_factura", "DatosCUFE",
    "validar_contra_ejemplo_dian",
    "TIPO_AMBIENTE_PRODUCCION", "TIPO_AMBIENTE_HABILITACION",
    # XML
    "generar_xml_factura",
]
