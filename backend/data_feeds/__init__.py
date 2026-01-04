"""
Data Feeds Module
Multi-source data aggregation for Strategy A (Front-Running) triggers.

Available feeds:
- PolymarketPriceMonitor: Detects price movements on Polymarket itself
- BaseFeed: Abstract interface for all feeds
"""

from .base_feed import BaseFeed, FeedTrigger, TriggerType
from .polymarket_feed import PolymarketPriceMonitor

__all__ = [
    'BaseFeed',
    'FeedTrigger',
    'TriggerType',
    'PolymarketPriceMonitor'
]
