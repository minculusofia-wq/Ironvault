"""
Market Scanner Module
Intelligent market discovery and scoring for optimal trading opportunities.

v2.5 Features:
- Multi-factor market scoring
- Volume and liquidity analysis
- Spread opportunity detection
- Time-to-resolution weighting
- Historical profitability tracking
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from enum import Enum

from .audit_logger import AuditLogger
from .market_data import GammaClient
from .clob_adapter import ClobAdapter, MarketSnapshot


class MarketType(Enum):
    """Market classification for strategy routing."""
    HIGH_VOLUME = "high_volume"
    WIDE_SPREAD = "wide_spread"
    VOLATILE = "volatile"
    STABLE = "stable"
    NEW_MARKET = "new_market"
    EXPIRING_SOON = "expiring_soon"


@dataclass
class MarketScore:
    """Scored market with all relevant metrics."""
    token_id: str
    condition_id: str
    question: str
    score: float  # 0.0 to 1.0
    market_type: MarketType

    # Metrics used for scoring
    volume_24h: float
    spread_pct: float
    midpoint: float
    bid_depth: float
    ask_depth: float
    time_to_resolution_hours: float
    activity_score: float

    # Strategy recommendations
    recommended_for_mm: bool  # Market Making
    recommended_for_fr: bool  # Front-Running

    last_updated: float


class MarketScanner:
    """
    Intelligent market scanner for opportunity detection.
    Scores and ranks markets based on trading potential.
    """

    def __init__(
        self,
        gamma_client: GammaClient,
        clob_adapter: ClobAdapter,
        audit_logger: AuditLogger
    ):
        self._gamma = gamma_client
        self._clob = clob_adapter
        self._audit = audit_logger

        # Cache of scored markets
        self._scored_markets: Dict[str, MarketScore] = {}
        self._last_full_scan: float = 0
        self._scan_interval: float = 30.0  # Seconds between full scans

        # Scoring weights (configurable)
        self._weights = {
            'volume': 0.25,
            'spread': 0.25,
            'depth': 0.20,
            'activity': 0.15,
            'time_to_resolution': 0.15
        }

        # Thresholds for recommendations
        self._thresholds = {
            'min_volume_24h': 1000,      # USD
            'min_spread_for_mm': 0.01,   # 1% minimum spread for MM to be profitable
            'max_spread_for_mm': 0.20,   # 20% max spread (too illiquid)
            'min_depth_usd': 100,        # Minimum depth on each side
            'min_score_for_trading': 0.3
        }

        # Price history for activity scoring
        self._price_history: Dict[str, List[tuple]] = {}  # token_id -> [(timestamp, price)]

    async def scan_markets(self, limit: int = 50) -> List[MarketScore]:
        """
        Perform a full market scan and return scored markets.
        """
        now = time.time()

        # Throttle full scans
        if now - self._last_full_scan < self._scan_interval:
            return list(self._scored_markets.values())

        self._audit.log_system_event("MARKET_SCAN_STARTED", {"limit": limit})

        try:
            # 1. Fetch events from Gamma API
            events = await self._gamma.get_events(limit=limit)

            if not events:
                self._audit.log_system_event("MARKET_SCAN_NO_EVENTS")
                return []

            # 2. Extract all active market tokens
            markets_to_scan = []
            for event in events:
                event_markets = event.get("markets", [])
                for market in event_markets:
                    if market.get("active") and market.get("acceptingOrders"):
                        try:
                            tids = market.get("clobTokenIds")
                            if tids:
                                if isinstance(tids, str):
                                    import json
                                    tids = json.loads(tids)
                                for tid in tids:
                                    markets_to_scan.append({
                                        'token_id': tid,
                                        'condition_id': market.get('conditionId', ''),
                                        'question': market.get('question', event.get('title', 'Unknown')),
                                        'volume_24h': float(market.get('volume24hr', 0) or 0),
                                        'end_date': market.get('endDate', ''),
                                        'outcomes': market.get('outcomes', [])
                                    })
                        except Exception:
                            continue

            # 3. v3.0: Fetch orderbooks concurrently (larger batches for speed)
            batch_size = 25  # Increased from 10 for better throughput
            scored_markets = []

            for i in range(0, len(markets_to_scan), batch_size):
                batch = markets_to_scan[i:i+batch_size]

                # Fetch orderbooks in parallel
                tasks = [self._clob.get_orderbook(m['token_id']) for m in batch]
                orderbooks = await asyncio.gather(*tasks, return_exceptions=True)

                for j, (market_info, book) in enumerate(zip(batch, orderbooks)):
                    if isinstance(book, Exception) or book is None:
                        continue

                    score = self._score_market(market_info, book)
                    if score:
                        scored_markets.append(score)
                        self._scored_markets[score.token_id] = score

                # v3.0: Reduced delay between batches
                await asyncio.sleep(0.02)

            # 4. Sort by score descending
            scored_markets.sort(key=lambda m: m.score, reverse=True)

            self._last_full_scan = now
            self._audit.log_system_event("MARKET_SCAN_COMPLETED", {
                "markets_found": len(scored_markets),
                "top_score": scored_markets[0].score if scored_markets else 0
            })

            return scored_markets

        except Exception as e:
            self._audit.log_error("MARKET_SCAN_ERROR", str(e))
            return list(self._scored_markets.values())

    def _score_market(self, market_info: dict, book: MarketSnapshot) -> Optional[MarketScore]:
        """
        Calculate a composite score for a market.
        """
        token_id = market_info['token_id']
        volume_24h = market_info.get('volume_24h', 0)

        # Extract metrics from orderbook
        spread_pct = book.spread_percent / 100.0  # Convert to decimal
        midpoint = book.midpoint

        # Calculate depth (sum of top 5 levels)
        bid_depth = sum(float(b[1]) for b in book.bids[:5]) if book.bids else 0
        ask_depth = sum(float(a[1]) for a in book.asks[:5]) if book.asks else 0

        # Calculate time to resolution (if end_date available)
        time_to_resolution_hours = 24 * 30  # Default 30 days
        if market_info.get('end_date'):
            try:
                from datetime import datetime
                end_date = datetime.fromisoformat(market_info['end_date'].replace('Z', '+00:00'))
                delta = end_date - datetime.now(end_date.tzinfo)
                time_to_resolution_hours = max(0, delta.total_seconds() / 3600)
            except Exception:
                pass

        # Calculate activity score from price history
        activity_score = self._calculate_activity_score(token_id, midpoint)

        # Skip markets below thresholds
        if volume_24h < self._thresholds['min_volume_24h']:
            return None
        if bid_depth < self._thresholds['min_depth_usd'] or ask_depth < self._thresholds['min_depth_usd']:
            return None

        # Composite scoring
        w = self._weights

        # Volume score (log scale, capped at 1.0)
        volume_score = min(1.0, (volume_24h / 100000) ** 0.5)

        # Spread score (inverted - wider spread = higher opportunity for MM)
        spread_score = min(1.0, spread_pct / 0.10) if spread_pct > 0 else 0

        # Depth score (log scale)
        avg_depth = (bid_depth + ask_depth) / 2
        depth_score = min(1.0, (avg_depth / 10000) ** 0.5)

        # Activity score (from price movement tracking)
        activity_normalized = min(1.0, activity_score)

        # Time urgency (closer to resolution = higher priority, but not too close)
        if time_to_resolution_hours < 1:
            time_score = 0.1  # Too close, risky
        elif time_to_resolution_hours < 24:
            time_score = 0.9  # Good urgency
        elif time_to_resolution_hours < 168:  # 1 week
            time_score = 0.7
        else:
            time_score = 0.3

        # Calculate composite score
        composite_score = (
            w['volume'] * volume_score +
            w['spread'] * spread_score +
            w['depth'] * depth_score +
            w['activity'] * activity_normalized +
            w['time_to_resolution'] * time_score
        )

        # Determine market type
        if volume_24h > 50000:
            market_type = MarketType.HIGH_VOLUME
        elif spread_pct > 0.05:
            market_type = MarketType.WIDE_SPREAD
        elif time_to_resolution_hours < 24:
            market_type = MarketType.EXPIRING_SOON
        elif activity_score > 0.5:
            market_type = MarketType.VOLATILE
        else:
            market_type = MarketType.STABLE

        # Strategy recommendations
        thresholds = self._thresholds
        recommended_for_mm = (
            spread_pct >= thresholds['min_spread_for_mm'] and
            spread_pct <= thresholds['max_spread_for_mm'] and
            avg_depth >= thresholds['min_depth_usd']
        )

        recommended_for_fr = (
            volume_24h > 10000 and
            activity_score > 0.3 and
            bid_depth > 500 and ask_depth > 500
        )

        return MarketScore(
            token_id=token_id,
            condition_id=market_info.get('condition_id', ''),
            question=market_info.get('question', 'Unknown'),
            score=round(composite_score, 4),
            market_type=market_type,
            volume_24h=volume_24h,
            spread_pct=round(spread_pct * 100, 2),
            midpoint=round(midpoint, 4),
            bid_depth=round(bid_depth, 2),
            ask_depth=round(ask_depth, 2),
            time_to_resolution_hours=round(time_to_resolution_hours, 1),
            activity_score=round(activity_score, 3),
            recommended_for_mm=recommended_for_mm,
            recommended_for_fr=recommended_for_fr,
            last_updated=time.time()
        )

    def _calculate_activity_score(self, token_id: str, current_price: float) -> float:
        """
        Calculate activity score based on recent price movements.
        Higher score = more price action = more opportunity.
        """
        now = time.time()

        # Initialize history if needed
        if token_id not in self._price_history:
            self._price_history[token_id] = []

        # Add current price
        self._price_history[token_id].append((now, current_price))

        # Keep only last 5 minutes of history
        five_min_ago = now - 300
        self._price_history[token_id] = [
            (t, p) for t, p in self._price_history[token_id]
            if t > five_min_ago
        ]

        history = self._price_history[token_id]
        if len(history) < 2:
            return 0.0

        # Calculate price velocity (max change in 5 min)
        prices = [p for _, p in history]
        max_price = max(prices)
        min_price = min(prices)

        if min_price == 0:
            return 0.0

        price_range = (max_price - min_price) / min_price

        # Normalize: 5% move in 5 min = score of 1.0
        return min(1.0, price_range / 0.05)

    def get_top_markets_for_mm(self, limit: int = 20) -> List[MarketScore]:
        """Get top markets recommended for Market Making."""
        markets = [m for m in self._scored_markets.values() if m.recommended_for_mm]
        markets.sort(key=lambda m: m.score, reverse=True)
        return markets[:limit]

    def get_top_markets_for_fr(self, limit: int = 10) -> List[MarketScore]:
        """Get top markets recommended for Front-Running."""
        markets = [m for m in self._scored_markets.values() if m.recommended_for_fr]
        markets.sort(key=lambda m: m.activity_score, reverse=True)
        return markets[:limit]

    def get_market_score(self, token_id: str) -> Optional[MarketScore]:
        """Get the score for a specific market."""
        return self._scored_markets.get(token_id)

    def configure(self, weights: dict = None, thresholds: dict = None) -> None:
        """Update scoring weights and thresholds."""
        if weights:
            for key in weights:
                if key in self._weights:
                    self._weights[key] = weights[key]

        if thresholds:
            for key in thresholds:
                if key in self._thresholds:
                    self._thresholds[key] = thresholds[key]

        self._audit.log_system_event("MARKET_SCANNER_CONFIGURED", {
            "weights": self._weights,
            "thresholds": self._thresholds
        })

    @property
    def cached_market_count(self) -> int:
        """Number of markets currently cached."""
        return len(self._scored_markets)

    @property
    def last_scan_age_seconds(self) -> float:
        """Seconds since last full scan."""
        return time.time() - self._last_full_scan if self._last_full_scan > 0 else float('inf')
