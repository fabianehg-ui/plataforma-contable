"""
core/dian_pt/vault.py

Almacén cifrado de certificados y credenciales DIAN por cliente.

Cada cliente tiene sus 5 credenciales DIAN almacenadas cifradas:
  1. Certificado .p12 (binario)
  2. Contraseña del .p12
  3. Software ID (UUID asignado por DIAN)
  4. Software Security Code (PIN del software)
  5. Clave técnica (TestSetId)

Cifrado:
  - AES-256-GCM (cifrado autenticado, garantiza integridad)
  - Clave derivada de master password con PBKDF2-HMAC-SHA256 (300k iter)
  - Salt único por cliente
  - Nonce único por operación

Estructura en disco:
  core/data/empresas/{NIT}_{slug}/credenciales_dian.enc
    {
      "version": 1,
      "salt_b64": "...",
      "nonce_b64": "...",
      "ciphertext_b64": "...",
      "tag_b64": "...",
      "fecha_almacenado": "2026-05-19T...",
      "huella_p12_sha1": "..."   # No sensible, para identificación
    }

⚠️ NUNCA escribir el plaintext en logs, archivos temporales, ni stdout.
"""
from __future__ import annotations

import base64
import json
import os
import secrets
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .certificado import CertificadoP12, cargar_p12


# ════════════════════════════════════════════════════════════════════════
# Constantes
# ════════════════════════════════════════════════════════════════════════

PBKDF2_ITERATIONS = 300_000      # Recomendación OWASP 2024+
KEY_SIZE_BYTES = 32              # AES-256
NONCE_SIZE_BYTES = 12            # GCM standard
SALT_SIZE_BYTES = 16             # Único por cliente
VAULT_VERSION = 1


# ════════════════════════════════════════════════════════════════════════
# Estructuras
# ════════════════════════════════════════════════════════════════════════

@dataclass
class CredencialesDIAN:
    """
    Las 5 credenciales DIAN de un cliente para emitir documentos electrónicos.

    En memoria contiene el .p12 descifrado, listo para usar.
    """
    nit: str                            # NIT sin DV
    razon_social: str                   # Para mostrar en UI
    p12_bytes: bytes                    # Contenido del .p12 (binario)
    p12_password: str                   # Contraseña del .p12
    software_id: str                    # UUID asignado por DIAN
    software_security_code: str         # PIN del software (secreto)
    clave_tecnica: str                  # TestSetId / clave técnica
    ambiente: str = "habilitacion"      # "habilitacion" o "produccion"

    def cargar_certificado(self) -> CertificadoP12:
        """Devuelve el CertificadoP12 listo para firmar."""
        return cargar_p12(self.p12_bytes, self.p12_password)

    @property
    def info_publica(self) -> dict:
        """Datos NO sensibles, seguros para mostrar/loguear."""
        return {
            "nit": self.nit,
            "razon_social": self.razon_social,
            "ambiente": self.ambiente,
            "software_id": self.software_id[:8] + "..." if self.software_id else "",
            "tiene_p12": bool(self.p12_bytes),
        }


# ════════════════════════════════════════════════════════════════════════
# Excepciones
# ════════════════════════════════════════════════════════════════════════

class ErrorVault(Exception):
    """Error base para problemas del vault."""


class MasterPasswordIncorrecto(ErrorVault):
    """La master password no descifra correctamente."""


class CredencialesNoEncontradas(ErrorVault):
    """No hay credenciales almacenadas para ese NIT."""


class VaultCorrupto(ErrorVault):
    """El archivo cifrado está corrupto o tiene formato inválido."""


# ════════════════════════════════════════════════════════════════════════
# Funciones criptográficas
# ════════════════════════════════════════════════════════════════════════

