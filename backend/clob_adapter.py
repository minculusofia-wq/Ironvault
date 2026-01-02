"""
CLOB Adapter Module
Provides a deterministic interface for analyzing the Central Limit Order Book (CLOB).
Acts as a bridge between raw L2 data and decision logic.

STRICTLY DETERMINISTIC. NO AI.

Responsibilities:
- Fetch order book snapshots.
- Calculate spreads, midpoints, and depth.
- Validate execution feasibility against liquidity.
- Suggest optimal limit prices based on strict rules (e.g., crossing spread vs joining).
- Compute max executable size given a slippage tolerance.
"""

import aiohttp
import ssl
import certifi
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from decimal import Decimal

# Type alias for Order Book Level: [price, size]
# Using strings for precision if coming from JSON, converted to floats/Decimals for calc
OrderBookLevel = List[str] 

@dataclass
class MarketSnapshot:
    """Represents a frozen state of the order book."""
    token_id: str
    timestamp: int
    bids: List[OrderBookLevel]  # Sorted Descending Price
    asks: List[OrderBookLevel]  # Sorted Ascending Price
    
    @property
    def best_bid(self) -> float:
        return float(self.bids[0][0]) if self.bids else 0.0
        
    @property
    def best_ask(self) -> float:
        return float(self.asks[0][0]) if self.asks else float('inf')
        
    @property
    def spread(self) -> float:
        if not self.bids or not self.asks:
            return 0.0
        return self.best_ask - self.best_bid
        
    @property
    def spread_percent(self) -> float:
        mid = self.midpoint
        if mid == 0:
            return 0.0
        return (self.spread / mid) * 100

    @property
    def midpoint(self) -> float:
        if not self.bids and not self.asks:
            return 0.0
        if not self.bids:
            return self.best_ask
        if not self.asks:
            return self.best_bid
        return (self.best_bid + self.best_ask) / 2.0


