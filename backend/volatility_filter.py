"""
Volatility Filter Module
Detects high-velocity price movements and triggers safety pauses.
"""

import time
from collections import deque
from typing import Dict
from .audit_logger import AuditLogger

class VolatilityFilter:
    """
    Monitors price velocity of tokens and provides a safety signal.
    """
    
    def __init__(
        self, 
        audit_logger: AuditLogger, 
        window_seconds: int = 60,
        threshold_percent: float = 2.0
    ):
        self._audit = audit_logger
        self._window = window_seconds
        self._threshold = threshold_percent
        
        # token_id -> deque[(timestamp, price)]
        self._history: Dict[str, deque] = {}
        
    def update_price(self, token_id: str, price: float):
        """Update price history for a token and clean up old data."""
        now = time.time()
        
        if token_id not in self._history:
            self._history[token_id] = deque()
            
        history = self._history[token_id]
        history.append((now, price))
        
        # Clean up window
        while history and history[0][0] < now - self._window:
            history.popleft()
            
    def is_safe(self, token_id: str) -> bool:
        """
        Check if the price of a token is stable within the configured threshold.
        Returns False if a 'Flash Move' is detected.
        """
        history = self._history.get(token_id)
        if not history or len(history) < 2:
            return True
            
        min_price = min(p[1] for p in history)
        max_price = max(p[1] for p in history)
        
        if min_price == 0:
            return True
            
        move_percent = ((max_price - min_price) / min_price) * 100
        
        if move_percent > self._threshold:
            self._audit.log_policy_violation(
                "VOLATILITY_FILTER_TRIGGER", 
                f"Token {token_id} moved {move_percent:.2f}% (Threshold: {self._threshold}%)"
            )
            return False
            
        return True

    def reset(self):
        """Reset all tracked history."""
        self._history.clear()
        self._audit.log_system_event("VOLATILITY_FILTER_RESET")
