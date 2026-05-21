"""
core/dian_pt/certificado.py

Manejo de certificado digital .p12 (PKCS#12) para firma de documentos
electrónicos ante DIAN.

Soporta los certificados emitidos por Andes SCD, Certicámara y GSE
(los 3 proveedores autorizados ONAC en Colombia).

Uso típico:
    cert = CertificadoP12.cargar("/ruta/al/certificado.p12", "contraseña")
    print(cert.razon_social)        # Nombre de la empresa titular
    print(cert.nit)                 # NIT del titular
    print(cert.fecha_vencimiento)   # Cuándo se vence
    print(cert.dias_para_vencer)    # Cuántos días quedan

El certificado se mantiene en memoria. NUNCA lo guardes en disco
descifrado. Si necesitas persistirlo, usa el VaultCertificados (separado).
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.hazmat.primitives import hashes
from cryptography import x509
from cryptography.x509.oid import NameOID


# ════════════════════════════════════════════════════════════════════════
# Estructura de datos del certificado cargado
# ════════════════════════════════════════════════════════════════════════

@dataclass
class CertificadoP12:
    """
    Certificado .p12 cargado y validado.

    Contiene la llave privada (para firmar), la cadena de certificados
    (para verificación) y los datos del titular extraídos del subject.
    """
    # Componentes criptográficos
    private_key: object              # rsa.RSAPrivateKey
    certificate: x509.Certificate    # El certificado del titular
    cadena_adicional: list           # Certificados intermedios (cadena CA)

    # Datos del titular (extraídos del subject)
    razon_social: str                # CN o O del certificado
    nit: str                          # serialNumber (formato DIAN)
    pais: str                         # C
    organizacion: str                 # O
    email: Optional[str]              # emailAddress (si está)

    # Datos del emisor (autoridad certificadora)
    emisor_razon_social: str         # Andes, Certicámara, GSE

    # Fechas de validez
    fecha_emision: datetime           # not_valid_before
    fecha_vencimiento: datetime       # not_valid_after

    # Identificadores
    serial_number: int                # Serial del certificado
    huella_sha1: str                  # Huella digital (para identificar)

    @property
    def dias_para_vencer(self) -> int:
        """Días que faltan para que el certificado venza."""
        ahora = datetime.now(timezone.utc)
        # Normalizar timezones
        vence = self.fecha_vencimiento
        if vence.tzinfo is None:
            vence = vence.replace(tzinfo=timezone.utc)
        delta = vence - ahora
        return delta.days

    @property
    def esta_vigente(self) -> bool:
        """¿El certificado está dentro de su período de validez?"""
        ahora = datetime.now(timezone.utc)
        emision = self.fecha_emision
        vence = self.fecha_vencimiento
        if emision.tzinfo is None:
            emision = emision.replace(tzinfo=timezone.utc)
        if vence.tzinfo is None:
            vence = vence.replace(tzinfo=timezone.utc)
        return emision <= ahora <= vence

    @property
    def info_publica(self) -> dict:
        """Datos NO sensibles del certificado, seguros para mostrar/loguear."""
        return {
            "razon_social": self.razon_social,
            "nit": self.nit,
            "emisor": self.emisor_razon_social,
            "fecha_emision": self.fecha_emision.isoformat(),
            "fecha_vencimiento": self.fecha_vencimiento.isoformat(),
            "dias_para_vencer": self.dias_para_vencer,
            "esta_vigente": self.esta_vigente,
            "serial": str(self.serial_number),
            "huella_sha1": self.huella_sha1,
        }


# ════════════════════════════════════════════════════════════════════════
# Excepciones específicas
# ════════════════════════════════════════════════════════════════════════

class ErrorCertificado(Exception):
    """Error base para problemas con el certificado."""


class CertificadoInvalido(ErrorCertificado):
    """El archivo .p12 no se pudo abrir o no es válido."""


class PasswordIncorrecto(ErrorCertificado):
    """La contraseña del .p12 no es correcta."""


class CertificadoVencido(ErrorCertificado):
    """El certificado está fuera de su período de validez."""


# ════════════════════════════════════════════════════════════════════════
# Carga del certificado
# ════════════════════════════════════════════════════════════════════════

def cargar_p12(
    archivo: Union[str, Path, bytes],
    password: str,
    validar_vigencia: bool = True,
) -> CertificadoP12:
    """
    Carga un archivo .p12 (PKCS#12) y devuelve los datos estructurados.

    Args:
        archivo: ruta al archivo .p12, o bytes del archivo.
        password: contraseña del .p12.
        validar_vigencia: si True, lanza CertificadoVencido si está fuera
                           del período de validez. Default True.

    Returns:
        CertificadoP12 con todos los datos extraídos.

    Raises:
        CertificadoInvalido: archivo corrupto o no es .p12.
        PasswordIncorrecto: contraseña errada.
        CertificadoVencido: si validar_vigencia=True y está vencido.
    """
    # Leer bytes
    if isinstance(archivo, (str, Path)):
        p = Path(archivo)
        if not p.exists():
            raise CertificadoInvalido(f"No existe el archivo: {p}")
        contenido = p.read_bytes()
    elif isinstance(archivo, bytes):
        contenido = archivo
    else:
        raise CertificadoInvalido(
            f"Tipo de archivo no soportado: {type(archivo)}"
        )

    # password como bytes (PKCS12 lo espera así)
    pwd_bytes = password.encode("utf-8") if password else None

    # Cargar con cryptography
    try:
        private_key, cert, cadena = pkcs12.load_key_and_certificates(
            contenido, pwd_bytes,
        )
    except ValueError as e:
        # cryptography lanza ValueError para varios casos
        msg = str(e).lower()
        if "mac" in msg or "invalid password" in msg or "incorrect" in msg:
            raise PasswordIncorrecto("Contraseña del .p12 incorrecta")
        raise CertificadoInvalido(f"No se pudo abrir el .p12: {e}")
    except Exception as e:
        raise CertificadoInvalido(f"Error inesperado: {e}")

    if cert is None:
        raise CertificadoInvalido(
            "El .p12 no contiene certificado (solo llave privada)"
        )
    if private_key is None:
        raise CertificadoInvalido(
            "El .p12 no contiene llave privada (solo certificado)"
        )

    # Extraer datos del subject
    subject = cert.subject
    cn = _extraer_atributo(subject, NameOID.COMMON_NAME) or ""
    o = _extraer_atributo(subject, NameOID.ORGANIZATION_NAME) or ""
    c = _extraer_atributo(subject, NameOID.COUNTRY_NAME) or "CO"
    sn = _extraer_atributo(subject, NameOID.SERIAL_NUMBER) or ""
    email = _extraer_atributo(subject, NameOID.EMAIL_ADDRESS)

    # El nombre del titular suele estar en O (organización) para certs de empresa
    # o en CN para personas naturales. Tomamos lo que esté.
    razon_social = o or cn or "DESCONOCIDO"

    # NIT: viene en serialNumber. Puede traer guion o no.
    nit = _normalizar_nit(sn)

    # Emisor (Andes, Certicámara, GSE)
    emisor = cert.issuer
    emisor_o = _extraer_atributo(emisor, NameOID.ORGANIZATION_NAME) or ""
    emisor_cn = _extraer_atributo(emisor, NameOID.COMMON_NAME) or ""
    emisor_nombre = emisor_o or emisor_cn or "DESCONOCIDO"

    # Huella SHA1 (para identificación)
    huella = cert.fingerprint(hashes.SHA1()).hex().upper()

    # Construir
    obj = CertificadoP12(
        private_key=private_key,
        certificate=cert,
        cadena_adicional=list(cadena) if cadena else [],
        razon_social=razon_social,
        nit=nit,
        pais=c,
        organizacion=o,
        email=email,
        emisor_razon_social=emisor_nombre,
        fecha_emision=_fecha_aware(cert.not_valid_before_utc if hasattr(cert, "not_valid_before_utc") else cert.not_valid_before),
        fecha_vencimiento=_fecha_aware(cert.not_valid_after_utc if hasattr(cert, "not_valid_after_utc") else cert.not_valid_after),
        serial_number=cert.serial_number,
        huella_sha1=huella,
    )

    # Validar vigencia si se pidió
    if validar_vigencia and not obj.esta_vigente:
        raise CertificadoVencido(
            f"Certificado vencido o no vigente. "
            f"Validez: {obj.fecha_emision} → {obj.fecha_vencimiento}"
        )

    return obj


# ════════════════════════════════════════════════════════════════════════
# Helpers internos
# ════════════════════════════════════════════════════════════════════════

def _extraer_atributo(name: x509.Name, oid) -> Optional[str]:
    """Extrae un atributo del subject/issuer por su OID, o None."""
    try:
        attrs = name.get_attributes_for_oid(oid)
        if attrs:
            return attrs[0].value
    except Exception:
        pass
    return None


def _normalizar_nit(serial: str) -> str:
    """
    Normaliza el NIT que viene en el serialNumber del certificado.

    Casos típicos:
      "901038325-1"   → "901038325"
      "CC 901038325"  → "901038325"
      "901038325"     → "901038325"
    """
    if not serial:
        return ""
    # Quitar prefijos comunes
    s = serial.upper().replace("NIT", "").replace("CC", "").strip()
    # Tomar solo dígitos hasta el primer guion (DV)
    if "-" in s:
        s = s.split("-")[0]
    # Quedarnos solo con dígitos
    digitos = "".join(c for c in s if c.isdigit())
    return digitos


def _fecha_aware(fecha: datetime) -> datetime:
    """Asegura que la fecha tenga timezone (UTC por defecto)."""
    if fecha.tzinfo is None:
        return fecha.replace(tzinfo=timezone.utc)
    return fecha
