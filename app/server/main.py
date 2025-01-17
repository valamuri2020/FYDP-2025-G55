# to run the server: poetry run python3 main.py
# to test the server: curl localhost:8000/rt-notification
# curl --header "Content-Type: application/json" --request POST --data '{"message":"BIRD!!"}' http://localhost:8000/rt-notification
import os
from typing import List
from dotenv import load_dotenv  
import pydantic
import uvicorn
import boto3
import json
import asyncio
import websockets
from botocore.exceptions import NoCredentialsError, PartialCredentialsError
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
import sys
from botocore import UNSIGNED
from botocore.client import Config
import subprocess
import tempfile
import shutil

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
        await manager.broadcast(json.dumps({"message": "Connected to notification server"}))
        while True:
            data = await websocket.receive_text()
            print(data)
            try:
                json_data = json.loads(data)
                action = json_data.get('action')
                print('parsed action', action)
                
                if action == 'schedule_notification':
                    title = json_data.get('title', 'Notification')
                    body = json_data.get('body', 'You have a new notification')
                    delay = json_data.get('delay', 5)
                    
                    # Send the notification data back to the client
                    await manager.broadcast(json.dumps({
                        "action": "schedule_notification",
                        "title": title,
                        "body": body,
                        "delay": delay
                    }))
                else:
                    await manager.broadcast(json.dumps({"error": "Invalid action"}))
            
            except json.JSONDecodeError:
                await manager.broadcast(json.dumps({"error": "Invalid JSON"}))

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        print("Client disconnected")

# Route is hit by device, pushes notification to front-end
@app.get("/rt-notification-bird")
async def push_rt_notif():
    # push the notification to the front-end
    uri = "ws://54.161.131.68:8000/ws"
    async with websockets.connect(uri) as websocket:
        message = json.dumps({
            "action": "schedule_notification",
            "title": "Bird arrived",
            "body": "A bird has shown up at the birdfeeder!",
            "delay": 1
        })
        print(f"Sending message: {message}")
        await websocket.send(message)
        print("Message sent, waiting for response...")
        response = await websocket.recv()
        print(f"Received response: {response}")

@app.get("/rt-notification-seed")
async def push_rt_notif():
    # push the notification to the front-end
    uri = "ws://54.161.131.68:8000/ws"
    async with websockets.connect(uri) as websocket:
        message = json.dumps({
            "action": "schedule_notification",
            "title": "Seed is low",
            "body": "Please refill the seed in the birdfeeder",
            "delay": 1
        })
        print(f"Sending message: {message}")
        await websocket.send(message)
        print("Message sent, waiting for response...")
        response = await websocket.recv()
        print(f"Received response: {response}")
    
@app.post("/video-clip")
async def push_video_clip_notif(data: VideoClipRequest):
    # push the video to the front-end
    await manager.broadcast(data.video_link)


# Initialize the S3 client
aws_access_key_id = os.environ['AWS_ACCESS_KEY_ID']
aws_secret_access_key = os.environ['AWS_SECRET_ACCESS_KEY']
BUCKET_NAME = "wingwatcher-videos"


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

@app.get("/get-videos")
async def get_videos():
    try:
        bucket_name = 'wingwatcher-videos'
        bucket_list = s3.list_objects_v2(Bucket=bucket_name)
        response = []
        if 'Contents' in bucket_list:
            for obj in bucket_list['Contents']:
                if obj['Key'].startswith("videos/") and len(obj["Key"]) > 7:
                    print(obj['Key'])
                    response.append({"title": obj['Key'], "videoLink": "https://wingwatcher-videos.s3.amazonaws.com/" + obj['Key']})
            return response
        else:
            print(f"No files found in bucket {bucket_name}")
        return bucket_list
        
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

def is_jpeg(data):
    # Check if the data starts with the JPEG start marker and ends with the JPEG end marker
    return data.startswith(b'\xff\xd8') and data.endswith(b'\xff\xd9')

def process_bin_file(bin_file: UploadFile, output_dir: str, video_file: str):
    with open(bin_file.filename, 'rb') as f:
        data = f.read()
    
    start = 0
    end = 0
    image_number = 0
    
    image_files = []

    while True:
        start = data.find(b'\xff\xd8', end)
        if start == -1:
            break
        end = data.find(b'\xff\xd9', start)
        if end == -1:
            break
        end += 2
        image_data = data[start:end]
        
        if is_jpeg(image_data):
            with open(os.path.join(output_dir, f'frame_{image_number:04d}.jpg'), 'wb') as img_file:
                img_file.write(image_data)
                image_files.append(f'frame_{image_number:04d}.jpg')
            image_number += 1

        print(f'Extracted {image_number} images to {output_dir}')

    # Create a video from the images using ffmpeg
    if image_files:
        # Assuming images are named image_001.jpg, image_002.jpg, ...
        ffmpeg_input_pattern = os.path.join(output_dir, 'frame_%04d.jpg')
        subprocess.run(['ffmpeg', '-framerate', '20', '-i', ffmpeg_input_pattern, '-c:v', 'libx264', '-pix_fmt', 'yuv420p', video_file])
    
        # Upload the video to S3
        video_bytes = open(video_file, 'rb').read()
        upload_to_s3(os.path.join("video_", os.path.basename(video_file)), video_bytes, 'video/mp4')

        # Clean up the temporary files
        shutil.rmtree(output_dir)
        shutil.rmtree(os.path.dirname(video_file))
    else:
        print("No images were extracted from the .bin file.")


@app.post("/upload-bin")
async def upload_bin_file(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    try:
        temp_dir = "temp"
        output_dir = os.path.join(temp_dir, "images")
        os.makedirs(output_dir, exist_ok=True)
        video_filepath = os.path.join(temp_dir, "videos", "output_video_" + file.filename + ".mp4")
        os.makedirs(os.path.dirname(video_filepath), exist_ok=True)
        background_tasks.add_task(process_bin_file, file, output_dir, video_filepath)
    
        return {"filename": file.filename, "message": "Processing in background"}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run(app=app, host=sys.argv[1], port=8000)