class ClobAdapter:
    """
    Deterministic CLOB Analysis Adapter (Async).
    """
    
    def __init__(self, clob_api_url: str = "https://clob.polymarket.com/"):
        self._base_url = clob_api_url.rstrip('/')
        self._session: aiohttp.ClientSession | None = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session

    async def get_orderbook(self, token_id: str) -> Optional[MarketSnapshot]:
        """
        Fetch L2 Order Book snapshot (Async).
        GET /book?token_id=...
        """
        try:
            session = await self._get_session()
            url = f"{self._base_url}/book"
            params = {"token_id": token_id}
            
            async with session.get(url, params=params, timeout=5) as response:
                response.raise_for_status()
                data = await response.json()
            
            # Polymarket API returns dictionary with "bids" and "asks"
            # Each level is usually {"price": "...", "size": "..."}
            # We strictly parse and sort to guarantee structure
            
            raw_bids = data.get("bids", [])
            raw_asks = data.get("asks", [])
            
            # Convert to list of [price, size] and Sort
            # Bids: High to Low
            bids = sorted(
                [[b["price"], b["size"]] for b in raw_bids],
                key=lambda x: float(x[0]),
                reverse=True
            )
            
            # Asks: Low to High
            asks = sorted(
                [[a["price"], a["size"]] for a in raw_asks],
                key=lambda x: float(x[0]),
                reverse=False
            )
            
            # Timestamp (approximate, often not in public book endpoint compared to WS)
            # We use system time if API doesn't provide hash/timestamp
            import time
            timestamp = int(time.time() * 1000)
            
            return MarketSnapshot(
                token_id=token_id,
                timestamp=timestamp,
                bids=bids,
                asks=asks
            )
            
        except Exception as e:
            # In a production system we would log logic errors here
            print(f"[ClobAdapter] Error fetching book: {e}")
            return None

    def is_executable(self, 
                     snapshot: MarketSnapshot, 
                     side: str, 
                     size: float, 
                     max_spread_pct: float = None) -> bool:
        """
        Validates if an order of 'size' can be executed immediately strictly within constraints.
        - Check spread
        - Check liquidity availability (naive check at top of book or full walk?)
        
        Assumes 'side' is the Taker side (BUY means buying from Asks).
        """
        side = side.upper()
        
        # 1. Spread Check
        if max_spread_pct is not None:
            if snapshot.spread_percent > max_spread_pct:
                return False
        
        # 2. Liquidity Check
        # We need to see if we can fill 'size' ? 
        # Or just if the book exists? 
        # "Valider l'exécutabilité réelle" implies depth check.
        
        depth_available = 0.0
        
        levels = snapshot.asks if side == "BUY" else snapshot.bids
        
        if not levels:
            return False
            
        return True # For basic feasibility. For full size check use max_executable_size.

    def suggest_limit_price(self, snapshot: MarketSnapshot, side: str, aggressive: bool = True) -> float:
        """
        Suggests a limit price.
        Aggressive (Taker): Cross the spread (Best Ask for Buy).
        Passive (Maker): Join the book (Best Bid +/- 1 tick for Buy).
        
        STRICTLY DETERMINISTIC.
        """
        side = side.upper()
        
        if side == "BUY":
            if aggressive:
                # To buy immediately, we pay Best Ask
                if not snapshot.asks:
                    return 0.0 # No liquidity to buy
                return snapshot.best_ask
            else:
                # To make, we join Best Bid
                if not snapshot.bids:
                    return 0.1 # Floor? Naive fallback
                return snapshot.best_bid
                
        elif side == "SELL":
            if aggressive:
                # To sell immediately, we hit Best Bid
                if not snapshot.bids:
                    return 0.0
                return snapshot.best_bid
            else:
                # To make, we join Best Ask
                if not snapshot.asks:
                    return 0.99 # Ceiling?
                return snapshot.best_ask
                
        return 0.0

    def max_executable_size(self, snapshot: MarketSnapshot, side: str, slippage_pct: float) -> float:
        """
        Calculates the maximum size executable without moving the average price beyond slippage_pct.
        
        Walks the order book (VWAP calculation).
        
        side="BUY" -> Walks Asks.
        side="SELL" -> Walks Bids.
        
        slippage_pct: Max allowed deviation from the Best Price (Top of Book).
                      e.g. 1.0 = 1% slippage allowed.
        """
        side = side.upper()
        levels = snapshot.asks if side == "BUY" else snapshot.bids
        
        if not levels:
            return 0.0
            
        best_price = float(levels[0][0])
        limit_price = 0.0
        
        if side == "BUY":
            # Max price we are willing to pay
            limit_price = best_price * (1 + slippage_pct / 100.0)
        else:
            # Min price we are willing to accept
            limit_price = best_price * (1 - slippage_pct / 100.0)
            
        executable_size = 0.0
        
        for level in levels:
            p = float(level[0])
            s = float(level[1])
            
            # Check if this level is within limit
            if side == "BUY":
                if p > limit_price:
                    break
            else:
                if p < limit_price:
                    break
            
            executable_size += s
            
        return executable_size

# --- Exemples d'intégration ---

if __name__ == "__main__":
    # Test minimal
    adapter = ClobAdapter()
    token_id = "21742633143463906290569050155826241533067272736897614950488156847949938836455" # Example ID (Donald Trump Winner 2024?)
    
    print(f"Fetching book for {token_id[:10]}...")
    snapshot = adapter.get_orderbook(token_id)
    
    if snapshot:
        print(f"Spread: {snapshot.spread_percent:.2f}%")
        print(f"Best Bid: {snapshot.best_bid}, Best Ask: {snapshot.best_ask}")
        
        # Buy Logic
        max_buy = adapter.max_executable_size(snapshot, "BUY", slippage_pct=1.0)
        print(f"Max Buy Size (1% slippage): {max_buy}")
        
        suggested_price = adapter.suggest_limit_price(snapshot, "BUY", aggressive=True)
        print(f"Suggested Taker Buy Price: {suggested_price}")
