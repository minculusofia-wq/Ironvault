"""
Orchestrator Module
Coordinates strategies and maintains global state machine.
Heartbeat monitoring and dispatch to execution engine.
"""

from enum import Enum
from typing import Callable
import threading
import asyncio
import time
import aiohttp
import json
import ssl
import certifi

from .config_loader import BotConfig, ConfigLoader
from .capital_manager import CapitalManager
from .policy_layer import PolicyLayer, ActionType
from .execution_engine import ExecutionEngine, OrderStatus, Order
from .kill_switch import KillSwitch, KillSwitchTrigger
from .audit_logger import AuditLogger
from .credentials_manager import CredentialsManager, CredentialsStatus
from .market_data import GammaClient
from .clob_adapter import ClobAdapter
from .websocket_client import WebSocketClient
from .strategies.base_strategy import StrategyStatus
from .strategies.strategy_a_front_running import StrategyAFrontRunning
from .strategies.strategy_b_market_making import StrategyBMarketMaking
from .scoreboard_monitor import ScoreboardMonitor
from .performance_tracker import PerformanceTracker, TradeRecord
from .volatility_filter import VolatilityFilter
from .market_scanner import MarketScanner
from .analytics_engine import AnalyticsEngine
from .data_feeds.polymarket_feed import PolymarketPriceMonitor


class BotState(Enum):
    """Global bot states."""
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    KILLED = "KILLED"


