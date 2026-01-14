"""
Config Builder Module
Interactive configuration creation with real-time validation.
"""

import json
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QFrame, QGroupBox, QPushButton, QScrollArea,
    QDoubleSpinBox, QSpinBox, QSlider, QCheckBox,
    QTextEdit, QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt, Signal, Slot

from .styles import COLORS


class CapitalSection(QGroupBox):
    """Capital allocation section."""

    value_changed = Signal()

    def __init__(self):
        super().__init__("CAPITAL")
        self._setup_ui()

    def _setup_ui(self):
        layout = QGridLayout(self)
        layout.setSpacing(10)

        # Total Capital
        layout.addWidget(QLabel("Capital Total ($):"), 0, 0)
        self.total_spin = QDoubleSpinBox()
        self.total_spin.setRange(50, 100000)
        self.total_spin.setValue(500)
        self.total_spin.setDecimals(2)
        self.total_spin.setSingleStep(50)
        self.total_spin.valueChanged.connect(self._on_value_changed)
        layout.addWidget(self.total_spin, 0, 1)

        # Allocation A (slider)
        layout.addWidget(QLabel("Allocation Strategy A (%):"), 1, 0)
        self.alloc_a_slider = QSlider(Qt.Orientation.Horizontal)
        self.alloc_a_slider.setRange(0, 100)
        self.alloc_a_slider.setValue(50)
        self.alloc_a_slider.valueChanged.connect(self._on_slider_changed)
        layout.addWidget(self.alloc_a_slider, 1, 1)
        self.alloc_a_label = QLabel("50% ($250.00)")
        layout.addWidget(self.alloc_a_label, 1, 2)

        # Allocation B (slider)
        layout.addWidget(QLabel("Allocation Strategy B (%):"), 2, 0)
        self.alloc_b_slider = QSlider(Qt.Orientation.Horizontal)
        self.alloc_b_slider.setRange(0, 100)
        self.alloc_b_slider.setValue(50)
        self.alloc_b_slider.valueChanged.connect(self._on_slider_changed)
        layout.addWidget(self.alloc_b_slider, 2, 1)
        self.alloc_b_label = QLabel("50% ($250.00)")
        layout.addWidget(self.alloc_b_label, 2, 2)

        # Warning label
        self.warning_label = QLabel("")
        self.warning_label.setStyleSheet(f"color: {COLORS['danger']}")
        layout.addWidget(self.warning_label, 3, 0, 1, 3)

    def _on_slider_changed(self):
        total = self.total_spin.value()
        pct_a = self.alloc_a_slider.value()
        pct_b = self.alloc_b_slider.value()

        self.alloc_a_label.setText(f"{pct_a}% (${total * pct_a / 100:.2f})")
        self.alloc_b_label.setText(f"{pct_b}% (${total * pct_b / 100:.2f})")

        if pct_a + pct_b > 100:
            self.warning_label.setText("Allocations depassent 100%!")
        else:
            self.warning_label.setText("")

        self.value_changed.emit()

    def _on_value_changed(self):
        self._on_slider_changed()

    def get_config(self) -> dict:
        total = self.total_spin.value()
        pct_a = self.alloc_a_slider.value()
        pct_b = self.alloc_b_slider.value()
        return {
            "total": total,
            "max_allocation_strategy_a": total * pct_a / 100,
            "max_allocation_strategy_b": total * pct_b / 100
        }

    def is_valid(self) -> tuple[bool, str]:
        pct_a = self.alloc_a_slider.value()
        pct_b = self.alloc_b_slider.value()
        if pct_a + pct_b > 100:
            return False, "Allocations depassent 100%"
        if self.total_spin.value() <= 0:
            return False, "Capital doit etre > 0"
        return True, ""


