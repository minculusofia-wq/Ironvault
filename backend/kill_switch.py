"""
Kill Switch Module
Global emergency stop with multi-source triggers.
Freezes all operations and requires manual restart.
"""

from enum import Enum
from typing import Callable
import threading

from .capital_manager import CapitalManager
from .audit_logger import AuditLogger


class KillSwitchTrigger(Enum):
    """Sources that can trigger the kill switch."""
    OPERATOR_MANUAL = "OPERATOR_MANUAL"
    CAPITAL_BREACH = "CAPITAL_BREACH"
    POLICY_VIOLATION = "POLICY_VIOLATION"
    HEARTBEAT_TIMEOUT = "HEARTBEAT_TIMEOUT"
    EXTERNAL_WATCHDOG = "EXTERNAL_WATCHDOG"
    SYSTEM_ERROR = "SYSTEM_ERROR"


class KillSwitch:
    """
    Global kill switch for emergency shutdown.
    Once triggered, requires manual reset.
    """
    
    def __init__(
        self,
        capital_manager: CapitalManager,
        audit_logger: AuditLogger,
        on_triggered: Callable[[], None] | None = None
    ):
        self._capital = capital_manager
        self._audit = audit_logger
        self._on_triggered = on_triggered
        
        self._active = False
        self._trigger: KillSwitchTrigger | None = None
        self._trigger_reason: str = ""
        self._lock = threading.Lock()
        
        self._subscribers: list[Callable[[bool], None]] = []
    
    def trigger(self, source: KillSwitchTrigger, reason: str = "") -> None:
        """
        Trigger the kill switch.
        Immediately halts all operations and freezes capital.
        """
        with self._lock:
            if self._active:
                return
            
            self._active = True
            self._trigger = source
            self._trigger_reason = reason
            
            self._audit.log_kill_switch(source.value, {
                "reason": reason
            })
            
            self._capital.freeze_all()
            
            if self._on_triggered:
                try:
                    self._on_triggered()
                except Exception as e:
                    self._audit.log(
                        self._audit._logger.info,
                        "KILL_SWITCH_CALLBACK_ERROR",
                        {"error": str(e)}
                    )
            
            self._notify_subscribers()
    
    def reset(self) -> bool:
        """
        Reset the kill switch (manual operation).
        Returns True if successfully reset.
        NOTE: This only resets the switch state, not the capital freeze.
        A new config must be loaded to restore capital allocations.
        """
        with self._lock:
            if not self._active:
                return False
            
            self._audit.log_operator_action("KILL_SWITCH_RESET", {
                "previous_trigger": self._trigger.value if self._trigger else None,
                "previous_reason": self._trigger_reason
            })
            
            self._active = False
            self._trigger = None
            self._trigger_reason = ""
            
            self._notify_subscribers()
            return True
    
    def check_capital_breach(self, current_loss_percent: float, threshold: float) -> None:
        """Check if capital loss exceeds threshold and trigger if so."""
        if current_loss_percent >= threshold:
            self.trigger(
                KillSwitchTrigger.CAPITAL_BREACH,
                f"Loss {current_loss_percent:.2f}% >= threshold {threshold:.2f}%"
            )
    
    def check_heartbeat_timeout(self) -> None:
        """Trigger kill switch due to heartbeat timeout."""
        self.trigger(
            KillSwitchTrigger.HEARTBEAT_TIMEOUT,
            "Orchestrator heartbeat timeout"
        )
    
    def subscribe(self, callback: Callable[[bool], None]) -> None:
        """Subscribe to kill switch state changes."""
        self._subscribers.append(callback)
    
    def _notify_subscribers(self) -> None:
        """Notify subscribers of state change."""
        for callback in self._subscribers:
            try:
                callback(self._active)
            except Exception:
                pass
    
    @property
    def is_active(self) -> bool:
        """Whether kill switch is currently active."""
        return self._active
    
    @property
    def trigger_source(self) -> KillSwitchTrigger | None:
        """Source that triggered the kill switch."""
        return self._trigger
    
    @property
    def trigger_reason(self) -> str:
        """Reason for kill switch trigger."""
        return self._trigger_reason
    
    @property
    def status(self) -> dict:
        """Current kill switch status."""
        return {
            "active": self._active,
            "trigger": self._trigger.value if self._trigger else None,
            "reason": self._trigger_reason
        }
