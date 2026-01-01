"""
Secure Vault Module
Encrypted storage for sensitive credentials.
AES-GCM encryption with PBKDF2 key derivation.
"""

import os
import json
import secrets
from pathlib import Path
from dataclasses import dataclass
from typing import Any
from datetime import datetime

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend


# Constants
SALT_SIZE = 32
NONCE_SIZE = 12
KEY_SIZE = 32
ITERATIONS = 600000  # OWASP recommended minimum for PBKDF2-SHA256


class VaultError(Exception):
    """Base exception for vault operations."""
    pass


class VaultNotFoundError(VaultError):
    """Vault file does not exist."""
    pass


class VaultCorruptedError(VaultError):
    """Vault integrity check failed."""
    pass


class VaultDecryptionError(VaultError):
    """Decryption failed (wrong password or corrupted)."""
    pass


@dataclass
class VaultHeader:
    """Vault file header."""
    version: int
    created_at: str
    salt: bytes
    nonce: bytes


class SecureVault:
    """
    Secure encrypted vault for credentials storage.
    
    Security features:
    - AES-256-GCM authenticated encryption
    - PBKDF2 key derivation with high iteration count
    - Random salt per vault
    - Random nonce per encryption
    - Integrity verification via GCM tag
    """
    
    VAULT_VERSION = 1
    HEADER_SEPARATOR = b"---VAULT_DATA---"
    
    def __init__(self, vault_path: str):
        self._vault_path = Path(vault_path)
        self._vault_path.parent.mkdir(parents=True, exist_ok=True)
    
    def create(self, credentials: dict[str, str], master_password: str) -> bool:
        """
        Create a new encrypted vault with credentials.
        
        Args:
            credentials: Dictionary of credentials to store
            master_password: Password for encryption (not stored)
            
        Returns:
            True if vault created successfully
        """
        try:
            # Generate random salt and nonce
            salt = secrets.token_bytes(SALT_SIZE)
            nonce = secrets.token_bytes(NONCE_SIZE)
            
            # Derive encryption key from master password
            key = self._derive_key(master_password, salt)
            
            # Prepare credentials data
            data = {
                "credentials": credentials,
                "created_at": datetime.now().isoformat()
            }
            plaintext = json.dumps(data).encode('utf-8')
            
            # Encrypt with AES-GCM
            aesgcm = AESGCM(key)
            ciphertext = aesgcm.encrypt(nonce, plaintext, None)
            
            # Build vault file
            header = {
                "version": self.VAULT_VERSION,
                "created_at": datetime.now().isoformat()
            }
            header_bytes = json.dumps(header).encode('utf-8')
            
            vault_content = (
                header_bytes + 
                self.HEADER_SEPARATOR + 
                salt + 
                nonce + 
                ciphertext
            )
            
            # Write vault file with restricted permissions
            self._vault_path.write_bytes(vault_content)
            os.chmod(self._vault_path, 0o600)  # Owner read/write only
            
            # Securely clear sensitive data from memory
            self._secure_clear(key)
            self._secure_clear(plaintext)
            
            return True
            
        except Exception:
            # Clean up partial file on error
            if self._vault_path.exists():
                self._vault_path.unlink()
            raise
    
    def decrypt(self, master_password: str) -> dict[str, str]:
        """
        Decrypt vault and return credentials.
        
        Args:
            master_password: Password for decryption
            
        Returns:
            Dictionary of decrypted credentials
            
        Raises:
            VaultNotFoundError: Vault file doesn't exist
            VaultCorruptedError: Vault format invalid
            VaultDecryptionError: Decryption failed
        """
        if not self._vault_path.exists():
            raise VaultNotFoundError(f"Vault not found: {self._vault_path}")
        
        try:
            vault_content = self._vault_path.read_bytes()
            
            # Parse header
            if self.HEADER_SEPARATOR not in vault_content:
                raise VaultCorruptedError("Invalid vault format")
            
            header_bytes, encrypted_part = vault_content.split(self.HEADER_SEPARATOR, 1)
            
            # Validate header
            try:
                header = json.loads(header_bytes.decode('utf-8'))
                if header.get("version") != self.VAULT_VERSION:
                    raise VaultCorruptedError("Unsupported vault version")
            except json.JSONDecodeError:
                raise VaultCorruptedError("Invalid vault header")
            
            # Extract salt, nonce, and ciphertext
            if len(encrypted_part) < SALT_SIZE + NONCE_SIZE + 16:  # 16 = min GCM tag
                raise VaultCorruptedError("Vault data too short")
            
            salt = encrypted_part[:SALT_SIZE]
            nonce = encrypted_part[SALT_SIZE:SALT_SIZE + NONCE_SIZE]
            ciphertext = encrypted_part[SALT_SIZE + NONCE_SIZE:]
            
            # Derive key and decrypt
            key = self._derive_key(master_password, salt)
            
            try:
                aesgcm = AESGCM(key)
                plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            except Exception:
                self._secure_clear(key)
                raise VaultDecryptionError("Decryption failed - wrong password or corrupted vault")
            
            # Parse credentials
            try:
                data = json.loads(plaintext.decode('utf-8'))
                credentials = data.get("credentials", {})
            except json.JSONDecodeError:
                self._secure_clear(key)
                self._secure_clear(plaintext)
                raise VaultCorruptedError("Invalid credentials format")
            
            # Clear sensitive data
            self._secure_clear(key)
            self._secure_clear(plaintext)
            
            return credentials
            
        except (VaultNotFoundError, VaultCorruptedError, VaultDecryptionError):
            raise
        except Exception as e:
            raise VaultCorruptedError(f"Vault read error: {e}")
    
    def exists(self) -> bool:
        """Check if vault file exists."""
        return self._vault_path.exists()
    
    def delete(self) -> bool:
        """
        Securely delete vault file.
        
        Returns:
            True if deleted, False if didn't exist
        """
        if self._vault_path.exists():
            # Overwrite with random data before deletion
            size = self._vault_path.stat().st_size
            self._vault_path.write_bytes(secrets.token_bytes(size))
            self._vault_path.unlink()
            return True
        return False
    
    def _derive_key(self, password: str, salt: bytes) -> bytes:
        """
        Derive encryption key from password using PBKDF2.
        
        Key is derived fresh each time - never stored.
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=KEY_SIZE,
            salt=salt,
            iterations=ITERATIONS,
            backend=default_backend()
        )
        return kdf.derive(password.encode('utf-8'))
    
    def _secure_clear(self, data: bytes | bytearray) -> None:
        """
        Attempt to securely clear sensitive data from memory.
        
        Note: Due to Python's memory management, this is best-effort.
        The data may still exist in memory until garbage collected.
        """
        if isinstance(data, bytearray):
            for i in range(len(data)):
                data[i] = 0
        # For bytes objects, we can't modify in place
        # Python will garbage collect when references are removed
    
    @property
    def path(self) -> str:
        """Vault file path."""
        return str(self._vault_path)
