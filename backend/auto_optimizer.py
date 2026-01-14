"""
Auto-Optimizer Module
Automatic parameter optimization based on market conditions and performance.
"""

import asyncio
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Callable, Any
from PySide6.QtCore import QObject, Signal

from .kelly_criterion import KellyCriterion


class OptimizerMode(Enum):
    """Optimizer operation modes."""
    MANUAL = "manual"
    SEMI_AUTO = "semi_auto"
    FULL_AUTO = "full_auto"


@dataclass
class Suggestion:
    """Optimization suggestion."""
    param_name: str
    current_value: Any
    suggested_value: Any
    reason: str
    timestamp: float = field(default_factory=time.time)
    applied: bool = False


@dataclass
class HistoryEntry:
    """History of parameter changes."""
    param_name: str
    old_value: Any
    new_value: Any
    reason: str
    timestamp: float = field(default_factory=time.time)


# Capital tier scaling rules
CAPITAL_TIERS = {
    "micro": {
        "max_capital": 100,
        "trade_size_pct": 8.0,
        "max_markets": 25,
        "spread_min": 0.008,
        "spread_max": 0.12,
        "max_drawdown": 15.0,
        "daily_loss": 15.0,
        "discovery_interval": 25
    },
    "small": {
        "max_capital": 250,
        "trade_size_pct": 6.0,
        "max_markets": 30,
        "spread_min": 0.006,
        "spread_max": 0.10,
        "max_drawdown": 10.0,
        "daily_loss": 25.0,
        "discovery_interval": 22
    },
    "medium": {
        "max_capital": 500,
        "trade_size_pct": 5.0,
        "max_markets": 35,
        "spread_min": 0.005,
        "spread_max": 0.10,
        "max_drawdown": 8.0,
        "daily_loss": 40.0,
        "discovery_interval": 20
    },
    "large": {
        "max_capital": 1000,
        "trade_size_pct": 4.0,
        "max_markets": 50,
        "spread_min": 0.004,
        "spread_max": 0.08,
        "max_drawdown": 6.0,
        "daily_loss": 60.0,
        "discovery_interval": 15
    },
    "xlarge": {
        "max_capital": float('inf'),
        "trade_size_pct": 3.0,
        "max_markets": 75,
        "spread_min": 0.003,
        "spread_max": 0.06,
        "max_drawdown": 5.0,
        "daily_loss": 100.0,
        "discovery_interval": 10
    }
}


