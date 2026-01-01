"""
Policy Layer Module
Validates all actions against configuration rules before execution.
Blocks any action not explicitly permitted.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Any

from .config_loader import BotConfig
from .capital_manager import CapitalManager
from .audit_logger import AuditLogger


class ActionType(Enum):
    """Types of actions that require policy validation."""
    LAUNCH_BOT = "LAUNCH_BOT"
    PAUSE_BOT = "PAUSE_BOT"
    RESUME_BOT = "RESUME_BOT"
    EMERGENCY_STOP = "EMERGENCY_STOP"
    ACTIVATE_STRATEGY_A = "ACTIVATE_STRATEGY_A"
    ACTIVATE_STRATEGY_B = "ACTIVATE_STRATEGY_B"
    DEACTIVATE_STRATEGY_A = "DEACTIVATE_STRATEGY_A"
    DEACTIVATE_STRATEGY_B = "DEACTIVATE_STRATEGY_B"
    LOCK_CAPITAL_A = "LOCK_CAPITAL_A"
    LOCK_CAPITAL_B = "LOCK_CAPITAL_B"
    PLACE_ORDER = "PLACE_ORDER"


@dataclass
class PolicyDecision:
    """Result of policy validation."""
    allowed: bool
    reason: str


class PolicyViolationError(Exception):
    """Raised when an action violates policy."""
    pass


class PolicyLayer:
    """
    Validates all actions against configuration and current state.
    No action can bypass this layer.
    """
    
    def __init__(
        self,
        config: BotConfig,
        capital_manager: CapitalManager,
        audit_logger: AuditLogger
    ):
        self._config = config
        self._capital = capital_manager
        self._audit = audit_logger
        self._kill_switch_active = False
        self._bot_state = "IDLE"
    
    def validate(self, action: ActionType, params: dict[str, Any] | None = None) -> PolicyDecision:
        """
        Validate an action against policy rules.
        Returns PolicyDecision indicating if action is allowed.
        """
        params = params or {}
        
        if self._kill_switch_active and action != ActionType.EMERGENCY_STOP:
            self._audit.log_policy_violation(action.value, "Kill switch is active")
            return PolicyDecision(False, "Kill switch is active - no actions permitted")
        
        validator = getattr(self, f"_validate_{action.value.lower()}", None)
        if validator:
            decision = validator(params)
        else:
            decision = PolicyDecision(False, f"Unknown action type: {action.value}")
        
        if not decision.allowed:
            self._audit.log_policy_violation(action.value, decision.reason)
        
        return decision
    
    def _validate_launch_bot(self, params: dict[str, Any]) -> PolicyDecision:
        """Validate bot launch."""
        if self._bot_state != "IDLE":
            return PolicyDecision(False, f"Bot not in IDLE state (current: {self._bot_state})")
        
        if not self._config:
            return PolicyDecision(False, "No configuration loaded")
        
        return PolicyDecision(True, "Launch permitted")
    
    def _validate_pause_bot(self, params: dict[str, Any]) -> PolicyDecision:
        """Validate bot pause."""
        if self._bot_state != "RUNNING":
            return PolicyDecision(False, f"Bot not running (current: {self._bot_state})")
        
        return PolicyDecision(True, "Pause permitted")
    
    def _validate_resume_bot(self, params: dict[str, Any]) -> PolicyDecision:
        """Validate bot resume."""
        if self._bot_state != "PAUSED":
            return PolicyDecision(False, f"Bot not paused (current: {self._bot_state})")
        
        return PolicyDecision(True, "Resume permitted")
    
    def _validate_emergency_stop(self, params: dict[str, Any]) -> PolicyDecision:
        """Emergency stop is always allowed."""
        return PolicyDecision(True, "Emergency stop always permitted")
    
    def _validate_activate_strategy_a(self, params: dict[str, Any]) -> PolicyDecision:
        """Validate Strategy A activation."""
        if not self._config.strategy_a.enabled:
            return PolicyDecision(False, "Strategy A is disabled in configuration")
        
        if self._bot_state != "RUNNING":
            return PolicyDecision(False, "Bot must be running to activate strategy")
        
        return PolicyDecision(True, "Strategy A activation permitted")
    
    def _validate_activate_strategy_b(self, params: dict[str, Any]) -> PolicyDecision:
        """Validate Strategy B activation."""
        if not self._config.strategy_b.enabled:
            return PolicyDecision(False, "Strategy B is disabled in configuration")
        
        if self._bot_state != "RUNNING":
            return PolicyDecision(False, "Bot must be running to activate strategy")
        
        return PolicyDecision(True, "Strategy B activation permitted")
    
    def _validate_deactivate_strategy_a(self, params: dict[str, Any]) -> PolicyDecision:
        """Validate Strategy A deactivation."""
        return PolicyDecision(True, "Strategy A deactivation permitted")
    
    def _validate_deactivate_strategy_b(self, params: dict[str, Any]) -> PolicyDecision:
        """Validate Strategy B deactivation."""
        return PolicyDecision(True, "Strategy B deactivation permitted")
    
    def _validate_lock_capital_a(self, params: dict[str, Any]) -> PolicyDecision:
        """Validate capital lock for Strategy A."""
        amount = params.get("amount", 0)
        
        if amount <= 0:
            return PolicyDecision(False, "Lock amount must be positive")
        
        if amount > self._config.capital.max_allocation_strategy_a:
            return PolicyDecision(
                False,
                f"Amount {amount} exceeds max allocation {self._config.capital.max_allocation_strategy_a}"
            )
        
        if amount > self._capital.free:
            return PolicyDecision(
                False,
                f"Insufficient free capital: {amount} > {self._capital.free}"
            )
        
        return PolicyDecision(True, "Capital lock for Strategy A permitted")
    
    def _validate_lock_capital_b(self, params: dict[str, Any]) -> PolicyDecision:
        """Validate capital lock for Strategy B."""
        amount = params.get("amount", 0)
        
        if amount <= 0:
            return PolicyDecision(False, "Lock amount must be positive")
        
        if amount > self._config.capital.max_allocation_strategy_b:
            return PolicyDecision(
                False,
                f"Amount {amount} exceeds max allocation {self._config.capital.max_allocation_strategy_b}"
            )
        
        if amount > self._capital.free:
            return PolicyDecision(
                False,
                f"Insufficient free capital: {amount} > {self._capital.free}"
            )
        
        return PolicyDecision(True, "Capital lock for Strategy B permitted")
    
    def _validate_place_order(self, params: dict[str, Any]) -> PolicyDecision:
        """Validate order placement."""
        if self._bot_state != "RUNNING":
            return PolicyDecision(False, "Bot must be running to place orders")
        
        return PolicyDecision(True, "Order placement permitted")
    
    def set_bot_state(self, state: str) -> None:
        """Update tracked bot state."""
        self._bot_state = state
    
    def set_kill_switch_active(self, active: bool) -> None:
        """Update kill switch status."""
        self._kill_switch_active = active
    
    @property
    def kill_switch_active(self) -> bool:
        return self._kill_switch_active
