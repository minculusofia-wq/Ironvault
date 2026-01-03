"""
Strategy A: Scoreboard/Fast-Data Front-Running
Reacts to external data triggers to place orders before market adjustment.
"""

import asyncio
import time
from typing import Optional
from .base_strategy import BaseStrategy, StrategyState
from ..capital_manager import CapitalManager
from ..execution_engine import ExecutionEngine
from ..audit_logger import AuditLogger
from ..config_loader import StrategyAConfig
from ..clob_adapter import ClobAdapter
from ..scoreboard_monitor import ScoreboardTrigger, ScoreboardMonitor
from ..volatility_filter import VolatilityFilter

class StrategyAFrontRunning(BaseStrategy):
    """
    Scoreboard Front-Running Strategy.
    
    Listens to ScoreboardMonitor for ultra-fast triggers.
    Executes aggressive market orders (Taker) on the target outcome.
    """
    
    def __init__(
        self,
        config: StrategyAConfig,
        capital_manager: CapitalManager,
        execution_engine: ExecutionEngine,
        audit_logger: AuditLogger,
        clob_adapter: ClobAdapter,
        scoreboard_monitor: ScoreboardMonitor,
        volatility_filter: VolatilityFilter | None = None
    ):
        super().__init__("Strategy_A_FrontRunning")
        
        self._config = config
        self._capital = capital_manager
        self._execution = execution_engine
        self._audit = audit_logger
        self._clob_adapter = clob_adapter
        self._scoreboard = scoreboard_monitor
        self._volatility = volatility_filter
        
        self._active_positions_map: dict[str, dict] = {} # token_id -> {entry_time, price, size}
        self._pending_triggers: asyncio.Queue = asyncio.Queue()
        
        # Register for triggers
        self._scoreboard.subscribe(self.on_scoreboard_trigger)

    def activate(self) -> bool:
        """Activate the strategy and lock initial capital."""
        if not self._config.enabled:
            return False
        
        if self._state != StrategyState.INACTIVE:
            return False
            
        self._set_state(StrategyState.ACTIVATING, "ACTIVATING")
        
        # Lock max allocation for visibility
        max_alloc = self._capital.max_a
        if self._capital.lock_for_strategy_a(max_alloc):
            self._locked_capital = max_alloc
            
        self._set_state(StrategyState.ACTIVE, "ACTIVE")
        self._audit.log_strategy_event(self._name, "ACTIVATED_FRONT_RUNNING")
        return True

    def deactivate(self) -> bool:
        """Deactivate and release capital."""
        if self._state not in [StrategyState.ACTIVE, StrategyState.ERROR]:
            return False
            
        self._set_state(StrategyState.DEACTIVATING, "DEACTIVATING")
        
        if self._locked_capital > 0:
            self._capital.release_from_strategy_a(self._locked_capital)
            self._locked_capital = 0.0
            
        self._active_positions_map.clear()
        self._set_state(StrategyState.INACTIVE, "DEACTIVATED")
        return True

    async def on_scoreboard_trigger(self, trigger: ScoreboardTrigger):
        """Callback from ScoreboardMonitor."""
        if self._state != StrategyState.ACTIVE:
            return
            
        # Put into queue to process in main tick loop (to maintain order and thread-safety)
        await self._pending_triggers.put(trigger)
        self._audit.log_strategy_event(self._name, "TRIGGER_QUEUED", {"type": trigger.trigger_type})

    async def process_tick(self) -> None:
        """Process pending triggers and manage active positions."""
        if self._state != StrategyState.ACTIVE:
            return
            
        # 1. Process New Triggers
        while not self._pending_triggers.empty():
            trigger = await self._pending_triggers.get()
            await self._execute_front_run(trigger)
            
        # 2. Manage Time-Based Exits (v2.5 Auto-Exit window)
        await self._manage_exits()

    async def _execute_front_run(self, trigger: ScoreboardTrigger):
        """Execute a trade based on a scoreboard trigger."""
        token_id = trigger.token_id
        
        # Check if we already have a position
        if token_id in self._active_positions_map:
            return

        # 1. Liquidity & Volatility Check
        book = await self._clob_adapter.get_orderbook(token_id)
        if not book: return
        
        if self._volatility and not self._volatility.is_safe(token_id):
            self._audit.log_strategy_event(self._name, "SKIP_VOLATILE", {"token": token_id})
            return

        # 2. Execution Decision
        # For front-running, we ALWAYS take liquidity (Aggressive)
        price = book.best_ask # We are buying
        
        # Calculate size based on config % of locked capital
        trade_size_usd = self._locked_capital * (self._config.trade_size_percent / 100.0)
        
        # Verify slippage isn't too high already
        max_size = self._clob_adapter.max_executable_size(book, "BUY", slippage_pct=1.0)
        final_size = min(trade_size_usd, max_size)
        
        if final_size < 1.0:
            self._audit.log_strategy_event(self._name, "SKIP_INSUFFICIENT_LIQUIDITY", {"token": token_id})
            return

        # 3. Submit Market/FOK Order
        order_id = self._execution.submit_order(
            strategy=self._name,
            order_type="FOK", # Fill Or Kill for speed
            params={
                "token_id": token_id,
                "price": str(price),
                "size": str(final_size),
                "side": "BUY"
            }
        )
        
        if order_id:
            self._active_positions_map[token_id] = {
                "entry_time": time.time(),
                "price": price,
                "size": final_size,
                "order_id": order_id
            }
            self._active_positions = len(self._active_positions_map)
            self._last_action = f"FRONT-RUN: {trigger.trigger_type}"
            self._notify_status()

    async def _manage_exits(self):
        """Exit positions after price adjustment or timeout."""
        now = time.time()
        exit_window = 60 # Default 60 seconds for scoreboard reaction
        
        tokens_to_exit = []
        for tid, pos in self._active_positions_map.items():
            if now - pos["entry_time"] > exit_window:
                tokens_to_exit.append(tid)
                
        for tid in tokens_to_exit:
            await self._exit_position(tid)

    async def _exit_position(self, token_id: str):
        """Exit a specific position."""
        pos = self._active_positions_map.get(token_id)
        if not pos: return
        
        book = await self._clob_adapter.get_orderbook(token_id)
        if not book: return
        
        # Aggressive exit (Take the Bid)
        exit_price = book.best_bid
        
        order_id = self._execution.submit_order(
            strategy=self._name,
            order_type="FOK",
            params={
                "token_id": token_id,
                "price": str(exit_price),
                "size": str(pos["size"]),
                "side": "SELL"
            }
        )
        
        if order_id:
            del self._active_positions_map[token_id]
            self._active_positions = len(self._active_positions_map)
            self._last_action = "EXIT_COMPLETE"
            self._notify_status()

    def abort(self) -> None:
        """Emergency cleanup."""
        for tid in list(self._active_positions_map.keys()):
            # Emergency exit is just clearing state for now, 
            # ideally would send Market Sell orders but abort is immediate.
            pass
        self._active_positions_map.clear()
        self._active_positions = 0
        self._set_state(StrategyState.INACTIVE, "ABORTED")
