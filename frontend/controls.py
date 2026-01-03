"""
Controls Module
Strictly limited operator controls.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, 
    QFileDialog, QMessageBox, QFrame
)
from PySide6.QtCore import Signal, Slot


class ControlPanel(QFrame):
    """
    Operator control panel.
    Actions strictly limited to:
    - Load configuration file
    - Manage credentials (create/unlock vault)
    - Launch bot
    - Pause / Resume
    - Emergency stop (with confirmation)
    """
    
    config_load_requested = Signal(str)
    credentials_requested = Signal()
    launch_requested = Signal()
    pause_requested = Signal()
    resume_requested = Signal()
    emergency_stop_requested = Signal()
    safe_shutdown_requested = Signal()
    
    def __init__(self):
        super().__init__()
        self._bot_state = "IDLE"
        self._config_loaded = False
        self._paper_trading = False
        self._vault_unlocked = False
        self._setup_ui()
        self._update_button_states()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)
        
        # Section 1: Configuration
        from PySide6.QtWidgets import QLabel, QGroupBox
        config_group = QGroupBox("Configuration & Accès")
        config_layout = QVBoxLayout(config_group)
        config_layout.setSpacing(15)
        
        self._load_config_btn = QPushButton("📁 Charger Fichier JSON")
        self._load_config_btn.clicked.connect(self._on_load_config)
        config_layout.addWidget(self._load_config_btn)
        
        self._credentials_btn = QPushButton("🔐 Déverrouiller le Vault")
        self._credentials_btn.clicked.connect(self._on_credentials)
        config_layout.addWidget(self._credentials_btn)
        
        layout.addWidget(config_group)
        
        # Section 2: Commandes de Bord
        ops_group = QGroupBox("Commandes Opérationnelles")
        ops_layout = QVBoxLayout(ops_group)
        ops_layout.setSpacing(15)
        
        self._launch_btn = QPushButton("🚀 DÉMARRER LE BOT")
        self._launch_btn.setProperty("class", "launch")
        self._launch_btn.clicked.connect(self._on_launch)
        ops_layout.addWidget(self._launch_btn)
        
        pause_row = QHBoxLayout()
        self._pause_btn = QPushButton("⏸️ PAUSE")
        self._pause_btn.setProperty("class", "pause")
        self._pause_btn.clicked.connect(self._on_pause)
        pause_row.addWidget(self._pause_btn)
        
        self._resume_btn = QPushButton("▶️ REPRENDRE")
        self._resume_btn.setProperty("class", "launch")
        self._resume_btn.clicked.connect(self._on_resume)
        pause_row.addWidget(self._resume_btn)
        ops_layout.addLayout(pause_row)
        
        self._shutdown_btn = QPushButton("🚪 FERMETURE SÉCURISÉE")
        self._shutdown_btn.setFixedHeight(40)
        self._shutdown_btn.setProperty("class", "pause")
        self._shutdown_btn.clicked.connect(self._on_shutdown)
        ops_layout.addWidget(self._shutdown_btn)
        
        layout.addWidget(ops_group)
        
        layout.addStretch()
        
        # Section 3: Urgence
        self._emergency_btn = QPushButton("🛑 ARRÊT D'URGENCE TOTAL")
        self._emergency_btn.setProperty("class", "danger")
        self._emergency_btn.setFixedHeight(50)
        self._emergency_btn.clicked.connect(self._on_emergency_stop)
        layout.addWidget(self._emergency_btn)
    
    def _on_load_config(self):
        """Handle load config button click."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Sélectionner fichier de configuration",
            "",
            "JSON Files (*.json)"
        )
        if file_path:
            self.config_load_requested.emit(file_path)
    
    def _on_credentials(self):
        """Handle credentials button click."""
        self.credentials_requested.emit()
    
    def _on_launch(self):
        """Handle launch button click."""
        self.launch_requested.emit()
    
    def _on_pause(self):
        """Handle pause button click."""
        self.pause_requested.emit()
    
    def _on_resume(self):
        """Handle resume button click."""
        self.resume_requested.emit()
    
    def _on_emergency_stop(self):
        """Handle emergency stop with confirmation."""
        reply = QMessageBox.warning(
            self,
            "⚠️ Confirmation Arrêt d'Urgence",
            "Cette action va:\n\n"
            "• Annuler tous les ordres en attente\n"
            "• Geler tous les pools de capital\n"
            "• Désactiver toutes les stratégies\n"
            "• Nécessiter un redémarrage manuel\n\n"
            "Êtes-vous sûr de vouloir continuer?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.emergency_stop_requested.emit()
            
    def _on_shutdown(self):
        """Handle safe shutdown request."""
        self.safe_shutdown_requested.emit()
    
    def _update_button_states(self):
        """Update button enabled states based on current bot state."""
        is_idle = self._bot_state == "IDLE"
        is_running = self._bot_state == "RUNNING"
        is_paused = self._bot_state == "PAUSED"
        is_killed = self._bot_state == "KILLED"
        
        # Load Config Button
        self._load_config_btn.setEnabled(not is_killed)
        
        # Credentials Button
        self._credentials_btn.setEnabled(is_idle)
        
        # Launch Button Logic & Tooltips
        # Launch requires config AND (vault unlocked OR paper trading)
        can_launch = is_idle and self._config_loaded and (self._vault_unlocked or self._paper_trading)
        self._launch_btn.setEnabled(can_launch)
        
        if not is_idle:
            self._launch_btn.setToolTip("Le bot est déjà en cours d'exécution.")
        elif not self._config_loaded:
            self._launch_btn.setToolTip("Veuillez charger une configuration d'abord.")
        elif not (self._vault_unlocked or self._paper_trading):
            self._launch_btn.setToolTip("Veuillez déverrouiller le vault ou activer le paper trading.")
        else:
            self._launch_btn.setToolTip("Prêt à démarrer.")
        
        # Pause/Resume/Stop
        self._pause_btn.setEnabled(is_running)
        self._resume_btn.setEnabled(is_paused)
        self._emergency_btn.setEnabled(not is_killed and not is_idle)
        self._shutdown_btn.setEnabled(not is_killed)
    
    @Slot(str)
    def set_bot_state(self, state: str):
        """Update tracked bot state and refresh buttons."""
        self._bot_state = state
        self._update_button_states()
    
    @Slot(bool)
    def set_config_loaded(self, loaded: bool):
        """Update config loaded status and refresh buttons."""
        self._config_loaded = loaded
        self._update_button_states()

    @Slot(bool)
    def set_paper_trading(self, active: bool):
        """Update paper trading status and refresh buttons."""
        self._paper_trading = active
        self._update_button_states()
    
    @Slot(bool)
    def set_vault_unlocked(self, unlocked: bool):
        """Update vault status and refresh buttons."""
        self._vault_unlocked = unlocked
        if unlocked:
            self._credentials_btn.setText("🔓 Vault Déverrouillé")
            self._credentials_btn.setProperty("class", "launch")
        else:
            self._credentials_btn.setText("🔐 Credentials")
            self._credentials_btn.setProperty("class", "")
        self._credentials_btn.style().unpolish(self._credentials_btn)
        self._credentials_btn.style().polish(self._credentials_btn)
        self._update_button_states()
