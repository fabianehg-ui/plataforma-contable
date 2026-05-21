"""
core/dian_pt/firmador_xades.py

Firma XAdES-EPES de XMLs UBL para envío a DIAN.

XAdES-EPES = XML Advanced Electronic Signature - Explicit Policy-based
Electronic Signature. Es el formato de firma que DIAN exige para todos los
documentos electrónicos (facturas, notas, eventos RADIAN).

Particularidades de la firma DIAN:
  1. Algoritmo digest: SHA-256
  2. Canonicalización: C14N exclusiva (http://www.w3.org/2001/10/xml-exc-c14n#)
  3. Tres referencias firmadas:
     - Referencia al documento (URI="")
     - Referencia al KeyInfo
     - Referencia a SignedProperties
  4. Política de firma DIAN explícita (SignaturePolicyIdentifier)
  5. SigningCertificate digest (SHA-256 del .cer)
  6. La firma se inserta dentro del segundo <ext:ExtensionContent/>

Política de firma DIAN vigente al momento de escribir este módulo:
  - OID: 1.2.3.4.5.6.7.8.9 (placeholder - confirmar URL vigente)
  - URL: https://facturaelectronica.dian.gov.co/politicadefirma/v2/...

⚠️ IMPORTANTE: La URL y el digest exacto de la política de firma DIAN
cambian con resoluciones. ANTES DE PRODUCCIÓN, descargar la última
política desde:
  https://facturaelectronica.dian.gov.co/politicadefirma/v2/

y actualizar las constantes POLITICA_FIRMA_URL y POLITICA_FIRMA_HASH en
este archivo. El hash debe ser SHA-256 base64 del archivo PDF de la
política.

Referencias:
  - ETSI TS 101 903 v1.4.1 (XAdES)
  - Anexo Técnico DIAN, Apéndice 7
  - https://www.w3.org/TR/xmldsig-core/
"""
from __future__ import annotations

import base64
import hashlib
import uuid
from datetime import datetime, timezone
from typing import Optional

from lxml import etree
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography import x509

from .certificado import CertificadoP12


# ════════════════════════════════════════════════════════════════════════
# Constantes DIAN
# ════════════════════════════════════════════════════════════════════════

# Política de firma DIAN (URL y hash deben actualizarse al vigente)
POLITICA_FIRMA_URL = (
    "https://facturaelectronica.dian.gov.co/politicadefirma/v2/"
    "politicadefirmav2.pdf"
)
# Hash SHA-256 base64 del PDF de la política vigente
# ⚠️ ACTUALIZAR descargando el PDF y calculando: openssl dgst -sha256 -binary politica.pdf | base64
POLITICA_FIRMA_HASH = "dMrIywVZIduWlxIE5DkshamEPjPHzbq/STMQHRpUmwM="

# OID de la política DIAN
POLITICA_FIRMA_OID = "https://facturaelectronica.dian.gov.co/politicadefirma/v2/politicadefirmav2.pdf"
POLITICA_FIRMA_DESCRIPCION = "Política de firma para facturas electrónicas de la República de Colombia."

# Algoritmos
DIGEST_ALGORITHM = "http://www.w3.org/2001/04/xmlenc#sha256"
SIGNATURE_ALGORITHM = "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
CANON_METHOD = "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"
EXC_CANON_METHOD = "http://www.w3.org/2001/10/xml-exc-c14n#"

# Namespaces (los mismos del XML del evento)
NS_DS = "http://www.w3.org/2000/09/xmldsig#"
NS_XADES = "http://uri.etsi.org/01903/v1.3.2#"
NS_XADES141 = "http://uri.etsi.org/01903/v1.4.1#"
NS_EXT = "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2"

NSMAP = {
    "ds": NS_DS,
    "xades": NS_XADES,
    "xades141": NS_XADES141,
}


# ════════════════════════════════════════════════════════════════════════
# Excepciones
# ════════════════════════════════════════════════════════════════════════

class ErrorFirma(Exception):
    """Error base para problemas de firma."""


