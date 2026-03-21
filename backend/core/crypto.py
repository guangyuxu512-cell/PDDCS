from __future__ import annotations

import hashlib
import os
from functools import lru_cache

import bcrypt
from cryptography.fernet import Fernet, InvalidToken


def _get_encryption_key() -> str:
    key = os.environ.get("ENCRYPTION_KEY", "").strip()
    if not key:
        raise RuntimeError("ENCRYPTION_KEY is required")
    return key


@lru_cache(maxsize=8)
def _build_fernet(key: str) -> Fernet:
    try:
        return Fernet(key.encode("utf-8"))
    except ValueError as exc:
        raise RuntimeError("ENCRYPTION_KEY must be a valid Fernet key") from exc


def _get_fernet() -> Fernet:
    return _build_fernet(_get_encryption_key())


def ensure_encryption_key() -> None:
    _get_fernet()


def encrypt(plaintext: str) -> str:
    token = _get_fernet().encrypt(plaintext.encode("utf-8"))
    return token.decode("utf-8")


def decrypt(ciphertext: str) -> str:
    try:
        payload = _get_fernet().decrypt(ciphertext.encode("utf-8"))
    except InvalidToken as exc:
        raise ValueError("Invalid encrypted payload") from exc
    return payload.decode("utf-8")


def hash_password(password: str) -> str:
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def fingerprint(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()[:8]
