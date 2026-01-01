"""
Main Window Module
Primary application window integrating dashboard and controls.
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QStatusBar,
    QMessageBox
)
from PySide6.QtCore import Slot, QTimer

from .dashboard import Dashboard
from .controls import ControlPanel
from .credentials_dialog import CreateVaultDialog, UnlockVaultDialog
from .styles import MAIN_STYLESHEET
from backend.orchestrator import Orchestrator, BotState


class MainWindow(QMainWindow):
    """
    Main application window.
    Integrates dashboard (read-only) and controls (limited actions).
    """
    
    def __init__(self):
        super().__init__()
        
        self._orchestrator = Orchestrator()
        
        self._setup_ui()
        self._connect_signals()
        self._start_update_timer()
        self._check_initial_vault_status()
    
    def _setup_ui(self):
        """Setup the main window UI."""
        self.setWindowTitle("🏦 IRONVAULT - Trading Bot")
        self.setMinimumSize(800, 750)
        self.setStyleSheet(MAIN_STYLESHEET)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        self._dashboard = Dashboard()
        layout.addWidget(self._dashboard, stretch=1)
        
        self._controls = ControlPanel()
        layout.addWidget(self._controls)
        
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Prêt - Charger config et déverrouiller vault pour commencer")
    
    def _connect_signals(self):
        """Connect control signals to handlers."""
        self._controls.config_load_requested.connect(self._on_load_config)
        self._controls.credentials_requested.connect(self._on_credentials)
        self._controls.launch_requested.connect(self._on_launch)
        self._controls.pause_requested.connect(self._on_pause)
        self._controls.resume_requested.connect(self._on_resume)
        self._controls.emergency_stop_requested.connect(self._on_emergency_stop)
        
        self._orchestrator.subscribe_state(self._on_bot_state_changed)
    
    def _start_update_timer(self):
        """Start periodic UI update timer."""
        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self._update_ui)
        self._update_timer.start(500)
    
    def _check_initial_vault_status(self):
        """Check vault status on startup."""
        creds = self._orchestrator.credentials_manager
        if creds.vault_exists:
            self._status_bar.showMessage("Vault existant détecté - déverrouillage requis")
    
    @Slot(str)
    def _on_load_config(self, file_path: str):
        """Handle config load request."""
        success, message = self._orchestrator.load_config(file_path)
        
        if success:
            # Force immediate sync of the control panel
            self._controls.set_config_loaded(True)
            self._dashboard.system_panel.update_config(file_path)
            
            self._status_bar.showMessage(f"✓ Configuration chargée: {file_path.split('/')[-1]}")
            # Trigger full UI update to refresh button enabled states
            self._update_ui()
        else:
            QMessageBox.critical(
                self,
                "Erreur de Configuration",
                f"Impossible de charger la configuration:\n\n{message}"
            )
            self._status_bar.showMessage(f"✗ Échec chargement config: {message}")
            self._controls.set_config_loaded(False)
    
    @Slot()
    def _on_credentials(self):
        """Handle credentials button click."""
        creds = self._orchestrator.credentials_manager
        
        if creds.is_unlocked:
            # Already unlocked - offer to lock
            reply = QMessageBox.question(
                self,
                "Vault Déverrouillé",
                "Le vault est actuellement déverrouillé.\n\n"
                "Voulez-vous le verrouiller?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                creds.lock_vault()
                self._controls.set_vault_unlocked(False)
                self._dashboard.system_panel.update_vault_status(False)
                self._status_bar.showMessage("Vault verrouillé")
            return
        
        if creds.vault_exists:
            # Vault exists - unlock dialog
            dialog = UnlockVaultDialog(self)
            dialog.vault_unlock_requested.connect(self._on_unlock_vault)
            dialog.exec()
        else:
            # No vault - create dialog
            dialog = CreateVaultDialog(self)
            dialog.vault_create_requested.connect(self._on_create_vault)
            dialog.exec()
    
    @Slot(str, str, str, str, str)
    def _on_create_vault(self, wallet_key: str, api_key: str, api_secret: str, api_passphrase: str, password: str):
        """Handle vault creation request."""
        creds = self._orchestrator.credentials_manager
        success, message = creds.create_vault(wallet_key, api_key, api_secret, api_passphrase, password)
        
        if success:
            # Auto-unlock after creation
            unlock_success, unlock_msg = creds.unlock_vault(password)
            if unlock_success:
                self._controls.set_vault_unlocked(True)
                self._dashboard.system_panel.update_vault_status(True)
                self._status_bar.showMessage("✓ Vault créé et déverrouillé")
            else:
                self._status_bar.showMessage(f"Vault créé mais échec déverrouillage: {unlock_msg}")
        else:
            QMessageBox.critical(self, "Erreur Vault", f"Échec création vault:\n\n{message}")
            self._status_bar.showMessage(f"✗ {message}")
    
    @Slot(str)
    def _on_unlock_vault(self, password: str):
        """Handle vault unlock request."""
        creds = self._orchestrator.credentials_manager
        success, message = creds.unlock_vault(password)
        
        if success:
            # Force immediate sync
            self._controls.set_vault_unlocked(True)
            self._dashboard.system_panel.update_vault_status(True)
            self._status_bar.showMessage("✓ Vault déverrouillé avec succès")
            self._update_ui()
        else:
            if message == "VAULT_CORRUPTED":
                # Trigger kill switch for corrupted vault
                self._orchestrator.emergency_stop()
                QMessageBox.critical(
                    self,
                    "🛑 Vault Corrompu",
                    "Le vault est corrompu ou a été modifié.\n\n"
                    "Kill switch activé par sécurité.\n"
                    "Supprimez le vault et recréez-le."
                )
            else:
                QMessageBox.warning(self, "Échec Déverrouillage", f"Mot de passe incorrect ou erreur: {message}")
                self._status_bar.showMessage(f"✗ Échec déverrouillage: {message}")
                self._controls.set_vault_unlocked(False)
    
    @Slot()
    def _on_launch(self):
        """Handle launch request."""
        success, message = self._orchestrator.launch()
        
        if success:
            self._status_bar.showMessage(f"✓ {message}")
        else:
            QMessageBox.warning(self, "Lancement échoué", message)
            self._status_bar.showMessage(f"✗ {message}")
    
    @Slot()
    def _on_pause(self):
        """Handle pause request."""
        success, message = self._orchestrator.pause()
        self._status_bar.showMessage(f"{'✓' if success else '✗'} {message}")
    
    @Slot()
    def _on_resume(self):
        """Handle resume request."""
        success, message = self._orchestrator.resume()
        self._status_bar.showMessage(f"{'✓' if success else '✗'} {message}")
    
    @Slot()
    def _on_emergency_stop(self):
        """Handle emergency stop request."""
        success, message = self._orchestrator.emergency_stop()
        self._status_bar.showMessage(f"🛑 {message}")
    
    def _on_bot_state_changed(self, state: BotState):
        """Handle bot state change from orchestrator."""
        # We don't update UI directly here to avoid thread safety issues
        # since this callback might come from the orchestrator's heartbeat thread.
        # The periodic _update_ui timer will pick up state changes.
        
        if state == BotState.KILLED:
            self._dashboard.system_panel.update_vault_status(False)
            
            QMessageBox.critical(
                self,
                "🛑 Kill Switch Activé",
                "Le kill switch a été déclenché.\n\n"
                "Tous les ordres ont été annulés.\n"
                "Tous les pools de capital sont gelés.\n"
                "Les credentials ont été détruits.\n\n"
                "Vérifiez les logs et redémarrez l'application."
            )
    
    @Slot()
    def _update_ui(self):
        """Periodic UI update from orchestrator state."""
        # 1. Update Global Bot State
        current_state = self._orchestrator.state
        self._controls.set_bot_state(current_state.value)
        self._dashboard.system_panel.update_bot_state(current_state.value)

        # 2. Update Configuration Status
        is_config_loaded = self._orchestrator.is_config_loaded
        self._controls.set_config_loaded(is_config_loaded)
        
        if is_config_loaded:
            is_paper = self._orchestrator._config.market.paper_trading
            self._controls.set_paper_trading(is_paper)
        else:
            self._controls.set_paper_trading(False)

        # 3. Update Vault/Credentials Status
        creds_status = self._orchestrator.credentials_status
        is_unlocked = creds_status.vault_loaded
        self._controls.set_vault_unlocked(is_unlocked)
        self._dashboard.system_panel.update_vault_status(is_unlocked)

        # 4. Update Capital & Strategy Status
        capital = self._orchestrator.capital_state
        if capital:
            self._dashboard.capital_panel.update_capital(
                capital.total,
                capital.free,
                capital.locked_a,
                capital.locked_b
            )
        
        status_a = self._orchestrator.strategy_a_status
        if status_a:
            self._dashboard.strategy_a_panel.update_status(
                status_a.state.value,
                status_a.locked_capital,
                status_a.active_positions,
                status_a.last_action
            )
        
        status_b = self._orchestrator.strategy_b_status
        if status_b:
            self._dashboard.strategy_b_panel.update_status(
                status_b.state.value,
                status_b.locked_capital,
                status_b.active_positions,
                status_b.last_action
            )
        
        ks_status = self._orchestrator.kill_switch_status
        if ks_status:
            self._dashboard.system_panel.update_kill_switch(ks_status["active"])
    


    def closeEvent(self, event):
        """Handle window close."""
        if self._orchestrator.state == BotState.RUNNING:
            reply = QMessageBox.question(
                self,
                "Confirmer fermeture",
                "Le bot est en cours d'exécution.\n\n"
                "Voulez-vous vraiment fermer l'application?\n"
                "(Cela déclenchera l'arrêt d'urgence)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
            
        # Full system shutdown via orchestrator
        # This stops threads and locks vault
        self._orchestrator.shutdown()
        
        self._update_timer.stop()
        event.accept()
