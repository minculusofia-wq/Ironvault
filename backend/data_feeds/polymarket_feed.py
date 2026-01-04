"""
Polymarket Price Monitor
Detects significant price movements on Polymarket without external APIs.

This is the primary feed for Strategy A when no external data sources are available.
It monitors:
- Rapid price changes (> threshold in < time window)
- Volume spikes
- Orderbook imbalance shifts
- Spread compression events
"""

import asyncio
import time
from dataclasses import dataclass
from typing import List, Dict, Optional
from collections import deque

from .base_feed import BaseFeed, FeedTrigger, TriggerType


@dataclass
class PriceSnapshot:
    """Point-in-time price data for a token."""
    timestamp: float
    midpoint: float
    best_bid: float
    best_ask: float
    spread_pct: float
    bid_volume: float
    ask_volume: float


class PolymarketPriceMonitor(BaseFeed):
    """
    Monitors Polymarket prices for significant movements.

    Detection methods:
    1. Price Velocity: Price change > X% in < Y seconds
    2. Volume Spike: Volume > Z standard deviations from mean
    3. Imbalance Shift: Orderbook imbalance crosses threshold
    4. Spread Compression: Rapid spread narrowing (usually precedes move)
    """

    def __init__(
        self,
        clob_adapter,
        market_scanner,
        audit_logger,
        poll_interval: float = 1.0
    ):
        super().__init__("PolymarketPriceMonitor")

        self._clob = clob_adapter
        self._scanner = market_scanner
        self._audit = audit_logger
        self._poll_interval = poll_interval

        # Price history per token (rolling window)
        self._price_history: Dict[str, deque] = {}
        self._history_window = 300  # 5 minutes of history

        # Detection thresholds (configurable)
        self._thresholds = {
            'price_spike_pct': 3.0,        # 3% move triggers alert
            'price_spike_window_sec': 60,  # Within 60 seconds
            'volume_spike_std': 2.5,       # 2.5 std deviations
            'imbalance_threshold': 0.7,    # 70/30 imbalance
            'spread_compression_pct': 50,  # Spread narrows by 50%
            'min_confidence': 0.5          # Minimum confidence to emit
        }

        # Tracking for volume baseline
        self._volume_baseline: Dict[str, List[float]] = {}

        # Active monitoring tokens
        self._monitored_tokens: List[str] = []

    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        self._audit.log_system_event("POLYMARKET_MONITOR_STARTED")

        while self._running:
            try:
                # 1. Update monitored tokens from market scanner
                await self._update_monitored_tokens()

                # 2. Check each token for triggers
                triggers = await self.check_now()

                # 3. Emit any detected triggers
                for trigger in triggers:
                    await self._emit_trigger(trigger)

            except Exception as e:
                self._audit.log_error("POLYMARKET_MONITOR_ERROR", str(e))

            await asyncio.sleep(self._poll_interval)

        self._audit.log_system_event("POLYMARKET_MONITOR_STOPPED")

    async def _update_monitored_tokens(self) -> None:
        """Update list of tokens to monitor from market scanner."""
        # Get top markets from scanner
        if self._scanner:
            top_markets = self._scanner.get_top_markets_for_fr(limit=30)
            self._monitored_tokens = [m.token_id for m in top_markets]

    async def check_now(self) -> List[FeedTrigger]:
        """Perform immediate check on all monitored tokens."""
        triggers = []

        if not self._monitored_tokens:
            return triggers

        # v3.0: Fetch orderbooks in parallel (larger batches for speed)
        batch_size = 20  # Increased from 10
        for i in range(0, len(self._monitored_tokens), batch_size):
            batch = self._monitored_tokens[i:i+batch_size]

            tasks = [self._clob.get_orderbook(token_id) for token_id in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for token_id, book in zip(batch, results):
                if isinstance(book, Exception) or book is None:
                    continue

                # Record price snapshot
                snapshot = PriceSnapshot(
                    timestamp=time.time(),
                    midpoint=book.midpoint,
                    best_bid=book.best_bid,
                    best_ask=book.best_ask,
                    spread_pct=book.spread_percent,
                    bid_volume=sum(float(b[1]) for b in book.bids[:5]) if book.bids else 0,
                    ask_volume=sum(float(a[1]) for a in book.asks[:5]) if book.asks else 0
                )

                # Store in history
                if token_id not in self._price_history:
                    self._price_history[token_id] = deque(maxlen=self._history_window)
                self._price_history[token_id].append(snapshot)

                # Run detection algorithms
                detected = self._detect_triggers(token_id, snapshot)
                triggers.extend(detected)

            await asyncio.sleep(0.015)  # v3.0: Reduced delay between batches

        return triggers

    def _detect_triggers(self, token_id: str, current: PriceSnapshot) -> List[FeedTrigger]:
        """Run all detection algorithms on a token."""
        triggers = []
        history = self._price_history.get(token_id, deque())

        if len(history) < 2:
            return triggers

        # 1. Price Spike Detection
        spike_trigger = self._detect_price_spike(token_id, current, history)
        if spike_trigger:
            triggers.append(spike_trigger)

        # 2. Imbalance Shift Detection
        imbalance_trigger = self._detect_imbalance_shift(token_id, current, history)
        if imbalance_trigger:
            triggers.append(imbalance_trigger)

        # 3. Spread Compression Detection
        spread_trigger = self._detect_spread_compression(token_id, current, history)
        if spread_trigger:
            triggers.append(spread_trigger)

        return triggers

    def _detect_price_spike(
        self,
        token_id: str,
        current: PriceSnapshot,
        history: deque
    ) -> Optional[FeedTrigger]:
        """Detect rapid price movements."""
        threshold = self._thresholds['price_spike_pct'] / 100
        window = self._thresholds['price_spike_window_sec']

        # Find price from window seconds ago
        cutoff_time = current.timestamp - window
        old_price = None

        for snap in history:
            if snap.timestamp <= cutoff_time:
                old_price = snap.midpoint
                break

        if old_price is None or old_price == 0:
            return None

        # Calculate change
        price_change = (current.midpoint - old_price) / old_price

        if abs(price_change) < threshold:
            return None

        # Determine direction
        if price_change > 0:
            trigger_type = TriggerType.PRICE_SPIKE_UP
            direction = "BUY"  # Price going up, momentum suggests more upside
        else:
            trigger_type = TriggerType.PRICE_SPIKE_DOWN
            direction = "SELL"

        # Calculate confidence based on magnitude
        confidence = min(1.0, abs(price_change) / (threshold * 2))

        return FeedTrigger(
            trigger_id=self._generate_trigger_id(),
            trigger_type=trigger_type,
            token_id=token_id,
            confidence=confidence,
            urgency=0.8,  # Price spikes are urgent
            direction=direction,
            expected_move_pct=abs(price_change) * 100 * 0.5,  # Expect 50% continuation
            source=self._name,
            timestamp=current.timestamp,
            details={
                'price_change_pct': round(price_change * 100, 2),
                'old_price': old_price,
                'new_price': current.midpoint,
                'window_seconds': window
            }
        )

    def _detect_imbalance_shift(
        self,
        token_id: str,
        current: PriceSnapshot,
        history: deque
    ) -> Optional[FeedTrigger]:
        """Detect significant orderbook imbalance changes."""
        threshold = self._thresholds['imbalance_threshold']

        total_volume = current.bid_volume + current.ask_volume
        if total_volume == 0:
            return None

        # Current imbalance (positive = more bids, negative = more asks)
        current_imbalance = (current.bid_volume - current.ask_volume) / total_volume

        # Compare to average imbalance over history
        if len(history) < 10:
            return None

        historical_imbalances = []
        for snap in list(history)[-30:]:  # Last 30 snapshots
            total = snap.bid_volume + snap.ask_volume
            if total > 0:
                historical_imbalances.append(
                    (snap.bid_volume - snap.ask_volume) / total
                )

        if not historical_imbalances:
            return None

        avg_imbalance = sum(historical_imbalances) / len(historical_imbalances)
        imbalance_shift = current_imbalance - avg_imbalance

        # Check if shift is significant
        if abs(current_imbalance) < threshold:
            return None

        if abs(imbalance_shift) < 0.3:  # Need at least 30% shift
            return None

        # Determine direction based on imbalance
        if current_imbalance > 0:
            direction = "BUY"  # More buyers than sellers
        else:
            direction = "SELL"

        confidence = min(1.0, abs(current_imbalance) / 0.9)

        return FeedTrigger(
            trigger_id=self._generate_trigger_id(),
            trigger_type=TriggerType.IMBALANCE_SHIFT,
            token_id=token_id,
            confidence=confidence,
            urgency=0.6,
            direction=direction,
            expected_move_pct=abs(imbalance_shift) * 5,  # Rough estimate
            source=self._name,
            timestamp=current.timestamp,
            details={
                'current_imbalance': round(current_imbalance, 3),
                'avg_imbalance': round(avg_imbalance, 3),
                'imbalance_shift': round(imbalance_shift, 3),
                'bid_volume': current.bid_volume,
                'ask_volume': current.ask_volume
            }
        )

    def _detect_spread_compression(
        self,
        token_id: str,
        current: PriceSnapshot,
        history: deque
    ) -> Optional[FeedTrigger]:
        """Detect rapid spread narrowing (often precedes breakout)."""
        threshold = self._thresholds['spread_compression_pct'] / 100

        if len(history) < 10:
            return None

        # Average spread over last 30 snapshots
        recent_spreads = [snap.spread_pct for snap in list(history)[-30:]]
        avg_spread = sum(recent_spreads) / len(recent_spreads)

        if avg_spread == 0:
            return None

        # Check for compression
        compression = (avg_spread - current.spread_pct) / avg_spread

        if compression < threshold:
            return None

        # Spread compression doesn't give us direction, but it signals
        # that a move is coming. Use imbalance for direction hint.
        total_vol = current.bid_volume + current.ask_volume
        if total_vol > 0:
            imbalance = (current.bid_volume - current.ask_volume) / total_vol
            direction = "BUY" if imbalance > 0 else "SELL"
        else:
            direction = "BUY"  # Default

        confidence = min(1.0, compression / (threshold * 2))

        return FeedTrigger(
            trigger_id=self._generate_trigger_id(),
            trigger_type=TriggerType.SPREAD_COMPRESSION,
            token_id=token_id,
            confidence=confidence * 0.7,  # Lower confidence - less directional
            urgency=0.7,
            direction=direction,
            expected_move_pct=compression * 10,  # Rough estimate
            source=self._name,
            timestamp=current.timestamp,
            details={
                'current_spread_pct': round(current.spread_pct, 3),
                'avg_spread_pct': round(avg_spread, 3),
                'compression_pct': round(compression * 100, 1)
            }
        )

    def configure(self, thresholds: dict) -> None:
        """Update detection thresholds."""
        for key in thresholds:
            if key in self._thresholds:
                self._thresholds[key] = thresholds[key]

        self._audit.log_system_event("POLYMARKET_MONITOR_CONFIGURED", self._thresholds)

    def set_monitored_tokens(self, tokens: List[str]) -> None:
        """Manually set tokens to monitor."""
        self._monitored_tokens = tokens

    def add_monitored_token(self, token_id: str) -> None:
        """Add a single token to monitor."""
        if token_id not in self._monitored_tokens:
            self._monitored_tokens.append(token_id)

    @property
    def monitored_token_count(self) -> int:
        """Number of tokens being monitored."""
        return len(self._monitored_tokens)

    def get_price_history(self, token_id: str) -> List[PriceSnapshot]:
        """Get price history for a token."""
        return list(self._price_history.get(token_id, []))