class StrategyASection(QGroupBox):
    """Strategy A (Front-Running) configuration section."""

    value_changed = Signal()

    def __init__(self):
        super().__init__("STRATEGY A - Front-Running")
        self._setup_ui()

    def _setup_ui(self):
        layout = QGridLayout(self)
        layout.setSpacing(8)

        # Enabled checkbox
        self.enabled_check = QCheckBox("Enabled")
        self.enabled_check.setChecked(True)
        self.enabled_check.stateChanged.connect(lambda: self.value_changed.emit())
        layout.addWidget(self.enabled_check, 0, 0, 1, 2)

        # Trade Size %
        layout.addWidget(QLabel("Trade Size (%):"), 1, 0)
        self.trade_size_spin = QDoubleSpinBox()
        self.trade_size_spin.setRange(1, 25)
        self.trade_size_spin.setValue(6)
        self.trade_size_spin.setDecimals(1)
        self.trade_size_spin.valueChanged.connect(lambda: self.value_changed.emit())
        layout.addWidget(self.trade_size_spin, 1, 1)

        # Max Events
        layout.addWidget(QLabel("Max Events:"), 1, 2)
        self.max_events_spin = QSpinBox()
        self.max_events_spin.setRange(1, 50)
        self.max_events_spin.setValue(10)
        self.max_events_spin.valueChanged.connect(lambda: self.value_changed.emit())
        layout.addWidget(self.max_events_spin, 1, 3)

        # Min/Max Odds
        layout.addWidget(QLabel("Min Odds:"), 2, 0)
        self.min_odds_spin = QDoubleSpinBox()
        self.min_odds_spin.setRange(1.01, 10)
        self.min_odds_spin.setValue(1.02)
        self.min_odds_spin.setDecimals(2)
        self.min_odds_spin.valueChanged.connect(lambda: self.value_changed.emit())
        layout.addWidget(self.min_odds_spin, 2, 1)

        layout.addWidget(QLabel("Max Odds:"), 2, 2)
        self.max_odds_spin = QDoubleSpinBox()
        self.max_odds_spin.setRange(1.1, 100)
        self.max_odds_spin.setValue(20)
        self.max_odds_spin.setDecimals(1)
        self.max_odds_spin.valueChanged.connect(lambda: self.value_changed.emit())
        layout.addWidget(self.max_odds_spin, 2, 3)

        # Exit Config
        layout.addWidget(QLabel("Exit - Profit Target (%):"), 3, 0)
        self.profit_target_spin = QDoubleSpinBox()
        self.profit_target_spin.setRange(0.1, 10)
        self.profit_target_spin.setValue(1.5)
        self.profit_target_spin.setDecimals(2)
        self.profit_target_spin.valueChanged.connect(lambda: self.value_changed.emit())
        layout.addWidget(self.profit_target_spin, 3, 1)

        layout.addWidget(QLabel("Stop Loss (%):"), 3, 2)
        self.stop_loss_spin = QDoubleSpinBox()
        self.stop_loss_spin.setRange(0.1, 10)
        self.stop_loss_spin.setValue(0.8)
        self.stop_loss_spin.setDecimals(2)
        self.stop_loss_spin.valueChanged.connect(lambda: self.value_changed.emit())
        layout.addWidget(self.stop_loss_spin, 3, 3)

        layout.addWidget(QLabel("Trailing Stop (%):"), 4, 0)
        self.trailing_stop_spin = QDoubleSpinBox()
        self.trailing_stop_spin.setRange(0.1, 5)
        self.trailing_stop_spin.setValue(0.4)
        self.trailing_stop_spin.setDecimals(2)
        self.trailing_stop_spin.valueChanged.connect(lambda: self.value_changed.emit())
        layout.addWidget(self.trailing_stop_spin, 4, 1)

        layout.addWidget(QLabel("Timeout (s):"), 4, 2)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(10, 600)
        self.timeout_spin.setValue(90)
        self.timeout_spin.valueChanged.connect(lambda: self.value_changed.emit())
        layout.addWidget(self.timeout_spin, 4, 3)

    def get_config(self) -> dict:
        return {
            "enabled": self.enabled_check.isChecked(),
            "name": "Strategy A - Front-Running",
            "max_events": self.max_events_spin.value(),
            "min_odds": self.min_odds_spin.value(),
            "max_odds": self.max_odds_spin.value(),
            "trade_size_percent": self.trade_size_spin.value(),
            "exit_config": {
                "exit_mode": "dynamic",
                "profit_target_pct": self.profit_target_spin.value(),
                "stop_loss_pct": self.stop_loss_spin.value(),
                "trailing_stop_pct": self.trailing_stop_spin.value(),
                "max_hold_seconds": self.timeout_spin.value(),
                "min_hold_seconds": 5
            },
            "trigger_cooldown_seconds": 5.0,
            "orderbook_cache_ttl_ms": 150
        }


