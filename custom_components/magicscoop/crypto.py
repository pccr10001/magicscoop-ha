"""MagicScoop client-side crypto.

The app does not send the 6-digit e-mail verification code in the clear: it
builds an 8-byte block ``code + 0x00 + <len>``, encrypts it with 2-key
Triple-DES (DES-EDE) in ECB mode and base64-encodes the result.

Verified against captured traffic:

    "952924" -> 39 35 32 39 32 34 00 06 -> des-ede-ecb -> ae42540698b891d0
             -> base64 "rkJUBpi4kdA="
    "952927" -> 39 35 32 39 32 37 00 06 -> des-ede-ecb -> 7a077aafb641c50c
             -> base64 "egd6r7ZBxQw="

The key below is the 16-byte constant embedded at .rodata 0x1c501f0 in
libMagicScoop.so and handed to the client's cipher object at +0x798.
"""
from __future__ import annotations

import base64

# 16-byte (2-key) Triple-DES key taken from libMagicScoop.so
_KEY16 = bytes.fromhex("8f7eb776a28f06c9a3146cfc5d0a9350")
# Expand to K1|K2|K1 so libraries that only accept 24-byte keys keep working.
_KEY = _KEY16 + _KEY16[:8]
_BLOCK = 8


def _triple_des_ecb_encrypt(block: bytes) -> bytes:
    """Encrypt one 8-byte block. Tries cryptography, then pycryptodome."""
    if len(block) != _BLOCK:
        raise ValueError("Triple-DES block must be 8 bytes")

    # 1) cryptography >= 43 exposes TripleDES under .decrepit
    try:
        from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
        from cryptography.hazmat.primitives.ciphers import Cipher, modes

        encryptor = Cipher(TripleDES(_KEY), modes.ECB()).encryptor()
        return encryptor.update(block) + encryptor.finalize()
    except ImportError:
        pass

    # 2) cryptography < 43 kept TripleDES in the main namespace
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, modes
        from cryptography.hazmat.primitives.ciphers.algorithms import TripleDES

        encryptor = Cipher(TripleDES(_KEY), modes.ECB()).encryptor()
        return encryptor.update(block) + encryptor.finalize()
    except ImportError:
        pass

    # 3) pycryptodome fallback
    try:
        from Crypto.Cipher import DES3

        return DES3.new(_KEY, DES3.MODE_ECB).encrypt(block)
    except ImportError as err:  # pragma: no cover
        raise RuntimeError(
            "No 3DES implementation available (install 'cryptography' "
            "or 'pycryptodome')"
        ) from err


def _build_block(code: str) -> bytes:
    """Recreate the 8-byte plaintext block the app encrypts.

    Observed layout for a 6-digit code: ``<ascii digits><0x00><0x06>``.
    """
    raw = code.encode("ascii")
    if len(raw) > _BLOCK - 2:
        raise ValueError("Verification code is too long")
    return raw + b"\x00" + bytes([len(raw)])


def encrypt_verification_code(code: str) -> str:
    """Return the base64 string the cloud expects in ``VerificationCode``."""
    code = (code or "").strip()
    if not code:
        raise ValueError("Empty verification code")
    if not code.isdigit():
        raise ValueError("Verification code must be digits only")
    block = _build_block(code)
    # pad with zero bytes if a shorter code ever shows up
    block = block.ljust(_BLOCK, b"\x00")
    return base64.b64encode(_triple_des_ecb_encrypt(block)).decode("ascii")
