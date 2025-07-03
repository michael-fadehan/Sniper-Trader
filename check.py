import ssl
import certifi
ctx = ssl.create_default_context()
ctx.load_verify_locations(certifi.where())
print("SSL context loaded successfully!")

import asyncio
import websockets

async def test_ws():
    uri = "wss://api.mainnet-beta.solana.com"
    async with websockets.connect(uri) as ws:
        print("WebSocket connection successful!")

asyncio.run(test_ws())