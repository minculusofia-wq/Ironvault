"""
Credentials Dialog Module
Secure dialogs for credentials input.
Passwords transmitted directly to backend, never stored in frontend.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QMessageBox, QFrame
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from .styles import COLORS, MAIN_STYLESHEET


class CreateVaultDialog(QDialog):
    """
    Dialog for creating a new credentials vault.
    Collects credentials and master password.
    
    Security:
    - All fields are password-masked
    - Values transmitted via signal, then cleared
    - No validation or storage in frontend
    """
    
    vault_create_requested = Signal(str, str, str, str, str)  # wallet, api_key, api_secret, api_passphrase, password
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔐 Créer Vault Sécurisé")
        self.setMinimumWidth(500)
        self.setStyleSheet(MAIN_STYLESHEET)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Header
        header = QLabel("Création du Vault Sécurisé")
        header.setStyleSheet(f"color: {COLORS['accent']}; font-size: 16px; font-weight: bold;")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)
        
        # Warning
        warning = QFrame()
        warning.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['surface_light']};
                border: 1px solid {COLORS['warning']};
                border-radius: 6px;
                padding: 10px;
            }}
        """)
        warning_layout = QVBoxLayout(warning)
        warning_label = QLabel(
            "⚠️ Ces informations seront chiffrées et stockées localement.\n"
            "Le mot de passe maître n'est JAMAIS sauvegardé.\n"
            "Conservez-le en lieu sûr - il est irrécupérable."
        )
        warning_label.setStyleSheet(f"color: {COLORS['warning']}; font-size: 12px;")
        warning_label.setWordWrap(True)
        warning_layout.addWidget(warning_label)
        layout.addWidget(warning)
        
        # Form
        form = QFormLayout()
        form.setSpacing(10)
        
        # Wallet private key
        self._wallet_input = QLineEdit()
        self._wallet_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._wallet_input.setPlaceholderText("Clé privée wallet Web3")
        form.addRow("🔑 Clé Privée Wallet:", self._wallet_input)
        
        # Polymarket API Key
        self._api_key_input = QLineEdit()
        self._api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_input.setPlaceholderText("Clé API Polymarket")
        form.addRow("🔗 API Key Polymarket:", self._api_key_input)
        
        # Polymarket API Secret
        self._api_secret_input = QLineEdit()
        self._api_secret_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_secret_input.setPlaceholderText("Secret API Polymarket")
        form.addRow("🔒 API Secret:", self._api_secret_input)
        
        # Polymarket API Passphrase
        self._api_passphrase_input = QLineEdit()
        self._api_passphrase_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_passphrase_input.setPlaceholderText("Passphrase API Polymarket")
        form.addRow("🔑 API Passphrase:", self._api_passphrase_input)
        
        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet(f"background-color: {COLORS['border']}")
        
        # Master password
        self._password_input = QLineEdit()
        self._password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_input.setPlaceholderText("Mot de passe maître (min 8 caractères)")
        form.addRow("🛡️ Mot de Passe Maître:", self._password_input)
        
        # Confirm password
        self._password_confirm = QLineEdit()
        self._password_confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_confirm.setPlaceholderText("Confirmer le mot de passe")
        form.addRow("🛡️ Confirmation:", self._password_confirm)
        
        layout.addLayout(form)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        cancel_btn = QPushButton("Annuler")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        create_btn = QPushButton("🔐 Créer Vault")
        create_btn.setProperty("class", "launch")
        create_btn.clicked.connect(self._on_create)
        btn_layout.addWidget(create_btn)
        
        layout.addLayout(btn_layout)
    
    def _on_create(self):
        """Handle create button click."""
        wallet = self._wallet_input.text()
        api_key = self._api_key_input.text()
        api_secret = self._api_secret_input.text()
        api_passphrase = self._api_passphrase_input.text()
        password = self._password_input.text()
        confirm = self._password_confirm.text()
        
        # Basic validation (no secret inspection)
        if not all([wallet, api_key, api_secret, api_passphrase, password]):
            QMessageBox.warning(self, "Champs requis", "Tous les champs sont obligatoires.")
            return
        
        if len(password) < 8:
            QMessageBox.warning(self, "Mot de passe faible", "Le mot de passe doit contenir au moins 8 caractères.")
            return
        
        if password != confirm:
            QMessageBox.warning(self, "Confirmation", "Les mots de passe ne correspondent pas.")
            return
        
        # Emit credentials to backend
        self.vault_create_requested.emit(wallet, api_key, api_secret, api_passphrase, password)
        
        # Clear all fields immediately after emission
        self._wallet_input.clear()
        self._api_key_input.clear()
        self._api_secret_input.clear()
        self._api_passphrase_input.clear()
        self._password_input.clear()
        self._password_confirm.clear()
        
        self.accept()
    
    def reject(self):
        """Clear fields on cancel."""
        self._wallet_input.clear()
        self._api_key_input.clear()
        self._api_secret_input.clear()
        self._api_passphrase_input.clear()
        self._password_input.clear()
        self._password_confirm.clear()
        super().reject()


class UnlockVaultDialog(QDialog):
    """
    Dialog for unlocking existing vault.
    Collects master password only.
    
    Security:
    - Password field is masked
    - Value transmitted via signal, then cleared
    """
    
    vault_unlock_requested = Signal(str)  # password
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔓 Déverrouiller Vault")
        self.setMinimumWidth(400)
        self.setStyleSheet(MAIN_STYLESHEET)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Header
        header = QLabel("Déverrouillage du Vault")
        header.setStyleSheet(f"color: {COLORS['accent']}; font-size: 16px; font-weight: bold;")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)
        
        # Info
        info = QLabel("Entrez votre mot de passe maître pour déverrouiller les credentials.")
        info.setStyleSheet(f"color: {COLORS['text_dim']}")
        info.setWordWrap(True)
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(info)
        
        # Password input
        form = QFormLayout()
        self._password_input = QLineEdit()
        self._password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_input.setPlaceholderText("Mot de passe maître")
        self._password_input.returnPressed.connect(self._on_unlock)
        form.addRow("🔑 Mot de Passe:", self._password_input)
        layout.addLayout(form)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        cancel_btn = QPushButton("Annuler")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        unlock_btn = QPushButton("🔓 Déverrouiller")
        unlock_btn.setProperty("class", "launch")
        unlock_btn.clicked.connect(self._on_unlock)
        btn_layout.addWidget(unlock_btn)
        
        layout.addLayout(btn_layout)
    
    def _on_unlock(self):
        """Handle unlock button click."""
        password = self._password_input.text()
        
        if not password:
            QMessageBox.warning(self, "Requis", "Le mot de passe est requis.")
            return
        
        # Emit password to backend
        self.vault_unlock_requested.emit(password)
        
        # Clear field immediately after emission
        self._password_input.clear()
        
        self.accept()
    
    def reject(self):
        """Clear field on cancel."""
        self._password_input.clear()
        super().reject()
