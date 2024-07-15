import asyncio
import websockets
import sys


async def listen():
    uri = f"ws://{sys.argv[1]}:8000/ws"
    async with websockets.connect(uri) as websocket:
        await websocket.send("Connecting to server...")
        while True:
            message = await websocket.recv()
            print(f"Received message: {message}")

asyncio.run(listen())
