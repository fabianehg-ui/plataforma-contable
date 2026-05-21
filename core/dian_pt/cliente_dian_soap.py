"""
core/dian_pt/cliente_dian_soap.py

Cliente SOAP para envío de documentos electrónicos firmados a DIAN.

DIAN expone 2 endpoints principales:

  Habilitación (pruebas):
    https://vpfe-hab.dian.gov.co/WcfDianCustomerServices.svc

  Producción:
    https://vpfe.dian.gov.co/WcfDianCustomerServices.svc

Operaciones expuestas (las que usamos para eventos RADIAN):
  - SendEventUpdateStatus    → envía un evento individual firmado
  - SendNominaSync           → no aplica a eventos
  - GetStatus                → consulta el estado de un envío por TrackId
  - GetStatusZip             → descarga el AppResponse de DIAN

Flujo de envío:
  1. Construir SOAP envelope con WSSecurity header firmado
  2. Insertar el XML del evento como contentFile (base64-zipped)
  3. POST a la URL del endpoint
  4. DIAN responde con TrackId (síncrono) o error
  5. Después se consulta con GetStatus para ver el AppResponse final

⚠️ IMPORTANTE:
  - Este cliente usa Zeep para SOAP pero la firma WSSecurity del header
    SOAP se hace manualmente porque Zeep no maneja XAdES-EPES.
  - La firma del header SOAP es DISTINTA a la firma del documento:
    * Documento firmado con XAdES-EPES (firmador_xades.py)
    * Header SOAP firmado con WSSecurity (este módulo)
  - DIAN valida AMBAS firmas. Si falta una, rechaza.

Referencia:
  - Anexo Técnico DIAN, Apéndice 12 - Servicios Web
  - WS-Security 1.1: http://docs.oasis-open.org/wss-m/wss/v1.1/
"""
from __future__ import annotations

import base64
import hashlib
import io
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Literal, Optional

import requests
from lxml import etree
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from .certificado import CertificadoP12


# ════════════════════════════════════════════════════════════════════════
# Endpoints
# ════════════════════════════════════════════════════════════════════════

ENDPOINT_HABILITACION = "https://vpfe-hab.dian.gov.co/WcfDianCustomerServices.svc"
ENDPOINT_PRODUCCION = "https://vpfe.dian.gov.co/WcfDianCustomerServices.svc"

# Namespaces SOAP + WSSecurity
NS_SOAP = "http://www.w3.org/2003/05/soap-envelope"
NS_WSA = "http://www.w3.org/2005/08/addressing"
NS_WSSE = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
NS_WSU = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
NS_DS = "http://www.w3.org/2000/09/xmldsig#"
NS_WCF = "http://wcf.dian.colombia"

NSMAP_SOAP = {
    "s": NS_SOAP,
    "wsa": NS_WSA,
    "wsse": NS_WSSE,
    "wsu": NS_WSU,
    "ds": NS_DS,
    "wcf": NS_WCF,
}


# ════════════════════════════════════════════════════════════════════════
# Estructuras de respuesta
# ════════════════════════════════════════════════════════════════════════

@dataclass
class RespuestaDIAN:
    """Respuesta del envío de un evento a DIAN."""
    exitoso: bool
    track_id: Optional[str] = None              # ID asignado por DIAN
    es_valido: Optional[bool] = None            # IsValid del AppResponse
    status_code: Optional[str] = None           # StatusCode DIAN
    status_description: Optional[str] = None    # StatusDescription
    status_message: Optional[str] = None        # StatusMessage
    error_message: Optional[str] = None         # Si hubo error en el envío
    xml_respuesta_raw: Optional[bytes] = None   # XML SOAP completo (debug)
    http_status: Optional[int] = None           # Código HTTP de la respuesta


@dataclass
class ResultadoConsulta:
    """Resultado de GetStatus de un envío previo."""
    track_id: str
    estado: str                                  # "Procesando", "Aceptado", "Rechazado", "No existe"
    fecha_recepcion: Optional[str] = None
    fecha_procesamiento: Optional[str] = None
    es_valido: Optional[bool] = None
    errores: list = None                         # Lista de mensajes de error


# ════════════════════════════════════════════════════════════════════════
# Excepciones
# ════════════════════════════════════════════════════════════════════════

class ErrorClienteDIAN(Exception):
    """Error base para problemas del cliente DIAN."""