class StrategyBSection(QGroupBox):
    """Strategy B (Market Making) configuration section."""

    value_changed = Signal()

    def __init__(self):
        super().__init__("STRATEGY B - Market Making")
        self._setup_ui()

    def _setup_ui(self):
        layout = QGridLayout(self)
        layout.setSpacing(8)

        # Enabled checkbox
        self.enabled_check = QCheckBox("Enabled")
        self.enabled_check.setChecked(True)
        self.enabled_check.stateChanged.connect(lambda: self.value_changed.emit())
        layout.addWidget(self.enabled_check, 0, 0, 1, 2)

        # Trade Size %
        layout.addWidget(QLabel("Trade Size (%):"), 1, 0)
        self.trade_size_spin = QDoubleSpinBox()
        self.trade_size_spin.setRange(1, 25)
        self.trade_size_spin.setValue(5)
        self.trade_size_spin.setDecimals(1)
        self.trade_size_spin.valueChanged.connect(lambda: self.value_changed.emit())
        layout.addWidget(self.trade_size_spin, 1, 1)

        # Max Exposure
        layout.addWidget(QLabel("Max Exposure ($):"), 1, 2)
        self.max_exposure_spin = QDoubleSpinBox()
        self.max_exposure_spin.setRange(10, 10000)
        self.max_exposure_spin.setValue(250)
        self.max_exposure_spin.setDecimals(0)
        self.max_exposure_spin.valueChanged.connect(lambda: self.value_changed.emit())
        layout.addWidget(self.max_exposure_spin, 1, 3)

        # Spread Min/Max
        layout.addWidget(QLabel("Spread Min:"), 2, 0)
        self.spread_min_spin = QDoubleSpinBox()
        self.spread_min_spin.setRange(0.001, 0.1)
        self.spread_min_spin.setValue(0.005)
        self.spread_min_spin.setDecimals(4)
        self.spread_min_spin.setSingleStep(0.001)
        self.spread_min_spin.valueChanged.connect(lambda: self.value_changed.emit())
        layout.addWidget(self.spread_min_spin, 2, 1)

        layout.addWidget(QLabel("Spread Max:"), 2, 2)
        self.spread_max_spin = QDoubleSpinBox()
        self.spread_max_spin.setRange(0.01, 0.5)
        self.spread_max_spin.setValue(0.10)
        self.spread_max_spin.setDecimals(3)
        self.spread_max_spin.setSingleStep(0.01)
        self.spread_max_spin.valueChanged.connect(lambda: self.value_changed.emit())
        layout.addWidget(self.spread_max_spin, 2, 3)

        # Max Markets
        layout.addWidget(QLabel("Max Markets:"), 3, 0)
        self.max_markets_spin = QSpinBox()
        self.max_markets_spin.setRange(5, 100)
        self.max_markets_spin.setValue(35)
        self.max_markets_spin.valueChanged.connect(lambda: self.value_changed.emit())
        layout.addWidget(self.max_markets_spin, 3, 1)

        # Discovery Interval
        layout.addWidget(QLabel("Discovery (s):"), 3, 2)
        self.discovery_spin = QSpinBox()
        self.discovery_spin.setRange(5, 120)
        self.discovery_spin.setValue(20)
        self.discovery_spin.valueChanged.connect(lambda: self.value_changed.emit())
        layout.addWidget(self.discovery_spin, 3, 3)

        # Exit Config
        layout.addWidget(QLabel("Exit - Profit Target (%):"), 4, 0)
        self.profit_target_spin = QDoubleSpinBox()
        self.profit_target_spin.setRange(0.1, 10)
        self.profit_target_spin.setValue(1.4)
        self.profit_target_spin.setDecimals(2)
        self.profit_target_spin.valueChanged.connect(lambda: self.value_changed.emit())
        layout.addWidget(self.profit_target_spin, 4, 1)

        layout.addWidget(QLabel("Stop Loss (%):"), 4, 2)
        self.stop_loss_spin = QDoubleSpinBox()
        self.stop_loss_spin.setRange(0.1, 10)
        self.stop_loss_spin.setValue(0.9)
        self.stop_loss_spin.setDecimals(2)
        self.stop_loss_spin.valueChanged.connect(lambda: self.value_changed.emit())
        layout.addWidget(self.stop_loss_spin, 4, 3)

        layout.addWidget(QLabel("Trailing Stop (%):"), 5, 0)
        self.trailing_stop_spin = QDoubleSpinBox()
        self.trailing_stop_spin.setRange(0.1, 5)
        self.trailing_stop_spin.setValue(0.45)
        self.trailing_stop_spin.setDecimals(2)
        self.trailing_stop_spin.valueChanged.connect(lambda: self.value_changed.emit())
        layout.addWidget(self.trailing_stop_spin, 5, 1)

        layout.addWidget(QLabel("Timeout (s):"), 5, 2)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(30, 600)
        self.timeout_spin.setValue(240)
        self.timeout_spin.valueChanged.connect(lambda: self.value_changed.emit())
        layout.addWidget(self.timeout_spin, 5, 3)

    def get_config(self) -> dict:
        return {
            "enabled": self.enabled_check.isChecked(),
            "name": "Strategy B - Market Making",
            "spread_min": self.spread_min_spin.value(),
            "spread_max": self.spread_max_spin.value(),
            "max_exposure": self.max_exposure_spin.value(),
            "trade_size_percent": self.trade_size_spin.value(),
            "spread_config": {
                "base_spread": (self.spread_min_spin.value() + self.spread_max_spin.value()) / 2,
                "min_spread": self.spread_min_spin.value(),
                "max_spread": self.spread_max_spin.value(),
                "volatility_multiplier": 1.5,
                "inventory_skew_max": 0.005,
                "imbalance_factor": 0.0015,
                "reprice_threshold": 0.003
            },
            "market_config": {
                "max_markets": self.max_markets_spin.value(),
                "discovery_interval": self.discovery_spin.value(),
                "min_volume_24h": 800,
                "min_spread_opportunity": self.spread_min_spin.value(),
                "parallel_reconcile": True
            },
            "exit_config": {
                "profit_target_pct": self.profit_target_spin.value(),
                "stop_loss_pct": self.stop_loss_spin.value(),
                "trailing_stop_pct": self.trailing_stop_spin.value(),
                "max_hold_seconds": self.timeout_spin.value(),
                "min_hold_seconds": 8,
                "exit_mode": "dynamic"
            }
        }

    def is_valid(self) -> tuple[bool, str]:
        if self.spread_min_spin.value() >= self.spread_max_spin.value():
            return False, "Spread min doit etre < spread max"
        return True, ""


