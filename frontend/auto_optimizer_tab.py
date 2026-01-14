"""
Auto-Optimizer Tab Module
UI for automatic parameter optimization.
"""

import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QFrame, QGroupBox, QPushButton, QScrollArea,
    QDoubleSpinBox, QSpinBox, QSlider, QCheckBox,
    QTextEdit, QRadioButton, QButtonGroup, QListWidget,
    QListWidgetItem
)
from PySide6.QtCore import Qt, Signal, Slot

from .styles import COLORS
from backend.auto_optimizer import AutoOptimizer, OptimizerMode


class ModeSelector(QGroupBox):
    """Mode selection widget."""

    mode_changed = Signal(str)

    def __init__(self):
        super().__init__("MODE D'OPTIMISATION")
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)

        self.btn_group = QButtonGroup(self)

        self.manual_radio = QRadioButton("Manuel")
        self.manual_radio.setChecked(True)
        self.btn_group.addButton(self.manual_radio)
        layout.addWidget(self.manual_radio)

        self.semi_auto_radio = QRadioButton("Semi-Auto")
        self.btn_group.addButton(self.semi_auto_radio)
        layout.addWidget(self.semi_auto_radio)

        self.full_auto_radio = QRadioButton("Full-Auto")
        self.btn_group.addButton(self.full_auto_radio)
        layout.addWidget(self.full_auto_radio)

        layout.addStretch()

        self.start_btn = QPushButton("Demarrer")
        self.start_btn.setMinimumWidth(100)
        layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("Arreter")
        self.stop_btn.setMinimumWidth(100)
        self.stop_btn.setEnabled(False)
        layout.addWidget(self.stop_btn)

        # Connect signals
        self.btn_group.buttonClicked.connect(self._on_mode_changed)

    def _on_mode_changed(self):
        if self.manual_radio.isChecked():
            self.mode_changed.emit("manual")
        elif self.semi_auto_radio.isChecked():
            self.mode_changed.emit("semi_auto")
        else:
            self.mode_changed.emit("full_auto")

    def get_mode(self) -> str:
        if self.manual_radio.isChecked():
            return "manual"
        elif self.semi_auto_radio.isChecked():
            return "semi_auto"
        return "full_auto"

    def set_running(self, running: bool):
        self.start_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)
        self.manual_radio.setEnabled(not running)
        self.semi_auto_radio.setEnabled(not running)
        self.full_auto_radio.setEnabled(not running)


class CapitalOptimizerSection(QGroupBox):
    """Capital-based optimization section."""

    optimize_clicked = Signal(float)

    def __init__(self):
        super().__init__("OPTIMISER POUR CAPITAL")
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)

        layout.addWidget(QLabel("Capital ($):"))

        self.capital_spin = QDoubleSpinBox()
        self.capital_spin.setRange(50, 100000)
        self.capital_spin.setValue(500)
        self.capital_spin.setDecimals(0)
        self.capital_spin.setSingleStep(100)
        self.capital_spin.setMinimumWidth(120)
        layout.addWidget(self.capital_spin)

        self.optimize_btn = QPushButton("Optimiser")
        self.optimize_btn.clicked.connect(self._on_optimize)
        layout.addWidget(self.optimize_btn)

        layout.addStretch()

        # Result label
        self.result_label = QLabel("")
        self.result_label.setStyleSheet(f"color: {COLORS['accent']}")
        layout.addWidget(self.result_label)

    def _on_optimize(self):
        self.optimize_clicked.emit(self.capital_spin.value())

    def show_result(self, tier: str, params: dict):
        trade_size = params.get("strategy_a", {}).get("trade_size_usd", 0)
        self.result_label.setText(f"Tier: {tier.upper()} | Trade: ${trade_size:.2f}")


