"""
Base Feed Module
Abstract interface for all data feeds used by Strategy A.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Callable, List, Any
import asyncio
import time


class TriggerType(Enum):
    """Types of triggers that can be emitted by feeds."""
    # Price-based triggers
    PRICE_SPIKE_UP = "price_spike_up"      # Rapid price increase
    PRICE_SPIKE_DOWN = "price_spike_down"  # Rapid price decrease
    PRICE_BREAKOUT = "price_breakout"      # Price breaks key level

    # Volume-based triggers
    VOLUME_SPIKE = "volume_spike"          # Abnormal volume increase
    LARGE_ORDER = "large_order"            # Large order detected

    # External data triggers
    SCORE_UPDATE = "score_update"          # Sports score change
    NEWS_EVENT = "news_event"              # Breaking news
    SOCIAL_SPIKE = "social_spike"          # Social media activity spike

    # Market structure triggers
    SPREAD_COMPRESSION = "spread_compression"  # Spread narrowing rapidly
    IMBALANCE_SHIFT = "imbalance_shift"        # Orderbook imbalance change


@dataclass
class FeedTrigger:
    """
    Standardized trigger format from any feed source.
    """
    trigger_id: str
    trigger_type: TriggerType
    token_id: str
    confidence: float       # 0.0 to 1.0 - how confident are we in this signal
    urgency: float          # 0.0 to 1.0 - how quickly should we act

    # Signal details
    direction: str          # "BUY" or "SELL" recommendation
    expected_move_pct: float  # Expected price movement percentage

    # Source information
    source: str             # Feed name that generated this
    timestamp: float

    # Additional context
    details: dict


class BaseFeed(ABC):
    """
    Abstract base class for all data feeds.
    Feeds monitor external or internal data sources and emit triggers.
    """

    def __init__(self, feed_name: str):
        self._name = feed_name
        self._running = False
        self._subscribers: List[Callable[[FeedTrigger], Any]] = []
        self._task: asyncio.Task | None = None
        self._trigger_count = 0
        self._last_trigger_time = 0.0

    @property
    def name(self) -> str:
        """Feed identifier."""
        return self._name

    @property
    def is_running(self) -> bool:
        """Check if feed is active."""
        return self._running

    @property
    def trigger_count(self) -> int:
        """Total triggers emitted."""
        return self._trigger_count

    def subscribe(self, callback: Callable[[FeedTrigger], Any]) -> None:
        """
        Subscribe to trigger events from this feed.
        Callback should be async-compatible.
        """
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[FeedTrigger], Any]) -> None:
        """Remove a subscriber."""
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    async def start(self) -> None:
        """Start the feed monitoring loop."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())

    async def stop(self) -> None:
        """Stop the feed monitoring loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    @abstractmethod
    async def _monitor_loop(self) -> None:
        """
        Main monitoring loop. Subclasses implement specific monitoring logic.
        Should call self._emit_trigger() when a signal is detected.
        """
        pass

    @abstractmethod
    async def check_now(self) -> List[FeedTrigger]:
        """
        Perform an immediate check and return any triggers.
        Useful for on-demand scanning.
        """
        pass

    async def _emit_trigger(self, trigger: FeedTrigger) -> None:
        """
        Emit a trigger to all subscribers.
        """
        self._trigger_count += 1
        self._last_trigger_time = time.time()

        for callback in self._subscribers:
            try:
                if asyncio.iscoroutinefunction(callback):
                    asyncio.create_task(callback(trigger))
                else:
                    callback(trigger)
            except Exception:
                pass  # Don't let subscriber errors crash the feed

    def _generate_trigger_id(self) -> str:
        """Generate a unique trigger ID."""
        return f"{self._name}_{int(time.time() * 1000)}_{self._trigger_count}"
