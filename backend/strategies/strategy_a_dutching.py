"""
Strategy A: Multi-Outcome Dutching
Places bets across multiple outcomes to guarantee profit regardless of result.
Capital locked = sum of all outcome stakes.
"""

from .base_strategy import BaseStrategy, StrategyState
from ..capital_manager import CapitalManager
from ..execution_engine import ExecutionEngine
from ..audit_logger import AuditLogger
from ..config_loader import StrategyAConfig
from ..market_data import GammaClient
from ..clob_adapter import ClobAdapter

class StrategyADutching(BaseStrategy):
    """
    Multi-Outcome Dutching Strategy.
    
    Distributes stakes across outcomes to guarantee profit.
    Capital is locked for the sum of all stakes.
    Released only on event settlement or abort.
    """
    
    def __init__(
        self,
        config: StrategyAConfig,
        capital_manager: CapitalManager,
        execution_engine: ExecutionEngine,
        audit_logger: AuditLogger,
        market_data: GammaClient,
        clob_adapter: ClobAdapter
    ):
        super().__init__("Strategy_A_Dutching")
        
        self._config = config
        self._capital = capital_manager
        self._execution = execution_engine
        self._audit = audit_logger
        self._market_data = market_data
        self._clob_adapter = clob_adapter
        
        self._active_events: list[dict] = []
        self._pending_orders: list[str] = []
    
    def activate(self) -> bool:
        """
        Activate the Dutching strategy.
        Requests minimum capital lock to begin scanning.
        """
        if not self._config.enabled:
            self._set_error("Strategy disabled in configuration")
            return False
        
        if self._state != StrategyState.INACTIVE:
            return False
        
        self._set_state(StrategyState.ACTIVATING, "ACTIVATING")
        
        self._audit.log_strategy_event(self._name, "ACTIVATION_STARTED")
        
        self._clear_error()
        self._set_state(StrategyState.ACTIVE, "ACTIVE")
        
        self._audit.log_strategy_event(self._name, "ACTIVATED")
        return True
    
    def deactivate(self) -> bool:
        """
        Deactivate the Dutching strategy.
        Releases all locked capital.
        """
        if self._state not in [StrategyState.ACTIVE, StrategyState.ERROR]:
            return False
        
        self._set_state(StrategyState.DEACTIVATING, "DEACTIVATING")
        
        for order_id in self._pending_orders:
            self._execution.cancel_order(order_id)
        self._pending_orders.clear()
        
        if self._locked_capital > 0:
            self._capital.release_from_strategy_a(self._locked_capital)
            self._locked_capital = 0.0
        
        self._active_events.clear()
        self._active_positions = 0
        
        self._set_state(StrategyState.INACTIVE, "DEACTIVATED")
        self._audit.log_strategy_event(self._name, "DEACTIVATED")
        
        return True
    
    def process_tick(self) -> None:
        """
        Process market tick.
        Scan for dutching opportunities using Gamma and CLOB adapter.
        """
        if self._state != StrategyState.ACTIVE:
            return
        
        # Max events check
        if len(self._active_events) >= self._config.max_events:
            return
        
        try:
            # 1. Scan for Events via Gamma API
            events = self._market_data.get_events(limit=5)
            
            for event in events:
                # Basic filter
                if not self._is_valid_event(event):
                    continue
                    
                # 2. Analyze Order Book for each Market in Event
                markets = event.get('markets', [])
                for market in markets:
                     token_id = market.get('id') # or condition_id depending on structure
                     # Polymarket Gamma API returns specific structure, simplifying for this step
                     # Assuming market['id'] is usable token_id for CLOB (often need mapping condition_id -> token_id)
                     # For this implementation we assume market['token_id'] exists or is derivable.
                     # If not, would need lookup. Using market['clobTokenIds'][0] if available or similar.
                     
                     # Simple logic: if we find a book, check liquidity
                     if token_id:
                        book = self._clob_adapter.get_orderbook(token_id)
                        if book:
                             # 3. Check Liquidity / Spread
                             # Calculate sizing based on available capital and config %
                             available_cap = self._capital.get_available_capital()
                             trade_size_usd = available_cap * (self._config.trade_size_percent / 100.0)
                             
                             # Cap size at max_executable (1% slippage)
                             max_size_no_slip = self._clob_adapter.max_executable_size(book, "BUY", slippage_pct=1.0)
                             
                             # Final size is min of config size and safe liquidity size
                             final_size = min(trade_size_usd, max_size_no_slip)
                             
                             # Ensure size is above min threshold (e.g. 5 USD)
                             if final_size < 5.0:
                                 continue

                             if self._clob_adapter.is_executable(book, "BUY", final_size, max_spread_pct=5.0):
                                 self._audit.log_strategy_event(self._name, "OPPORTUNITY_FOUND", {
                                     "token": token_id,
                                     "size": final_size
                                 })
                                 
                                 # 4. EXECUTE LIVE ORDER
                                 # We are buying, so we cross the spread (Taker)
                                 # Price = Best Ask
                                 price = book.best_ask
                                 
                                 order_id = self._execution.submit_order(
                                     strategy=self._name,
                                     order_type="FOK", # Fill or Kill for safety
                                     params={
                                         "token_id": token_id,
                                         "price": str(price),
                                         "size": str(final_size),
                                         "side": "BUY"
                                     }
                                 )
                                 
                                 if order_id:
                                     self._pending_orders.append(order_id)
                                     self._audit.log_strategy_event(self._name, "ORDER_SUBMITTED", {"id": order_id})
                                 
        except Exception as e:
            self._audit.log_error("STRATEGY_A_ERROR", f"Error in process_tick: {e}")

    def _is_valid_event(self, event: dict) -> bool:
        """Helper to filter events."""
        # Check volume, etc.
        volume = float(event.get('volume_24h', 0))
        return volume > 1000 # Configurable threshold
    
    def abort(self) -> None:
        """
        Emergency abort.
        Cancel all orders and release capital immediately.
        """
        self._audit.log_strategy_event(self._name, "ABORT_INITIATED")
        
        for order_id in self._pending_orders:
            self._execution.cancel_order(order_id)
        self._pending_orders.clear()
        
        if self._locked_capital > 0:
            self._capital.release_all_strategy_a()
            self._locked_capital = 0.0
        
        self._active_events.clear()
        self._active_positions = 0
        
        self._set_state(StrategyState.INACTIVE, "ABORTED")
        self._audit.log_strategy_event(self._name, "ABORTED")
    
    def _lock_capital_for_event(self, total_stake: float) -> bool:
        """Attempt to lock capital for a new event."""
        if self._capital.lock_for_strategy_a(total_stake):
            self._locked_capital += total_stake
            self._notify_status()
            return True
        return False
    
    def _release_capital_for_event(self, amount: float) -> None:
        """Release capital after event settlement."""
        if amount > 0 and amount <= self._locked_capital:
            self._capital.release_from_strategy_a(amount)
            self._locked_capital -= amount
            self._notify_status()
    
    @property
    def active_event_count(self) -> int:
        """Number of active events."""
        return len(self._active_events)
