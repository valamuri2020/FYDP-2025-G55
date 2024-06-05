import asyncio
import websockets

async def listen():
    uri = "ws://localhost:8000/ws"
    async with websockets.connect(uri) as websocket:
        await websocket.send("Connecting to server...")
        while True:
            message = await websocket.recv()
            print(f"Received message: {message}")

asyncio.run(listen())