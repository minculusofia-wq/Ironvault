"""
Market Data Module
Handles interaction with Polymarket Gamma API for market discovery and data retrieval.
Independent of the CLOB execution layer.
"""

import requests
import time
from typing import Any
from .audit_logger import AuditLogger

class GammaClient:
    """
    Client for Polymarket Gamma API (Market Discovery).
    """
    
    def __init__(self, api_url: str, audit_logger: AuditLogger):
        self._base_url = api_url.rstrip('/')
        self._audit = audit_logger
        self._session = requests.Session()
        
    def get_market(self, condition_id: str) -> dict[str, Any] | None:
        """
        Fetch specific market details by condition ID.
        """
        try:
            url = f"{self._base_url}/markets/{condition_id}"
            response = self._session.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self._audit.log_error("GAMMA_API_ERROR", f"Failed to fetch market {condition_id}: {str(e)}")
            return None

    def get_events(self, limit: int = 20, volume_min: float = 0) -> list[dict[str, Any]]:
        """
        Scan for active events.
        """
        try:
            url = f"{self._base_url}/events"
            params = {
                "limit": limit,
                "closed": False,
                "order": "volume_24h",
                "ascending": False
            }
            response = self._session.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            events = response.json()
            
            # Additional client-side filtering if needed (e.g. min volume if API doesnt support fully)
            # Gamma usually supports volume sort, filtering here just in case specific logic needed
            
            return events
            
        except Exception as e:
            self._audit.log_error("GAMMA_API_ERROR", f"Scan failed: {str(e)}")
            return []