class RiskSection(QGroupBox):
    """Risk management configuration section."""

    value_changed = Signal()

    def __init__(self):
        super().__init__("RISK MANAGEMENT")
        self._setup_ui()

    def _setup_ui(self):
        layout = QGridLayout(self)
        layout.setSpacing(8)

        # Max Drawdown
        layout.addWidget(QLabel("Max Drawdown (%):"), 0, 0)
        self.max_drawdown_spin = QDoubleSpinBox()
        self.max_drawdown_spin.setRange(1, 50)
        self.max_drawdown_spin.setValue(8)
        self.max_drawdown_spin.setDecimals(1)
        self.max_drawdown_spin.valueChanged.connect(lambda: self.value_changed.emit())
        layout.addWidget(self.max_drawdown_spin, 0, 1)

        # Daily Loss Limit
        layout.addWidget(QLabel("Daily Loss Limit ($):"), 0, 2)
        self.daily_loss_spin = QDoubleSpinBox()
        self.daily_loss_spin.setRange(5, 1000)
        self.daily_loss_spin.setValue(40)
        self.daily_loss_spin.setDecimals(0)
        self.daily_loss_spin.valueChanged.connect(lambda: self.value_changed.emit())
        layout.addWidget(self.daily_loss_spin, 0, 3)

        # Kill Switch Threshold
        layout.addWidget(QLabel("Kill Switch (%):"), 1, 0)
        self.kill_switch_spin = QDoubleSpinBox()
        self.kill_switch_spin.setRange(5, 50)
        self.kill_switch_spin.setValue(12)
        self.kill_switch_spin.setDecimals(1)
        self.kill_switch_spin.valueChanged.connect(lambda: self.value_changed.emit())
        layout.addWidget(self.kill_switch_spin, 1, 1)

    def get_config(self) -> dict:
        return {
            "max_drawdown_percent": self.max_drawdown_spin.value(),
            "max_daily_loss": self.daily_loss_spin.value(),
            "kill_switch_threshold": self.kill_switch_spin.value()
        }


