"""
Kelly Criterion Module
Calculates optimal position sizing based on historical performance.
"""

from dataclasses import dataclass
from typing import Optional
import sqlite3


@dataclass
class KellyStats:
    """Statistics for Kelly calculation."""
    win_rate: float
    avg_win: float
    avg_loss: float
    total_trades: int
    kelly_fraction: float
    recommended_size_pct: float


class KellyCriterion:
    """
    Implements Kelly Criterion for optimal position sizing.

    f* = (p * b - q) / b

    where:
        f* = optimal fraction of capital to risk
        p  = probability of winning
        q  = probability of losing (1 - p)
        b  = odds (average_win / average_loss)
    """

    def __init__(self, db_path: str = "data/performance.db"):
        self._db_path = db_path
        self._min_trades = 20  # Minimum trades for reliable calculation
        self._default_fraction = 0.25  # Quarter Kelly by default

    def calculate_kelly(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float
    ) -> float:
        """
        Calculate optimal Kelly fraction.

        Args:
            win_rate: Probability of winning (0-1)
            avg_win: Average profit on winning trades
            avg_loss: Average loss on losing trades (positive value)

        Returns:
            Optimal fraction of capital to risk (0-1)
        """
        if avg_loss <= 0 or win_rate <= 0 or win_rate >= 1:
            return 0.0

        b = avg_win / avg_loss  # Win/loss ratio
        p = win_rate
        q = 1 - p

        kelly = (p * b - q) / b

        # Clamp to reasonable bounds
        return max(0.0, min(kelly, 1.0))

    def get_strategy_stats(self, strategy: str) -> Optional[KellyStats]:
        """
        Get Kelly statistics for a specific strategy.

        Args:
            strategy: Strategy name (e.g., "Strategy_A_FrontRunning")

        Returns:
            KellyStats or None if insufficient data
        """
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()

            # Get win/loss stats
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                    AVG(CASE WHEN pnl > 0 THEN pnl ELSE NULL END) as avg_win,
                    AVG(CASE WHEN pnl < 0 THEN ABS(pnl) ELSE NULL END) as avg_loss
                FROM trades
                WHERE strategy LIKE ? AND pnl != 0
            """, (f"%{strategy}%",))

            row = cursor.fetchone()
            conn.close()

            if not row or row[0] < self._min_trades:
                return None

            total, wins, avg_win, avg_loss = row

            if avg_win is None or avg_loss is None:
                return None

            win_rate = wins / total if total > 0 else 0
            kelly = self.calculate_kelly(win_rate, avg_win, avg_loss)

            # Apply fraction (quarter/half Kelly)
            adjusted_kelly = kelly * self._default_fraction

            return KellyStats(
                win_rate=win_rate,
                avg_win=avg_win,
                avg_loss=avg_loss,
                total_trades=total,
                kelly_fraction=kelly,
                recommended_size_pct=adjusted_kelly * 100
            )

        except Exception:
            return None

    def get_recommended_size(
        self,
        strategy: str,
        capital: float,
        fraction: float = 0.25,
        max_multiplier: float = 2.0,
        min_edge: float = 0.02
    ) -> float:
        """
        Get recommended trade size in dollars.

        Args:
            strategy: Strategy name
            capital: Total capital available
            fraction: Kelly fraction to use (0.25 = quarter Kelly)
            max_multiplier: Maximum multiplier on base size
            min_edge: Minimum required edge to use Kelly

        Returns:
            Recommended trade size in dollars
        """
        stats = self.get_strategy_stats(strategy)

        if stats is None:
            # Not enough data, return conservative default
            return capital * 0.05  # 5% default

        # Check if edge is sufficient
        edge = (stats.win_rate * stats.avg_win) - ((1 - stats.win_rate) * stats.avg_loss)
        if edge < min_edge:
            return capital * 0.05  # Conservative if edge is small

        # Calculate Kelly-adjusted size
        kelly_size = capital * stats.kelly_fraction * fraction

        # Apply max multiplier cap
        base_size = capital * 0.05
        max_size = base_size * max_multiplier

        return min(kelly_size, max_size)

    def set_fraction(self, fraction: float):
        """Set Kelly fraction (0.25 = quarter, 0.5 = half, 1.0 = full)."""
        self._default_fraction = max(0.1, min(fraction, 1.0))

    def set_min_trades(self, min_trades: int):
        """Set minimum trades required for Kelly calculation."""
        self._min_trades = max(10, min_trades)
