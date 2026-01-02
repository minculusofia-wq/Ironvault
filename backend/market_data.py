"""
Market Data Module
Handles interaction with Polymarket Gamma API for market discovery and data retrieval.
AsyncIO implementation using aiohttp.
"""

import aiohttp
import asyncio
import ssl
import certifi
from typing import Any
from .audit_logger import AuditLogger

class GammaClient:
    """
    Async Client for Polymarket Gamma API (Market Discovery).
    """
    
    def __init__(self, api_url: str, audit_logger: AuditLogger):
        self._base_url = api_url.rstrip('/')
        self._audit = audit_logger
        self._session: aiohttp.ClientSession | None = None
        
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session
    
    async def close(self):
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_market(self, condition_id: str) -> dict[str, Any] | None:
        """
        Fetch specific market details by condition ID.
        """
        try:
            session = await self._get_session()
            url = f"{self._base_url}/markets/{condition_id}"
            
            async with session.get(url, timeout=10) as response:
                response.raise_for_status()
                return await response.json()
                
        except Exception as e:
            self._audit.log_error("GAMMA_API_ERROR", f"Failed to fetch market {condition_id}: {str(e)}")
            return None

    async def get_events(self, limit: int = 20, volume_min: float = 0) -> list[dict[str, Any]]:
        """
        Scan for active events asynchronously.
        """
        try:
            session = await self._get_session()
            url = f"{self._base_url}/events"
            params = {
                "limit": limit,
                "closed": "false"
            }
            # Note: boolean params in requests can differ from aiohttp params handling 
            # (aiohttp often needs str for bools in params dict if strict)
            
            async with session.get(url, params=params, timeout=10) as response:
                response.raise_for_status()
                events = await response.json()
            
            return events
            
        except Exception as e:
            self._audit.log_error("GAMMA_API_ERROR", f"Scan failed: {str(e)}")
            return []
