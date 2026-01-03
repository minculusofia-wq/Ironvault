import asyncio
import aiohttp
import websockets
import ssl
import certifi
import time

async def test_connectivity():
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    
    # 1. Test Gamma API
    print("Testing Gamma API...")
    try:
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
            async with session.get("https://gamma-api.polymarket.com/events?limit=1", timeout=10) as resp:
                print(f"Gamma API Status: {resp.status}")
                if resp.status == 200:
                    data = await resp.json()
                    print(f"Gamma API OK. Events found: {len(data)}")
    except Exception as e:
        print(f"Gamma API Error: {e}")

    # 2. Test WebSocket
    print("\nTesting WebSocket...")
    ws_url = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    try:
        start = time.time()
        async with websockets.connect(ws_url, ssl=ssl_context, open_timeout=10) as ws:
            duration = time.time() - start
            print(f"WebSocket Connected in {duration:.2f}s")
            # Try to send a heartbeat or subscribe
            await ws.send('{"type": "ping"}')
            print("Ping sent.")
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                print(f"Received: {msg}")
            except Exception as e:
                print(f"No response to ping: {e}")
    except Exception as e:
        print(f"WebSocket Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_connectivity())