class MarketSection(QGroupBox):
    """Market connection configuration section."""

    value_changed = Signal()

    def __init__(self):
        super().__init__("MARKET")
        self._setup_ui()

    def _setup_ui(self):
        layout = QGridLayout(self)
        layout.setSpacing(8)

        # Paper Trading
        self.paper_trading_check = QCheckBox("Paper Trading (Simulation)")
        self.paper_trading_check.setChecked(True)
        self.paper_trading_check.stateChanged.connect(lambda: self.value_changed.emit())
        layout.addWidget(self.paper_trading_check, 0, 0, 1, 2)

        # Timeout
        layout.addWidget(QLabel("Connection Timeout (s):"), 1, 0)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 60)
        self.timeout_spin.setValue(15)
        self.timeout_spin.valueChanged.connect(lambda: self.value_changed.emit())
        layout.addWidget(self.timeout_spin, 1, 1)

        # Heartbeat
        layout.addWidget(QLabel("Heartbeat (s):"), 1, 2)
        self.heartbeat_spin = QDoubleSpinBox()
        self.heartbeat_spin.setRange(0.5, 10)
        self.heartbeat_spin.setValue(1.2)
        self.heartbeat_spin.setDecimals(1)
        self.heartbeat_spin.valueChanged.connect(lambda: self.value_changed.emit())
        layout.addWidget(self.heartbeat_spin, 1, 3)

    def get_config(self) -> dict:
        return {
            "connection_timeout_seconds": self.timeout_spin.value(),
            "heartbeat_interval_seconds": self.heartbeat_spin.value(),
            "clob_api_url": "https://clob.polymarket.com/",
            "gamma_api_url": "https://gamma-api.polymarket.com/",
            "paper_trading": self.paper_trading_check.isChecked()
        }


