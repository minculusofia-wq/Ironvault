"""
Analytics Engine Module
Real-time calculation of trading metrics and performance statistics.

v2.5 Features:
- Rolling Sharpe Ratio
- Maximum Drawdown tracking
- Win rate by strategy
- Profit factor calculation
- Expected value per trade
- Real-time PnL tracking
"""

import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from collections import deque
import math

from .audit_logger import AuditLogger


@dataclass
class TradeMetric:
    """Single trade for analytics tracking."""
    trade_id: str
    strategy: str
    timestamp: float
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    pnl_pct: float
    hold_time_sec: float
    is_winner: bool


@dataclass
class PerformanceSnapshot:
    """Point-in-time performance snapshot."""
    timestamp: float
    total_pnl: float
    equity: float
    drawdown: float
    drawdown_pct: float


class AnalyticsEngine:
    """
    Real-time analytics and performance tracking.
    """

    def __init__(self, audit_logger: AuditLogger, initial_capital: float = 1000.0):
        self._audit = audit_logger
        self._initial_capital = initial_capital
        self._current_equity = initial_capital

        # Trade history
        self._trades: List[TradeMetric] = []
        self._trades_by_strategy: Dict[str, List[TradeMetric]] = {}

        # Rolling windows for calculations
        self._pnl_history: deque = deque(maxlen=1000)  # Last 1000 PnL points
        self._equity_history: deque = deque(maxlen=10000)  # Equity curve

        # Performance tracking
        self._peak_equity = initial_capital
        self._max_drawdown = 0.0
        self._max_drawdown_pct = 0.0

        # Session stats
        self._session_start = time.time()
        self._total_pnl = 0.0
        self._total_trades = 0
        self._winning_trades = 0
        self._losing_trades = 0

        # Risk-free rate for Sharpe (annualized, ~5% = 0.05)
        self._risk_free_rate = 0.05

        # Initialize with starting point
        self._equity_history.append(PerformanceSnapshot(
            timestamp=time.time(),
            total_pnl=0.0,
            equity=initial_capital,
            drawdown=0.0,
            drawdown_pct=0.0
        ))

    def record_trade(
        self,
        trade_id: str,
        strategy: str,
        entry_price: float,
        exit_price: float,
        size: float,
        hold_time_sec: float
    ) -> TradeMetric:
        """
        Record a completed trade and update all metrics.
        """
        pnl = (exit_price - entry_price) * size
        pnl_pct = ((exit_price / entry_price) - 1) * 100 if entry_price > 0 else 0
        is_winner = pnl > 0

        trade = TradeMetric(
            trade_id=trade_id,
            strategy=strategy,
            timestamp=time.time(),
            entry_price=entry_price,
            exit_price=exit_price,
            size=size,
            pnl=pnl,
            pnl_pct=pnl_pct,
            hold_time_sec=hold_time_sec,
            is_winner=is_winner
        )

        # Update tracking
        self._trades.append(trade)
        if strategy not in self._trades_by_strategy:
            self._trades_by_strategy[strategy] = []
        self._trades_by_strategy[strategy].append(trade)

        # Update statistics
        self._total_pnl += pnl
        self._total_trades += 1
        if is_winner:
            self._winning_trades += 1
        else:
            self._losing_trades += 1

        # Update equity and drawdown
        self._current_equity += pnl
        self._pnl_history.append(pnl)
        self._update_drawdown()

        # Record snapshot
        self._equity_history.append(PerformanceSnapshot(
            timestamp=time.time(),
            total_pnl=self._total_pnl,
            equity=self._current_equity,
            drawdown=self._max_drawdown,
            drawdown_pct=self._max_drawdown_pct
        ))

        return trade

    def _update_drawdown(self) -> None:
        """Update peak equity and drawdown."""
        if self._current_equity > self._peak_equity:
            self._peak_equity = self._current_equity

        current_drawdown = self._peak_equity - self._current_equity
        current_drawdown_pct = (current_drawdown / self._peak_equity * 100) if self._peak_equity > 0 else 0

        if current_drawdown > self._max_drawdown:
            self._max_drawdown = current_drawdown
            self._max_drawdown_pct = current_drawdown_pct

    def calculate_sharpe_ratio(self, period_trades: int = 100) -> float:
        """
        Calculate Sharpe Ratio based on recent trades.
        Uses daily returns approximation.
        """
        if len(self._pnl_history) < 2:
            return 0.0

        recent_pnls = list(self._pnl_history)[-period_trades:]

        if len(recent_pnls) < 2:
            return 0.0

        avg_return = sum(recent_pnls) / len(recent_pnls)
        std_return = math.sqrt(
            sum((pnl - avg_return) ** 2 for pnl in recent_pnls) / len(recent_pnls)
        )

        if std_return == 0:
            return 0.0

        # Annualize (assuming ~250 trading days, ~10 trades per day)
        annualization_factor = math.sqrt(250 * 10)

        # Calculate excess return (subtract risk-free rate per trade)
        rfr_per_trade = self._risk_free_rate / (250 * 10)
        excess_return = avg_return - rfr_per_trade

        sharpe = (excess_return / std_return) * annualization_factor

        return round(sharpe, 2)

    def calculate_profit_factor(self) -> float:
        """
        Calculate Profit Factor = Gross Profit / Gross Loss
        """
        gross_profit = sum(t.pnl for t in self._trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in self._trades if t.pnl < 0))

        if gross_loss == 0:
            return float('inf') if gross_profit > 0 else 0.0

        return round(gross_profit / gross_loss, 2)

    def calculate_expected_value(self) -> float:
        """
        Calculate Expected Value per trade.
        EV = (Win Rate * Avg Win) - (Loss Rate * Avg Loss)
        """
        if self._total_trades == 0:
            return 0.0

        winning = [t for t in self._trades if t.pnl > 0]
        losing = [t for t in self._trades if t.pnl <= 0]

        win_rate = len(winning) / self._total_trades
        loss_rate = len(losing) / self._total_trades

        avg_win = sum(t.pnl for t in winning) / len(winning) if winning else 0
        avg_loss = abs(sum(t.pnl for t in losing) / len(losing)) if losing else 0

        ev = (win_rate * avg_win) - (loss_rate * avg_loss)

        return round(ev, 4)

    def get_strategy_stats(self, strategy: str) -> dict:
        """Get statistics for a specific strategy."""
        trades = self._trades_by_strategy.get(strategy, [])

        if not trades:
            return {
                'total_trades': 0,
                'win_rate': 0,
                'total_pnl': 0,
                'avg_pnl': 0,
                'avg_hold_time': 0
            }

        winners = [t for t in trades if t.is_winner]
        total_pnl = sum(t.pnl for t in trades)

        return {
            'total_trades': len(trades),
            'winning_trades': len(winners),
            'losing_trades': len(trades) - len(winners),
            'win_rate': round(len(winners) / len(trades) * 100, 1),
            'total_pnl': round(total_pnl, 4),
            'avg_pnl': round(total_pnl / len(trades), 4),
            'avg_hold_time': round(sum(t.hold_time_sec for t in trades) / len(trades), 1),
            'best_trade': round(max(t.pnl for t in trades), 4),
            'worst_trade': round(min(t.pnl for t in trades), 4)
        }

    def get_summary(self) -> dict:
        """Get comprehensive performance summary."""
        runtime_hours = (time.time() - self._session_start) / 3600

        return {
            # Overview
            'session_runtime_hours': round(runtime_hours, 2),
            'initial_capital': self._initial_capital,
            'current_equity': round(self._current_equity, 2),
            'total_pnl': round(self._total_pnl, 4),
            'return_pct': round((self._total_pnl / self._initial_capital) * 100, 2),

            # Trade Statistics
            'total_trades': self._total_trades,
            'winning_trades': self._winning_trades,
            'losing_trades': self._losing_trades,
            'win_rate': round(
                (self._winning_trades / self._total_trades * 100) if self._total_trades > 0 else 0, 1
            ),

            # Risk Metrics
            'max_drawdown': round(self._max_drawdown, 4),
            'max_drawdown_pct': round(self._max_drawdown_pct, 2),
            'peak_equity': round(self._peak_equity, 2),

            # Performance Metrics
            'sharpe_ratio': self.calculate_sharpe_ratio(),
            'profit_factor': self.calculate_profit_factor(),
            'expected_value_per_trade': self.calculate_expected_value(),
            'avg_pnl_per_trade': round(
                self._total_pnl / self._total_trades if self._total_trades > 0 else 0, 4
            ),

            # Strategy Breakdown
            'strategies': {
                strategy: self.get_strategy_stats(strategy)
                for strategy in self._trades_by_strategy.keys()
            }
        }

    def get_equity_curve(self, points: int = 100) -> List[dict]:
        """Get equity curve data for charting."""
        history = list(self._equity_history)

        if len(history) <= points:
            return [
                {
                    'timestamp': s.timestamp,
                    'equity': s.equity,
                    'pnl': s.total_pnl,
                    'drawdown_pct': s.drawdown_pct
                }
                for s in history
            ]

        # Sample evenly
        step = len(history) / points
        sampled = []
        for i in range(points):
            idx = int(i * step)
            s = history[idx]
            sampled.append({
                'timestamp': s.timestamp,
                'equity': s.equity,
                'pnl': s.total_pnl,
                'drawdown_pct': s.drawdown_pct
            })

        return sampled

    def get_recent_trades(self, limit: int = 20) -> List[dict]:
        """Get most recent trades."""
        recent = self._trades[-limit:] if len(self._trades) >= limit else self._trades

        return [
            {
                'trade_id': t.trade_id,
                'strategy': t.strategy,
                'timestamp': t.timestamp,
                'pnl': round(t.pnl, 4),
                'pnl_pct': round(t.pnl_pct, 2),
                'hold_time_sec': round(t.hold_time_sec, 1),
                'is_winner': t.is_winner
            }
            for t in reversed(recent)
        ]

    def reset(self) -> None:
        """Reset all analytics (for new session)."""
        self._trades.clear()
        self._trades_by_strategy.clear()
        self._pnl_history.clear()
        self._equity_history.clear()

        self._current_equity = self._initial_capital
        self._peak_equity = self._initial_capital
        self._max_drawdown = 0.0
        self._max_drawdown_pct = 0.0
        self._total_pnl = 0.0
        self._total_trades = 0
        self._winning_trades = 0
        self._losing_trades = 0
        self._session_start = time.time()

        self._audit.log_system_event("ANALYTICS_RESET")

    def set_initial_capital(self, capital: float) -> None:
        """Update initial capital (typically from config)."""
        self._initial_capital = capital
        self._current_equity = capital + self._total_pnl
        self._peak_equity = max(self._peak_equity, self._current_equity)
        self._audit.log_system_event("ANALYTICS_CAPITAL_SET", {"capital": capital})