def _derivar_clave(master_password: str, salt: bytes) -> bytes:
    """
    Deriva una clave AES-256 desde la master password usando PBKDF2-HMAC-SHA256.

    300k iteraciones es lento intencionalmente (~250ms en hardware moderno)
    para resistir ataques de fuerza bruta.
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=KEY_SIZE_BYTES,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    return kdf.derive(master_password.encode("utf-8"))


def _cifrar(plaintext: bytes, master_password: str) -> dict:
    """
    Cifra plaintext con AES-256-GCM.

    Returns:
        dict con salt, nonce, ciphertext y tag (todos base64).
    """
    salt = secrets.token_bytes(SALT_SIZE_BYTES)
    nonce = secrets.token_bytes(NONCE_SIZE_BYTES)
    key = _derivar_clave(master_password, salt)

    aesgcm = AESGCM(key)
    ciphertext_with_tag = aesgcm.encrypt(nonce, plaintext, associated_data=None)

    # AESGCM retorna ciphertext+tag concatenados. Los separamos para
    # almacenarlos claramente.
    ciphertext = ciphertext_with_tag[:-16]
    tag = ciphertext_with_tag[-16:]

    return {
        "salt_b64": base64.b64encode(salt).decode("ascii"),
        "nonce_b64": base64.b64encode(nonce).decode("ascii"),
        "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
        "tag_b64": base64.b64encode(tag).decode("ascii"),
    }


def _descifrar(datos: dict, master_password: str) -> bytes:
    """
    Descifra datos AES-256-GCM.

    Raises:
        MasterPasswordIncorrecto: si la clave no descifra correctamente.
        VaultCorrupto: si el formato es inválido.
    """
    try:
        salt = base64.b64decode(datos["salt_b64"])
        nonce = base64.b64decode(datos["nonce_b64"])
        ciphertext = base64.b64decode(datos["ciphertext_b64"])
        tag = base64.b64decode(datos["tag_b64"])
    except (KeyError, ValueError) as e:
        raise VaultCorrupto(f"Formato inválido: {e}")

    key = _derivar_clave(master_password, salt)
    aesgcm = AESGCM(key)

    try:
        # Reconcatenar ciphertext + tag para AESGCM.decrypt
        plaintext = aesgcm.decrypt(nonce, ciphertext + tag, associated_data=None)
    except Exception:
        # AESGCM no distingue "password incorrecto" de "datos corruptos"
        # — ambos producen falla de autenticación
        raise MasterPasswordIncorrecto(
            "No se pudo descifrar. Master password incorrecta o datos corruptos."
        )

    return plaintext


# ════════════════════════════════════════════════════════════════════════
# Vault API principal
# ════════════════════════════════════════════════════════════════════════

class VaultDIAN:
    """
    Almacén cifrado de credenciales DIAN multi-empresa.

    Uso:
        vault = VaultDIAN(master_password="...")

        # Guardar credenciales de un cliente
        vault.guardar(CredencialesDIAN(
            nit="901038325",
            razon_social="JIPER SAS",
            p12_bytes=open("jiper.p12", "rb").read(),
            p12_password="...",
            software_id="...",
            software_security_code="...",
            clave_tecnica="...",
        ))

        # Cargar después
        creds = vault.cargar("901038325")
        cert = creds.cargar_certificado()
    """

    def __init__(
        self,
        master_password: str,
        ruta_base: Optional[Path] = None,
    ):
        """
        Args:
            master_password: clave maestra para cifrar/descifrar.
                              Debe configurarse en el ambiente del operador.
            ruta_base: directorio donde se almacenan las credenciales.
                        Default: core/data/empresas/
        """
        if not master_password or len(master_password) < 8:
            raise ErrorVault(
                "master_password debe tener al menos 8 caracteres"
            )
        self._master = master_password
        self.ruta_base = ruta_base or self._ruta_default()

    @staticmethod
    def _ruta_default() -> Path:
        """Devuelve core/data/empresas/ relativo al repo."""
        # Buscar hacia arriba el directorio del proyecto
        aqui = Path(__file__).resolve()
        for p in [aqui.parent.parent.parent / "core" / "data" / "empresas",
                  Path.cwd() / "core" / "data" / "empresas"]:
            if p.exists() or p.parent.exists():
                return p
        return aqui.parent.parent.parent / "core" / "data" / "empresas"

    def _ruta_credenciales(self, nit: str) -> Path:
        """Ruta del archivo cifrado para un NIT."""
        # Buscar el directorio que coincida con el NIT (formato {NIT}_{slug})
        if not self.ruta_base.exists():
            self.ruta_base.mkdir(parents=True, exist_ok=True)

        # Si existe directorio con NIT_..., usarlo. Si no, crear NIT_default
        existentes = list(self.ruta_base.glob(f"{nit}_*"))
        if existentes:
            dir_emp = existentes[0]
        else:
            dir_emp = self.ruta_base / f"{nit}_sin_slug"
            dir_emp.mkdir(parents=True, exist_ok=True)

        return dir_emp / "credenciales_dian.enc"

    # ════════════════════════════════════════════════════════════════
    # Operaciones
    # ════════════════════════════════════════════════════════════════

    def guardar(self, credenciales: CredencialesDIAN) -> Path:
        """
        Cifra y almacena las credenciales de un cliente.

        Si ya existían credenciales para ese NIT, se sobreescriben.

        Returns:
            Path del archivo cifrado.
        """
        # Validar el .p12 antes de guardar
        try:
            cert = cargar_p12(credenciales.p12_bytes, credenciales.p12_password)
        except Exception as e:
            raise ErrorVault(
                f"El certificado .p12 no se puede abrir: {e}. "
                f"Verifica el archivo y la contraseña antes de guardar."
            )

        # Verificar que el NIT del cert coincida con el NIT declarado
        if cert.nit and cert.nit != credenciales.nit:
            raise ErrorVault(
                f"El NIT del certificado ({cert.nit}) no coincide con el "
                f"NIT declarado ({credenciales.nit}). ¿Subió el certificado correcto?"
            )

        # Serializar credenciales a JSON (con p12 en base64)
        payload = {
            "nit": credenciales.nit,
            "razon_social": credenciales.razon_social,
            "p12_bytes_b64": base64.b64encode(credenciales.p12_bytes).decode("ascii"),
            "p12_password": credenciales.p12_password,
            "software_id": credenciales.software_id,
            "software_security_code": credenciales.software_security_code,
            "clave_tecnica": credenciales.clave_tecnica,
            "ambiente": credenciales.ambiente,
        }
        plaintext = json.dumps(payload).encode("utf-8")

        # Cifrar
        cifrado = _cifrar(plaintext, self._master)
        cifrado["version"] = VAULT_VERSION
        cifrado["fecha_almacenado"] = datetime.now(timezone.utc).isoformat()
        cifrado["huella_p12_sha1"] = cert.huella_sha1  # Para identificación

        # Escribir a disco
        ruta = self._ruta_credenciales(credenciales.nit)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps(cifrado, indent=2), encoding="utf-8")

        return ruta

    def cargar(self, nit: str) -> CredencialesDIAN:
        """
        Descifra y devuelve las credenciales de un cliente.

        Raises:
            CredencialesNoEncontradas: no hay credenciales para ese NIT.
            MasterPasswordIncorrecto: master password errada.
            VaultCorrupto: archivo dañado.
        """
        ruta = self._ruta_credenciales(nit)
        if not ruta.exists():
            raise CredencialesNoEncontradas(
                f"No hay credenciales almacenadas para NIT {nit}. "
                f"Usa vault.guardar() para registrarlas primero."
            )

        # Leer y validar formato
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise VaultCorrupto(f"Archivo JSON inválido: {e}")

        if datos.get("version") != VAULT_VERSION:
            raise VaultCorrupto(
                f"Versión del vault no soportada: {datos.get('version')}"
            )

        # Descifrar
        plaintext = _descifrar(datos, self._master)
        payload = json.loads(plaintext.decode("utf-8"))

        return CredencialesDIAN(
            nit=payload["nit"],
            razon_social=payload["razon_social"],
            p12_bytes=base64.b64decode(payload["p12_bytes_b64"]),
            p12_password=payload["p12_password"],
            software_id=payload["software_id"],
            software_security_code=payload["software_security_code"],
            clave_tecnica=payload["clave_tecnica"],
            ambiente=payload.get("ambiente", "habilitacion"),
        )

    def existe(self, nit: str) -> bool:
        """¿Hay credenciales almacenadas para ese NIT?"""
        return self._ruta_credenciales(nit).exists()

    def eliminar(self, nit: str) -> bool:
        """
        Elimina las credenciales de un cliente.

        Returns:
            True si se eliminó, False si no existían.
        """
        ruta = self._ruta_credenciales(nit)
        if ruta.exists():
            # Sobreescribir con basura antes de eliminar (defensa básica
            # contra recuperación forense desde disco no SSD)
            try:
                size = ruta.stat().st_size
                with open(ruta, "wb") as f:
                    f.write(secrets.token_bytes(size))
                    f.flush()
                    os.fsync(f.fileno())
            except Exception:
                pass  # Mejor esfuerzo
            ruta.unlink()
            return True
        return False

    def listar_clientes(self) -> list[dict]:
        """
        Lista los NITs que tienen credenciales almacenadas, con metadatos
        NO sensibles (no descifra el contenido).

        Útil para mostrar en UI sin pedir master password todavía.
        """
        if not self.ruta_base.exists():
            return []

        clientes = []
        for dir_emp in self.ruta_base.glob("*/"):
            archivo = dir_emp / "credenciales_dian.enc"
            if not archivo.exists():
                continue
            try:
                datos = json.loads(archivo.read_text(encoding="utf-8"))
                # NIT está al inicio del nombre del directorio (NIT_slug)
                nit = dir_emp.name.split("_")[0]
                clientes.append({
                    "nit": nit,
                    "fecha_almacenado": datos.get("fecha_almacenado"),
                    "huella_p12_sha1": datos.get("huella_p12_sha1", "")[:16] + "...",
                    "ruta": str(archivo),
                })
            except (json.JSONDecodeError, IOError):
                continue
        return clientes

    # ════════════════════════════════════════════════════════════════
    # Verificación de master password
    # ════════════════════════════════════════════════════════════════

    def verificar_master(self, nit: str) -> bool:
        """
        Verifica que la master password puede descifrar las credenciales
        de un cliente conocido.

        Útil para validar al inicio antes de mostrar UI.
        """
        if not self.existe(nit):
            return False
        try:
            self.cargar(nit)
            return True
        except MasterPasswordIncorrecto:
            return False
