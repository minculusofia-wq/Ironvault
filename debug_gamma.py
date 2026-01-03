import asyncio
import aiohttp
import ssl
import certifi
import json

async def inspect_gamma():
    url = "https://gamma-api.polymarket.com/events?limit=2&closed=false"
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(ssl=ssl_context)
    
    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.get(url) as response:
            data = await response.json()
            if isinstance(data, list) and len(data) > 0:
                event = data[0]
                print("Event ID:", event.get('id'))
                print("Event Keys:", event.keys())
                
                markets = event.get('markets', [])
                if markets:
                    print("First Market Keys:", markets[0].keys())
                    print("First Market ID:", markets[0].get('id'))
                    print("First Market clobTokenIds:", markets[0].get('clobTokenIds'))
                    print("First Market Dump:", json.dumps(markets[0], indent=2))
                else:
                    print("No markets in event")
            else:
                print("No data or unexpected format:", data)

if __name__ == "__main__":
    asyncio.run(inspect_gamma())
