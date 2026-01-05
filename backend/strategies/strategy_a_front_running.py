"""
Strategy A: Scoreboard/Fast-Data Front-Running
Reacts to external data triggers to place orders before market adjustment.

v2.5 Optimizations:
- Dynamic exit strategy (profit target, stop-loss, trailing stop)
- Integration with data feeds (PolymarketPriceMonitor)
- Concurrent orderbook fetching
- Position PnL tracking
"""

import asyncio
import time
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from .base_strategy import BaseStrategy, StrategyState
from ..capital_manager import CapitalManager
from ..execution_engine import ExecutionEngine
from ..audit_logger import AuditLogger
from ..config_loader import StrategyAConfig
from ..clob_adapter import ClobAdapter, MarketSnapshot
from ..scoreboard_monitor import ScoreboardTrigger, ScoreboardMonitor
from ..volatility_filter import VolatilityFilter


@dataclass
class ActivePosition:
    """Enhanced position tracking with dynamic exit info."""
    token_id: str
    entry_time: float
    entry_price: float
    size: float
    order_id: str
    trigger_type: str

    # Dynamic exit tracking
    highest_price: float  # For trailing stop
    lowest_price: float
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_pct: float

    # Exit flags
    profit_target_hit: bool = False
    stop_loss_hit: bool = False
    trailing_stop_hit: bool = False
    timeout_hit: bool = False

