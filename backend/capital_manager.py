"""
Capital Manager Module
Manages capital pools with atomic locking mechanism.
Prevents double-allocation between strategies.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Callable
import threading

from .audit_logger import AuditLogger


class CapitalPool(Enum):
    """Capital pool identifiers."""
    TOTAL = "total"
    LOCKED_A = "locked_a"
    LOCKED_B = "locked_b"
    FREE = "free"


@dataclass
class CapitalState:
    """Current state of all capital pools."""
    total: float
    locked_a: float
    locked_b: float
    free: float


class CapitalAllocationError(Exception):
    """Raised when capital allocation fails."""
    pass


class CapitalManager:
    """
    Manages capital pools with atomic locking.
    
    Pools:
    - total: Total available capital
    - locked_a: Capital locked for Strategy A (Dutching)
    - locked_b: Capital locked for Strategy B (Market Making)
    - free: Available for allocation (total - locked_a - locked_b)
    """
    
    def __init__(self, total_capital: float, max_a: float, max_b: float, audit_logger: AuditLogger):
        self._total = total_capital
        self._max_a = max_a
        self._max_b = max_b
        self._locked_a = 0.0
        self._locked_b = 0.0
        self._audit = audit_logger
        
        self._lock = threading.Lock()
        self._subscribers: list[Callable[[CapitalState], None]] = []
        
        self._audit.log_capital_change("total", 0, total_capital, "INITIALIZATION")
    
    def lock_for_strategy_a(self, amount: float) -> bool:
        """
        Attempt to lock capital for Strategy A (Dutching).
        Returns True if successful, False if insufficient capital.
        """
        with self._lock:
            if amount <= 0:
                raise CapitalAllocationError("Lock amount must be positive")
            
            if amount > self._max_a:
                self._audit.log_policy_violation(
                    "LOCK_STRATEGY_A",
                    f"Amount {amount} exceeds max allocation {self._max_a}"
                )
                return False
            
            new_locked_a = self._locked_a + amount
            if new_locked_a > self._max_a:
                self._audit.log_policy_violation(
                    "LOCK_STRATEGY_A",
                    f"Total locked would exceed max: {new_locked_a} > {self._max_a}"
                )
                return False
            
            if amount > self.free:
                self._audit.log_policy_violation(
                    "LOCK_STRATEGY_A",
                    f"Insufficient free capital: {amount} > {self.free}"
                )
                return False
            
            old_locked = self._locked_a
            self._locked_a = new_locked_a
            
            self._audit.log_capital_change("locked_a", old_locked, self._locked_a, "LOCK_STRATEGY_A")
            self._notify_subscribers()
            return True
    
    def lock_for_strategy_b(self, amount: float) -> bool:
        """
        Attempt to lock capital for Strategy B (Market Making).
        Returns True if successful, False if insufficient capital.
        """
        with self._lock:
            if amount <= 0:
                raise CapitalAllocationError("Lock amount must be positive")
            
            if amount > self._max_b:
                self._audit.log_policy_violation(
                    "LOCK_STRATEGY_B",
                    f"Amount {amount} exceeds max allocation {self._max_b}"
                )
                return False
            
            new_locked_b = self._locked_b + amount
            if new_locked_b > self._max_b:
                self._audit.log_policy_violation(
                    "LOCK_STRATEGY_B",
                    f"Total locked would exceed max: {new_locked_b} > {self._max_b}"
                )
                return False
            
            if amount > self.free:
                self._audit.log_policy_violation(
                    "LOCK_STRATEGY_B",
                    f"Insufficient free capital: {amount} > {self.free}"
                )
                return False
            
            old_locked = self._locked_b
            self._locked_b = new_locked_b
            
            self._audit.log_capital_change("locked_b", old_locked, self._locked_b, "LOCK_STRATEGY_B")
            self._notify_subscribers()
            return True
    
    def release_from_strategy_a(self, amount: float) -> None:
        """Release locked capital from Strategy A."""
        with self._lock:
            if amount <= 0:
                raise CapitalAllocationError("Release amount must be positive")
            
            if amount > self._locked_a:
                raise CapitalAllocationError(
                    f"Cannot release {amount}, only {self._locked_a} locked"
                )
            
            old_locked = self._locked_a
            self._locked_a -= amount
            
            self._audit.log_capital_change("locked_a", old_locked, self._locked_a, "RELEASE_STRATEGY_A")
            self._notify_subscribers()
    
    def release_from_strategy_b(self, amount: float) -> None:
        """Release locked capital from Strategy B."""
        with self._lock:
            if amount <= 0:
                raise CapitalAllocationError("Release amount must be positive")
            
            if amount > self._locked_b:
                raise CapitalAllocationError(
                    f"Cannot release {amount}, only {self._locked_b} locked"
                )
            
            old_locked = self._locked_b
            self._locked_b -= amount
            
            self._audit.log_capital_change("locked_b", old_locked, self._locked_b, "RELEASE_STRATEGY_B")
            self._notify_subscribers()
    
    def release_all_strategy_a(self) -> float:
        """Release all capital locked for Strategy A. Returns amount released."""
        with self._lock:
            amount = self._locked_a
            if amount > 0:
                self._locked_a = 0
                self._audit.log_capital_change("locked_a", amount, 0, "RELEASE_ALL_STRATEGY_A")
                self._notify_subscribers()
            return amount
    
    def release_all_strategy_b(self) -> float:
        """Release all capital locked for Strategy B. Returns amount released."""
        with self._lock:
            amount = self._locked_b
            if amount > 0:
                self._locked_b = 0
                self._audit.log_capital_change("locked_b", amount, 0, "RELEASE_ALL_STRATEGY_B")
                self._notify_subscribers()
            return amount
    
    def freeze_all(self) -> None:
        """Freeze all pools (for kill switch). Sets max allocations to 0."""
        with self._lock:
            self._max_a = 0
            self._max_b = 0
            self._audit.log_capital_change("max_allocations", -1, 0, "FREEZE_ALL_POOLS")
            self._notify_subscribers()
    
    def subscribe(self, callback: Callable[[CapitalState], None]) -> None:
        """Subscribe to capital state changes."""
        self._subscribers.append(callback)
    
    def _notify_subscribers(self) -> None:
        """Notify all subscribers of state change."""
        state = self.state
        for callback in self._subscribers:
            try:
                callback(state)
            except Exception:
                pass
    
    @property
    def free(self) -> float:
        """Available (unallocated) capital."""
        return self._total - self._locked_a - self._locked_b
    
    def get_available_capital(self) -> float:
        """Helper for strategies to check their available allocation."""
        return self.free

    @property
    def state(self) -> CapitalState:
        """Current state of all pools."""
        return CapitalState(
            total=self._total,
            locked_a=self._locked_a,
            locked_b=self._locked_b,
            free=self.free
        )
    
    @property
    def total(self) -> float:
        return self._total
    
    @property
    def locked_a(self) -> float:
        return self._locked_a
    
    @property
    def locked_b(self) -> float:
        return self._locked_b