class ConfigBuilderTab(QWidget):
    """Main Config Builder tab widget."""

    config_saved = Signal(str)  # Emits file path of saved config

    def __init__(self):
        super().__init__()
        self._setup_ui()
        self._connect_signals()
        self._update_preview()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # Scroll area for sections
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(15)

        # Sections
        self.capital_section = CapitalSection()
        scroll_layout.addWidget(self.capital_section)

        self.strategy_a_section = StrategyASection()
        scroll_layout.addWidget(self.strategy_a_section)

        self.strategy_b_section = StrategyBSection()
        scroll_layout.addWidget(self.strategy_b_section)

        self.risk_section = RiskSection()
        scroll_layout.addWidget(self.risk_section)

        self.market_section = MarketSection()
        scroll_layout.addWidget(self.market_section)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll, 3)

        # Preview section
        preview_group = QGroupBox("PREVIEW JSON")
        preview_layout = QVBoxLayout(preview_group)

        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMaximumHeight(150)
        self.preview_text.setStyleSheet(f"background-color: {COLORS['bg_dark']}; font-family: monospace;")
        preview_layout.addWidget(self.preview_text)

        # Validation label
        self.validation_label = QLabel("")
        self.validation_label.setStyleSheet(f"color: {COLORS['danger']}")
        preview_layout.addWidget(self.validation_label)

        layout.addWidget(preview_group, 1)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.save_btn = QPushButton("Sauvegarder Configuration")
        self.save_btn.setMinimumWidth(200)
        self.save_btn.clicked.connect(self._on_save_clicked)
        btn_layout.addWidget(self.save_btn)

        layout.addLayout(btn_layout)

    def _connect_signals(self):
        self.capital_section.value_changed.connect(self._update_preview)
        self.strategy_a_section.value_changed.connect(self._update_preview)
        self.strategy_b_section.value_changed.connect(self._update_preview)
        self.risk_section.value_changed.connect(self._update_preview)
        self.market_section.value_changed.connect(self._update_preview)

    def _update_preview(self):
        """Update JSON preview and validation status."""
        config = self._build_config()
        self.preview_text.setPlainText(json.dumps(config, indent=2))

        is_valid, errors = self._validate()
        if is_valid:
            self.validation_label.setText("Configuration valide")
            self.validation_label.setStyleSheet(f"color: {COLORS['success']}")
            self.save_btn.setEnabled(True)
        else:
            self.validation_label.setText(f"Erreurs: {', '.join(errors)}")
            self.validation_label.setStyleSheet(f"color: {COLORS['danger']}")
            self.save_btn.setEnabled(False)

    def _build_config(self) -> dict:
        """Build complete config dict from all sections."""
        return {
            "capital": self.capital_section.get_config(),
            "strategy_a": self.strategy_a_section.get_config(),
            "strategy_b": self.strategy_b_section.get_config(),
            "risk": self.risk_section.get_config(),
            "market": self.market_section.get_config(),
            "analytics": {
                "enabled": True,
                "equity_curve_points": 200,
                "recent_trades_limit": 100,
                "rolling_sharpe_window": 60,
                "track_per_strategy": True
            },
            "market_scanner": {
                "enabled": True,
                "scan_interval_seconds": 20,
                "batch_size": 20,
                "batch_delay_ms": 35
            },
            "rate_limiter": {
                "max_tokens": 80,
                "refill_rate": 40
            },
            "logging": {
                "level": "INFO",
                "trade_details": True,
                "pnl_updates": True
            }
        }

    def _validate(self) -> tuple[bool, list[str]]:
        """Validate all sections."""
        errors = []

        valid, msg = self.capital_section.is_valid()
        if not valid:
            errors.append(msg)

        valid, msg = self.strategy_b_section.is_valid()
        if not valid:
            errors.append(msg)

        return len(errors) == 0, errors

    @Slot()
    def _on_save_clicked(self):
        """Handle save button click."""
        is_valid, errors = self._validate()
        if not is_valid:
            QMessageBox.warning(self, "Validation", f"Configuration invalide:\n{', '.join(errors)}")
            return

        # Generate filename based on capital and mode
        config = self._build_config()
        capital = int(config["capital"]["total"])
        mode = "paper" if config["market"]["paper_trading"] else "live"
        default_name = f"config_{capital}_{mode}.json"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Sauvegarder Configuration",
            f"config/{default_name}",
            "JSON Files (*.json)"
        )

        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=4)

                QMessageBox.information(self, "Succes", f"Configuration sauvegardee:\n{file_path}")
                self.config_saved.emit(file_path)
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Echec sauvegarde:\n{str(e)}")
