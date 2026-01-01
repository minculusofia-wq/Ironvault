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

class StrategyBMarketMaking(BaseStrategy):
    """
    Automated Market Making Strategy.
    
    Places bid and ask quotes to earn spread.
    Capital is locked for maximum exposure.
    Released only on position exit or abort.
    """
    
    def __init__(
        self,
        config: StrategyBConfig,
        capital_manager: CapitalManager,
        execution_engine: ExecutionEngine,
        audit_logger: AuditLogger,
        clob_adapter: ClobAdapter
    ):
        super().__init__("Strategy_B_MarketMaking")
        
        self._config = config
        self._capital = capital_manager
        self._execution = execution_engine
        self._audit = audit_logger
        self._clob_adapter = clob_adapter
        
        self._active_quotes: dict[str, dict] = {}
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
        
    def process_tick(self) -> None:
        """
        Process market tick.
        Update quotes based on market conditions using CLOB analysis.
        """
        if self._state != StrategyState.ACTIVE:
            return
            
        # Example: Iterate over active markets (or config targets)
        # For demo, we assume we are quoting on markets in _active_quotes keys
        # If empty, we might want to scan or just return
        if not self._active_quotes:
            return

        for market_id in list(self._active_quotes.keys()):
            try:
                # 1. Analyze via CLOB Adapter
                book = self._clob_adapter.get_orderbook(market_id)
                if not book:
                    continue
                    
                # 2. Calculate Pricing
                mid = book.midpoint
                if mid == 0:
                    continue
                    
                # Optimal Maker Prices (Passive)
                # We use suggest_limit_price or manual calculation relative to mid
                # Using adapter's suggestion for Maker side (joining best bid/ask)
                buy_price = self._clob_adapter.suggest_limit_price(book, "BUY", aggressive=False)
                sell_price = self._clob_adapter.suggest_limit_price(book, "SELL", aggressive=False)
                
                # Apply spread config constraints
                spread = (sell_price - buy_price)
                if spread < (mid * self._config.spread_min):
                     # Widen quotes to meet min spread
                     buy_price = mid * (1 - self._config.spread_min/2)
                     sell_price = mid * (1 + self._config.spread_min/2)

                # 3. Update State (and in real bot, submit updates to ExecutionEngine)
                self._active_quotes[market_id] = {
                    "bid": buy_price,
                    "ask": sell_price,
                    "mid": mid,
                    "last_update": book.timestamp
                }
                
                # EXECUTE LIVE QUOTES
                # 1. Cancel existing (Simple cleanup for demo) - Real MM does modify
                # For this version, we place new orders. Real engine should handle better.
                # Calculating Size: 1% of exposure pool
                exposure_pool = self._locked_capital
                size_usd = exposure_pool * (self._config.trade_size_percent / 100.0)
                
                # Submit Buy Quote (Maker)
                self._execution.submit_order(
                     strategy=self._name,
                     order_type="GTC", # Maker order
                     params={
                         "token_id": market_id,
                         "price": str(buy_price),
                         "size": str(size_usd),
                         "side": "BUY"
                     }
                )
                
                # Submit Sell Quote (Maker)
                self._execution.submit_order(
                     strategy=self._name,
                     order_type="GTC",
                     params={
                         "token_id": market_id,
                         "price": str(sell_price),
                         "size": str(size_usd),
                         "side": "SELL"
                     }
                )
                
            except Exception as e:
                self._audit.log_error("STRATEGY_B_ERROR", f"Error processing market {market_id}: {e}")
    
    def abort(self) -> None:
        """
        Emergency abort.
        Cancel all quotes and release capital immediately.
        """
        self._audit.log_strategy_event(self._name, "ABORT_INITIATED")
        
        for order_id in self._pending_orders:
            self._execution.cancel_order(order_id)
        self._pending_orders.clear()
        
        self._active_quotes.clear()
        
        if self._locked_capital > 0:
            self._capital.release_all_strategy_b()
            self._locked_capital = 0.0
        
        self._positions.clear()
        self._active_positions = 0
        
        self._set_state(StrategyState.INACTIVE, "ABORTED")
        self._audit.log_strategy_event(self._name, "ABORTED")
    
    def _update_quotes(self, market_id: str, mid_price: float) -> None:
        """Update bid/ask quotes for a market."""
        spread = (self._config.spread_min + self._config.spread_max) / 2
        bid_price = mid_price * (1 - spread / 2)
        ask_price = mid_price * (1 + spread / 2)
        
        self._active_quotes[market_id] = {
            "bid": bid_price,
            "ask": ask_price,
            "mid": mid_price
        }
    
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
