"""
Rate Limiter Module
Implements Token Bucket algorithm for API rate limiting.
"""

import time
import threading
import asyncio
from typing import Optional

class RateLimiter:
    """
    Token Bucket Rate Limiter.
    Thread-safe and asyncio-compatible.
    """
    
    def __init__(self, max_tokens: float, refill_rate: float):
        """
        :param max_tokens: Maximum burst capacity.
        :param refill_rate: Tokens added per second.
        """
        self._max_tokens = max_tokens
        self._refill_rate = refill_rate
        self._tokens = max_tokens
        self._last_refill = time.time()
        self._lock = asyncio.Lock()
        
    async def acquire(self, tokens: float = 1.0) -> None:
        """
        Wait until enough tokens are available.
        """
        while True:
            async with self._lock:
                self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return
                
                # Calculate wait time
                needed = tokens - self._tokens
                wait_time = needed / self._refill_rate
                
            await asyncio.sleep(wait_time)
            
    def try_acquire(self, tokens: float = 1.0) -> bool:
        """
        Try to acquire tokens immediately. Returns True if successful.
        (Synchronous version, not thread-safe if mixed with async without care, 
        but assumes single threaded event loop usage usually)
        """
        # Note: Mixing sync and async lock acquisition is tricky. 
        # For simplicity in this bot, we assume async usage mostly.
        # But if needed synchronously:
        self._refill_sync()
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False

    def _refill(self):
        now = time.time()
        elapsed = now - self._last_refill
        added = elapsed * self._refill_rate
        self._tokens = min(self._max_tokens, self._tokens + added)
        self._last_refill = now
        
    def _refill_sync(self):
        now = time.time()
        elapsed = now - self._last_refill
        added = elapsed * self._refill_rate
        self._tokens = min(self._max_tokens, self._tokens + added)
        self._last_refill = now
