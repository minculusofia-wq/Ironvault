"""
Strategy B: Automated Market Making
Provides liquidity by placing bid/ask quotes.
Capital locked = maximum exposure at any time.

v2.5 Optimizations:
- Dynamic spread based on volatility
- Multi-market parallel processing (up to 50 markets)
- Integration with MarketScanner for intelligent selection
- Enhanced performance tracking and PnL calculation
"""

from .base_strategy import BaseStrategy, StrategyState
from ..capital_manager import CapitalManager
from ..execution_engine import ExecutionEngine
from ..audit_logger import AuditLogger
from ..config_loader import StrategyBConfig
from ..clob_adapter import ClobAdapter
from ..websocket_client import WebSocketClient
from ..live_orderbook import LiveOrderBook
from ..performance_tracker import PerformanceTracker, TradeRecord
from ..volatility_filter import VolatilityFilter
from ..market_data import GammaClient
from typing import Any, List, Dict, Optional
from dataclasses import dataclass
import time
import asyncio


@dataclass
class MarketState:
    """Track state for each market we're making."""
    token_id: str
    buy_order_id: Optional[str] = None
    sell_order_id: Optional[str] = None
    buy_price: float = 0.0
    sell_price: float = 0.0
    position: float = 0.0
    realized_pnl: float = 0.0
    trades_count: int = 0
    last_update: float = 0.0
    volatility_score: float = 0.0
    current_spread: float = 0.0

