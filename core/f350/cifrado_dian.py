"""
core/f350/cifrado_dian.py
Cifra/descifra las credenciales DIAN por empresa antes de guardarlas en Supabase.
Usa Fernet (AES-128) con una clave que vive SOLO en variables de entorno
(F350_FERNET_KEY), nunca en el repo ni en la base de datos.

Generar la clave una vez y ponerla en Railway/entorno:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

Guardar credenciales (ejemplo):
    cred = {"tipo_doc": "CC", "num_doc": "12345", "password": "****"}
    token = cifrar(json.dumps(cred))     # -> guardas 'token' en la tabla
Recuperar:
    cred = json.loads(descifrar(token))  # solo en memoria, al momento de usar
"""
from __future__ import annotations

import os

from cryptography.fernet import Fernet


def _fernet() -> Fernet:
    key = os.environ.get("F350_FERNET_KEY")
    if not key:
        raise RuntimeError("Falta la variable de entorno F350_FERNET_KEY (clave de cifrado).")
    return Fernet(key.encode() if isinstance(key, str) else key)


def cifrar(texto: str) -> str:
    return _fernet().encrypt(texto.encode("utf-8")).decode("ascii")


def descifrar(token: str) -> str:
    return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