class AutoOptimizer(QObject):
    """
    Automatic parameter optimizer.

    Modes:
    - MANUAL: No automatic changes, user controls everything
    - SEMI_AUTO: Generates suggestions, user approves/rejects
    - FULL_AUTO: Automatically applies optimizations
    """

    # Signals
    suggestion_generated = Signal(dict)  # New suggestion available
    param_changed = Signal(str, object, object)  # param, old, new
    kelly_updated = Signal(dict)  # Kelly stats updated
    mode_changed = Signal(str)  # Mode changed
    status_changed = Signal(dict)  # General status update

    def __init__(self, orchestrator=None):
        super().__init__()
        self._orchestrator = orchestrator
        self._mode = OptimizerMode.MANUAL
        self._running = False
        self._interval = 5.0  # Optimization cycle interval in seconds

        self._suggestions: list[Suggestion] = []
        self._history: list[HistoryEntry] = []
        self._max_history = 50

        self._kelly = KellyCriterion()
        self._kelly_enabled_a = False
        self._kelly_enabled_b = False
        self._kelly_fraction = 0.25  # Quarter Kelly default
        self._kelly_min_edge = 0.02
        self._kelly_max_multiplier = 2.0

        self._loop_task: Optional[asyncio.Task] = None

    @property
    def mode(self) -> OptimizerMode:
        return self._mode

    @mode.setter
    def mode(self, value: OptimizerMode):
        self._mode = value
        self.mode_changed.emit(value.value)

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def suggestions(self) -> list[Suggestion]:
        return [s for s in self._suggestions if not s.applied]

    @property
    def history(self) -> list[HistoryEntry]:
        return self._history[-20:]  # Last 20 entries

    def get_tier_for_capital(self, capital: float) -> str:
        """Get the appropriate tier name for a capital amount."""
        for tier_name, tier_config in CAPITAL_TIERS.items():
            if capital <= tier_config["max_capital"]:
                return tier_name
        return "xlarge"

    def optimize_for_capital(self, capital: float) -> dict:
        """
        Generate optimized configuration for a given capital amount.

        Args:
            capital: Total capital in dollars

        Returns:
            Dictionary with optimized parameters
        """
        tier_name = self.get_tier_for_capital(capital)
        tier = CAPITAL_TIERS[tier_name]

        # Calculate allocations (50/50 split)
        alloc_a = capital * 0.5
        alloc_b = capital * 0.5

        return {
            "tier": tier_name,
            "capital": {
                "total": capital,
                "max_allocation_strategy_a": alloc_a,
                "max_allocation_strategy_b": alloc_b
            },
            "strategy_a": {
                "trade_size_percent": tier["trade_size_pct"],
                "trade_size_usd": alloc_a * tier["trade_size_pct"] / 100,
                "exit_config": {
                    "profit_target_pct": 1.5 + (0.1 if capital < 200 else 0),
                    "stop_loss_pct": 0.8 + (0.2 if capital < 200 else 0),
                    "trailing_stop_pct": 0.4,
                    "max_hold_seconds": 90
                }
            },
            "strategy_b": {
                "trade_size_percent": tier["trade_size_pct"],
                "trade_size_usd": alloc_b * tier["trade_size_pct"] / 100,
                "spread_min": tier["spread_min"],
                "spread_max": tier["spread_max"],
                "max_markets": tier["max_markets"],
                "discovery_interval": tier["discovery_interval"],
                "max_exposure": alloc_b,
                "exit_config": {
                    "profit_target_pct": 1.4,
                    "stop_loss_pct": 0.9,
                    "trailing_stop_pct": 0.45,
                    "max_hold_seconds": 240
                }
            },
            "risk": {
                "max_drawdown_percent": tier["max_drawdown"],
                "max_daily_loss": tier["daily_loss"],
                "kill_switch_threshold": tier["max_drawdown"] * 1.5
            }
        }

    def calculate_kelly_sizes(self) -> dict:
        """
        Calculate Kelly-optimal position sizes for each strategy.

        Returns:
            Dictionary with Kelly statistics for each strategy
        """
        result = {}

        if self._kelly_enabled_a:
            stats_a = self._kelly.get_strategy_stats("Strategy_A")
            if stats_a:
                result["strategy_a"] = {
                    "win_rate": stats_a.win_rate,
                    "avg_win": stats_a.avg_win,
                    "avg_loss": stats_a.avg_loss,
                    "kelly_fraction": stats_a.kelly_fraction,
                    "recommended_pct": stats_a.recommended_size_pct,
                    "total_trades": stats_a.total_trades
                }

        if self._kelly_enabled_b:
            stats_b = self._kelly.get_strategy_stats("Strategy_B")
            if stats_b:
                result["strategy_b"] = {
                    "win_rate": stats_b.win_rate,
                    "avg_win": stats_b.avg_win,
                    "avg_loss": stats_b.avg_loss,
                    "kelly_fraction": stats_b.kelly_fraction,
                    "recommended_pct": stats_b.recommended_size_pct,
                    "total_trades": stats_b.total_trades
                }

        self.kelly_updated.emit(result)
        return result

    def set_kelly_config(
        self,
        enabled_a: bool = False,
        enabled_b: bool = False,
        fraction: float = 0.25,
        min_edge: float = 0.02,
        max_multiplier: float = 2.0
    ):
        """Configure Kelly Criterion parameters."""
        self._kelly_enabled_a = enabled_a
        self._kelly_enabled_b = enabled_b
        self._kelly_fraction = fraction
        self._kelly_min_edge = min_edge
        self._kelly_max_multiplier = max_multiplier
        self._kelly.set_fraction(fraction)

    async def start(self):
        """Start the optimization loop."""
        if self._running:
            return

        self._running = True
        self._loop_task = asyncio.create_task(self._optimization_loop())
        self.status_changed.emit({"running": True, "mode": self._mode.value})

    async def stop(self):
        """Stop the optimization loop."""
        self._running = False
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
        self.status_changed.emit({"running": False, "mode": self._mode.value})

    async def _optimization_loop(self):
        """Main optimization loop."""
        while self._running:
            try:
                if self._mode != OptimizerMode.MANUAL:
                    # Collect market conditions
                    conditions = self._collect_conditions()

                    # Generate suggestions based on conditions
                    new_suggestions = self._generate_suggestions(conditions)

                    for suggestion in new_suggestions:
                        self._suggestions.append(suggestion)
                        self.suggestion_generated.emit({
                            "param": suggestion.param_name,
                            "current": suggestion.current_value,
                            "suggested": suggestion.suggested_value,
                            "reason": suggestion.reason
                        })

                        # Auto-apply in FULL_AUTO mode
                        if self._mode == OptimizerMode.FULL_AUTO:
                            self.apply_suggestion(suggestion)

                    # Update Kelly calculations
                    if self._kelly_enabled_a or self._kelly_enabled_b:
                        self.calculate_kelly_sizes()

            except Exception as e:
                print(f"Optimizer error: {e}")

            await asyncio.sleep(self._interval)

    def _collect_conditions(self) -> dict:
        """Collect current market conditions from orchestrator."""
        conditions = {
            "timestamp": time.time(),
            "spread_avg": None,
            "volume_24h": None,
            "active_positions": 0,
            "current_pnl": 0.0
        }

        if self._orchestrator:
            # Get strategy status
            status_a = self._orchestrator.strategy_a_status
            status_b = self._orchestrator.strategy_b_status

            if status_a:
                conditions["positions_a"] = status_a.active_positions
            if status_b:
                conditions["positions_b"] = status_b.active_positions
                conditions["active_positions"] = (
                    (status_a.active_positions if status_a else 0) +
                    (status_b.active_positions if status_b else 0)
                )

            # Get performance stats
            stats = self._orchestrator.performance_stats
            if stats:
                conditions["current_pnl"] = stats.get("total_pnl", 0)
                conditions["win_rate"] = stats.get("win_rate", 0)

        return conditions

    def _generate_suggestions(self, conditions: dict) -> list[Suggestion]:
        """Generate optimization suggestions based on conditions."""
        suggestions = []

        # Example: If win rate is high, suggest increasing trade size
        win_rate = conditions.get("win_rate", 0)
        if win_rate > 65:
            suggestions.append(Suggestion(
                param_name="trade_size_percent",
                current_value=5.0,
                suggested_value=6.0,
                reason=f"Win rate eleve ({win_rate:.1f}%)"
            ))

        # Example: If too many positions, suggest reducing
        positions = conditions.get("active_positions", 0)
        if positions > 20:
            suggestions.append(Suggestion(
                param_name="max_markets",
                current_value=35,
                suggested_value=25,
                reason=f"Trop de positions actives ({positions})"
            ))

        return suggestions

    def apply_suggestion(self, suggestion: Suggestion):
        """Apply a suggestion and record in history."""
        # Record in history
        entry = HistoryEntry(
            param_name=suggestion.param_name,
            old_value=suggestion.current_value,
            new_value=suggestion.suggested_value,
            reason=suggestion.reason
        )
        self._history.append(entry)

        # Trim history if needed
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        # Mark as applied
        suggestion.applied = True

        # Emit signal
        self.param_changed.emit(
            suggestion.param_name,
            suggestion.current_value,
            suggestion.suggested_value
        )

        # TODO: Actually apply to orchestrator config
        # This would require config hot-reload support

    def reject_suggestion(self, suggestion: Suggestion):
        """Reject a suggestion."""
        suggestion.applied = True  # Mark as processed

    def get_status(self) -> dict:
        """Get current optimizer status."""
        return {
            "running": self._running,
            "mode": self._mode.value,
            "pending_suggestions": len(self.suggestions),
            "history_count": len(self._history),
            "kelly_enabled_a": self._kelly_enabled_a,
            "kelly_enabled_b": self._kelly_enabled_b,
            "kelly_fraction": self._kelly_fraction
        }