class ErrorRed(ErrorClienteDIAN):
    """Error de conexión, timeout, DNS, etc."""


class ErrorRespuestaDIAN(ErrorClienteDIAN):
    """DIAN respondió pero con un fault SOAP."""


# ════════════════════════════════════════════════════════════════════════
# API principal
# ════════════════════════════════════════════════════════════════════════

class ClienteDIAN:
    """
    Cliente para enviar eventos firmados a DIAN.

    Uso:
        cliente = ClienteDIAN(certificado, ambiente="habilitacion")
        respuesta = cliente.enviar_evento(xml_firmado_bytes)
        if respuesta.exitoso:
            print(f"TrackId: {respuesta.track_id}")
    """

    def __init__(
        self,
        certificado: CertificadoP12,
        ambiente: Literal["habilitacion", "produccion"] = "habilitacion",
        timeout: int = 60,
    ):
        self.certificado = certificado
        self.ambiente = ambiente
        self.endpoint = (
            ENDPOINT_PRODUCCION if ambiente == "produccion" else ENDPOINT_HABILITACION
        )
        self.timeout = timeout

    def enviar_evento(self, xml_firmado: bytes, nombre_archivo: str = "evento.xml") -> RespuestaDIAN:
        """
        Envía un XML de evento ya firmado al endpoint SendEventUpdateStatus.

        Args:
            xml_firmado: bytes del XML con firma XAdES-EPES ya aplicada.
            nombre_archivo: nombre del archivo dentro del ZIP que se envía.

        Returns:
            RespuestaDIAN con el resultado del envío.
        """
        # 1) Comprimir el XML en ZIP (DIAN lo exige)
        zip_bytes = self._empaquetar_zip(xml_firmado, nombre_archivo)

        # 2) Base64 del ZIP
        contenido_b64 = base64.b64encode(zip_bytes).decode("ascii")

        # 3) Construir SOAP envelope con WSSecurity firmado
        soap_envelope = self._construir_soap_envelope(
            operacion="SendEventUpdateStatus",
            contenido_b64=contenido_b64,
            nombre_archivo=nombre_archivo + ".zip",
        )

        # 4) POST a DIAN
        return self._enviar_post(soap_envelope, action="SendEventUpdateStatus")

    def consultar_estado(self, track_id: str) -> ResultadoConsulta:
        """
        Consulta el estado de un envío previo por su TrackId.

        Args:
            track_id: ID devuelto por DIAN en el envío inicial.

        Returns:
            ResultadoConsulta con el estado actual.
        """
        soap_envelope = self._construir_soap_envelope_consulta(track_id)
        resp = self._enviar_post(soap_envelope, action="GetStatus")

        # Parsear respuesta
        return self._parsear_consulta(resp.xml_respuesta_raw, track_id)

    def enviar_factura(
        self,
        xml_firmado: bytes,
        nombre_archivo: str = "factura.xml",
    ) -> RespuestaDIAN:
        """
        Envía una FACTURA electrónica ya firmada al endpoint SendBillSync.

        A diferencia de enviar_evento() (que usa SendEventUpdateStatus para
        eventos RADIAN), las facturas electrónicas de venta se envían con la
        operación SendBillSync, que DIAN exige con DOS parámetros en el body:
        fileName y contentFile.

        Args:
            xml_firmado: bytes del XML de la factura con firma XAdES-EPES ya aplicada.
            nombre_archivo: nombre base del archivo (sin .zip). El nombre del
                ZIP que DIAN espera suele seguir la convención
                "<NombreXML>.zip"; aquí usamos nombre_archivo + ".zip".

        Returns:
            RespuestaDIAN con TrackId si fue aceptada, error si no.
        """
        # 1) Comprimir el XML en ZIP (DIAN lo exige, un solo .xml por ZIP)
        zip_bytes = self._empaquetar_zip(xml_firmado, nombre_archivo)

        # 2) Base64 del ZIP
        contenido_b64 = base64.b64encode(zip_bytes).decode("ascii")

        # 3) Construir SOAP envelope con WSSecurity firmado.
        #    SendBillSync requiere fileName + contentFile.
        soap_envelope = self._construir_soap_envelope_bill(
            operacion="SendBillSync",
            file_name=nombre_archivo + ".zip",
            contenido_b64=contenido_b64,
        )

        # 4) POST a DIAN
        return self._enviar_post(soap_envelope, action="SendBillSync")

    # ════════════════════════════════════════════════════════════════════
    # Construcción del SOAP
    # ════════════════════════════════════════════════════════════════════

    def _empaquetar_zip(self, xml_bytes: bytes, nombre: str) -> bytes:
        """Comprime el XML en un ZIP en memoria."""
        bio = io.BytesIO()
        with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(nombre, xml_bytes)
        return bio.getvalue()

    def _construir_soap_envelope(
        self,
        operacion: str,
        contenido_b64: str,
        nombre_archivo: str,
    ) -> bytes:
        """
        Construye el sobre SOAP completo con:
          - Header WSA (Action, To, MessageID)
          - Header WSSecurity con BinarySecurityToken + firma
          - Body con la operación DIAN
        """
        # IDs únicos para los elementos firmados
        token_id = f"X509-{uuid.uuid4()}"
        timestamp_id = f"TS-{uuid.uuid4()}"
        body_id = f"id-{uuid.uuid4()}"
        sig_id = f"SIG-{uuid.uuid4()}"

        # Fechas del timestamp
        now = datetime.now(timezone.utc)
        created = now.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        expires = (now + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

        # Certificado en base64 DER
        cert_der = self.certificado.certificate.public_bytes(serialization.Encoding.DER)
        cert_b64 = base64.b64encode(cert_der).decode("ascii")

        # Construir el envelope
        envelope = etree.Element(_t("s", "Envelope"), nsmap=NSMAP_SOAP)

        # ── Header ──
        header = etree.SubElement(envelope, _t("s", "Header"))

        # WSA elements
        action = etree.SubElement(header, _t("wsa", "Action"))
        action.set(_t("s", "mustUnderstand"), "1")
        action.text = f"http://wcf.dian.colombia/IWcfDianCustomerServices/{operacion}"

        to = etree.SubElement(header, _t("wsa", "To"))
        to.set(_t("s", "mustUnderstand"), "1")
        to.set(_t("wsu", "Id"), "id-To")
        to.text = self.endpoint

        msgid = etree.SubElement(header, _t("wsa", "MessageID"))
        msgid.text = f"urn:uuid:{uuid.uuid4()}"

        # WSSecurity
        security = etree.SubElement(header, _t("wsse", "Security"))
        security.set(_t("s", "mustUnderstand"), "1")

        # BinarySecurityToken con el certificado
        bst = etree.SubElement(security, _t("wsse", "BinarySecurityToken"))
        bst.set("EncodingType",
                "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary")
        bst.set("ValueType",
                "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-x509-token-profile-1.0#X509v3")
        bst.set(_t("wsu", "Id"), token_id)
        bst.text = cert_b64

        # Timestamp
        ts = etree.SubElement(security, _t("wsu", "Timestamp"))
        ts.set(_t("wsu", "Id"), timestamp_id)
        ts_created = etree.SubElement(ts, _t("wsu", "Created"))
        ts_created.text = created
        ts_expires = etree.SubElement(ts, _t("wsu", "Expires"))
        ts_expires.text = expires

        # Placeholder para Signature (se llena después)
        sig_placeholder = etree.SubElement(security, _t("ds", "Signature"))
        sig_placeholder.set("Id", sig_id)

        # ── Body ──
        body = etree.SubElement(envelope, _t("s", "Body"))
        body.set(_t("wsu", "Id"), body_id)

        op_elem = etree.SubElement(body, _t("wcf", operacion))
        cf = etree.SubElement(op_elem, _t("wcf", "contentFile"))
        cf.text = contenido_b64

        # ── Firmar el SOAP (WSSecurity) ──
        self._firmar_soap(
            envelope=envelope,
            sig_placeholder=sig_placeholder,
            token_id=token_id,
            timestamp_id=timestamp_id,
            body_id=body_id,
        )

        return etree.tostring(envelope, xml_declaration=True, encoding="UTF-8")

    def _construir_soap_envelope_bill(
        self,
        operacion: str,
        file_name: str,
        contenido_b64: str,
    ) -> bytes:
        """
        Construye el sobre SOAP para SendBillSync (envío de facturas).

        Idéntico a _construir_soap_envelope() salvo que el body lleva DOS
        sub-elementos en el orden que exige DIAN: fileName y contentFile.
        """
        token_id = f"X509-{uuid.uuid4()}"
        timestamp_id = f"TS-{uuid.uuid4()}"
        body_id = f"id-{uuid.uuid4()}"
        sig_id = f"SIG-{uuid.uuid4()}"

        now = datetime.now(timezone.utc)
        created = now.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        expires = (now + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

        cert_der = self.certificado.certificate.public_bytes(serialization.Encoding.DER)
        cert_b64 = base64.b64encode(cert_der).decode("ascii")

        envelope = etree.Element(_t("s", "Envelope"), nsmap=NSMAP_SOAP)

        # ── Header ──
        header = etree.SubElement(envelope, _t("s", "Header"))

        action = etree.SubElement(header, _t("wsa", "Action"))
        action.set(_t("s", "mustUnderstand"), "1")
        action.text = f"http://wcf.dian.colombia/IWcfDianCustomerServices/{operacion}"

        to = etree.SubElement(header, _t("wsa", "To"))
        to.set(_t("s", "mustUnderstand"), "1")
        to.set(_t("wsu", "Id"), "id-To")
        to.text = self.endpoint

        msgid = etree.SubElement(header, _t("wsa", "MessageID"))
        msgid.text = f"urn:uuid:{uuid.uuid4()}"

        security = etree.SubElement(header, _t("wsse", "Security"))
        security.set(_t("s", "mustUnderstand"), "1")

        bst = etree.SubElement(security, _t("wsse", "BinarySecurityToken"))
        bst.set("EncodingType",
                "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary")
        bst.set("ValueType",
                "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-x509-token-profile-1.0#X509v3")
        bst.set(_t("wsu", "Id"), token_id)
        bst.text = cert_b64

        ts = etree.SubElement(security, _t("wsu", "Timestamp"))
        ts.set(_t("wsu", "Id"), timestamp_id)
        ts_created = etree.SubElement(ts, _t("wsu", "Created"))
        ts_created.text = created
        ts_expires = etree.SubElement(ts, _t("wsu", "Expires"))
        ts_expires.text = expires

        sig_placeholder = etree.SubElement(security, _t("ds", "Signature"))
        sig_placeholder.set("Id", sig_id)

        # ── Body: SendBillSync(fileName, contentFile) ──
        body = etree.SubElement(envelope, _t("s", "Body"))
        body.set(_t("wsu", "Id"), body_id)

        op_elem = etree.SubElement(body, _t("wcf", operacion))
        fn = etree.SubElement(op_elem, _t("wcf", "fileName"))
        fn.text = file_name
        cf = etree.SubElement(op_elem, _t("wcf", "contentFile"))
        cf.text = contenido_b64

        # ── Firmar el SOAP (WSSecurity) ──
        self._firmar_soap(
            envelope=envelope,
            sig_placeholder=sig_placeholder,
            token_id=token_id,
            timestamp_id=timestamp_id,
            body_id=body_id,
        )

        return etree.tostring(envelope, xml_declaration=True, encoding="UTF-8")

        """Construye SOAP para GetStatus."""
        # Similar a enviar pero con operation = GetStatus y trackId en el body
        token_id = f"X509-{uuid.uuid4()}"
        timestamp_id = f"TS-{uuid.uuid4()}"
        body_id = f"id-{uuid.uuid4()}"
        sig_id = f"SIG-{uuid.uuid4()}"

        now = datetime.now(timezone.utc)
        created = now.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        expires = (now + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

        cert_der = self.certificado.certificate.public_bytes(serialization.Encoding.DER)
        cert_b64 = base64.b64encode(cert_der).decode("ascii")

        envelope = etree.Element(_t("s", "Envelope"), nsmap=NSMAP_SOAP)
        header = etree.SubElement(envelope, _t("s", "Header"))

        action = etree.SubElement(header, _t("wsa", "Action"))
        action.set(_t("s", "mustUnderstand"), "1")
        action.text = "http://wcf.dian.colombia/IWcfDianCustomerServices/GetStatus"

        to = etree.SubElement(header, _t("wsa", "To"))
        to.set(_t("s", "mustUnderstand"), "1")
        to.set(_t("wsu", "Id"), "id-To")
        to.text = self.endpoint

        msgid = etree.SubElement(header, _t("wsa", "MessageID"))
        msgid.text = f"urn:uuid:{uuid.uuid4()}"

        security = etree.SubElement(header, _t("wsse", "Security"))
        security.set(_t("s", "mustUnderstand"), "1")

        bst = etree.SubElement(security, _t("wsse", "BinarySecurityToken"))
        bst.set("EncodingType",
                "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary")
        bst.set("ValueType",
                "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-x509-token-profile-1.0#X509v3")
        bst.set(_t("wsu", "Id"), token_id)
        bst.text = cert_b64

        ts = etree.SubElement(security, _t("wsu", "Timestamp"))
        ts.set(_t("wsu", "Id"), timestamp_id)
        etree.SubElement(ts, _t("wsu", "Created")).text = created
        etree.SubElement(ts, _t("wsu", "Expires")).text = expires

        sig_placeholder = etree.SubElement(security, _t("ds", "Signature"))
        sig_placeholder.set("Id", sig_id)

        body = etree.SubElement(envelope, _t("s", "Body"))
        body.set(_t("wsu", "Id"), body_id)

        op_elem = etree.SubElement(body, _t("wcf", "GetStatus"))
        ti = etree.SubElement(op_elem, _t("wcf", "trackId"))
        ti.text = track_id

        self._firmar_soap(envelope, sig_placeholder, token_id, timestamp_id, body_id)

        return etree.tostring(envelope, xml_declaration=True, encoding="UTF-8")

    def _firmar_soap(
        self,
        envelope,
        sig_placeholder,
        token_id: str,
        timestamp_id: str,
        body_id: str,
    ) -> None:
        """
        Firma el envelope SOAP siguiendo WSSecurity 1.1.

        DIAN exige que se firmen tres elementos: el Body, el Timestamp y
        el To.
        """
        # Localizar elementos a firmar
        body = envelope.find(f".//{_t('s', 'Body')}")
        timestamp = envelope.find(f".//{_t('wsu', 'Timestamp')}")
        to = envelope.find(f".//{_t('wsa', 'To')}")

        # Construir SignedInfo
        signed_info = etree.SubElement(sig_placeholder, _t("ds", "SignedInfo"))
        cm = etree.SubElement(signed_info, _t("ds", "CanonicalizationMethod"))
        cm.set("Algorithm", "http://www.w3.org/2001/10/xml-exc-c14n#")
        sm = etree.SubElement(signed_info, _t("ds", "SignatureMethod"))
        sm.set("Algorithm", "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256")

        # Referencias a Body, Timestamp, To
        for elem, eid in [(body, body_id), (timestamp, timestamp_id), (to, "id-To")]:
            ref = etree.SubElement(signed_info, _t("ds", "Reference"))
            ref.set("URI", f"#{eid}")
            transforms = etree.SubElement(ref, _t("ds", "Transforms"))
            t = etree.SubElement(transforms, _t("ds", "Transform"))
            t.set("Algorithm", "http://www.w3.org/2001/10/xml-exc-c14n#")
            dm = etree.SubElement(ref, _t("ds", "DigestMethod"))
            dm.set("Algorithm", "http://www.w3.org/2001/04/xmlenc#sha256")
            dv = etree.SubElement(ref, _t("ds", "DigestValue"))

            # Canonicalizar el elemento y calcular digest
            canon = etree.tostring(elem, method="c14n", exclusive=True)
            dv.text = base64.b64encode(hashlib.sha256(canon).digest()).decode("ascii")

        # SignatureValue
        sv = etree.SubElement(sig_placeholder, _t("ds", "SignatureValue"))

        # Firmar el SignedInfo canonicalizado
        canon_si = etree.tostring(signed_info, method="c14n", exclusive=True)
        sig_bytes = self.certificado.private_key.sign(
            canon_si,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        sv.text = base64.b64encode(sig_bytes).decode("ascii")

        # KeyInfo con SecurityTokenReference
        ki = etree.SubElement(sig_placeholder, _t("ds", "KeyInfo"))
        str_elem = etree.SubElement(ki, _t("wsse", "SecurityTokenReference"))
        ref = etree.SubElement(str_elem, _t("wsse", "Reference"))
        ref.set("URI", f"#{token_id}")
        ref.set("ValueType",
                "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-x509-token-profile-1.0#X509v3")

    # ════════════════════════════════════════════════════════════════════
    # HTTP
    # ════════════════════════════════════════════════════════════════════

    def _enviar_post(self, soap_envelope: bytes, action: str) -> RespuestaDIAN:
        """Envía el POST al endpoint DIAN y procesa la respuesta."""
        headers = {
            "Content-Type": "application/soap+xml;charset=UTF-8",
            "SOAPAction": f"http://wcf.dian.colombia/IWcfDianCustomerServices/{action}",
        }

        try:
            response = requests.post(
                self.endpoint,
                data=soap_envelope,
                headers=headers,
                timeout=self.timeout,
            )
        except requests.exceptions.Timeout:
            return RespuestaDIAN(
                exitoso=False,
                error_message="Timeout esperando respuesta de DIAN",
            )
        except requests.exceptions.ConnectionError as e:
            return RespuestaDIAN(
                exitoso=False,
                error_message=f"Error de conexión: {e}",
            )

        if response.status_code != 200:
            return RespuestaDIAN(
                exitoso=False,
                http_status=response.status_code,
                error_message=f"HTTP {response.status_code}: {response.text[:500]}",
                xml_respuesta_raw=response.content,
            )

        # Parsear respuesta SOAP
        return self._parsear_respuesta(response.content)

    def _parsear_respuesta(self, xml_bytes: bytes) -> RespuestaDIAN:
        """Parsea la respuesta SOAP de DIAN."""
        try:
            root = etree.fromstring(xml_bytes)
        except etree.XMLSyntaxError as e:
            return RespuestaDIAN(
                exitoso=False,
                error_message=f"Respuesta no es XML válido: {e}",
                xml_respuesta_raw=xml_bytes,
            )

        # Verificar si es un fault SOAP
        ns_s = {"s": NS_SOAP}
        fault = root.find(".//s:Fault", ns_s)
        if fault is not None:
            reason = fault.find(".//s:Reason/s:Text", ns_s)
            return RespuestaDIAN(
                exitoso=False,
                error_message=reason.text if reason is not None else "SOAP Fault",
                xml_respuesta_raw=xml_bytes,
            )

        # Buscar elementos típicos de respuesta exitosa
        # Estructura típica: SendEventUpdateStatusResponse > SendEventUpdateStatusResult > XmlBytesBase64...
        ns_wcf = {"wcf": NS_WCF}
        track_id_elem = root.find(".//wcf:XmlDocumentKey", ns_wcf)
        is_valid_elem = root.find(".//wcf:IsValid", ns_wcf)
        status_code_elem = root.find(".//wcf:StatusCode", ns_wcf)
        status_desc_elem = root.find(".//wcf:StatusDescription", ns_wcf)
        status_msg_elem = root.find(".//wcf:StatusMessage", ns_wcf)

        return RespuestaDIAN(
            exitoso=True,
            track_id=track_id_elem.text if track_id_elem is not None else None,
            es_valido=(is_valid_elem.text.lower() == "true") if is_valid_elem is not None else None,
            status_code=status_code_elem.text if status_code_elem is not None else None,
            status_description=status_desc_elem.text if status_desc_elem is not None else None,
            status_message=status_msg_elem.text if status_msg_elem is not None else None,
            xml_respuesta_raw=xml_bytes,
            http_status=200,
        )

    def _parsear_consulta(self, xml_bytes: bytes, track_id: str) -> ResultadoConsulta:
        """Parsea la respuesta de GetStatus."""
        try:
            root = etree.fromstring(xml_bytes)
        except etree.XMLSyntaxError:
            return ResultadoConsulta(track_id=track_id, estado="Error parseo")

        ns_wcf = {"wcf": NS_WCF}
        status = root.find(".//wcf:StatusDescription", ns_wcf)
        is_valid = root.find(".//wcf:IsValid", ns_wcf)

        errores = []
        for err in root.findall(".//wcf:ErrorMessage//wcf:string", ns_wcf):
            if err.text:
                errores.append(err.text)

        return ResultadoConsulta(
            track_id=track_id,
            estado=status.text if status is not None else "Desconocido",
            es_valido=(is_valid.text.lower() == "true") if is_valid is not None else None,
            errores=errores,
        )


# ════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════

def _t(prefix: str, tag: str) -> str:
    return f"{{{NSMAP_SOAP[prefix]}}}{tag}"
