"""
WebSocket Client Module
Handles real-time connection to Polymarket CLOB WebSocket API.
Maintains live OrderBook state via delta updates.
"""

import asyncio
import json
import logging
import ssl
import certifi
import websockets
from typing import Dict, Callable, Any

from .audit_logger import AuditLogger

class WebSocketClient:
    """
    Async WebSocket Client for Polymarket.
    Manages connection, subscriptions, and message dispatch.
    """
    
    def __init__(self, ws_url: str, audit_logger: AuditLogger):
        self._url = ws_url
        self._audit = audit_logger
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._running = False
        self._lock = asyncio.Lock()
        
        # Callbacks: token_id -> function(snapshot)
        self._book_callbacks: Dict[str, list[Callable[[Any], None]]] = {}
        
        # Setup SSL context for macOS
        self._ssl_context = ssl.create_default_context(cafile=certifi.where())
        
    async def connect(self):
        """Establish WebSocket connection."""
        try:
            self._ws = await websockets.connect(self._url, ssl=self._ssl_context)
            self._running = True
            self._audit.log_system_event("WS_CONNECTED", {"url": self._url})
            asyncio.create_task(self._listen())
        except Exception as e:
            self._audit.log_error("WS_CONNECT_ERROR", str(e))
            self._running = False
            self._ws = None
    async def disconnect(self):
        """Close the WebSocket connection."""
        self._running = False
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        self._audit.log_system_event("WS_DISCONNECTED")

    async def subscribe_orderbook(self, token_id: str, callback: Callable[[Any], None]):
        """
        Subscribe to orderbook updates for a token.
        """
        async with self._lock:
            if token_id not in self._book_callbacks:
                self._book_callbacks[token_id] = []
            self._book_callbacks[token_id].append(callback)
            
        # Send subscribe message if connected
        if self._ws and self._running:
            try:
                msg = {
                    "type": "subscribe",
                    "channel": "orderbook",
                    "token_id": token_id
                }
                await self._ws.send(json.dumps(msg))
                self._audit.log_system_event("WS_SUBSCRIBED", {"token": token_id})
            except Exception as e:
                self._audit.log_error("WS_SUB_ERROR", str(e))

    async def _listen(self):
        """Main message loop."""
        while self._running and self._ws:
            try:
                msg = await self._ws.recv()
                data = json.loads(msg)
                
                # Check for event type
                event_type = data.get("event_type") or data.get("type")
                
                if event_type == "book":
                    # Snapshot or Update
                    token_id = data.get("token_id") or data.get("market")
                    if token_id and token_id in self._book_callbacks:
                        for cb in self._book_callbacks[token_id]:
                            try:
                                cb(data)
                            except Exception as e:
                                self._audit.log_error("WS_CALLBACK_ERROR", str(e))
                                
            except websockets.exceptions.ConnectionClosed:
                self._audit.log_error("WS_CLOSED", "Connection closed unexpectedly")
                self._running = False
                self._ws = None
                break
            except Exception as e:
                self._audit.log_error("WS_ERROR", str(e))
                await asyncio.sleep(1)