class XMLInvalido(ErrorFirma):
    """El XML no tiene la estructura esperada para firmar."""


# ════════════════════════════════════════════════════════════════════════
# API principal
# ════════════════════════════════════════════════════════════════════════

def firmar_xml(
    xml_bytes: bytes,
    certificado: CertificadoP12,
    fecha_firma: Optional[datetime] = None,
) -> bytes:
    """
    Firma un XML UBL con XAdES-EPES e inserta la firma en el segundo
    <ext:ExtensionContent/> (placeholder dejado por xml_evento_radian).

    Args:
        xml_bytes: el XML sin firmar (output de generar_xml_evento).
        certificado: certificado .p12 cargado.
        fecha_firma: timestamp de la firma. Si None, usa datetime.now(UTC).

    Returns:
        XML firmado como bytes UTF-8.

    Raises:
        XMLInvalido: si no se encuentra el placeholder de firma.
        ErrorFirma: si hay error en el proceso criptográfico.
    """
    if fecha_firma is None:
        fecha_firma = datetime.now(timezone.utc)

    # 1) Parsear XML
    parser = etree.XMLParser(remove_blank_text=False)
    root = etree.fromstring(xml_bytes, parser)

    # 2) Localizar el placeholder de firma (segundo <ext:ExtensionContent/>)
    placeholder = _localizar_placeholder_firma(root)

    # 3) Generar IDs únicos para los elementos de la firma
    sig_id = f"xmldsig-{uuid.uuid4()}"
    sig_value_id = f"{sig_id}-sigvalue"
    keyinfo_id = f"{sig_id}-keyinfo"
    signed_props_id = f"{sig_id}-signedprops"
    ref_signed_props_id = f"{sig_id}-ref-signedprops"
    ref_keyinfo_id = f"{sig_id}-ref-keyinfo"
    ref_doc_id = f"{sig_id}-ref-doc"

    # 4) Construir el bloque <ds:Signature> completo
    signature = _construir_signature_element(
        sig_id=sig_id,
        sig_value_id=sig_value_id,
        keyinfo_id=keyinfo_id,
        signed_props_id=signed_props_id,
        ref_signed_props_id=ref_signed_props_id,
        ref_keyinfo_id=ref_keyinfo_id,
        ref_doc_id=ref_doc_id,
        certificado=certificado,
        fecha_firma=fecha_firma,
    )

    # 5) Insertar la firma dentro del placeholder
    placeholder.append(signature)

    # 6) Calcular digests reales de las referencias
    _calcular_digests_referencias(root, signature, sig_id)

    # 7) Calcular SignatureValue (firma RSA sobre SignedInfo canonicalizado)
    _calcular_signature_value(signature, certificado, sig_value_id)

    # Serializar
    return etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone=False,
    )


# ════════════════════════════════════════════════════════════════════════
# Construcción de los elementos de la firma
# ════════════════════════════════════════════════════════════════════════

def _localizar_placeholder_firma(root) -> etree._Element:
    """
    Encuentra el segundo <ext:ExtensionContent/> que está reservado para la firma.

    El primero contiene <sts:DianExtensions>. El segundo está vacío
    (placeholder dejado por xml_evento_radian.generar_xml_evento).
    """
    ns = {"ext": NS_EXT}
    ext_contents = root.findall(".//ext:UBLExtension/ext:ExtensionContent", ns)

    if len(ext_contents) < 2:
        raise XMLInvalido(
            f"El XML debe tener al menos 2 ExtensionContent. "
            f"Encontrados: {len(ext_contents)}"
        )

    # El segundo es el placeholder (debe estar vacío)
    placeholder = ext_contents[1]
    if len(placeholder) > 0:
        raise XMLInvalido(
            "El segundo ExtensionContent no está vacío "
            "(¿ya está firmado el XML?)"
        )

    return placeholder


