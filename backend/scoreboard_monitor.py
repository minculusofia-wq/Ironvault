"""
Scoreboard Monitor Module
Handles ultra-fast external data sources (feeds) and emits triggers for front-running.
"""

import asyncio
import time
import json
from typing import Callable, Dict, Any, List
from dataclasses import dataclass
from .audit_logger import AuditLogger

@dataclass
class ScoreboardTrigger:
    event_id: str
    token_id: str
    trigger_type: str # e.g., 'GOAL', 'SCORE', 'ELECTION_UPDATE'
    details: Dict[str, Any]
    timestamp: float

class ScoreboardMonitor:
    """
    Interface for high-speed external data monitoring.
    Connects to various feeds and notifies subscribers of critical events.
    """
    
    def __init__(self, audit_logger: AuditLogger):
        self._audit = audit_logger
        self._subscribers: List[Callable[[ScoreboardTrigger], None]] = []
        self._running = False
        self._task: asyncio.Task | None = None
        
    def subscribe(self, callback: Callable[[ScoreboardTrigger], None]):
        """Subscribe to trigger events."""
        self._subscribers.append(callback)
        
    async def start(self):
        """Start the monitoring process."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._main_loop())
        self._audit.log_system_event("SCOREBOARD_MONITOR_STARTED")
        
    async def stop(self):
        """Stop the monitoring process."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._audit.log_system_event("SCOREBOARD_MONITOR_STOPPED")
        
    async def _main_loop(self):
        """
        Background loop for monitoring feeds.
        For now, this implements a modular mock that can be replaced by real API connectors.
        """
        while self._running:
            try:
                # In a real implementation, we would poll an API or listen to a WebSocket here.
                # Example:
                # data = await self._fetch_live_data()
                # if self._detect_anomaly(data):
                #     self._emit_trigger(...)
                
                await asyncio.sleep(1.0) # Heartbeat for the monitor
            except Exception as e:
                self._audit.log_error("SCOREBOARD_MONITOR_ERROR", str(e))
                await asyncio.sleep(5)
                
    def _emit_trigger(self, trigger: ScoreboardTrigger):
        """Dispatch trigger to all subscribers."""
        self._audit.log_system_event("SCOREBOARD_TRIGGER_EMITTED", {
            "type": trigger.trigger_type,
            "event": trigger.event_id
        })
        for callback in self._subscribers:
            try:
                # Strategies receive the trigger in the same thread (async callback)
                # Should be fast to avoid blocking the monitor
                asyncio.create_task(self._safe_dispatch(callback, trigger))
            except Exception:
                pass
                
    async def _safe_dispatch(self, callback, trigger):
        try:
            # Check if it's a coroutine
            if asyncio.iscoroutinefunction(callback):
                await callback(trigger)
            else:
                callback(trigger)
        except Exception as e:
            self._audit.log_error("SCOREBOARD_DISPATCH_FAIL", str(e))

    # --- MOCK METHOD FOR DEMO/TEST ---
    async def inject_mock_trigger(self, event_id: str, token_id: str, trigger_type: str):
        """Allows manual/config-based trigger injection for testing."""
        trigger = ScoreboardTrigger(
            event_id=event_id,
            token_id=token_id,
            trigger_type=trigger_type,
            details={},
            timestamp=time.time()
        )
        self._emit_trigger(trigger)
