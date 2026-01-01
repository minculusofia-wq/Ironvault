"""
Credentials Manager Module
Secure handling of user credentials for trading operations.
Credentials exist in memory only during bot execution.
"""

from dataclasses import dataclass
from typing import Callable
from pathlib import Path
import threading

from .secure_vault import (
    SecureVault, 
    VaultError, 
    VaultNotFoundError, 
    VaultCorruptedError, 
    VaultDecryptionError
)
from .audit_logger import AuditLogger, EventType


# Credential keys (constants to avoid typos)
CRED_WALLET_PRIVATE_KEY = "wallet_private_key"
CRED_POLYMARKET_API_KEY = "polymarket_api_key"
CRED_POLYMARKET_API_SECRET = "polymarket_api_secret"
CRED_POLYMARKET_API_PASSPHRASE = "polymarket_api_passphrase"


@dataclass
class CredentialsStatus:
    """Status of credentials manager."""
    vault_exists: bool
    vault_loaded: bool
    has_wallet: bool
    has_polymarket: bool


class CredentialsManager:
    """
    Secure credentials manager.
    
    Security guarantees:
    - Credentials stored encrypted on disk (vault)
    - Master password never stored
    - Credentials decrypted only in memory
    - Credentials destroyed on shutdown/kill
    - No logging of credential values
    """
    
    DEFAULT_VAULT_PATH = ".ironvault/credentials.vault"
    
    def __init__(self, audit_logger: AuditLogger, vault_path: str | None = None):
        self._audit = audit_logger
        
        # Determine vault path
        if vault_path:
            self._vault_path = vault_path
        else:
            home = Path.home()
            self._vault_path = str(home / self.DEFAULT_VAULT_PATH)
        
        self._vault = SecureVault(self._vault_path)
        
        # In-memory credentials (NEVER logged or persisted)
        self._credentials: dict[str, str] | None = None
        self._lock = threading.Lock()
        
        # Callbacks
        self._status_callbacks: list[Callable[[CredentialsStatus], None]] = []
        
        self._audit.log(EventType.SYSTEM_ERROR, "CREDENTIALS_MANAGER_INITIALIZED", {
            "vault_path": self._vault_path,
            "vault_exists": self._vault.exists()
        })
    
    def create_vault(
        self, 
        wallet_private_key: str,
        polymarket_api_key: str,
        polymarket_api_secret: str,
        polymarket_api_passphrase: str,
        master_password: str
    ) -> tuple[bool, str]:
        """
        Create a new vault with credentials.
        
        Args:
            wallet_private_key: Web3 wallet private key
            polymarket_api_key: Polymarket API key
            polymarket_api_secret: Polymarket API secret
            master_password: Password for vault encryption
            
        Returns:
            (success, message)
        """
        with self._lock:
            try:
                credentials = {
                    CRED_WALLET_PRIVATE_KEY: wallet_private_key,
                    CRED_POLYMARKET_API_KEY: polymarket_api_key,
                    CRED_POLYMARKET_API_SECRET: polymarket_api_secret,
                    CRED_POLYMARKET_API_PASSPHRASE: polymarket_api_passphrase
                }
                
                self._vault.create(credentials, master_password)
                
                # Log event (NO credential values!)
                self._audit.log(EventType.OPERATOR_ACTION, "VAULT_CREATED", {
                    "vault_path": self._vault_path
                })
                
                self._notify_status()
                return True, "Vault créé avec succès"
                
            except Exception as e:
                self._audit.log(EventType.SYSTEM_ERROR, "VAULT_CREATE_FAILED", {
                    "error_type": type(e).__name__
                })
                return False, f"Échec création vault: {type(e).__name__}"
    
    def unlock_vault(self, master_password: str) -> tuple[bool, str]:
        """
        Unlock vault and load credentials into memory.
        
        Args:
            master_password: Password for vault decryption
            
        Returns:
            (success, message)
        """
        with self._lock:
            try:
                self._credentials = self._vault.decrypt(master_password)
                
                # Validate required credentials present
                if not self._validate_credentials():
                    self._credentials = None
                    return False, "Credentials incomplets dans le vault"
                
                self._audit.log(EventType.OPERATOR_ACTION, "VAULT_UNLOCKED", {
                    "has_wallet": bool(self._credentials.get(CRED_WALLET_PRIVATE_KEY)),
                    "has_polymarket": bool(self._credentials.get(CRED_POLYMARKET_API_KEY))
                })
                
                self._notify_status()
                return True, "Vault déverrouillé"
                
            except VaultNotFoundError:
                return False, "Vault inexistant"
            except VaultDecryptionError:
                self._audit.log(EventType.SYSTEM_ERROR, "VAULT_UNLOCK_FAILED", {
                    "reason": "DECRYPTION_FAILED"
                })
                return False, "Mot de passe incorrect"
            except VaultCorruptedError:
                self._audit.log(EventType.KILL_SWITCH, "VAULT_CORRUPTED", {})
                return False, "VAULT_CORRUPTED"
            except Exception as e:
                self._audit.log(EventType.SYSTEM_ERROR, "VAULT_UNLOCK_ERROR", {
                    "error_type": type(e).__name__
                })
                return False, f"Erreur: {type(e).__name__}"
    
    def lock_vault(self) -> None:
        """
        Lock vault and destroy credentials in memory.
        Called on bot shutdown or kill switch.
        """
        with self._lock:
            if self._credentials:
                # Clear credential values
                for key in self._credentials:
                    self._credentials[key] = ""
                self._credentials = None
                
                self._audit.log(EventType.OPERATOR_ACTION, "VAULT_LOCKED", {})
            
            self._notify_status()
    
    def destroy_credentials(self) -> None:
        """
        Emergency destruction of credentials.
        Called by kill switch.
        """
        with self._lock:
            if self._credentials:
                for key in list(self._credentials.keys()):
                    self._credentials[key] = "\x00" * len(self._credentials[key])
                self._credentials.clear()
                self._credentials = None
                
                self._audit.log(EventType.KILL_SWITCH, "CREDENTIALS_DESTROYED", {})
            
            self._notify_status()
    
    def get_wallet_private_key(self) -> str | None:
        """
        Get wallet private key for execution engine.
        Returns None if vault not unlocked.
        
        WARNING: Value must never be logged or transmitted.
        """
        with self._lock:
            if not self._credentials:
                return None
            return self._credentials.get(CRED_WALLET_PRIVATE_KEY)
    
    def get_polymarket_credentials(self) -> tuple[str, str, str] | None:
        """
        Get Polymarket API credentials for execution engine.
        Returns None if vault not unlocked.
        
        WARNING: Values must never be logged or transmitted.
        """
        with self._lock:
            if not self._credentials:
                return None
            api_key = self._credentials.get(CRED_POLYMARKET_API_KEY)
            api_secret = self._credentials.get(CRED_POLYMARKET_API_SECRET)
            api_passphrase = self._credentials.get(CRED_POLYMARKET_API_PASSPHRASE)
            
            if api_key and api_secret and api_passphrase:
                return (api_key, api_secret, api_passphrase)
            return None
    
    def _validate_credentials(self) -> bool:
        """Validate that all required credentials are present."""
        if not self._credentials:
            return False
        
        required = [
            CRED_WALLET_PRIVATE_KEY,
            CRED_POLYMARKET_API_KEY,
            CRED_POLYMARKET_API_SECRET,
            CRED_POLYMARKET_API_PASSPHRASE
        ]
        
        for key in required:
            if not self._credentials.get(key):
                return False
        
        return True
    
    def get_status(self) -> CredentialsStatus:
        """Get current credentials status (no secrets)."""
        with self._lock:
            return CredentialsStatus(
                vault_exists=self._vault.exists(),
                vault_loaded=self._credentials is not None,
                has_wallet=bool(self._credentials and self._credentials.get(CRED_WALLET_PRIVATE_KEY)),
                has_polymarket=bool(self._credentials and self._credentials.get(CRED_POLYMARKET_API_KEY))
            )
    
    def subscribe_status(self, callback: Callable[[CredentialsStatus], None]) -> None:
        """Subscribe to credentials status changes."""
        self._status_callbacks.append(callback)
    
    def _notify_status(self) -> None:
        """Notify subscribers of status change."""
        status = self.get_status()
        for callback in self._status_callbacks:
            try:
                callback(status)
            except Exception:
                pass
    
    @property
    def vault_exists(self) -> bool:
        """Whether vault file exists."""
        return self._vault.exists()
    
    @property
    def is_unlocked(self) -> bool:
        """Whether vault is currently unlocked."""
        with self._lock:
            return self._credentials is not None
    
    @property
    def vault_path(self) -> str:
        """Vault file path."""
        return self._vault_path
