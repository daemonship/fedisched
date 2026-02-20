"""Encryption utilities for storing sensitive credentials at rest."""

from cryptography.fernet import Fernet, InvalidToken
from app.config import settings


class CredentialEncryption:
    """Fernet encryption for OAuth tokens and app passwords."""

    def __init__(self, key: str):
        """Initialize with a base64-encoded 32-byte key."""
        self.fernet = Fernet(key.encode())

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a string, return base64-encoded ciphertext."""
        if not plaintext:
            raise ValueError("Cannot encrypt empty string")
        return self.fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a base64-encoded ciphertext, return plaintext."""
        if not ciphertext:
            raise ValueError("Cannot decrypt empty string")
        try:
            return self.fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken as e:
            raise ValueError("Invalid encryption token or corrupted data") from e


# Global encryption instance
encryption = CredentialEncryption(settings.server_key)


def encrypt_credential(plaintext: str) -> str:
    """Encrypt a credential string."""
    return encryption.encrypt(plaintext)


def decrypt_credential(ciphertext: str) -> str:
    """Decrypt a credential string."""
    return encryption.decrypt(ciphertext)