class KellySection(QGroupBox):
    """Kelly Criterion configuration section."""

    config_changed = Signal(dict)

    def __init__(self):
        super().__init__("KELLY CRITERION")
        self._setup_ui()

    def _setup_ui(self):
        layout = QGridLayout(self)
        layout.setSpacing(10)

        # Enable checkboxes
        self.enable_a_check = QCheckBox("Activer pour Strategy A")
        self.enable_a_check.stateChanged.connect(self._on_config_changed)
        layout.addWidget(self.enable_a_check, 0, 0)

        self.enable_b_check = QCheckBox("Activer pour Strategy B")
        self.enable_b_check.stateChanged.connect(self._on_config_changed)
        layout.addWidget(self.enable_b_check, 0, 1)

        # Fraction slider
        layout.addWidget(QLabel("Fraction Kelly:"), 1, 0)
        fraction_layout = QHBoxLayout()
        self.fraction_slider = QSlider(Qt.Orientation.Horizontal)
        self.fraction_slider.setRange(10, 100)
        self.fraction_slider.setValue(25)
        self.fraction_slider.valueChanged.connect(self._on_fraction_changed)
        fraction_layout.addWidget(self.fraction_slider)
        self.fraction_label = QLabel("0.25 (Quarter)")
        fraction_layout.addWidget(self.fraction_label)
        layout.addLayout(fraction_layout, 1, 1)

        # Min Edge
        layout.addWidget(QLabel("Min Edge (%):"), 2, 0)
        self.min_edge_spin = QDoubleSpinBox()
        self.min_edge_spin.setRange(0.5, 10)
        self.min_edge_spin.setValue(2)
        self.min_edge_spin.setDecimals(1)
        self.min_edge_spin.valueChanged.connect(self._on_config_changed)
        layout.addWidget(self.min_edge_spin, 2, 1)

        # Max Multiplier
        layout.addWidget(QLabel("Max Multiplier:"), 3, 0)
        self.max_mult_spin = QDoubleSpinBox()
        self.max_mult_spin.setRange(1, 5)
        self.max_mult_spin.setValue(2)
        self.max_mult_spin.setDecimals(1)
        self.max_mult_spin.valueChanged.connect(self._on_config_changed)
        layout.addWidget(self.max_mult_spin, 3, 1)

        # Stats display
        stats_frame = QFrame()
        stats_frame.setStyleSheet(f"background-color: {COLORS['surface']}; border-radius: 5px; padding: 10px;")
        stats_layout = QGridLayout(stats_frame)

        stats_layout.addWidget(QLabel("Strategy A:"), 0, 0)
        self.stats_a_label = QLabel("--")
        self.stats_a_label.setStyleSheet(f"color: {COLORS['accent']}")
        stats_layout.addWidget(self.stats_a_label, 0, 1)

        stats_layout.addWidget(QLabel("Strategy B:"), 1, 0)
        self.stats_b_label = QLabel("--")
        self.stats_b_label.setStyleSheet(f"color: {COLORS['accent']}")
        stats_layout.addWidget(self.stats_b_label, 1, 1)

        layout.addWidget(stats_frame, 4, 0, 1, 2)

    def _on_fraction_changed(self):
        value = self.fraction_slider.value() / 100
        if value <= 0.25:
            label = "Quarter"
        elif value <= 0.5:
            label = "Half"
        else:
            label = "Full"
        self.fraction_label.setText(f"{value:.2f} ({label})")
        self._on_config_changed()

    def _on_config_changed(self):
        self.config_changed.emit(self.get_config())

    def get_config(self) -> dict:
        return {
            "enabled_a": self.enable_a_check.isChecked(),
            "enabled_b": self.enable_b_check.isChecked(),
            "fraction": self.fraction_slider.value() / 100,
            "min_edge": self.min_edge_spin.value() / 100,
            "max_multiplier": self.max_mult_spin.value()
        }

    def update_stats(self, stats: dict):
        """Update Kelly stats display."""
        if "strategy_a" in stats:
            s = stats["strategy_a"]
            self.stats_a_label.setText(
                f"WR: {s['win_rate']*100:.1f}% | Kelly: {s['recommended_pct']:.1f}% | Trades: {s['total_trades']}"
            )
        else:
            self.stats_a_label.setText("Donnees insuffisantes")

        if "strategy_b" in stats:
            s = stats["strategy_b"]
            self.stats_b_label.setText(
                f"WR: {s['win_rate']*100:.1f}% | Kelly: {s['recommended_pct']:.1f}% | Trades: {s['total_trades']}"
            )
        else:
            self.stats_b_label.setText("Donnees insuffisantes")


class SuggestionsSection(QGroupBox):
    """Suggestions list for Semi-Auto mode."""

    suggestion_applied = Signal(int)
    suggestion_rejected = Signal(int)

    def __init__(self):
        super().__init__("SUGGESTIONS (Semi-Auto)")
        self._suggestions = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        self.list_widget = QListWidget()
        self.list_widget.setMaximumHeight(150)
        self.list_widget.setStyleSheet(f"background-color: {COLORS['surface']};")
        layout.addWidget(self.list_widget)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.apply_btn = QPushButton("Appliquer")
        self.apply_btn.clicked.connect(self._on_apply)
        self.apply_btn.setEnabled(False)
        btn_layout.addWidget(self.apply_btn)

        self.reject_btn = QPushButton("Ignorer")
        self.reject_btn.clicked.connect(self._on_reject)
        self.reject_btn.setEnabled(False)
        btn_layout.addWidget(self.reject_btn)

        layout.addLayout(btn_layout)

        self.list_widget.itemSelectionChanged.connect(self._on_selection_changed)

    def add_suggestion(self, suggestion: dict):
        """Add a new suggestion to the list."""
        text = f"{suggestion['param']}: {suggestion['current']} -> {suggestion['suggested']} ({suggestion['reason']})"
        item = QListWidgetItem(text)
        item.setData(Qt.ItemDataRole.UserRole, len(self._suggestions))
        self._suggestions.append(suggestion)
        self.list_widget.addItem(item)

    def _on_selection_changed(self):
        has_selection = len(self.list_widget.selectedItems()) > 0
        self.apply_btn.setEnabled(has_selection)
        self.reject_btn.setEnabled(has_selection)

    def _on_apply(self):
        items = self.list_widget.selectedItems()
        if items:
            idx = items[0].data(Qt.ItemDataRole.UserRole)
            self.suggestion_applied.emit(idx)
            self.list_widget.takeItem(self.list_widget.row(items[0]))

    def _on_reject(self):
        items = self.list_widget.selectedItems()
        if items:
            idx = items[0].data(Qt.ItemDataRole.UserRole)
            self.suggestion_rejected.emit(idx)
            self.list_widget.takeItem(self.list_widget.row(items[0]))

    def clear(self):
        self.list_widget.clear()
        self._suggestions = []


