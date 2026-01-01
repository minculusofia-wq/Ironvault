"""
Live OrderBook Module
Maintains a local, up-to-date copy of the OrderBook using delta updates.
"""

from dataclasses import dataclass
from typing import List, Dict
import time

from .clob_adapter import MarketSnapshot

@dataclass
class OrderBookLevel:
    price: float
    size: float

class LiveOrderBook:
    """
    Maintains state of a single market's order book.
    """
    def __init__(self, token_id: str):
        self.token_id = token_id
        self.bids: Dict[float, float] = {} # price -> size
        self.asks: Dict[float, float] = {} # price -> size
        self.timestamp = 0
        
    def apply_snapshot(self, bids: List[list], asks: List[list], timestamp: int = 0):
        """Reset book from snapshot."""
        self.bids.clear()
        self.asks.clear()
        
        for p, s in bids:
            self.bids[float(p)] = float(s)
            
        for p, s in asks:
            self.asks[float(p)] = float(s)
            
        self.timestamp = timestamp or int(time.time() * 1000)
        
    def apply_delta(self, side: str, price: float, size: float):
        """Apply a single update."""
        target = self.bids if side == "buy" else self.asks
        
        if size == 0:
            if price in target:
                del target[price]
        else:
            target[price] = size
            
    def get_snapshot(self) -> MarketSnapshot:
        """Convert to MarketSnapshot for strategies."""
        # Sort Bids Descending
        sorted_bids = sorted(
            [[str(p), str(s)] for p, s in self.bids.items()],
            key=lambda x: float(x[0]),
            reverse=True
        )
        
        # Sort Asks Ascending
        sorted_asks = sorted(
            [[str(p), str(s)] for p, s in self.asks.items()],
            key=lambda x: float(x[0]),
            reverse=False
        )
        
        return MarketSnapshot(
            token_id=self.token_id,
            timestamp=self.timestamp,
            bids=sorted_bids,
            asks=sorted_asks
        )
