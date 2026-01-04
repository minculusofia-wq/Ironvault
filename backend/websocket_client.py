"""
WebSocket Client Module
Handles real-time connection to Polymarket CLOB WebSocket API.
Maintains live OrderBook state via delta updates.
"""

import asyncio
import logging
import ssl
import certifi
import websockets
from typing import Dict, Callable, Any

try:
    import orjson
    # orjson returns bytes, which websockets can send directly
    json_dumps = lambda x: orjson.dumps(x).decode('utf-8') 
    json_loads = orjson.loads
except ImportError:
    import json
    json_dumps = json.dumps
    json_loads = json.loads

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
        self._audit.log_system_event("SSL_CONTEXT_CREATED", {"cafile": certifi.where()})

        self._reconnect_task: asyncio.Task | None = None
        self._retry_delay = 1.0
        self._max_retry_delay = 60.0

        # v3.0: Reduce log spam - only log every Nth subscription
        self._sub_count = 0
        self._sub_log_interval = 50  # Log every 50 subscriptions

    async def start(self):
        """Start the background connection manager."""
        if self._running:
            return
        self._running = True
        self._reconnect_task = asyncio.create_task(self._connection_manager())

    async def stop(self):
        """Stop the background connection manager and disconnect."""
        self._running = False
        if self._reconnect_task:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
        await self.disconnect()

    @property
    def is_connected(self) -> bool:
        """Check if websocket is connected safely across versions."""
        if self._ws is None:
            return False
        
        # Check for .state (State.OPEN == 1)
        if hasattr(self._ws, 'state'):
            return self._ws.state == 1
            
        try:
            # Modern websockets (10.0+)
            return not self._ws.closed
        except AttributeError:
            try:
                # Legacy websockets
                return self._ws.open
            except AttributeError:
                return False

    async def _connection_manager(self):
        """Background task to maintain connection with exponential backoff."""
        while self._running:
            try:
                if not self.is_connected:
                    self._audit.log_system_event("WS_CONNECTING", {"url": self._url})
                    async with asyncio.timeout(10): # 10s timeout for handshake
                        self._ws = await websockets.connect(self._url, ssl=self._ssl_context)
                    
                    self._retry_delay = 1.0 # Reset delay on success
                    self._audit.log_system_event("WS_CONNECTED", {"url": self._url})
                    
                    # Re-subscribe to all tokens
                    async with self._lock:
                        for token_id in self._book_callbacks:
                            await self._send_subscribe(token_id)
                    
                    # Start listening
                    await self._listen()
            except asyncio.TimeoutError:
                self._audit.log_error("WS_CONNECT_TIMEOUT", "Handshake timed out")
            except Exception as e:
                self._audit.log_error("WS_CONNECT_ERROR", str(e))
            
            if self._running:
                self._audit.log_system_event("WS_RETRY_WAIT", {"delay": self._retry_delay})
                await asyncio.sleep(self._retry_delay)
                self._retry_delay = min(self._retry_delay * 2, self._max_retry_delay)

    async def disconnect(self):
        """Close the WebSocket connection."""
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
            if self.is_connected:
                await self._send_subscribe(token_id)

    async def _send_subscribe(self, token_id: str):
        """Helper to send subscription message."""
        try:
            # v3.0: Correct Polymarket WebSocket subscription format
            # Docs: https://docs.polymarket.com/quickstart/websocket/WSS-Quickstart
            msg = {
                "type": "market",
                "assets_ids": [token_id]
            }
            await self._ws.send(json_dumps(msg))

            # v3.0: Reduce log spam - only log every Nth subscription
            self._sub_count += 1
            if self._sub_count % self._sub_log_interval == 0:
                self._audit.log_system_event("WS_SUBSCRIBED_BATCH", {
                    "count": self._sub_count,
                    "latest_token": token_id[:16] + "..."
                })
        except Exception as e:
            self._audit.log_error("WS_SUB_ERROR", str(e))

    async def _listen(self):
        """Main message loop."""
        try:
            async for msg in self._ws:
                if not self._running:
                    break

                # v3.0: Skip empty messages (keep-alive, ping responses)
                if not msg or (isinstance(msg, str) and not msg.strip()):
                    continue

                try:
                    data = json_loads(msg)
                except (ValueError, TypeError):
                    # Non-JSON message (ping/pong text, status messages) - skip silently
                    continue

                event_type = data.get("event_type") or data.get("type")

                # v3.0: Handle multiple Polymarket event types
                # Docs: book, price_change, tick_size_change, last_trade_price
                if event_type in ("book", "price_change"):
                    # Try multiple field names for token ID
                    token_id = (data.get("asset_id") or data.get("token_id")
                               or data.get("market") or data.get("market_id"))

                    if token_id and token_id in self._book_callbacks:
                        for cb in self._book_callbacks[token_id]:
                            try:
                                cb(data)
                            except Exception as e:
                                self._audit.log_error("WS_CALLBACK_ERROR", str(e))
        except websockets.exceptions.ConnectionClosed:
            self._audit.log_system_event("WS_CLOSED", "Connection closed")
        except Exception as e:
            self._audit.log_error("WS_LISTEN_ERROR", str(e))
        finally:
            self._ws = None