class HistorySection(QGroupBox):
    """History of parameter changes."""

    def __init__(self):
        super().__init__("HISTORIQUE DES MODIFICATIONS")
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        self.history_text = QTextEdit()
        self.history_text.setReadOnly(True)
        self.history_text.setMaximumHeight(120)
        self.history_text.setStyleSheet(f"background-color: {COLORS['surface']}; font-family: monospace;")
        layout.addWidget(self.history_text)

    def add_entry(self, param: str, old_val, new_val, reason: str = ""):
        """Add a history entry."""
        import time
        timestamp = time.strftime("%H:%M:%S")
        line = f"{timestamp} - {param}: {old_val} -> {new_val}"
        if reason:
            line += f" ({reason})"

        current = self.history_text.toPlainText()
        if current:
            self.history_text.setPlainText(line + "\n" + current)
        else:
            self.history_text.setPlainText(line)


class AutoOptimizerTab(QWidget):
    """Main Auto-Optimizer tab widget."""

    config_optimized = Signal(dict)  # Emits optimized config

    def __init__(self, orchestrator=None):
        super().__init__()
        self._orchestrator = orchestrator
        self._optimizer = AutoOptimizer(orchestrator)
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(10, 10, 10, 10)

        # Mode selector
        self.mode_section = ModeSelector()
        layout.addWidget(self.mode_section)

        # Capital optimizer
        self.capital_section = CapitalOptimizerSection()
        layout.addWidget(self.capital_section)

        # Kelly Criterion
        self.kelly_section = KellySection()
        layout.addWidget(self.kelly_section)

        # Suggestions
        self.suggestions_section = SuggestionsSection()
        layout.addWidget(self.suggestions_section)

        # History
        self.history_section = HistorySection()
        layout.addWidget(self.history_section)

        layout.addStretch()

    def _connect_signals(self):
        # Mode controls
        self.mode_section.mode_changed.connect(self._on_mode_changed)
        self.mode_section.start_btn.clicked.connect(self._on_start)
        self.mode_section.stop_btn.clicked.connect(self._on_stop)

        # Capital optimizer
        self.capital_section.optimize_clicked.connect(self._on_optimize_for_capital)

        # Kelly config
        self.kelly_section.config_changed.connect(self._on_kelly_config_changed)

        # Suggestions
        self.suggestions_section.suggestion_applied.connect(self._on_suggestion_applied)
        self.suggestions_section.suggestion_rejected.connect(self._on_suggestion_rejected)

        # Optimizer signals
        self._optimizer.suggestion_generated.connect(self._on_new_suggestion)
        self._optimizer.param_changed.connect(self._on_param_changed)
        self._optimizer.kelly_updated.connect(self._on_kelly_updated)

    def _on_mode_changed(self, mode: str):
        self._optimizer.mode = OptimizerMode(mode)

    def _on_start(self):
        import asyncio
        self.mode_section.set_running(True)

        # Run in background
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(self._optimizer.start())
        else:
            asyncio.run(self._optimizer.start())

    def _on_stop(self):
        import asyncio
        self.mode_section.set_running(False)

        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(self._optimizer.stop())

    def _on_optimize_for_capital(self, capital: float):
        """Generate optimized config for capital."""
        result = self._optimizer.optimize_for_capital(capital)
        self.capital_section.show_result(result["tier"], result)

        # Add to history
        self.history_section.add_entry(
            "capital_optimization",
            f"${capital}",
            f"tier={result['tier']}",
            "Optimisation manuelle"
        )

        # Emit config
        self.config_optimized.emit(result)

    def _on_kelly_config_changed(self, config: dict):
        self._optimizer.set_kelly_config(
            enabled_a=config["enabled_a"],
            enabled_b=config["enabled_b"],
            fraction=config["fraction"],
            min_edge=config["min_edge"],
            max_multiplier=config["max_multiplier"]
        )

        # Immediately calculate if enabled
        if config["enabled_a"] or config["enabled_b"]:
            stats = self._optimizer.calculate_kelly_sizes()
            self.kelly_section.update_stats(stats)

    def _on_new_suggestion(self, suggestion: dict):
        self.suggestions_section.add_suggestion(suggestion)

    def _on_suggestion_applied(self, idx: int):
        suggestions = self._optimizer.suggestions
        if idx < len(suggestions):
            self._optimizer.apply_suggestion(suggestions[idx])

    def _on_suggestion_rejected(self, idx: int):
        suggestions = self._optimizer.suggestions
        if idx < len(suggestions):
            self._optimizer.reject_suggestion(suggestions[idx])

    def _on_param_changed(self, param: str, old_val, new_val):
        self.history_section.add_entry(param, old_val, new_val)

    def _on_kelly_updated(self, stats: dict):
        self.kelly_section.update_stats(stats)
