"""Authenticated encryption utilities for link notes using Python stdlib."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import zlib

ENCRYPTED_NOTE_PREFIX = "aite_enc:v1:"

_SALT_SIZE = 16
_NONCE_SIZE = 16
_TAG_SIZE = 32
_HEADER_SIZE = _SALT_SIZE + _NONCE_SIZE + _TAG_SIZE
_PBKDF2_ITERATIONS = 200_000
_DOMAIN_TAG = b"aite_enc:v1"


class NoteCryptoError(Exception):
    """Base error for note encryption/decryption operations."""


class InvalidNotePasswordError(NoteCryptoError):
    """Raised when the provided password fails authentication."""


class CorruptedNotePayloadError(NoteCryptoError):
    """Raised when an encrypted note payload is malformed or truncated."""


def is_encrypted_note(text: str | None) -> bool:
    """Return True if the given note text is an encrypted note payload."""
    if not isinstance(text, str):
        return False
    return text.strip().startswith(ENCRYPTED_NOTE_PREFIX)


def _derive_keys(password: str, salt: bytes) -> tuple[bytes, bytes]:
    """Derive 256-bit encryption key and 256-bit MAC key from password and salt."""
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        _PBKDF2_ITERATIONS,
        dklen=64,
    )
    return dk[:32], dk[32:64]


def _xor_keystream(data: bytes, enc_key: bytes, nonce: bytes) -> bytes:
    """XOR data with a BLAKE2b counter-mode keystream."""
    out = bytearray(len(data))
    block_size = 64
    num_blocks = (len(data) + block_size - 1) // block_size

    for counter in range(num_blocks):
        block_Offset = counter * block_size
        chunk = data[block_Offset : block_Offset + block_size]
        ks_block = hashlib.blake2b(
            counter.to_bytes(8, "little"),
            key=enc_key,
            salt=nonce,
            digest_size=block_size,
        ).digest()
        for i, b in enumerate(chunk):
            out[block_Offset + i] = b ^ ks_block[i]

    return bytes(out)


def encrypt_note(plaintext: str, password: str) -> str:
    """Encrypt plaintext note string with password using Encrypt-then-MAC."""
    if not password:
        raise ValueError("Password must not be empty")
    clean_text = plaintext.strip() if plaintext else ""
    if not clean_text:
        return ""

    salt = secrets.token_bytes(_SALT_SIZE)
    nonce = secrets.token_bytes(_NONCE_SIZE)
    enc_key, mac_key = _derive_keys(password, salt)

    compressed = zlib.compress(clean_text.encode("utf-8"), level=6)
    ciphertext = _xor_keystream(compressed, enc_key, nonce)
    tag = hmac.digest(mac_key, _DOMAIN_TAG + salt + nonce + ciphertext, "sha256")

    blob = salt + nonce + tag + ciphertext
    encoded = base64.urlsafe_b64encode(blob).decode("ascii")
    return f"{ENCRYPTED_NOTE_PREFIX}{encoded}"


def decrypt_note(payload: str, password: str) -> str:
    """Authenticate and decrypt an encrypted note payload with password."""
    if not isinstance(payload, str):
        raise CorruptedNotePayloadError("Payload must be a string")

    stripped = payload.strip()
    if not stripped.startswith(ENCRYPTED_NOTE_PREFIX):
        return stripped

    if not password:
        raise InvalidNotePasswordError("Password must not be empty")

    b64_part = stripped[len(ENCRYPTED_NOTE_PREFIX) :]
    try:
        blob = base64.urlsafe_b64decode(b64_part.encode("ascii"))
    except Exception as exc:
        raise CorruptedNotePayloadError("Invalid base64 encoding in encrypted note") from exc

    if len(blob) <= _HEADER_SIZE:
        raise CorruptedNotePayloadError("Encrypted note payload is truncated")

    salt = blob[:_SALT_SIZE]
    nonce = blob[_SALT_SIZE : _SALT_SIZE + _NONCE_SIZE]
    tag = blob[_SALT_SIZE + _NONCE_SIZE : _HEADER_SIZE]
    ciphertext = blob[_HEADER_SIZE:]

    enc_key, mac_key = _derive_keys(password, salt)
    expected_tag = hmac.digest(mac_key, _DOMAIN_TAG + salt + nonce + ciphertext, "sha256")
    if not hmac.compare_digest(expected_tag, tag):
        raise InvalidNotePasswordError("Invalid password")

    try:
        compressed = _xor_keystream(ciphertext, enc_key, nonce)
        plaintext_bytes = zlib.decompress(compressed)
        return plaintext_bytes.decode("utf-8")
    except Exception as exc:
        raise CorruptedNotePayloadError("Failed to decode decrypted note payload") from exc
