"""Token encryption utilities using Fernet symmetric encryption.

Tokens are encrypted with a Fernet key configured via TOKEN_ENCRYPTION_KEY.
If the key is not set, encrypt_token returns None and a warning is logged.
Generate a key with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

logger = logging.getLogger(__name__)


def _get_fernet() -> Optional[Fernet]:
    """Return a Fernet instance if TOKEN_ENCRYPTION_KEY is configured."""
    key = settings.TOKEN_ENCRYPTION_KEY
    if not key:
        return None
    return Fernet(key.encode())


def encrypt_token(token: str) -> Optional[str]:
    """Encrypt *token* and return the ciphertext as a str.

    Returns ``None`` when TOKEN_ENCRYPTION_KEY is not configured.
    """
    fernet = _get_fernet()
    if fernet is None:
        logger.warning("TOKEN_ENCRYPTION_KEY is not set; GitHub access token will not be stored.")
        return None
    return fernet.encrypt(token.encode()).decode()


def decrypt_token(encrypted_token: str) -> Optional[str]:
    """Decrypt *encrypted_token* and return the plaintext token.

    Returns ``None`` if TOKEN_ENCRYPTION_KEY is not set or decryption fails.
    """
    fernet = _get_fernet()
    if fernet is None:
        return None
    try:
        return fernet.decrypt(encrypted_token.encode()).decode()
    except InvalidToken:
        logger.error("Failed to decrypt GitHub access token: invalid token or wrong key.")
        return None
