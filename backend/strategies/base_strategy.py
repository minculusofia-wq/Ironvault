"""
Base Strategy Module
Abstract base class for all strategies.
Defines standard interface for strategy lifecycle.
"""

from abc import ABC, abstractmethod
from enum import Enum
from dataclasses import dataclass
from typing import Callable, Any


class StrategyState(Enum):
    """Possible states of a strategy."""
    INACTIVE = "INACTIVE"
    ACTIVATING = "ACTIVATING"
    ACTIVE = "ACTIVE"
    DEACTIVATING = "DEACTIVATING"
    ERROR = "ERROR"


@dataclass
class StrategyStatus:
    """Current status of a strategy."""
    name: str
    state: StrategyState
    locked_capital: float
    active_positions: int
    last_action: str
    error_message: str | None = None


class BaseStrategy(ABC):
    """
    Abstract base class for trading strategies.
    All strategies must implement this interface.
    """
    
    def __init__(self, name: str):
        self._name = name
        self._state = StrategyState.INACTIVE
        self._locked_capital = 0.0
        self._active_positions = 0
        self._last_action = "INITIALIZED"
        self._error_message: str | None = None
        
        self._state_callbacks: list[Callable[[StrategyStatus], None]] = []
    
    @abstractmethod
    def activate(self) -> bool:
        """
        Activate the strategy.
        Returns True if activation successful, False otherwise.
        Must request capital lock before returning True.
        """
        pass
    
    @abstractmethod
    def deactivate(self) -> bool:
        """
        Deactivate the strategy.
        Returns True if deactivation successful, False otherwise.
        Must release all locked capital before returning True.
        """
        pass
    
    @abstractmethod
    async def process_tick(self) -> None:
        """
        Process a market tick (Async).
        Called by orchestrator on each market update.
        """
        pass
    
    @abstractmethod
    def abort(self) -> None:
        """
        Emergency abort.
        Cancel all pending operations and release capital.
        Called by kill switch.
        """
        pass
    
    def get_status(self) -> StrategyStatus:
        """Get current strategy status."""
        return StrategyStatus(
            name=self._name,
            state=self._state,
            locked_capital=self._locked_capital,
            active_positions=self._active_positions,
            last_action=self._last_action,
            error_message=self._error_message
        )
    
    def subscribe_status(self, callback: Callable[[StrategyStatus], None]) -> None:
        """Subscribe to strategy status changes."""
        self._state_callbacks.append(callback)
    
    def _set_state(self, state: StrategyState, action: str = "") -> None:
        """Update strategy state and notify subscribers."""
        self._state = state
        if action:
            self._last_action = action
        self._notify_status()
    
    def _set_error(self, message: str) -> None:
        """Set error state with message."""
        self._error_message = message
        self._state = StrategyState.ERROR
        self._last_action = "ERROR"
        self._notify_status()
    
    def _clear_error(self) -> None:
        """Clear error state."""
        self._error_message = None
        if self._state == StrategyState.ERROR:
            self._state = StrategyState.INACTIVE
    
    def _notify_status(self) -> None:
        """Notify subscribers of status change."""
        status = self.get_status()
        for callback in self._state_callbacks:
            try:
                callback(status)
            except Exception:
                pass
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def state(self) -> StrategyState:
        return self._state
    
    @property
    def is_active(self) -> bool:
        return self._state == StrategyState.ACTIVE
    
    @property
    def locked_capital(self) -> float:
        return self._locked_capital
