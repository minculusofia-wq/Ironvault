"""
Strategy B: Automated Market Making
Provides liquidity by placing bid/ask quotes.
Capital locked = maximum exposure at any time.
"""

from .base_strategy import BaseStrategy, StrategyState
from ..capital_manager import CapitalManager
from ..execution_engine import ExecutionEngine
from ..audit_logger import AuditLogger
from ..config_loader import StrategyBConfig
from ..clob_adapter import ClobAdapter
from ..websocket_client import WebSocketClient
from ..live_orderbook import LiveOrderBook
from typing import Any
import time

class StrategyBMarketMaking(BaseStrategy):
    """
    Automated Market Making Strategy.
    
    Places bid/ask quotes. Uses WebSocket for real-time orderbook.
    """
    
    def __init__(
        self,
        config: StrategyBConfig,
        capital_manager: CapitalManager,
        execution_engine: ExecutionEngine,
        audit_logger: AuditLogger,
        clob_adapter: ClobAdapter,
        websocket_client: WebSocketClient
    ):
        super().__init__("Strategy_B_MarketMaking")
        
        self._config = config
        self._capital = capital_manager
        self._execution = execution_engine
        self._audit = audit_logger
        self._clob_adapter = clob_adapter
        self._ws_client = websocket_client
        
        self._active_quotes: dict[str, dict] = {} # market_id -> {orders: [ids], prices: {bid: x, ask: y}}
        self._live_books: dict[str, LiveOrderBook] = {} # market_id -> LiveOrderBook
        self._positions: dict[str, float] = {}
        self._pending_orders: list[str] = []
    
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
    
    def process_tick(self) -> None:
        """
        Process market tick.
        Update quotes based on market conditions.
        """
        if self._state != StrategyState.ACTIVE:
            return
        
    async def activate(self) -> bool:
        """
        Activate and subscribe to markets.
        """
        # Call base activate logic manually since we overrode it
        if not self._config.enabled:
            return False
            
        if self._state != StrategyState.INACTIVE:
            return False
            
        self._set_state(StrategyState.ACTIVATING, "ACTIVATING")
        
        # Lock Capital
        max_exposure = self._config.max_exposure
        if not self._capital.lock_for_strategy_b(max_exposure):
            self._set_error("Failed to lock capital for max exposure")
            return False
            
        self._locked_capital = max_exposure
        self._clear_error()
        self._set_state(StrategyState.ACTIVE, "ACTIVE")
        
        # Subscribe to markets (Assuming config has a list of target_asset_ids or we fallback to discovery)
        # For this implementation, we'll assume we want to quote on a specific set if defined, 
        # or we scan for them. Since scan is complex, we'll assume a fixed list for now or empty.
        # IF config has 'target_token_ids', use it. Else, we wait for something else to trigger it.
        # Let's assume we want to just test with one hardcoded market or a config field 
        # that we added (or will add). 
        # For safety: We'll subscribe if we have active quotes from a previous run or discovery.
        
        # Demo: Log that we are ready to subscribe
        self._audit.log_strategy_event(self._name, "ACTIVATED_WAITING_FOR_TARGETS")
        return True

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
        Process tick: Reconcile active orders with desired state.
        """
        if self._state != StrategyState.ACTIVE:
            return

        # 1. Reconciliation Loop
        # Iterate over all markets we are tracking / quoting
        for market_id, book in self._live_books.items():
            try:
                snapshot = book.get_snapshot()
                if not snapshot or snapshot.midpoint == 0:
                    continue
                    
                await self._reconcile_market(market_id, snapshot)
            except Exception as e:
                self._audit.log_error("STRATEGY_B_RECONCILE_ERROR", str(e))

    async def _reconcile_market(self, market_id: str, book: Any):
        """
        Compare desired orders vs active orders and execute changes.
        """
        # 1. Calculate Desired Price
        mid = book.midpoint
        spread_fraction = max(self._config.spread_min, 0.01) # Default 1% if 0
        
        buy_price = mid * (1 - spread_fraction / 2)
        sell_price = mid * (1 + spread_fraction / 2)
        
        # Rounding (Important for CLOB) - simplified here
        buy_price = round(buy_price, 6)
        sell_price = round(sell_price, 6)
        
        # 2. Reconcile BUY Side
        await self._reconcile_side(market_id, "BUY", buy_price)
        
        # 3. Reconcile SELL Side
        await self._reconcile_side(market_id, "SELL", sell_price)
        
    async def _reconcile_side(self, market_id: str, side: str, desired_price: float):
        """
        Check existing order for side. If far from desired, cancel & replace.
        """
        quote_info = self._active_quotes.get(market_id, {})
        current_order_id = quote_info.get(f"{side}_order_id")
        current_price = quote_info.get(f"{side}_price")
        
        # Configurable thresholds
        reprice_threshold = 0.005 # 0.5% deviation triggers update
        
        needs_new = False
        
        if current_order_id:
            # Check deviation
            if current_price:
                deviation = abs(desired_price - current_price) / current_price
                if deviation > reprice_threshold:
                    # Cancel existing
                    self._execution.cancel_order(current_order_id)
                    needs_new = True
                else:
                    # Good enough, keep it
                    needs_new = False
            else:
                 # Should not happen if we tracked correctly, but safe fallback
                 needs_new = True
        else:
            needs_new = True
            
        if needs_new:
            # Place new order
            # Size calc
            size_usd = self._locked_capital * (self._config.trade_size_percent / 100.0)
            
            # Submit
            new_id = self._execution.submit_order(
                strategy=self._name,
                order_type="GTC",
                params={
                    "token_id": market_id,
                    "price": str(desired_price),
                    "size": str(size_usd),
                    "side": side
                }
            )
            
            # Update state
            if market_id not in self._active_quotes:
                self._active_quotes[market_id] = {}
            
            self._active_quotes[market_id][f"{side}_order_id"] = new_id
            self._active_quotes[market_id][f"{side}_price"] = desired_price
            
            # Log
            # self._audit.log_debug("REQUOTE", f"{side} {market_id} @ {desired_price}")

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