def _construir_signature_element(
    sig_id: str,
    sig_value_id: str,
    keyinfo_id: str,
    signed_props_id: str,
    ref_signed_props_id: str,
    ref_keyinfo_id: str,
    ref_doc_id: str,
    certificado: CertificadoP12,
    fecha_firma: datetime,
) -> etree._Element:
    """
    Construye toda la estructura <ds:Signature> con XAdES-EPES.

    Estructura:
      <ds:Signature Id="...">
        <ds:SignedInfo>
          <ds:CanonicalizationMethod/>
          <ds:SignatureMethod/>
          <ds:Reference Id="ref-doc" URI="">           ← Referencia al documento
            <ds:Transforms>
              <ds:Transform .../>                       (enveloped-signature)
            </ds:Transforms>
            <ds:DigestMethod/>
            <ds:DigestValue>...</ds:DigestValue>
          </ds:Reference>
          <ds:Reference Id="ref-keyinfo" URI="#keyinfo">  ← Ref al KeyInfo
            ...
          </ds:Reference>
          <ds:Reference Id="ref-signedprops" URI="#signedprops"
                        Type="http://uri.etsi.org/01903#SignedProperties">
            ...
          </ds:Reference>
        </ds:SignedInfo>
        <ds:SignatureValue Id="sigvalue">...</ds:SignatureValue>
        <ds:KeyInfo Id="keyinfo">
          <ds:X509Data>
            <ds:X509Certificate>...</ds:X509Certificate>
          </ds:X509Data>
        </ds:KeyInfo>
        <ds:Object>
          <xades:QualifyingProperties Target="#sig-id">
            <xades:SignedProperties Id="signedprops">
              <xades:SignedSignatureProperties>
                <xades:SigningTime>...</xades:SigningTime>
                <xades:SigningCertificate>
                  <xades:Cert>
                    <xades:CertDigest>...</xades:CertDigest>
                    <xades:IssuerSerial>...</xades:IssuerSerial>
                  </xades:Cert>
                </xades:SigningCertificate>
                <xades:SignaturePolicyIdentifier>
                  <xades:SignaturePolicyId>...</xades:SignaturePolicyId>
                </xades:SignaturePolicyIdentifier>
                <xades:SignerRole>...</xades:SignerRole>
              </xades:SignedSignatureProperties>
            </xades:SignedProperties>
          </xades:QualifyingProperties>
        </ds:Object>
      </ds:Signature>
    """
    sig = etree.Element(_ds("Signature"), nsmap=NSMAP)
    sig.set("Id", sig_id)

    # ── SignedInfo ──
    signed_info = etree.SubElement(sig, _ds("SignedInfo"))

    cm = etree.SubElement(signed_info, _ds("CanonicalizationMethod"))
    cm.set("Algorithm", EXC_CANON_METHOD)

    sm = etree.SubElement(signed_info, _ds("SignatureMethod"))
    sm.set("Algorithm", SIGNATURE_ALGORITHM)

    # Referencia 1: al documento completo
    ref_doc = etree.SubElement(signed_info, _ds("Reference"))
    ref_doc.set("Id", ref_doc_id)
    ref_doc.set("URI", "")
    transforms = etree.SubElement(ref_doc, _ds("Transforms"))
    t1 = etree.SubElement(transforms, _ds("Transform"))
    t1.set("Algorithm", "http://www.w3.org/2000/09/xmldsig#enveloped-signature")
    dm1 = etree.SubElement(ref_doc, _ds("DigestMethod"))
    dm1.set("Algorithm", DIGEST_ALGORITHM)
    dv1 = etree.SubElement(ref_doc, _ds("DigestValue"))
    dv1.text = "PLACEHOLDER"  # Se calcula después

    # Referencia 2: al KeyInfo
    ref_ki = etree.SubElement(signed_info, _ds("Reference"))
    ref_ki.set("Id", ref_keyinfo_id)
    ref_ki.set("URI", f"#{keyinfo_id}")
    dm2 = etree.SubElement(ref_ki, _ds("DigestMethod"))
    dm2.set("Algorithm", DIGEST_ALGORITHM)
    dv2 = etree.SubElement(ref_ki, _ds("DigestValue"))
    dv2.text = "PLACEHOLDER"

    # Referencia 3: a SignedProperties
    ref_sp = etree.SubElement(signed_info, _ds("Reference"))
    ref_sp.set("Id", ref_signed_props_id)
    ref_sp.set("URI", f"#{signed_props_id}")
    ref_sp.set("Type", "http://uri.etsi.org/01903#SignedProperties")
    dm3 = etree.SubElement(ref_sp, _ds("DigestMethod"))
    dm3.set("Algorithm", DIGEST_ALGORITHM)
    dv3 = etree.SubElement(ref_sp, _ds("DigestValue"))
    dv3.text = "PLACEHOLDER"

    # ── SignatureValue (placeholder, se calcula al final) ──
    sv = etree.SubElement(sig, _ds("SignatureValue"))
    sv.set("Id", sig_value_id)
    sv.text = "PLACEHOLDER"

    # ── KeyInfo ──
    key_info = etree.SubElement(sig, _ds("KeyInfo"))
    key_info.set("Id", keyinfo_id)
    x509_data = etree.SubElement(key_info, _ds("X509Data"))
    x509_cert = etree.SubElement(x509_data, _ds("X509Certificate"))
    cert_b64 = base64.b64encode(
        certificado.certificate.public_bytes(serialization.Encoding.DER)
    ).decode("ascii")
    x509_cert.text = cert_b64

    # ── Object con QualifyingProperties (XAdES) ──
    obj = etree.SubElement(sig, _ds("Object"))
    qp = etree.SubElement(obj, _xades("QualifyingProperties"))
    qp.set("Target", f"#{sig_id}")

    sp = etree.SubElement(qp, _xades("SignedProperties"))
    sp.set("Id", signed_props_id)

    ssp = etree.SubElement(sp, _xades("SignedSignatureProperties"))

    # SigningTime
    st = etree.SubElement(ssp, _xades("SigningTime"))
    st.text = fecha_firma.strftime("%Y-%m-%dT%H:%M:%S+00:00")

    # SigningCertificate
    sc = etree.SubElement(ssp, _xades("SigningCertificate"))
    cert_elem = etree.SubElement(sc, _xades("Cert"))

    cd = etree.SubElement(cert_elem, _xades("CertDigest"))
    cd_method = etree.SubElement(cd, _ds("DigestMethod"))
    cd_method.set("Algorithm", DIGEST_ALGORITHM)
    cd_value = etree.SubElement(cd, _ds("DigestValue"))
    # Digest SHA-256 del certificado DER
    cert_der = certificado.certificate.public_bytes(serialization.Encoding.DER)
    cd_value.text = base64.b64encode(hashlib.sha256(cert_der).digest()).decode("ascii")

    issuer_serial = etree.SubElement(cert_elem, _xades("IssuerSerial"))
    iname = etree.SubElement(issuer_serial, _ds("X509IssuerName"))
    iname.text = _formato_issuer_dn(certificado.certificate.issuer)
    serial = etree.SubElement(issuer_serial, _ds("X509SerialNumber"))
    serial.text = str(certificado.certificate.serial_number)

    # SignaturePolicyIdentifier (esto es lo que hace "EPES" a XAdES-EPES)
    spi = etree.SubElement(ssp, _xades("SignaturePolicyIdentifier"))
    spid = etree.SubElement(spi, _xades("SignaturePolicyId"))

    sigpid = etree.SubElement(spid, _xades("SigPolicyId"))
    sigpid_id = etree.SubElement(sigpid, _xades("Identifier"))
    sigpid_id.text = POLITICA_FIRMA_OID
    sigpid_desc = etree.SubElement(sigpid, _xades("Description"))
    sigpid_desc.text = POLITICA_FIRMA_DESCRIPCION

    sigph = etree.SubElement(spid, _xades("SigPolicyHash"))
    sph_method = etree.SubElement(sigph, _ds("DigestMethod"))
    sph_method.set("Algorithm", DIGEST_ALGORITHM)
    sph_value = etree.SubElement(sigph, _ds("DigestValue"))
    sph_value.text = POLITICA_FIRMA_HASH

    # SignerRole
    signer_role = etree.SubElement(ssp, _xades("SignerRole"))
    claimed_roles = etree.SubElement(signer_role, _xades("ClaimedRoles"))
    claimed_role = etree.SubElement(claimed_roles, _xades("ClaimedRole"))
    claimed_role.text = "supplier"

    return sig


