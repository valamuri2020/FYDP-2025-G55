# to run the server: poetry run python3 main.py
# to test the server: curl localhost:8000/rt-notification
# curl --header "Content-Type: application/json" --request POST --data '{"message":"BIRD!!"}' http://localhost:8000/rt-notification

from typing import List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import pydantic
from dotenv import load_dotenv  
import uvicorn

class RTNotificationTestInput(pydantic.BaseModel):
    message: str

class VideoClipRequest(pydantic.BaseModel):
    video_link: str

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)
# Load environment variables
load_dotenv()
# init server
app = FastAPI()

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await manager.send_personal_message(f"Websocke connection complete!", websocket)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        print("Client disconnected")

# Route is hit by device, pushes notification to front-end
# Mocking the front-end with rt-notification-test, to be removed later
@app.get("/rt-notification")
async def push_rt_notif():
    # push the notification to the front-end
    await manager.broadcast("RT Notification: Birds at the feeder!")
    # upload to s3 bucket
    
@app.post("/video-clip")
async def push_video_clip_notif(data: VideoClipRequest):
    # push the video to the front-end
    await manager.broadcast(data.video_link)

if __name__ == "__main__":
    uvicorn.run(app=app, host="localhost", port=8000)