class Orchestrator:
    """
    Central coordinator for the trading bot.
    Manages state machine, strategies, and system health.
    """
    
    def __init__(self):
        self._state = BotState.IDLE
        self._config: BotConfig | None = None
        
        self._audit = AuditLogger()
        self._config_loader = ConfigLoader()
        self._credentials = CredentialsManager(self._audit)
        self._market_data: GammaClient | None = None
        self._clob_adapter: ClobAdapter | None = None
        self._capital: CapitalManager | None = None
        self._policy: PolicyLayer | None = None
        self._execution: ExecutionEngine | None = None
        self._kill_switch: KillSwitch | None = None
        
        self._strategy_a: StrategyAFrontRunning | None = None
        self._scoreboard = ScoreboardMonitor(self._audit)
        self._strategy_b: StrategyBMarketMaking | None = None
        
        self._performance: PerformanceTracker | None = None
        self._volatility: VolatilityFilter | None = None

        # v2.5 New Components
        self._market_scanner: MarketScanner | None = None
        self._analytics: AnalyticsEngine | None = None
        self._price_monitor: PolymarketPriceMonitor | None = None

        self._ws_client: WebSocketClient | None = None
        self._session: aiohttp.ClientSession | None = None
        self._performance_results = {} # v2.5 UI Cache
        self._analytics_results = {} # v2.5 Analytics Cache
        
        self._heartbeat_thread: threading.Thread | None = None
        self._heartbeat_running = False
        self._last_heartbeat = 0.0
        
        self._state_callbacks: list[Callable[[BotState], None]] = []
        self._lock = threading.Lock()

    def check_connections(self) -> dict:
        """
        Diagnostic check for external connections.
        Returns a dict of component -> status (bool).
        """
        results = {
            "gamma_api": False,
            "clob_api": False,
            "internet": False
        }
        
        try:
            # Simple socket check to Google DNS for generic internet
            import socket
            sock = socket.create_connection(("8.8.8.8", 53), timeout=3)
            sock.close()
            results["internet"] = True
        except Exception as e:
            self._audit.log_error("DIAG_INTERNET_FAIL", str(e))
            
        # We don't check API endpoints here to avoid calling paid/rate-limited APIs on every startup
        # but we could check if client objects are initialized
        results["gamma_api"] = self._market_data is not None
        results["clob_api"] = self._clob_adapter is not None
        
        return results
    
    def load_config(self, file_path: str) -> tuple[bool, str]:
        """
        Load configuration from file.
        Supports Hot-Reload if already running.
        Returns (success, message).
        """
        try:
            was_running = self._state in [BotState.RUNNING, BotState.PAUSED]
            
            if was_running:
                # Stop heartbeat and strategies before reloading
                self._stop_heartbeat()
                
                # Release existing capital locks to avoid doubling up
                if self._strategy_a:
                    self._strategy_a.deactivate()
                if self._strategy_b:
                    self._strategy_b.deactivate()

            self._config = self._config_loader.load(file_path)
            self._audit.log_operator_action("CONFIG_LOADED", {
                "file": file_path,
                "hot_reload": was_running
            })
            
            self._initialize_components()

            if was_running:
                # Re-launch automatically if it was running
                # (Activation of strategies is handled in launch internally)
                # But here we might want to just resume if it was RUNNING
                if self._state == BotState.RUNNING:
                    # Relaunch strategies
                    if self._config.strategy_a.enabled:
                        self._strategy_a.activate()
                    if self._config.strategy_b.enabled:
                        self._strategy_b.activate()
                    self._start_heartbeat()
            
            return True, f"Configuration {'re' if was_running else ''}chargée: {file_path}"
        except Exception as e:
            self._audit.log_operator_action("CONFIG_LOAD_FAILED", {
                "file": file_path,
                "error": str(e)
            })
            return False, str(e)

    
    def _initialize_components(self) -> None:
        """Initialize all components with loaded config."""
        if not self._config:
            return
        
        self._capital = CapitalManager(
            total_capital=self._config.capital.total,
            max_a=self._config.capital.max_allocation_strategy_a,
            max_b=self._config.capital.max_allocation_strategy_b,
            audit_logger=self._audit
        )
        
        self._execution = ExecutionEngine(self._audit)
        
        self._policy = PolicyLayer(
            config=self._config,
            capital_manager=self._capital,
            audit_logger=self._audit
        )
        
        self._kill_switch = KillSwitch(
            capital_manager=self._capital,
            audit_logger=self._audit,
            on_triggered=self._on_kill_switch_triggered
        )
        
        # Initialize Market Data
        # Shared sessions will be provided during heartbeat loop entry
        self._market_data = GammaClient(self._config.market.gamma_api_url, self._audit)
        self._clob_adapter = ClobAdapter(self._config.market.clob_api_url)
        
        # v2.0 Optimizations
        self._performance = PerformanceTracker(self._audit)
        self._volatility = VolatilityFilter(self._audit)

        # v2.5 Market Scanner and Analytics
        self._market_scanner = MarketScanner(
            gamma_client=self._market_data,
            clob_adapter=self._clob_adapter,
            audit_logger=self._audit
        )

        self._analytics = AnalyticsEngine(
            audit_logger=self._audit,
            initial_capital=self._config.capital.total
        )

        # v2.5 Price Monitor for Strategy A (starts in heartbeat loop)
        self._price_monitor = PolymarketPriceMonitor(
            clob_adapter=self._clob_adapter,
            market_scanner=self._market_scanner,
            audit_logger=self._audit,
            poll_interval=1.0
        )

        # Configure from config if available
        if hasattr(self._config, 'market_scanner') and self._config.market_scanner:
            scanner_cfg = self._config.market_scanner
            if hasattr(scanner_cfg, 'weights'):
                self._market_scanner.configure(weights=scanner_cfg.weights)
            if hasattr(scanner_cfg, 'thresholds'):
                self._market_scanner.configure(thresholds=scanner_cfg.thresholds)

        # Initialize WebSocket Client (Connection happens in async loop)
        ws_url = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
        self._ws_client = WebSocketClient(ws_url, self._audit)
        
        # Configure Execution Engine
        if self._execution:
            self._execution.configure_api(
                host=self._config.market.clob_api_url,
                chain_id=137, # Default Polygon Mainnet
                paper_trading=self._config.market.paper_trading
            )
            self._execution.subscribe_status(self._on_execution_status_link)
        
        self._strategy_a = StrategyAFrontRunning(
            config=self._config.strategy_a,
            capital_manager=self._capital,
            execution_engine=self._execution,
            audit_logger=self._audit,
            clob_adapter=self._clob_adapter,
            scoreboard_monitor=self._scoreboard,
            volatility_filter=self._volatility,
            data_feed=self._price_monitor
        )
        
        self._strategy_b = StrategyBMarketMaking(
            config=self._config.strategy_b,
            capital_manager=self._capital,
            execution_engine=self._execution,
            audit_logger=self._audit,
            clob_adapter=self._clob_adapter,
            websocket_client=self._ws_client,
            market_data=self._market_data,
            performance_tracker=self._performance,
            volatility_filter=self._volatility
        )
    
    def launch(self) -> tuple[bool, str]:
        """
        Launch the bot.
        Returns (success, message).
        """
        with self._lock:
            if not self._config:
                return False, "No configuration loaded"
            
            # Verify credentials are loaded (unless paper trading)
            is_paper = self._config.market.paper_trading if self._config else False
            
            if not is_paper and not self._credentials.is_unlocked:
                return False, "Vault non déverrouillé - credentials requis"
            
            decision = self._policy.validate(ActionType.LAUNCH_BOT)
            if not decision.allowed:
                return False, decision.reason
            
            # Provide credentials to execution engine
            self._execution.set_credentials(self._credentials)
            # We Enable Execution Engine INSIDE the async loop to ensure task creation works
            
            self._set_state(BotState.RUNNING)
            self._policy.set_bot_state("RUNNING")
            
            self._start_heartbeat()
            
            if self._config.strategy_a.enabled:
                self._strategy_a.activate()
            
            if self._config.strategy_b.enabled:
                self._strategy_b.activate()
            
            self._audit.log_operator_action("BOT_LAUNCHED")
            return True, "Bot launched successfully"

    def pause(self) -> tuple[bool, str]:
        """Pause bot operations."""
        with self._lock:
            decision = self._policy.validate(ActionType.PAUSE_BOT)
            if not decision.allowed:
                return False, decision.reason
            
            self._set_state(BotState.PAUSED)
            self._policy.set_bot_state("PAUSED")
            self._audit.log_operator_action("BOT_PAUSED")
            return True, "Bot mis en pause"

    def resume(self) -> tuple[bool, str]:
        """Resume bot operations."""
        with self._lock:
            decision = self._policy.validate(ActionType.RESUME_BOT)
            if not decision.allowed:
                return False, decision.reason
            
            self._set_state(BotState.RUNNING)
            self._policy.set_bot_state("RUNNING")
            self._audit.log_operator_action("BOT_RESUMED")
            return True, "Bot a repris l'activité"

    def emergency_stop(self) -> tuple[bool, str]:
        """Trigger emergency stop."""
        if self._kill_switch:
            self._kill_switch.trigger(KillSwitchTrigger.OPERATOR_MANUAL, "Arrêt d'urgence opérateur")
            return True, "Arrêt d'urgence déclenché"
        return False, "Kill switch non initialisé"

    def _on_execution_status_link(self, order: Order) -> None:
        """Callback from ExecutionEngine when an order status changes."""
        if order.status == OrderStatus.COMPLETED and self._performance:
            try:
                # Map Order to TradeRecord
                # params structure: {'token_id': x, 'price': y, 'size': z, 'side': w}
                p = order.params
                result = order.result or {}
                
                trade = TradeRecord(
                    trade_id=order.order_id,
                    strategy=order.strategy,
                    order_type=order.order_type,
                    symbol=p.get('token_id', 'unknown'),
                    side=p.get('side', 'unknown'),
                    price=float(p.get('price', 0)),
                    size=float(p.get('size', 0)),
                    pnl=0.0, # PnL calculation would happen on settlement or sell
                    timestamp=result.get('timestamp', time.time()),
                    details=json.dumps(result)
                )
                self._performance.record_trade(trade)
                self._audit.log_strategy_event(order.strategy, "TRADE_RECORDED_PERSISTENTLY", {"id": order.order_id})
                
                # Dispatch fill to strategy
                if order.strategy == "Strategy_A_Dutching" and self._strategy_a:
                     # Strategy A might not need position tracking as much, but B does
                     pass
                elif order.strategy == "Strategy_B_MarketMaking" and self._strategy_b:
                     self._strategy_b.on_order_fill(
                         market_id=p.get('token_id'),
                         side=p.get('side'),
                         size=float(p.get('size', 0)),
                         price=float(p.get('price', 0))
                     )
            except Exception as e:
                self._audit.log_error("TRADE_RECORD_FAILED", f"Error mapping order to TradeRecord: {e}")

    def shutdown(self) -> None:
        """Clean shutdown of application."""
        self._stop_heartbeat()
        if self._scoreboard:
            asyncio.run_coroutine_threadsafe(self._scoreboard.stop(), asyncio.get_event_loop())
        if self._execution:
            self._execution.disable()
        if self._credentials:
            self._credentials.lock_vault()
        self._audit.log_operator_action("SYSTEM_SHUTDOWN")

    def _start_heartbeat(self) -> None:
        """Start heartbeat monitoring thread with AsyncIO loop."""
        self._heartbeat_running = True
        self._last_heartbeat = time.time()
        # Start a thread that runs the asyncio loop
        self._heartbeat_thread = threading.Thread(target=self._run_async_loop, daemon=True)
        self._heartbeat_thread.start()
        
    def _run_async_loop(self):
        """Entry point for the background thread."""
        try:
            asyncio.run(self._heartbeat_loop_async())
        except Exception as e:
            self._audit.log_error("CRITICAL_LOOP_FAILURE", str(e))
            
    async def _heartbeat_loop_async(self) -> None:
        """Heartbeat monitoring loop (Async)."""
        interval = self._config.market.heartbeat_interval_seconds if self._config else 5
        
        while self._heartbeat_running:
            try:
                # v2.5 Centralized Session Management
                if self._session is None or self._session.closed:
                    import ssl
                    import certifi
                    ssl_context = ssl.create_default_context(cafile=certifi.where())
                    connector = aiohttp.TCPConnector(ssl=ssl_context)
                    self._session = aiohttp.ClientSession(connector=connector)
                    
                    # Inject into components
                    if self._market_data: self._market_data.set_session(self._session)
                    if self._clob_adapter: self._clob_adapter.set_session(self._session)
                
                # 2. Start WebSocket Manager and Scoreboard if not running
                if self._ws_client and not self._ws_client._running:
                    try:
                        await self._ws_client.start()
                    except Exception as e:
                        self._audit.log_error("WS_MANAGER_START_FAILED", str(e))
                
                if self._scoreboard and not self._scoreboard._running:
                    await self._scoreboard.start()

                # v2.5: Start Market Scanner and Price Monitor
                if self._price_monitor and not self._price_monitor._running:
                    try:
                        await self._price_monitor.start()
                    except Exception as e:
                        self._audit.log_error("PRICE_MONITOR_START_FAILED", str(e))

                # Periodic market scan (non-blocking)
                if self._market_scanner:
                    try:
                        await self._market_scanner.scan_markets(limit=50)
                    except Exception as e:
                        self._audit.log_error("MARKET_SCAN_FAILED", str(e))
                
                # 2. Ensure Execution Engine is enabled
                if self._execution and not self._execution.is_enabled:
                    try:
                        self._execution.enable()
                    except Exception as e:
                        self._audit.log_error("EXECUTION_RE_ENABLE_FAILED", str(e))

                # 4. Process Strategy Ticks
                if self._state == BotState.RUNNING:
                    self._last_heartbeat = time.time()
                    self._audit.log_operator_action("HEARTBEAT_TICK")
                    
                    # Run strategies concurrently
                    tasks = []
                    if self._strategy_a and self._strategy_a.is_active:
                        tasks.append(self._strategy_a.process_tick())
                    
                    if self._strategy_b and self._strategy_b.is_active:
                        tasks.append(self._strategy_b.process_tick())
                        
                    if tasks:
                        # Use a timeout for strategy ticks to avoid hanging the loop
                        try:
                            # 2.5 Dynamic tick timeout: shorter of interval*2 or 10s
                            tick_timeout = min(interval * 2, 10.0)
                            await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=tick_timeout)
                        except asyncio.TimeoutError:
                            self._audit.log_error("STRATEGY_TICK_TIMEOUT", f"Ticks exceeded {tick_timeout}s")
                            
                    # 5. Background Task: Update Performance Results for UI (Offloaded from UI thread)
                    if self._performance:
                        self._performance_results = self._performance.get_summary_stats()

                    # v2.5: Update Analytics Cache for UI
                    if self._analytics:
                        self._analytics_results = self._analytics.get_summary()
                            
            except Exception as e:
                self._audit.log_error("HEARTBEAT_LOOP_TICK_ERROR", str(e))
            
            # 5. Always wait for interval even on error to prevent CPU hogging
            await asyncio.sleep(interval)
        
        if self._scoreboard:
            asyncio.create_task(self._scoreboard.stop())
            
        if self._ws_client:
            await self._ws_client.disconnect()
            
        if self._execution:
            self._execution.disable()

    def _stop_heartbeat(self) -> None:
        """Stop heartbeat monitoring thread."""
        self._heartbeat_running = False
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=2.0)

    def _on_kill_switch_triggered(self) -> None:
        """Callback when kill switch is triggered."""
        self._set_state(BotState.KILLED)
        self._audit.log_operator_action("KILL_SWITCH_CALLBACK_RECEIVED")
        # Ensure thread stops
        self._heartbeat_running = False
    
    def _set_state(self, state: BotState) -> None:
        """Update bot state and notify subscribers."""
        old_state = self._state
        self._state = state
        
        self._audit.log_state_transition(old_state.value, state.value, "STATE_CHANGE")
        
        for callback in self._state_callbacks:
            try:
                callback(state)
            except Exception:
                pass
    
    def subscribe_state(self, callback: Callable[[BotState], None]) -> None:
        """Subscribe to bot state changes."""
        self._state_callbacks.append(callback)
    
    @property
    def state(self) -> BotState:
        return self._state
    
    @property
    def is_config_loaded(self) -> bool:
        return self._config is not None
    
    @property
    def config_file(self) -> str | None:
        return self._config.file_path if self._config else None
    
    @property
    def capital_state(self):
        return self._capital.state if self._capital else None
    
    @property
    def live_orderbook_snapshots(self) -> dict[str, dict]:
        """Get live snapshots for all active markets in Strategy B."""
        if self._strategy_b:
            return self._strategy_b.live_orderbook_snapshots
        return {}

    @property
    def performance_stats(self) -> dict:
        """Get cached performance stats (Thread-safe for UI)."""
        return self._performance_results or {}

    @property
    def strategy_a_status(self) -> StrategyStatus | None:
        return self._strategy_a.get_status() if self._strategy_a else None
    
    @property
    def strategy_b_status(self) -> StrategyStatus | None:
        return self._strategy_b.get_status() if self._strategy_b else None
    
    @property
    def kill_switch_status(self) -> dict | None:
        return self._kill_switch.status if self._kill_switch else None
    
    @property
    def credentials_manager(self) -> CredentialsManager:
        """Access to credentials manager for GUI."""
        return self._credentials
    
    @property
    def credentials_status(self) -> CredentialsStatus:
        """Credentials status for dashboard."""
        return self._credentials.get_status()

    @property
    def analytics_summary(self) -> dict:
        """Get cached analytics summary (Thread-safe for UI)."""
        return self._analytics_results or {}

    @property
    def market_scanner_status(self) -> dict:
        """Get market scanner status."""
        if self._market_scanner:
            return {
                'cached_markets': self._market_scanner.cached_market_count,
                'last_scan_age_sec': round(self._market_scanner.last_scan_age_seconds, 1),
                'top_mm_markets': len(self._market_scanner.get_top_markets_for_mm(limit=10)),
                'top_fr_markets': len(self._market_scanner.get_top_markets_for_fr(limit=10))
            }
        return {}

    @property
    def price_monitor_status(self) -> dict:
        """Get price monitor status."""
        if self._price_monitor:
            return {
                'running': self._price_monitor._running,
                'monitored_tokens': self._price_monitor.monitored_token_count
            }
        return {}
