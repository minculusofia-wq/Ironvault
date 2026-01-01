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

from .config_loader import BotConfig, ConfigLoader
from .capital_manager import CapitalManager
from .policy_layer import PolicyLayer, ActionType
from .execution_engine import ExecutionEngine
from .kill_switch import KillSwitch, KillSwitchTrigger
from .audit_logger import AuditLogger
from .credentials_manager import CredentialsManager, CredentialsStatus
from .market_data import GammaClient
from .clob_adapter import ClobAdapter
from .websocket_client import WebSocketClient
from .strategies.base_strategy import StrategyStatus
from .strategies.strategy_a_dutching import StrategyADutching
from .strategies.strategy_b_market_making import StrategyBMarketMaking


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
        
        self._strategy_a: StrategyADutching | None = None
        self._strategy_b: StrategyBMarketMaking | None = None
        
        self._ws_client: WebSocketClient | None = None
        
        self._heartbeat_thread: threading.Thread | None = None
        self._heartbeat_running = False
        self._last_heartbeat = 0.0
        
        self._state_callbacks: list[Callable[[BotState], None]] = []
        self._lock = threading.Lock()
    
    def load_config(self, file_path: str) -> tuple[bool, str]:
        """
        Load configuration from file.
        Returns (success, message).
        """
        try:
            self._config = self._config_loader.load(file_path)
            self._audit.log_operator_action("CONFIG_LOADED", {
                "file": file_path
            })
            
            self._initialize_components()
            
            return True, f"Configuration loaded: {file_path}"
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
        self._market_data = GammaClient(self._config.market.gamma_api_url, self._audit)
        self._clob_adapter = ClobAdapter(self._config.market.clob_api_url)
        
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
        
        self._strategy_a = StrategyADutching(
            config=self._config.strategy_a,
            capital_manager=self._capital,
            execution_engine=self._execution,
            audit_logger=self._audit,
            market_data=self._market_data,
            clob_adapter=self._clob_adapter
        )
        
        self._strategy_b = StrategyBMarketMaking(
            config=self._config.strategy_b,
            capital_manager=self._capital,
            execution_engine=self._execution,
            audit_logger=self._audit,
            clob_adapter=self._clob_adapter,
            websocket_client=self._ws_client
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

    def shutdown(self) -> None:
        """Clean shutdown of application."""
        self._stop_heartbeat()
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
        
        # Connect WS Client if not connected
        if self._ws_client and not self._ws_client._running:
            try:
                await self._ws_client.connect()
            except Exception as e:
                self._audit.log_error("WS_CONNECT_RETRY_FAILED", str(e))
        
        # Enable Execution Engine here (in the loop)
        if self._execution and not self._execution.is_enabled:
             try:
                 self._execution.enable()
             except Exception as e:
                 self._audit.log_error("EXECUTION_ENABLE_FAILED", str(e))
        
        while self._heartbeat_running:
            try:
                await asyncio.sleep(interval)
                
                if self._state == BotState.RUNNING:
                    self._last_heartbeat = time.time()
                    
                    # Run strategies concurrently
                    tasks = []
                    if self._strategy_a and self._strategy_a.is_active:
                        tasks.append(self._strategy_a.process_tick())
                    
                    if self._strategy_b and self._strategy_b.is_active:
                        tasks.append(self._strategy_b.process_tick())
                        
                    if tasks:
                        await asyncio.gather(*tasks, return_exceptions=True)
            except Exception as e:
                self._audit.log_error("HEARTBEAT_LOOP_TICK_ERROR", str(e))
        
        # Cleanup when loop stops
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
