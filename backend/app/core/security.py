"""
Cryptographic utility for securing sensitive API keys in the SQLite database.
Uses AES-128 in CBC mode with HMAC (Fernet).
"""

import base64
import hashlib
import os
import logging
from pathlib import Path
from cryptography.fernet import Fernet
from app.core.config import settings

logger = logging.getLogger("cryptograph.security")

# Master key file stored locally and gitignored for persistent local development key retention
KEY_PATH = Path(__file__).parent.parent.parent / "master.key"

def _get_or_create_master_key() -> bytes:
    """Gets or derives a 32-byte Fernet key from environment variables or local disk file."""
    env_key = os.getenv("ENCRYPTION_KEY") or os.getenv("MASTER_KEY")
    if env_key:
        key_bytes = env_key.strip().encode("utf-8")
        try:
            # Test if it's already a valid Fernet key
            Fernet(key_bytes)
            return key_bytes
        except Exception:
            # Hash to 32 bytes and base64 encode for a valid Fernet key
            digest = hashlib.sha256(key_bytes).digest()
            return base64.urlsafe_b64encode(digest)

    if KEY_PATH.exists():
        try:
            with open(KEY_PATH, "rb") as f:
                content = f.read().strip()
                Fernet(content)
                return content
        except Exception:
            pass

    if settings.environment == "production":
        raise RuntimeError("CRITICAL: CRYPTOGRAPH_MASTER_KEY environment variable is required in production. Refusing to write key to local disk.")

    new_key = Fernet.generate_key()
    try:
        with open(KEY_PATH, "wb") as f:
            f.write(new_key)
        logger.warning(f"[Security] Generated new local master key at {KEY_PATH}. Do NOT use this in production.")
    except Exception as e:
        logger.error(f"[Security] Could not write master.key to disk: {e}")
    return new_key

# Initialize global cipher
try:
    _cipher = Fernet(_get_or_create_master_key())
except Exception as e:
    logger.error(f"[Security] Failed to initialize encryption: {e}")
    if settings.environment == "production":
        raise RuntimeError(f"CRITICAL: Failed to initialize encryption cipher: {e}")
    _cipher = None

def encrypt_secret(plain_text: str) -> str:
    """Encrypts a string into a base64 encoded token."""
    if not plain_text:
        return plain_text
    if not _cipher:
        raise RuntimeError("CRITICAL: Encryption cipher is not initialized. Cannot encrypt secret safely.")
    # Prefix with ENC: to identify encrypted strings easily
    encrypted = _cipher.encrypt(plain_text.encode("utf-8"))
    return f"ENC:{encrypted.decode('utf-8')}"

def decrypt_secret(cipher_text: str) -> str:
    """Decrypts an ENC: prefixed string back to plain text."""
    if not cipher_text:
        return cipher_text
    if not _cipher:
        raise RuntimeError("CRITICAL: Encryption cipher is not initialized. Cannot decrypt secret.")
        
    if cipher_text.startswith("ENC:"):
        actual_cipher = cipher_text[4:]
        try:
            decrypted = _cipher.decrypt(actual_cipher.encode("utf-8"))
            return decrypted.decode("utf-8")
        except Exception as e:
            logger.error(f"[Security] Failed to decrypt: {e}")
            return ""
            
    # Return as-is if not encrypted
    return cipher_text