# ════════════════════════════════════════════════════════════════════════
# Cálculo de digests y firma final
# ════════════════════════════════════════════════════════════════════════

def _calcular_digests_referencias(
    root,
    signature,
    sig_id: str,
) -> None:
    """
    Calcula los digests SHA-256 reales de las 3 referencias y los inserta
    en los DigestValue correspondientes.

    Orden de cálculo:
      1. Digest del documento (con enveloped-signature transform)
      2. Digest del KeyInfo canonicalizado
      3. Digest de SignedProperties canonicalizado
    """
    ns = {"ds": NS_DS}
    references = signature.findall(".//ds:SignedInfo/ds:Reference", ns)

    if len(references) != 3:
        raise ErrorFirma(
            f"Esperaba 3 referencias en SignedInfo, encontré {len(references)}"
        )

    # ── Referencia 1: documento completo (URI="") ──
    # Para el digest del documento: clonar root, quitar Signature, canonicalizar
    root_copy = etree.fromstring(etree.tostring(root))
    sig_in_copy = root_copy.find(f".//ds:Signature[@Id='{sig_id}']", ns)
    if sig_in_copy is not None:
        sig_in_copy.getparent().remove(sig_in_copy)
    canon_doc = etree.tostring(root_copy, method="c14n", exclusive=True)
    digest_doc = base64.b64encode(hashlib.sha256(canon_doc).digest()).decode("ascii")
    references[0].find("ds:DigestValue", ns).text = digest_doc

    # ── Referencia 2: KeyInfo ──
    key_info = signature.find("ds:KeyInfo", ns)
    canon_ki = etree.tostring(key_info, method="c14n", exclusive=True)
    digest_ki = base64.b64encode(hashlib.sha256(canon_ki).digest()).decode("ascii")
    references[1].find("ds:DigestValue", ns).text = digest_ki

    # ── Referencia 3: SignedProperties ──
    signed_props = signature.find(".//xades:SignedProperties", {"xades": NS_XADES})
    canon_sp = etree.tostring(signed_props, method="c14n", exclusive=True)
    digest_sp = base64.b64encode(hashlib.sha256(canon_sp).digest()).decode("ascii")
    references[2].find("ds:DigestValue", ns).text = digest_sp


