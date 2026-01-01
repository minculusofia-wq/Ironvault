"""
Audit Logger Module
Write-only logging of all operator actions and state transitions.
Structured format with timestamps.
"""

import logging
from datetime import datetime
from pathlib import Path
from enum import Enum
from typing import Any


class EventType(Enum):
    """Types of auditable events."""
    OPERATOR_ACTION = "OPERATOR_ACTION"
    STATE_TRANSITION = "STATE_TRANSITION"
    CAPITAL_CHANGE = "CAPITAL_CHANGE"
    STRATEGY_EVENT = "STRATEGY_EVENT"
    POLICY_VIOLATION = "POLICY_VIOLATION"
    KILL_SWITCH = "KILL_SWITCH"
    SYSTEM_ERROR = "SYSTEM_ERROR"


class AuditLogger:
    """
    Write-only audit logger.
    All actions are logged with timestamps in structured format.
    """
    
    def __init__(self, log_dir: str = "logs"):
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        
        self._log_file = self._log_dir / f"audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        
        self._logger = logging.getLogger("audit")
        self._logger.setLevel(logging.INFO)
        self._logger.handlers.clear()
        
        file_handler = logging.FileHandler(self._log_file, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        
        self._logger.addHandler(file_handler)
        
        self.log(EventType.SYSTEM_ERROR, "AUDIT_LOGGER_INITIALIZED", {
            "log_file": str(self._log_file)
        })
    
    def log(self, event_type: EventType, action: str, details: dict[str, Any] | None = None) -> None:
        """
        Log an auditable event.
        
        Args:
            event_type: Category of the event
            action: Specific action name
            details: Additional structured data
        """
        entry = {
            "type": event_type.value,
            "action": action,
            "details": details or {}
        }
        self._logger.info(f"{entry}")
    
    def log_operator_action(self, action: str, details: dict[str, Any] | None = None) -> None:
        """Log an operator-initiated action."""
        self.log(EventType.OPERATOR_ACTION, action, details)
    
    def log_state_transition(self, from_state: str, to_state: str, reason: str) -> None:
        """Log a state machine transition."""
        self.log(EventType.STATE_TRANSITION, "STATE_CHANGE", {
            "from": from_state,
            "to": to_state,
            "reason": reason
        })
    
    def log_capital_change(self, pool: str, old_value: float, new_value: float, reason: str) -> None:
        """Log a capital pool change."""
        self.log(EventType.CAPITAL_CHANGE, "CAPITAL_UPDATE", {
            "pool": pool,
            "old_value": old_value,
            "new_value": new_value,
            "reason": reason
        })
    
    def log_strategy_event(self, strategy: str, event: str, details: dict[str, Any] | None = None) -> None:
        """Log a strategy-related event."""
        self.log(EventType.STRATEGY_EVENT, event, {
            "strategy": strategy,
            **(details or {})
        })
    
    def log_policy_violation(self, action: str, reason: str) -> None:
        """Log a policy violation (blocked action)."""
        self.log(EventType.POLICY_VIOLATION, "VIOLATION_BLOCKED", {
            "attempted_action": action,
            "reason": reason
        })
    
    def log_kill_switch(self, trigger: str, details: dict[str, Any] | None = None) -> None:
        """Log a kill switch activation."""
        self.log(EventType.KILL_SWITCH, "KILL_SWITCH_TRIGGERED", {
            "trigger": trigger,
            **(details or {})
        })
    
    @property
    def log_file_path(self) -> str:
        """Path to current log file."""
        return str(self._log_file)
