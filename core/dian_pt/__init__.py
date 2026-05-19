"""
core/dian_pt — Módulo Proveedor Tecnológico DIAN.

Módulo base para construir un Proveedor Tecnológico DIAN propio. Cubre:

  1. Manejo de certificados digitales .p12 (Andes, Certicámara, GSE)
  2. Cálculo CUDE de eventos RADIAN
  3. Generación XML UBL 2.1 de eventos 030/031/032/033
  4. Firma XAdES-EPES con política DIAN
  5. Cliente SOAP para envío al endpoint de DIAN

⚠️ ESTADO: BASE DE CÓDIGO para iteración. NO está habilitado por DIAN.
   La habilitación es un proceso formal de 6-12 meses que requiere:
     - Set de pruebas (186 escenarios) pasados ante DIAN
     - Pólizas de cumplimiento
     - Infraestructura redundante 99.5% uptime
     - Personal de soporte 24/7
     - Acompañamiento de consultor experto

Ver README.md para detalles técnicos y plan de iteración.

Ejemplo de uso (envío de evento 030 acuse de recibo):

    from core.dian_pt import (
        cargar_p12, calcular_cude_evento_simple,
        EventoRadian, ParteEvento, FacturaReferida,
        generar_xml_evento, firmar_xml, ClienteDIAN,
    )
    from datetime import datetime, timezone, timedelta

    # 1) Cargar certificado
    cert = cargar_p12("/ruta/cert.p12", "password")

    # 2) Datos del evento
    tz = timezone(timedelta(hours=-5))
    ahora = datetime.now(tz).replace(microsecond=0)

    adquiriente = ParteEvento(
        nit="901038325", dv="1", razon_social="JIPER SAS",
        municipio_codigo="05001", departamento_codigo="05",
    )
    proveedor = ParteEvento(
        nit="800111222", dv="3", razon_social="PROVEEDOR SAS",
        municipio_codigo="11001", departamento_codigo="11",
    )
    factura = FacturaReferida(
        numero="FE-12345",
        cufe="a1b2c3...96chars",
        fecha_emision=datetime(2026, 3, 15, tzinfo=tz),
        monto_total=1500000.00,
    )

    # 3) Calcular CUDE
    cude = calcular_cude_evento_simple(
        num_evento="1", fecha_emision=ahora,
        nit_adquiriente="901038325", nit_proveedor="800111222",
        clave_tecnica="<clave asignada por DIAN>",
        ambiente="habilitacion",
    )

    # 4) Generar XML
    evento = EventoRadian(
        tipo_evento="030", num_evento="1", cude=cude, fecha_emision=ahora,
        emisor=adquiriente, receptor=proveedor, factura=factura,
        software_id="<software ID asignado por DIAN>",
        software_security_code="<PIN asignado por DIAN>",
        clave_tecnica="<clave asignada por DIAN>",
        proveedor_tecnologico_nit="901038325",
        proveedor_tecnologico_dv="1",
        ambiente="2",
    )
    xml_sin_firma = generar_xml_evento(evento)

    # 5) Firmar
    xml_firmado = firmar_xml(xml_sin_firma, cert)

    # 6) Enviar
    cliente = ClienteDIAN(cert, ambiente="habilitacion")
    resp = cliente.enviar_evento(xml_firmado)

    if resp.exitoso:
        print(f"TrackId DIAN: {resp.track_id}")
    else:
        print(f"Error: {resp.error_message}")
"""

# Re-exportar lo más importante para facilitar imports
from .certificado import (
    CertificadoP12,
    cargar_p12,
    ErrorCertificado,
    CertificadoInvalido,
    PasswordIncorrecto,
    CertificadoVencido,
)

from .cude_calculator import (
    DatosCUDEEvento,
    calcular_cude_evento,
    calcular_cude_evento_simple,
    TIPO_AMBIENTE_PRODUCCION,
    TIPO_AMBIENTE_HABILITACION,
)

from .xml_evento_radian import (
    EventoRadian,
    ParteEvento,
    FacturaReferida,
    EVENTOS,
    CODIGOS_RECLAMO,
    generar_xml_evento,
)

from .firmador_xades import (
    firmar_xml,
    ErrorFirma,
    XMLInvalido,
    POLITICA_FIRMA_URL,
    POLITICA_FIRMA_HASH,
)

from .cliente_dian_soap import (
    ClienteDIAN,
    RespuestaDIAN,
    ResultadoConsulta,
    ErrorClienteDIAN,
    ErrorRed,
    ErrorRespuestaDIAN,
    ENDPOINT_HABILITACION,
    ENDPOINT_PRODUCCION,
)

__all__ = [
    # Certificado
    "CertificadoP12", "cargar_p12",
    "ErrorCertificado", "CertificadoInvalido",
    "PasswordIncorrecto", "CertificadoVencido",
    # CUDE
    "DatosCUDEEvento", "calcular_cude_evento", "calcular_cude_evento_simple",
    "TIPO_AMBIENTE_PRODUCCION", "TIPO_AMBIENTE_HABILITACION",
    # XML
    "EventoRadian", "ParteEvento", "FacturaReferida",
    "EVENTOS", "CODIGOS_RECLAMO", "generar_xml_evento",
    # Firma
    "firmar_xml", "ErrorFirma", "XMLInvalido",
    "POLITICA_FIRMA_URL", "POLITICA_FIRMA_HASH",
    # SOAP
    "ClienteDIAN", "RespuestaDIAN", "ResultadoConsulta",
    "ErrorClienteDIAN", "ErrorRed", "ErrorRespuestaDIAN",
    "ENDPOINT_HABILITACION", "ENDPOINT_PRODUCCION",
]