def _calcular_signature_value(
    signature,
    certificado: CertificadoP12,
    sig_value_id: str,
) -> None:
    """
    Firma RSA-SHA256 el SignedInfo canonicalizado.

    El SignatureValue es la firma criptográfica que une todo el conjunto.
    """
    ns = {"ds": NS_DS}
    signed_info = signature.find("ds:SignedInfo", ns)

    # Canonicalizar SignedInfo
    canon_si = etree.tostring(signed_info, method="c14n", exclusive=True)

    # Firmar con RSA-SHA256
    signature_bytes = certificado.private_key.sign(
        canon_si,
        padding.PKCS1v15(),
        hashes.SHA256(),
    )

    # Insertar el valor en SignatureValue
    sv = signature.find("ds:SignatureValue", ns)
    sv.text = base64.b64encode(signature_bytes).decode("ascii")


# ════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════

def _ds(tag: str) -> str:
    return f"{{{NS_DS}}}{tag}"


def _xades(tag: str) -> str:
    return f"{{{NS_XADES}}}{tag}"


def _formato_issuer_dn(name: x509.Name) -> str:
    """
    Convierte un x509.Name a formato RFC 2253 (Distinguished Name).
    Ej: CN=Andes CA, O=Andes SCD, C=CO
    """
    return name.rfc4514_string()
