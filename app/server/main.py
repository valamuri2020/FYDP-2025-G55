# to run the server: poetry run python3 main.py
# to test the server: curl localhost:8000/rt-notification
# curl --header "Content-Type: application/json" --request POST --data '{"message":"BIRD!!"}' http://localhost:8000/rt-notification
import os
from typing import List
from dotenv import load_dotenv  
import pydantic
import uvicorn
import boto3
from botocore.exceptions import NoCredentialsError, PartialCredentialsError
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
import sys

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
# init server
app = FastAPI()

manager = ConnectionManager()

# Load environment variables
load_dotenv()

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
    print("Pushing notification to front-end")
    await manager.broadcast("RT Notification: Birds at the feeder!")
    # upload to s3 bucket
    
@app.post("/video-clip")
async def push_video_clip_notif(data: VideoClipRequest):
    # push the video to the front-end
    await manager.broadcast(data.video_link)


# Initialize the S3 client
aws_access_key_id = os.environ['AWS_ACCESS_KEY_ID']
aws_secret_access_key = os.environ['AWS_SECRET_ACCESS_KEY']
BUCKET_NAME = os.environ['BUCKET_NAME']

s3 = boto3.client(
    's3',
    aws_access_key_id=aws_access_key_id,
    aws_secret_access_key=aws_secret_access_key
)

def upload_to_s3(file_name: str, file_content: bytes, content_type: str):
    print(f"Uploading {file_name} to S3 has content type {content_type}")
    print("Uploading to S3 bucket: ", BUCKET_NAME)

    try:
        s3.put_object(Bucket=BUCKET_NAME, Key=file_name, Body=file_content, ContentType=content_type)
    except NoCredentialsError:
        print("AWS credentials not found.")
    except PartialCredentialsError:
        print("Incomplete AWS credentials.")
    except Exception as e:
        print(f"An error occurred: {str(e)}")

@app.post("/upload")
async def upload_file(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    try:
        # Read file contents
        file_contents = await file.read()
        if file_contents is None:
            print("File contents are None")
            raise HTTPException(status_code=400, detail="File contents are None")
        
        print(f"Received file: {file.filename} - {len(file_contents)} bytes.")
        
        # Add the upload task to the background
        background_tasks.add_task(upload_to_s3, file.filename, file_contents, file.content_type or "image/png")

        return {"filename": file.filename, "bucket": BUCKET_NAME, "message": "Upload in progress"}
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app=app, host=sys.argv[1], port=8000)