class StrategyBMarketMaking(BaseStrategy):
    """
    Automated Market Making Strategy.

    Places bid/ask quotes. Uses WebSocket for real-time orderbook.

    v2.5: Enhanced with dynamic spread and multi-market support.
    """

    def __init__(
        self,
        config: StrategyBConfig,
        capital_manager: CapitalManager,
        execution_engine: ExecutionEngine,
        audit_logger: AuditLogger,
        clob_adapter: ClobAdapter,
        websocket_client: WebSocketClient,
        market_data: GammaClient,
        performance_tracker: PerformanceTracker | None = None,
        volatility_filter: VolatilityFilter | None = None
    ):
        super().__init__("Strategy_B_MarketMaking")

        self._config = config
        self._capital = capital_manager
        self._execution = execution_engine
        self._audit = audit_logger
        self._clob_adapter = clob_adapter
        self._ws_client = websocket_client
        self._market_data = market_data
        self._performance = performance_tracker
        self._volatility = volatility_filter

        # v2.5: Enhanced state tracking
        self._market_states: Dict[str, MarketState] = {}
        self._live_books: dict[str, LiveOrderBook] = {}
        self._pending_orders: list[str] = []

        # v2.5: Dynamic spread configuration
        self._spread_config = {
            'base_spread': 0.02,              # 2% base spread
            'min_spread': 0.005,              # 0.5% minimum spread
            'max_spread': 0.10,               # 10% maximum spread
            'volatility_multiplier': 1.5,     # Spread multiplier for volatile markets
            'inventory_skew_max': 0.005,      # Maximum 0.5% inventory skew
            'imbalance_factor': 0.001,        # Imbalance-based shift
            'reprice_threshold': 0.005        # 0.5% deviation triggers reprice
        }

        # v2.5: Multi-market configuration
        self._market_config = {
            'max_markets': 50,                # Maximum markets to monitor
            'discovery_interval': 30,         # Seconds between market discovery
            'min_volume_24h': 1000,           # Minimum 24h volume in USD
            'min_spread_opportunity': 0.01,   # Minimum spread to be profitable
            'parallel_reconcile': True        # Process markets in parallel
        }

        # v2.5: Performance tracking
        self._total_pnl = 0.0
        self._total_trades = 0
        self._spread_captured = 0.0

        # v2.5: MarketScanner integration (optional)
        self._market_scanner = None

        # Legacy compatibility
        self._active_quotes = {}
        self._positions = {}
    
    def activate(self) -> bool:
        """
        Activate the Market Making strategy.
        Requests capital lock for maximum exposure.
        """
        if not self._config.enabled:
            self._set_error("Strategy disabled in configuration")
            return False
        
        if self._state != StrategyState.INACTIVE:
            return False
        
        self._set_state(StrategyState.ACTIVATING, "ACTIVATING")
        
        max_exposure = self._config.max_exposure
        if not self._capital.lock_for_strategy_b(max_exposure):
            self._set_error("Failed to lock capital for max exposure")
            self._set_state(StrategyState.INACTIVE, "ACTIVATION_FAILED")
            return False
        
        self._locked_capital = max_exposure
        
        self._audit.log_strategy_event(self._name, "ACTIVATION_STARTED", {
            "locked_capital": max_exposure
        })
        
        self._clear_error()
        self._set_state(StrategyState.ACTIVE, "ACTIVE")
        
        self._audit.log_strategy_event(self._name, "ACTIVATED")
        return True
    
    def deactivate(self) -> bool:
        """
        Deactivate the Market Making strategy.
        Cancels all quotes and releases capital.
        """
        if self._state not in [StrategyState.ACTIVE, StrategyState.ERROR]:
            return False
        
        self._set_state(StrategyState.DEACTIVATING, "DEACTIVATING")
        
        for order_id in self._pending_orders:
            self._execution.cancel_order(order_id)
        self._pending_orders.clear()
        
        self._active_quotes.clear()
        
        if self._locked_capital > 0:
            self._capital.release_from_strategy_b(self._locked_capital)
            self._locked_capital = 0.0
        
        self._positions.clear()
        self._active_positions = 0
        
        self._set_state(StrategyState.INACTIVE, "DEACTIVATED")
        self._audit.log_strategy_event(self._name, "DEACTIVATED")

        return True

    # v3.0: Removed duplicate sync process_tick() - only async version below

    def _on_book_update(self, data: dict):
        """Callback for WS updates."""
        token_id = data.get("token_id") or data.get("market")
        if not token_id:
            return
            
        if token_id not in self._live_books:
            self._live_books[token_id] = LiveOrderBook(token_id)
            
        # Parse update
        # Assuming data format matches what we expect from our customized WS client
        # In a real scenario, we parse structure: {bids: [], asks: [], ...}
        # For this 'stub' WS client, we assume it passes raw data.
        # We need to map it.
        
        # Simplified: If 'bids' in data, it's a snapshot or update.
        # This part depends heavily on the specific WS API format.
        # We will wrap in try-catch.
        try:
            timestamp = int(time.time() * 1000)
            if "bids" in data and "asks" in data:
                 # Snapshot or heavy update
                 self._live_books[token_id].apply_snapshot(data["bids"], data["asks"], timestamp)
                 
            if "changes" in data:
                 # Delta
                 for change in data["changes"]:
                     side = change.get("side", "buy").lower()
                     price = float(change.get("price", 0))
                     size = float(change.get("size", 0))
                     self._live_books[token_id].apply_delta(side, price, size)
                     
        except Exception as e:
            # Log verify verbose only if needed
            pass

    async def process_tick(self) -> None:
        """
        v2.5: Enhanced process tick with parallel market processing.
        """
        if self._state != StrategyState.ACTIVE:
            return

        # 1. Market Discovery (v2.5: Use MarketScanner if available, else Gamma API)
        await self._discover_markets()

        if not self._live_books:
            return

        # 2. Reconciliation Loop (v2.5: Parallel processing)
        if self._market_config['parallel_reconcile']:
            await self._parallel_reconcile()
        else:
            await self._sequential_reconcile()

    async def _discover_markets(self) -> None:
        """v3.0: Intelligent market discovery with dynamic interval."""
        now = time.time()
        max_markets = self._market_config['max_markets']

        # v3.0: Faster discovery when MarketScanner is available
        if self._market_scanner:
            interval = min(self._market_config['discovery_interval'], 10)  # Max 10s with scanner
        else:
            interval = self._market_config['discovery_interval']

        if hasattr(self, "_last_discovery") and now - self._last_discovery < interval:
            return

        try:
            target_tokens = []

            # Option 1: Use MarketScanner (preferred)
            if self._market_scanner:
                scored_markets = self._market_scanner.get_top_markets_for_mm(limit=max_markets)
                target_tokens = [m.token_id for m in scored_markets]

            # Option 2: Fallback to Gamma API
            if not target_tokens:
                events = await self._market_data.get_events(limit=50)

                discovered = []
                for event in events:
                    for market in event.get("markets", []):
                        if market.get("active") and market.get("acceptingOrders"):
                            try:
                                tids = market.get("clobTokenIds")
                                volume = float(market.get("volume24hr", 0) or 0)
                                if tids and volume >= self._market_config['min_volume_24h']:
                                    if isinstance(tids, str):
                                        import json
                                        tids = json.loads(tids)
                                    for tid in tids:
                                        discovered.append((tid, volume))
                            except Exception:
                                continue

                # Sort by volume and take top N
                discovered.sort(key=lambda x: x[1], reverse=True)
                target_tokens = [t[0] for t in discovered[:max_markets]]

            # Subscribe to new tokens
            for tid in target_tokens:
                if tid not in self._live_books:
                    await self._ws_client.subscribe_orderbook(tid, self._on_book_update)
                    self._live_books[tid] = LiveOrderBook(tid)
                    self._market_states[tid] = MarketState(token_id=tid)
                    self._audit.log_strategy_event(self._name, "MARKET_SUBSCRIBED", {
                        "token": tid[:16] + "..."
                    })

            self._last_discovery = now
            self._audit.log_strategy_event(self._name, "DISCOVERY_COMPLETE", {
                "markets_active": len(self._live_books),
                "new_subscriptions": len(target_tokens) - len([t for t in target_tokens if t in self._live_books])
            })

        except Exception as e:
            self._audit.log_error("STRATEGY_B_DISCOVERY_ERROR", str(e))

    async def _parallel_reconcile(self) -> None:
        """v2.5: Process all markets in parallel for speed."""
        tasks = []

        for market_id, book in list(self._live_books.items()):
            try:
                snapshot = book.get_snapshot()
                if snapshot and snapshot.midpoint > 0:
                    tasks.append(self._reconcile_market(market_id, snapshot))
            except Exception:
                continue

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Log any errors
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    self._audit.log_error("PARALLEL_RECONCILE_ERROR", str(result))

    async def _sequential_reconcile(self) -> None:
        """Sequential reconciliation (fallback)."""
        for market_id, book in list(self._live_books.items()):
            try:
                snapshot = book.get_snapshot()
                if not snapshot or snapshot.midpoint == 0:
                    continue

                await self._reconcile_market(market_id, snapshot)
            except Exception as e:
                self._audit.log_error("STRATEGY_B_RECONCILE_ERROR", str(e))

    async def _reconcile_market(self, market_id: str, book: Any):
        """
        v2.5: Enhanced reconciliation with dynamic spread calculation.
        """
        mid = book.midpoint
        cfg = self._spread_config

        # Get or create market state
        if market_id not in self._market_states:
            self._market_states[market_id] = MarketState(token_id=market_id)
        state = self._market_states[market_id]

        # 1. Calculate Dynamic Spread
        bids = book.bids[:5]
        asks = book.asks[:5]

        bid_vol = sum(float(b[1]) for b in bids)
        ask_vol = sum(float(a[1]) for a in asks)
        total_vol = bid_vol + ask_vol

        # Orderbook imbalance
        imbalance = (bid_vol - ask_vol) / total_vol if total_vol > 0 else 0

        # v3.0: Update volatility score from VolatilityFilter
        if self._volatility:
            if hasattr(self._volatility, 'get_score'):
                state.volatility_score = self._volatility.get_score(market_id)
            elif hasattr(self._volatility, 'is_safe'):
                # Fallback: binary 0 or 0.5 based on safety
                state.volatility_score = 0.0 if self._volatility.is_safe(market_id) else 0.5

        # v2.5: Calculate volatility-adjusted spread
        volatility_factor = 1.0
        if self._volatility:
            volatility_factor = 1.0 + (state.volatility_score * (cfg['volatility_multiplier'] - 1.0))

        # Dynamic spread calculation
        base_spread = max(cfg['base_spread'], cfg['min_spread'])
        dynamic_spread = base_spread * volatility_factor
        dynamic_spread = min(max(dynamic_spread, cfg['min_spread']), cfg['max_spread'])

        state.current_spread = dynamic_spread

        # 2. Inventory Skew
        pos = state.position
        inventory_ratio = pos / self._config.max_exposure if self._config.max_exposure > 0 else 0
        skew_bps = inventory_ratio * cfg['inventory_skew_max']
        inventory_shift = -skew_bps * mid

        # 3. Imbalance-based price shift
        shift_factor = imbalance * cfg['imbalance_factor']

        # 4. Calculate final prices
        buy_price = mid * (1 - dynamic_spread / 2 + shift_factor) + inventory_shift
        sell_price = mid * (1 + dynamic_spread / 2 + shift_factor) + inventory_shift

        # Ensure prices are within valid range [0.01, 0.99]
        buy_price = max(0.01, min(0.99, round(buy_price, 4)))
        sell_price = max(0.01, min(0.99, round(sell_price, 4)))

        # 5. Reconcile both sides
        await self._reconcile_side(market_id, "BUY", buy_price, book, state)
        await self._reconcile_side(market_id, "SELL", sell_price, book, state)

        state.last_update = time.time()
        
    def on_order_fill(self, market_id: str, side: str, size: float, price: float):
        """Update internal position on fill."""
        current = self._positions.get(market_id, 0.0)
        if side.upper() == "BUY":
            self._positions[market_id] = current + size
        else:
            self._positions[market_id] = current - size
        
        self._audit.log_strategy_event(self._name, "POSITION_UPDATE", {
            "market": market_id,
            "new_pos": self._positions[market_id]
        })
        
    async def _reconcile_side(self, market_id: str, side: str, desired_price: float, book: Any, state: MarketState):
        """
        v2.5: Enhanced reconciliation with state tracking.
        """
        cfg = self._spread_config
        reprice_threshold = cfg['reprice_threshold']

        # Get current order info from state
        current_order_id = state.buy_order_id if side == "BUY" else state.sell_order_id
        current_price = state.buy_price if side == "BUY" else state.sell_price

        needs_new = False

        if current_order_id:
            # Check deviation
            if current_price > 0:
                deviation = abs(desired_price - current_price) / current_price
                if deviation > reprice_threshold:
                    self._execution.cancel_order(current_order_id)
                    needs_new = True
            else:
                needs_new = True
        else:
            needs_new = True

        if not needs_new:
            return

        # Calculate size
        trade_size_usd = self._locked_capital * (self._config.trade_size_percent / 100.0)
        max_size = self._clob_adapter.max_executable_size(book, side, slippage_pct=0.5)
        final_size = min(trade_size_usd, max_size)

        if final_size < 1.0:
            return

        # Submit new order
        new_id = self._execution.submit_order(
            strategy=self._name,
            order_type="GTC",
            params={
                "token_id": market_id,
                "price": str(desired_price),
                "size": str(final_size),
                "side": side
            }
        )

        if new_id:
            # Update state
            if side == "BUY":
                state.buy_order_id = new_id
                state.buy_price = desired_price
            else:
                state.sell_order_id = new_id
                state.sell_price = desired_price

            # Legacy compatibility
            if market_id not in self._active_quotes:
                self._active_quotes[market_id] = {}
            self._active_quotes[market_id][f"{side}_order_id"] = new_id
            self._active_quotes[market_id][f"{side}_price"] = desired_price

            self._active_positions = len(self._market_states)
            self._last_action = f"QUOTE: {side} @{desired_price:.4f}"
            self._notify_status()

    def abort(self) -> None:
        """
        Emergency abort.
        Cancel all quotes and release capital immediately.
        """
        self._audit.log_strategy_event(self._name, "ABORT_INITIATED")
        
        # 1. Cancel tracked orders
        for info in self._active_quotes.values():
            if "BUY_order_id" in info:
                self._execution.cancel_order(info["BUY_order_id"])
            if "SELL_order_id" in info:
                 self._execution.cancel_order(info["SELL_order_id"])
                 
        for order_id in self._pending_orders:
            self._execution.cancel_order(order_id)
        self._pending_orders.clear()
        
        self._active_quotes.clear()
        
        if self._locked_capital > 0:
            self._capital.release_all_strategy_b()
            self._locked_capital = 0.0
        
        self._positions.clear()
        
        self._set_state(StrategyState.INACTIVE, "ABORTED")
        self._audit.log_strategy_event(self._name, "ABORTED")
    
    @property
    def live_orderbook_snapshots(self) -> dict[str, dict]:
        """Get live snapshots of all tracked orderbooks (Thread-safe copy)."""
        snapshots = {}
        # Use list() to iterate over a copy of items to avoid RuntimeError if changed during iteration
        for market_id, book in list(self._live_books.items()):
            snap = book.get_snapshot()
            if snap:
                snapshots[market_id] = {
                    "bids": snap.bids[:10],
                    "asks": snap.asks[:10],
                    "midpoint": snap.midpoint,
                    "spread_pct": snap.spread_percent
                }
        return snapshots

    def _check_exposure(self) -> float:
        """Calculate current position exposure."""
        return sum(abs(pos) for pos in self._positions.values())
    
    @property
    def active_quote_count(self) -> int:
        """Number of active quote pairs."""
        return len(self._active_quotes)
    
    @property
    def current_exposure(self) -> float:
        """Current position exposure."""
        return self._check_exposure()
    
    def set_ws_client(self, client: WebSocketClient):
        self._ws_client = client

    # ============= v2.5: Configuration & Statistics =============

    def set_market_scanner(self, scanner) -> None:
        """Set the MarketScanner for intelligent market selection."""
        self._market_scanner = scanner
        self._audit.log_strategy_event(self._name, "MARKET_SCANNER_SET")

    def configure_spread(self, config: dict) -> None:
        """Update dynamic spread configuration."""
        for key in config:
            if key in self._spread_config:
                self._spread_config[key] = config[key]
        self._audit.log_strategy_event(self._name, "SPREAD_CONFIG_UPDATED", self._spread_config)

    def configure_markets(self, config: dict) -> None:
        """Update market configuration."""
        for key in config:
            if key in self._market_config:
                self._market_config[key] = config[key]
        self._audit.log_strategy_event(self._name, "MARKET_CONFIG_UPDATED", self._market_config)

    @property
    def performance_stats(self) -> dict:
        """Get strategy performance statistics."""
        active_markets = len([s for s in self._market_states.values() if s.buy_order_id or s.sell_order_id])
        total_position = sum(s.position for s in self._market_states.values())
        total_realized = sum(s.realized_pnl for s in self._market_states.values())

        return {
            'active_markets': active_markets,
            'total_markets_tracked': len(self._market_states),
            'total_trades': self._total_trades,
            'total_pnl': round(total_realized + self._total_pnl, 4),
            'spread_captured': round(self._spread_captured, 4),
            'total_position': round(total_position, 4),
            'avg_spread': round(
                sum(s.current_spread for s in self._market_states.values()) / len(self._market_states)
                if self._market_states else 0, 4
            )
        }

    @property
    def spread_config(self) -> dict:
        """Get current spread configuration."""
        return self._spread_config.copy()

    @property
    def market_config(self) -> dict:
        """Get current market configuration."""
        return self._market_config.copy()

    def get_market_state(self, token_id: str) -> Optional[dict]:
        """Get state for a specific market."""
        state = self._market_states.get(token_id)
        if not state:
            return None

        return {
            'token_id': state.token_id,
            'buy_price': state.buy_price,
            'sell_price': state.sell_price,
            'position': state.position,
            'realized_pnl': state.realized_pnl,
            'trades_count': state.trades_count,
            'current_spread': state.current_spread,
            'last_update': state.last_update
        }

    def get_all_market_states(self) -> List[dict]:
        """Get state for all markets."""
        return [self.get_market_state(tid) for tid in self._market_states.keys()]

    def get_active_spreads(self) -> dict:
        """Get current spreads for all active markets."""
        return {
            tid: {
                'buy': state.buy_price,
                'sell': state.sell_price,
                'spread': state.current_spread,
                'position': state.position
            }
            for tid, state in self._market_states.items()
            if state.buy_price > 0 or state.sell_price > 0
        }
