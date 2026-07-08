"""
Unit tests for cryptographic secret encryption/decryption.
"""

import sys
import os
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))
backend_dir = root_dir / "backend"
if str(backend_dir) not in sys.path:
    sys.path.append(str(backend_dir))

import pytest
from backend.app.core.security import encrypt_secret, decrypt_secret, _get_or_create_master_key

def test_master_key_generation():
    key = _get_or_create_master_key()
    assert isinstance(key, bytes)
    assert len(key) > 0

def test_encryption_decryption_cycle():
    secret = "sk_live_groq_test_key_12345"
    encrypted = encrypt_secret(secret)
    assert encrypted.startswith("ENC:")
    assert encrypted != secret

    decrypted = decrypt_secret(encrypted)
    assert decrypted == secret

def test_env_key_derivation(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", "custom_user_secret_passphrase")
    key = _get_or_create_master_key()
    assert isinstance(key, bytes)
    # Fernet key must be 44 base64 chars
    assert len(key) == 44