class StrategyAFrontRunning(BaseStrategy):
    """
    Scoreboard Front-Running Strategy.

    Listens to ScoreboardMonitor for ultra-fast triggers.
    Executes aggressive market orders (Taker) on the target outcome.

    v2.5: Enhanced with dynamic exits and data feed integration.
    """

    def __init__(
        self,
        config: StrategyAConfig,
        capital_manager: CapitalManager,
        execution_engine: ExecutionEngine,
        audit_logger: AuditLogger,
        clob_adapter: ClobAdapter,
        scoreboard_monitor: ScoreboardMonitor,
        volatility_filter: VolatilityFilter | None = None,
        data_feed = None
    ):
        super().__init__("Strategy_A_FrontRunning")

        self._config = config
        self._capital = capital_manager
        self._execution = execution_engine
        self._audit = audit_logger
        self._clob_adapter = clob_adapter
        self._scoreboard = scoreboard_monitor
        self._volatility = volatility_filter

        # v2.5: Enhanced position tracking
        self._positions: Dict[str, ActivePosition] = {}
        self._pending_triggers: asyncio.Queue = asyncio.Queue()

        # v3.0: Position locks to prevent race conditions on entry
        self._position_locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()  # For lock dictionary access

        # v3.0: Trigger deduplication cache
        self._last_trigger_time: Dict[str, float] = {}
        self._trigger_cooldown = getattr(config, 'trigger_cooldown_seconds', 5.0)

        # v3.0: Orderbook cache for reduced API calls
        self._book_cache: Dict[str, tuple] = {}  # token_id -> (timestamp, snapshot)
        self._book_cache_ttl = getattr(config, 'orderbook_cache_ttl_ms', 150) / 1000.0

        # v2.5: Dynamic exit configuration
        self._exit_config = getattr(config, 'exit_config', None) or {
            'profit_target_pct': 2.0,      # Exit at +2% profit
            'stop_loss_pct': 1.0,          # Exit at -1% loss
            'trailing_stop_pct': 0.5,      # Trail by 0.5% from high
            'max_hold_seconds': 120,       # Maximum 2 minutes hold
            'min_hold_seconds': 5,         # Minimum 5 seconds before exit
            'exit_mode': 'dynamic'         # 'dynamic', 'fixed', or 'hybrid'
        }

        # v2.5: Performance tracking
        self._total_trades = 0
        self._winning_trades = 0
        self._total_pnl = 0.0

        # v2.5: Data feed integration (optional)
        self._price_monitor = data_feed

        # Register for triggers
        self._scoreboard.subscribe(self.on_scoreboard_trigger)

        # Legacy compatibility
        self._active_positions_map = self._positions

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

        # v3.0: Trigger deduplication - ignore repeated triggers for same token
        now = time.time()
        token_id = trigger.token_id
        last_time = self._last_trigger_time.get(token_id, 0)
        if now - last_time < self._trigger_cooldown:
            self._audit.log_strategy_event(self._name, "TRIGGER_DEDUPLICATED", {
                "token": token_id[:16] + "...",
                "cooldown_remaining": round(self._trigger_cooldown - (now - last_time), 1)
            })
            return

        self._last_trigger_time[token_id] = now

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

    async def _get_position_lock(self, token_id: str) -> asyncio.Lock:
        """Get or create a lock for a specific token_id (thread-safe)."""
        async with self._global_lock:
            if token_id not in self._position_locks:
                self._position_locks[token_id] = asyncio.Lock()
            return self._position_locks[token_id]

    async def _get_cached_orderbook(self, token_id: str) -> Optional[MarketSnapshot]:
        """v3.0: Get orderbook with TTL caching to reduce API calls."""
        now = time.time()
        if token_id in self._book_cache:
            timestamp, snapshot = self._book_cache[token_id]
            if now - timestamp < self._book_cache_ttl:
                return snapshot

        # Cache miss or expired - fetch fresh
        snapshot = await self._clob_adapter.get_orderbook(token_id)
        if snapshot:
            self._book_cache[token_id] = (now, snapshot)
        return snapshot

    async def _execute_front_run(self, trigger: ScoreboardTrigger):
        """Execute a trade based on a scoreboard trigger."""
        token_id = trigger.token_id

        # v3.0: Use per-token lock to prevent race conditions
        lock = await self._get_position_lock(token_id)

        async with lock:
            # Check if we already have a position (inside lock!)
            if token_id in self._active_positions_map:
                return

            # 1. Liquidity & Volatility Check (use cached orderbook)
            book = await self._get_cached_orderbook(token_id)
            if not book:
                return

            if self._volatility and not self._volatility.is_safe(token_id):
                self._audit.log_strategy_event(self._name, "SKIP_VOLATILE", {"token": token_id})
                return

            # 2. Execution Decision
            # For front-running, we ALWAYS take liquidity (Aggressive)
            base_price = book.best_ask  # We are buying

            # v3.0: Include expected slippage in price estimate
            avg_slippage = 0.002  # 0.2% average expected slippage
            expected_price = base_price * (1 + avg_slippage)

            # Calculate size based on config % of locked capital
            trade_size_usd = self._locked_capital * (self._config.trade_size_percent / 100.0)

            # v3.0: Volatility-adjusted position sizing
            size_multiplier = 1.0
            if self._volatility:
                vol_score = self._volatility.get_score(token_id) if hasattr(self._volatility, 'get_score') else 0
                size_multiplier = 1.0 / (1.0 + vol_score)  # Reduce size in high volatility
            adjusted_size_usd = trade_size_usd * size_multiplier

            # Verify slippage isn't too high already
            max_size = self._clob_adapter.max_executable_size(book, "BUY", slippage_pct=1.0)
            final_size = min(adjusted_size_usd, max_size)

            if final_size < 1.0:
                self._audit.log_strategy_event(self._name, "SKIP_INSUFFICIENT_LIQUIDITY", {"token": token_id})
                return

            # 3. Submit Market/FOK Order
            order_id = self._execution.submit_order(
                strategy=self._name,
                order_type="FOK",  # Fill Or Kill for speed
                params={
                    "token_id": token_id,
                    "price": str(base_price),  # Submit at best_ask, execution adds slippage
                    "size": str(final_size),
                    "side": "BUY"
                }
            )

            if order_id:
                # v2.5: Create enhanced position with tracking
                # Use expected_price for more accurate PnL tracking
                self._positions[token_id] = ActivePosition(
                    token_id=token_id,
                    entry_time=time.time(),
                    entry_price=expected_price,  # Use expected price with slippage
                    size=final_size,
                    order_id=order_id,
                    trigger_type=trigger.trigger_type,
                    highest_price=expected_price,
                    lowest_price=expected_price,
                    current_price=expected_price,
                    unrealized_pnl=0.0,
                    unrealized_pnl_pct=0.0
                )
                self._active_positions = len(self._positions)
                self._last_action = f"FRONT-RUN: {trigger.trigger_type}"
                self._notify_status()

    async def _manage_exits(self):
        """
        v2.5: Dynamic exit management with profit targets, stop-loss, and trailing stops.
        """
        if not self._positions:
            return

        now = time.time()
        cfg = self._exit_config

        # Fetch all orderbooks concurrently
        token_ids = list(self._positions.keys())
        tasks = [self._clob_adapter.get_orderbook(tid) for tid in token_ids]
        orderbooks = await asyncio.gather(*tasks, return_exceptions=True)

        tokens_to_exit: List[tuple] = []  # (token_id, exit_reason)

        for token_id, book in zip(token_ids, orderbooks):
            if isinstance(book, Exception) or book is None:
                continue

            pos = self._positions.get(token_id)
            if not pos:
                continue

            current_price = book.best_bid  # We would sell at bid
            hold_time = now - pos.entry_time

            # Update position tracking
            pos.current_price = current_price
            pos.highest_price = max(pos.highest_price, current_price)
            pos.lowest_price = min(pos.lowest_price, current_price)

            # Calculate unrealized PnL
            pos.unrealized_pnl = (current_price - pos.entry_price) * pos.size
            pos.unrealized_pnl_pct = ((current_price / pos.entry_price) - 1) * 100 if pos.entry_price > 0 else 0

            # Skip if minimum hold time not reached
            if hold_time < cfg['min_hold_seconds']:
                continue

            exit_reason = None

            # v3.2: Volatility-adjusted exit targets
            vol_multiplier = 1.0
            if self._volatility and hasattr(self._volatility, 'get_score'):
                vol_score = self._volatility.get_score(token_id)
                vol_multiplier = 1.0 + (vol_score * 0.5)  # Widen targets in volatile markets

            adjusted_profit_target = cfg['profit_target_pct'] * vol_multiplier
            adjusted_stop_loss = cfg['stop_loss_pct'] * vol_multiplier

            if cfg['exit_mode'] in ['dynamic', 'hybrid']:
                # 1. Check Profit Target (v3.2: volatility-adjusted)
                if pos.unrealized_pnl_pct >= adjusted_profit_target:
                    pos.profit_target_hit = True
                    exit_reason = f"PROFIT_TARGET ({pos.unrealized_pnl_pct:.2f}% >= {adjusted_profit_target:.2f}%)"

                # 2. Check Stop Loss (v3.2: volatility-adjusted)
                elif pos.unrealized_pnl_pct <= -adjusted_stop_loss:
                    pos.stop_loss_hit = True
                    exit_reason = f"STOP_LOSS ({pos.unrealized_pnl_pct:.2f}% <= -{adjusted_stop_loss:.2f}%)"

                # 3. Check Trailing Stop (v3.2: Fixed calculation - relative to HIGH not entry)
                elif pos.highest_price > pos.entry_price:
                    # Only trail if we've been in profit
                    profit_from_entry = ((pos.highest_price - pos.entry_price) / pos.entry_price) * 100
                    if profit_from_entry > 0:
                        # v3.2 FIX: Calculate drawdown relative to HIGH WATER MARK (not entry!)
                        drawdown_from_high = ((pos.highest_price - current_price) / pos.highest_price) * 100
                        # Trail threshold scales with profit: min trailing_stop_pct, or 30% of max profit
                        trail_threshold = max(cfg['trailing_stop_pct'], profit_from_entry * 0.3)
                        if drawdown_from_high >= trail_threshold and current_price > pos.entry_price:
                            pos.trailing_stop_hit = True
                            exit_reason = f"TRAILING_STOP ({drawdown_from_high:.2f}% from high, profit was {profit_from_entry:.2f}%)"

            # 4. Check Timeout (applies in all modes)
            if hold_time >= cfg['max_hold_seconds']:
                pos.timeout_hit = True
                exit_reason = exit_reason or f"TIMEOUT ({hold_time:.0f}s)"

            if exit_reason:
                tokens_to_exit.append((token_id, exit_reason))

        # Execute exits
        for token_id, reason in tokens_to_exit:
            await self._exit_position(token_id, reason)

    async def _exit_position(self, token_id: str, reason: str = "MANUAL"):
        """Exit a specific position with reason tracking."""
        pos = self._positions.get(token_id)
        if not pos:
            return

        book = await self._clob_adapter.get_orderbook(token_id)
        if not book:
            return

        exit_price = book.best_bid

        # Calculate final PnL
        final_pnl = (exit_price - pos.entry_price) * pos.size
        final_pnl_pct = ((exit_price / pos.entry_price) - 1) * 100 if pos.entry_price > 0 else 0

        order_id = self._execution.submit_order(
            strategy=self._name,
            order_type="FOK",
            params={
                "token_id": token_id,
                "price": str(exit_price),
                "size": str(pos.size),
                "side": "SELL"
            }
        )

        if order_id:
            # Update performance tracking
            self._total_trades += 1
            self._total_pnl += final_pnl
            if final_pnl > 0:
                self._winning_trades += 1

            self._audit.log_strategy_event(self._name, "POSITION_CLOSED", {
                "token": token_id[:16] + "...",
                "reason": reason,
                "entry_price": pos.entry_price,
                "exit_price": exit_price,
                "pnl": round(final_pnl, 4),
                "pnl_pct": round(final_pnl_pct, 2),
                "hold_time_sec": round(time.time() - pos.entry_time, 1),
                "highest_price": pos.highest_price,
                "total_pnl": round(self._total_pnl, 4)
            })

            del self._positions[token_id]
            self._active_positions = len(self._positions)
            self._last_action = f"EXIT: {reason}"
            self._notify_status()

    def abort(self) -> None:
        """Emergency cleanup."""
        for tid in list(self._positions.keys()):
            # Emergency exit is just clearing state for now,
            # ideally would send Market Sell orders but abort is immediate.
            pass
        self._positions.clear()
        self._active_positions = 0
        self._set_state(StrategyState.INACTIVE, "ABORTED")

    # ============= v2.5: Configuration & Statistics =============

    def configure_exits(self, config: dict) -> None:
        """Update dynamic exit configuration."""
        for key in config:
            if key in self._exit_config:
                self._exit_config[key] = config[key]

        self._audit.log_strategy_event(self._name, "EXIT_CONFIG_UPDATED", self._exit_config)

    def set_price_monitor(self, monitor) -> None:
        """Set the price monitor for data feed integration."""
        self._price_monitor = monitor
        if monitor:
            # Subscribe to price monitor triggers
            from ..data_feeds.base_feed import FeedTrigger
            monitor.subscribe(self._on_feed_trigger)

    async def _on_feed_trigger(self, trigger) -> None:
        """Handle triggers from data feeds (PolymarketPriceMonitor)."""
        if self._state != StrategyState.ACTIVE:
            return

        # Convert FeedTrigger to ScoreboardTrigger format for compatibility
        from ..scoreboard_monitor import ScoreboardTrigger
        scoreboard_trigger = ScoreboardTrigger(
            event_id=trigger.trigger_id,
            token_id=trigger.token_id,
            trigger_type=trigger.trigger_type.value,
            details=trigger.details,
            timestamp=trigger.timestamp
        )

        await self._pending_triggers.put(scoreboard_trigger)
        self._audit.log_strategy_event(self._name, "FEED_TRIGGER_RECEIVED", {
            "type": trigger.trigger_type.value,
            "confidence": trigger.confidence,
            "direction": trigger.direction
        })

    @property
    def performance_stats(self) -> dict:
        """Get strategy performance statistics."""
        win_rate = (self._winning_trades / self._total_trades * 100) if self._total_trades > 0 else 0
        return {
            'total_trades': self._total_trades,
            'winning_trades': self._winning_trades,
            'losing_trades': self._total_trades - self._winning_trades,
            'win_rate': round(win_rate, 1),
            'total_pnl': round(self._total_pnl, 4),
            'avg_pnl_per_trade': round(self._total_pnl / self._total_trades, 4) if self._total_trades > 0 else 0,
            'active_positions': len(self._positions)
        }

    @property
    def exit_config(self) -> dict:
        """Get current exit configuration."""
        return self._exit_config.copy()

    def get_position_details(self, token_id: str) -> Optional[dict]:
        """Get details for a specific position."""
        pos = self._positions.get(token_id)
        if not pos:
            return None

        return {
            'token_id': pos.token_id,
            'entry_time': pos.entry_time,
            'entry_price': pos.entry_price,
            'current_price': pos.current_price,
            'size': pos.size,
            'unrealized_pnl': pos.unrealized_pnl,
            'unrealized_pnl_pct': pos.unrealized_pnl_pct,
            'highest_price': pos.highest_price,
            'hold_time_sec': time.time() - pos.entry_time,
            'trigger_type': pos.trigger_type
        }

    def get_all_positions(self) -> List[dict]:
        """Get details for all active positions."""
        return [self.get_position_details(tid) for tid in self._positions.keys()]
