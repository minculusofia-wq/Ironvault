"""
Dashboard Module
Read-only display of bot status, capital, and strategies.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QFrame, QGroupBox, QProgressBar
)
from PySide6.QtCore import Qt, Slot

from .styles import COLORS, get_status_style, get_capital_bar_style
from .orderbook_visualizer import OrderbookVisualizer


class CapitalPanel(QFrame):
    """Panel displaying capital allocation."""
    
    def __init__(self):
        super().__init__()
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        title = QLabel("💰 CAPITAL")
        title.setProperty("class", "section")
        layout.addWidget(title)
        
        grid = QGridLayout()
        grid.setSpacing(10)
        
        grid.addWidget(QLabel("Total:"), 0, 0)
        self._total_label = QLabel("--")
        self._total_label.setProperty("class", "value")
        grid.addWidget(self._total_label, 0, 1, Qt.AlignmentFlag.AlignRight)
        
        grid.addWidget(QLabel("Disponible:"), 1, 0)
        self._free_label = QLabel("--")
        self._free_label.setProperty("class", "value")
        self._free_label.setStyleSheet(f"color: {COLORS['success']}")
        grid.addWidget(self._free_label, 1, 1, Qt.AlignmentFlag.AlignRight)
        
        grid.addWidget(QLabel("Verrouillé A:"), 2, 0)
        self._locked_a_label = QLabel("--")
        self._locked_a_label.setProperty("class", "value")
        grid.addWidget(self._locked_a_label, 2, 1, Qt.AlignmentFlag.AlignRight)
        
        grid.addWidget(QLabel("Verrouillé B:"), 3, 0)
        self._locked_b_label = QLabel("--")
        self._locked_b_label.setProperty("class", "value")
        grid.addWidget(self._locked_b_label, 3, 1, Qt.AlignmentFlag.AlignRight)
        
        layout.addLayout(grid)
        
        self._usage_bar = QProgressBar()
        self._usage_bar.setRange(0, 100)
        self._usage_bar.setValue(0)
        self._usage_bar.setFormat("%p% utilisé")
        layout.addWidget(self._usage_bar)
    
    @Slot(float, float, float, float)
    def update_capital(self, total: float, free: float, locked_a: float, locked_b: float):
        """Update capital display."""
        self._total_label.setText(f"{total:,.2f}")
        self._free_label.setText(f"{free:,.2f}")
        self._locked_a_label.setText(f"{locked_a:,.2f}")
        self._locked_b_label.setText(f"{locked_b:,.2f}")
        
        usage_percent = ((locked_a + locked_b) / total * 100) if total > 0 else 0
        self._usage_bar.setValue(int(usage_percent))
        self._usage_bar.setStyleSheet(get_capital_bar_style(usage_percent))


class StrategyPanel(QFrame):
    """Panel displaying strategy status."""
    
    def __init__(self, strategy_name: str, strategy_label: str):
        super().__init__()
        self._strategy_name = strategy_name
        self._setup_ui(strategy_label)
    
    def _setup_ui(self, label: str):
        layout = QVBoxLayout(self)
        
        header = QHBoxLayout()
        title = QLabel(f"📊 {label}")
        title.setProperty("class", "section")
        header.addWidget(title)
        
        self._status_label = QLabel("INACTIVE")
        self._status_label.setStyleSheet(get_status_style("INACTIVE"))
        header.addWidget(self._status_label, 0, Qt.AlignmentFlag.AlignRight)
        
        layout.addLayout(header)
        
        grid = QGridLayout()
        grid.setSpacing(8)
        
        grid.addWidget(QLabel("Capital verrouillé:"), 0, 0)
        self._capital_label = QLabel("--")
        grid.addWidget(self._capital_label, 0, 1, Qt.AlignmentFlag.AlignRight)
        
        grid.addWidget(QLabel("Positions actives:"), 1, 0)
        self._positions_label = QLabel("--")
        grid.addWidget(self._positions_label, 1, 1, Qt.AlignmentFlag.AlignRight)
        
        grid.addWidget(QLabel("Dernière action:"), 2, 0)
        self._action_label = QLabel("--")
        self._action_label.setProperty("class", "dim")
        grid.addWidget(self._action_label, 2, 1, Qt.AlignmentFlag.AlignRight)
        
        layout.addLayout(grid)
    
    @Slot(str, float, int, str)
    def update_status(self, state: str, locked_capital: float, positions: int, last_action: str):
        """Update strategy status display."""
        self._status_label.setText(state)
        self._status_label.setStyleSheet(get_status_style(state))
        self._capital_label.setText(f"{locked_capital:,.2f}")
        self._positions_label.setText(str(positions))
        self._action_label.setText(last_action)


class SystemPanel(QFrame):
    """Panel displaying system status."""
    
    def __init__(self):
        super().__init__()
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        title = QLabel("⚙️ SYSTÈME")
        title.setProperty("class", "section")
        layout.addWidget(title)
        
        grid = QGridLayout()
        grid.setSpacing(8)
        
        grid.addWidget(QLabel("État bot:"), 0, 0)
        self._state_label = QLabel("IDLE")
        self._state_label.setStyleSheet(get_status_style("IDLE"))
        grid.addWidget(self._state_label, 0, 1, Qt.AlignmentFlag.AlignRight)
        
        grid.addWidget(QLabel("Kill Switch:"), 1, 0)
        self._kill_switch_label = QLabel("DÉSENGAGÉ")
        self._kill_switch_label.setStyleSheet(f"color: {COLORS['success']}")
        grid.addWidget(self._kill_switch_label, 1, 1, Qt.AlignmentFlag.AlignRight)
        
        grid.addWidget(QLabel("Marché:"), 2, 0)
        self._market_label = QLabel("DÉCONNECTÉ")
        self._market_label.setStyleSheet(get_status_style("INACTIVE"))
        grid.addWidget(self._market_label, 2, 1, Qt.AlignmentFlag.AlignRight)
        
        grid.addWidget(QLabel("Config:"), 3, 0)
        self._config_label = QLabel("Non chargée")
        self._config_label.setProperty("class", "dim")
        grid.addWidget(self._config_label, 3, 1, Qt.AlignmentFlag.AlignRight)
        
        grid.addWidget(QLabel("Vault:"), 4, 0)
        self._vault_label = QLabel("Non chargé")
        self._vault_label.setStyleSheet(f"color: {COLORS['text_dim']}")
        grid.addWidget(self._vault_label, 4, 1, Qt.AlignmentFlag.AlignRight)
        
        layout.addLayout(grid)
    
    @Slot(str)
    def update_bot_state(self, state: str):
        """Update bot state display."""
        self._state_label.setText(state)
        self._state_label.setStyleSheet(get_status_style(state))
    
    @Slot(bool)
    def update_kill_switch(self, active: bool):
        """Update kill switch status."""
        if active:
            self._kill_switch_label.setText("⚠️ ACTIVÉ")
            self._kill_switch_label.setStyleSheet(f"color: {COLORS['danger']}; font-weight: bold;")
        else:
            self._kill_switch_label.setText("DÉSENGAGÉ")
            self._kill_switch_label.setStyleSheet(f"color: {COLORS['success']}")
    
    @Slot(bool)
    def update_market_status(self, connected: bool):
        """Update market connection status."""
        if connected:
            self._market_label.setText("CONNECTÉ")
            self._market_label.setStyleSheet(get_status_style("ACTIVE"))
        else:
            self._market_label.setText("DÉCONNECTÉ")
            self._market_label.setStyleSheet(get_status_style("INACTIVE"))
    
    @Slot(str)
    def update_config(self, file_path: str):
        """Update loaded config display."""
        if file_path:
            name = file_path.split("/")[-1]
            self._config_label.setText(name)
            self._config_label.setStyleSheet(f"color: {COLORS['text']}")
        else:
            self._config_label.setText("Non chargée")
            self._config_label.setStyleSheet(f"color: {COLORS['text_dim']}")
    
    @Slot(bool)
    def update_vault_status(self, loaded: bool):
        """Update vault status display (no secret info)."""
        if loaded:
            self._vault_label.setText("🔓 Déverrouillé")
            self._vault_label.setStyleSheet(f"color: {COLORS['success']}; font-weight: bold;")
        else:
            self._vault_label.setText("Non chargé")
            self._vault_label.setStyleSheet(f"color: {COLORS['text_dim']}")


class PerformancePanel(QFrame):
    """Panel displaying trading performance stats from SQLite."""
    
    def __init__(self):
        super().__init__()
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        title = QLabel("📈 Performance (v2.0)")
        title.setProperty("class", "section")
        layout.addWidget(title)
        
        grid = QGridLayout()
        grid.setSpacing(8)
        
        grid.addWidget(QLabel("TOTAL TRADES:"), 0, 0)
        self._trades_label = QLabel("0")
        grid.addWidget(self._trades_label, 0, 1, Qt.AlignmentFlag.AlignRight)
        
        grid.addWidget(QLabel("WIN RATE:"), 1, 0)
        self._winrate_label = QLabel("0.0%")
        self._winrate_label.setStyleSheet(f"color: {COLORS['accent']}")
        grid.addWidget(self._winrate_label, 1, 1, Qt.AlignmentFlag.AlignRight)
        
        grid.addWidget(QLabel("Profit Total (USD):"), 2, 0)
        self._pnl_label = QLabel("0.00")
        self._pnl_label.setProperty("class", "value")
        grid.addWidget(self._pnl_label, 2, 1, Qt.AlignmentFlag.AlignRight)
        
        layout.addLayout(grid)
    
    @Slot(dict)
    def update_stats(self, stats: dict):
        """Update performance metrics."""
        self._trades_label.setText(str(stats.get("total_trades", 0)))
        win_rate = stats.get("win_rate", 0)
        self._winrate_label.setText(f"{win_rate:.1f}%")
        pnl = stats.get("total_pnl", 0.0)
        self._pnl_label.setText(f"{pnl:,.2f}")
        if pnl > 0:
            self._pnl_label.setStyleSheet(f"color: {COLORS['success']}")
        elif pnl < 0:
            self._pnl_label.setStyleSheet(f"color: {COLORS['danger']}")


class Dashboard(QWidget):
    """Main dashboard widget - read-only display."""
    
    def __init__(self):
        super().__init__()
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # TOP: System & Capital side-by-side
        top_row = QHBoxLayout()
        self.system_panel = SystemPanel()
        top_row.addWidget(self.system_panel, 1)
        self.capital_panel = CapitalPanel()
        top_row.addWidget(self.capital_panel, 1)
        layout.addLayout(top_row)
        
        # MIDDLE: Strategies
        strat_row = QHBoxLayout()
        self.strategy_a_panel = StrategyPanel("Strategy_A", "DUTCHING MULTI-ISSUES")
        strat_row.addWidget(self.strategy_a_panel)
        self.strategy_b_panel = StrategyPanel("Strategy_B", "TENUE DE MARCHÉ (MM)")
        strat_row.addWidget(self.strategy_b_panel)
        layout.addLayout(strat_row)
        
        # BOTTOM: Analytics (v2.0)
        analytics_group = QGroupBox("ANALYTIQUES & CARNET (v2.0)")
        analytics_layout = QHBoxLayout(analytics_group)
        
        self.performance_panel = PerformancePanel()
        self.performance_panel.setFixedWidth(280)
        analytics_layout.addWidget(self.performance_panel)
        
        self.orderbook_panel = OrderbookVisualizer()
        analytics_layout.addWidget(self.orderbook_panel)
        
        layout.addWidget(analytics_group)
        layout.addStretch()
