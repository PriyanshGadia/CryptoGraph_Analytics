"""
Cryptographic utility for securing sensitive API keys in the SQLite database.
Uses AES-128 in CBC mode with HMAC (Fernet).
"""

import os
from pathlib import Path
from cryptography.fernet import Fernet
from app.core.config import settings

# A local master key file prevents keys from being leaked via SQLite alone.
# If SQLite is stolen, the keys are safe unless master.key is also stolen.
KEY_PATH = Path(__file__).parent.parent.parent / "master.key"

def _get_or_create_master_key() -> bytes:
    """Gets the master key from environment variables or disk, or generates a new one if it doesn't exist."""
    env_key = os.getenv("ENCRYPTION_KEY") or os.getenv("MASTER_KEY")
    if env_key:
        # If it's a raw string, we strip whitespace and encode it
        return env_key.strip().encode("utf-8")

    if KEY_PATH.exists():
        with open(KEY_PATH, "rb") as f:
            return f.read().strip()
    else:
        new_key = Fernet.generate_key()
        with open(KEY_PATH, "wb") as f:
            f.write(new_key)
        return new_key

# Initialize global cipher
try:
    _cipher = Fernet(_get_or_create_master_key())
except Exception as e:
    print(f"[Security] Failed to initialize encryption: {e}")
    _cipher = None

def encrypt_secret(plain_text: str) -> str:
    """Encrypts a string into a base64 encoded token."""
    if not _cipher or not plain_text:
        return plain_text
    # Prefix with ENC: to identify encrypted strings easily
    encrypted = _cipher.encrypt(plain_text.encode("utf-8"))
    return f"ENC:{encrypted.decode('utf-8')}"

def decrypt_secret(cipher_text: str) -> str:
    """Decrypts an ENC: prefixed string back to plain text."""
    if not _cipher or not cipher_text:
        return cipher_text
        
    if cipher_text.startswith("ENC:"):
        actual_cipher = cipher_text[4:]
        try:
            decrypted = _cipher.decrypt(actual_cipher.encode("utf-8"))
            return decrypted.decode("utf-8")
        except Exception as e:
            print(f"[Security] Failed to decrypt: {e}")
            return ""
            
    # Return as-is if not encrypted
    return cipher_text
