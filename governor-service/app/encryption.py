"""
encryption.py — Fernet symmetric encryption for notification secrets
=====================================================================
Encrypts sensitive data (SMTP passwords, Slack tokens, Jira API tokens, etc.)
before storing them in the database. Decrypts on read.

When GOVERNOR_ENCRYPTION_KEY is not set, storage falls back to plain text
(development mode). In production, set this to a Fernet key:

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
from __future__ import annotations

import logging

logger = logging.getLogger("governor.encryption")

_fernet = None
_initialized = False


def _get_fernet():
    """Lazily initialise Fernet cipher from settings."""
    global _fernet, _initialized
    if _initialized:
        return _fernet
    _initialized = True
    try:
        from .config import settings
        key = settings.encryption_key
        if key:
            from cryptography.fernet import Fernet
            _fernet = Fernet(key.encode() if isinstance(key, str) else key)
            logger.info("Encryption enabled for notification channel secrets.")
        else:
            logger.warning(
                "GOVERNOR_ENCRYPTION_KEY not set — notification secrets stored in plain text. "
                "Set this in production."
            )
    except Exception as exc:
        logger.warning("Failed to initialise encryption: %s", exc)
    return _fernet


def encrypt_value(plain_text: str) -> str:
    """Encrypt a string value. Returns the encrypted token or plain text if no key."""
    f = _get_fernet()
    if f is None:
        return plain_text
    try:
        return f.encrypt(plain_text.encode()).decode()
    except Exception:
        return plain_text


def decrypt_value(encrypted_text: str) -> str:
    """Decrypt a string value. Returns plain text if decryption fails or no key."""
    f = _get_fernet()
    if f is None:
        return encrypted_text
    try:
        return f.decrypt(encrypted_text.encode()).decode()
    except Exception:
        # Could be plain text stored before encryption was enabled
        return encrypted_text
