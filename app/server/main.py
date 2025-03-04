# to run the server: poetry run python3 main.py
# to test the server: curl localhost:8000/rt-notification
# curl --header "Content-Type: application/json" --request POST --data '{"message":"BIRD!!"}' http://localhost:8000/rt-notification
import os
import re
import datetime
from datetime import timedelta
import pytz
from pytz import timezone
from typing import List
from dotenv import load_dotenv  
import pydantic
import uvicorn
import boto3
import json
import asyncio
import websockets
from botocore.exceptions import NoCredentialsError, PartialCredentialsError
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect, Request
import sys
from botocore import UNSIGNED
from botocore.client import Config
import subprocess
import tempfile
import shutil
import jwt
import httpx

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

APNS_HOST = "https://api.push.apple.com"  # Use this for development; switch to production when needed
APNS_KEY_FILE = os.environ["APNS_KEY_FILE"]
APNS_KEY_ID = os.environ["APNS_KEY_ID"]
TEAM_ID = os.environ["TEAM_ID"]
APP_BUNDLE_ID = os.environ["APP_BUNDLE_ID"]

# --- S3 Configuration ---
DEVICE_TOKENS_FILE = "device_tokens.json"  # File in S3 where device tokens are stored
# BUCKET_NAME = os.environ["DEVICE_TOKEN_BUCKET"]

LAST_CONNECTED_FILE = "last_connected.json"  # File in S3 where last connected time is stored

def fetch_device_tokens() -> List[str]:
    """Fetch the list of device tokens stored in the S3 bucket."""
    try:
        response = s3.get_object(Bucket=BUCKET_NAME, Key=DEVICE_TOKENS_FILE)
        tokens = json.loads(response['Body'].read().decode('utf-8'))
        return tokens.get("device_tokens", [])
    except s3.exceptions.NoSuchKey:
        # If file doesn't exist, return an empty list
        return []
    except Exception as e:
        print(f"Error fetching device tokens: {str(e)}")
        return []

def store_device_token(device_token: str):
    """Store a new device token in the S3 bucket."""
    tokens = fetch_device_tokens()
    if device_token not in tokens:
        tokens.append(device_token)

        # Update the token file in S3
        s3.put_object(
            Bucket=BUCKET_NAME,
            Key=DEVICE_TOKENS_FILE,
            Body=json.dumps({"device_tokens": tokens}),
            ContentType='application/json'
        )
        print(f"Device token stored: {device_token}")
    else:
        print(f"Device token {device_token} is already registered.")

def store_last_connected():
    # Update the token file in S3
    tz = timezone('EST')
    time = datetime.datetime.now(tz) 
    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=LAST_CONNECTED_FILE,
        Body=json.dumps({"last_connected": time.strftime("%Y%m%d_%H%M%S")}),
        ContentType='application/json'
    )

def create_apns_jwt():
    with open(APNS_KEY_FILE, "r") as key_file:
        private_key = key_file.read()
    payload = {
        "iss": TEAM_ID,
        "iat": int(datetime.datetime.now(datetime.UTC).timestamp())
    }
    # print(jwt.encode(payload, private_key, algorithm="ES256", headers={"kid": APNS_KEY_ID}))
    return jwt.encode(payload, private_key, algorithm="ES256", headers={"kid": APNS_KEY_ID})

async def send_push_notification(device_token: str, title: str, body: str):
    token = create_apns_jwt()
    
    headers = {
        "authorization": f"bearer {token}",
        "apns-topic": APP_BUNDLE_ID,
        "apns-priority": "10"
    }

    payload = {
        "aps": {
            "alert": {
                "title": title,
                "body": body
            },
            "sound" : "default",
            "badge" : 10,
        }
    }

    async with httpx.AsyncClient(http2=True) as client:
        try:
            url = f"{APNS_HOST}/3/device/{device_token}"
            print(f"Sending request to: {url}")
            response = await client.post(url, headers=headers, json=payload)

            print(f"APNs Response: {response.status_code}")
            if response.status_code != 200:
                print(f"Response Error: {response.text}")

        except httpx.RequestError as e:
            print(f"An error occurred while requesting APNs: {str(e)}")

@app.get("/save-last-connected")
async def save_last_connected():
    store_last_connected()
    return {"message": "Saved last connected timestamp"}

@app.post("/register-device")
async def register_device_token(request: Request):
    data = await request.json()
    device_token = data.get("device_token")
    if device_token:
        store_device_token(device_token)
        return {"message": "Device token registered successfully"}
    else:
        raise HTTPException(status_code=400, detail="Invalid or missing device token")

@app.get("/rt-notification-bird")
async def trigger_push_notification_bird(title: str = "Bird arrived", body: str = "A bird has shown up at the birdfeeder!"):
    tokens = fetch_device_tokens()
    if not tokens:
        raise HTTPException(status_code=400, detail="No device tokens registered")
    # print(tokens)
    # Send the notification to all registered devices
    for token in tokens:
        await send_push_notification(token, title, body)

    return {"message": "Push notification sent to all registered devices"}

@app.get("/rt-notification-seed")
async def trigger_push_notification_seed(title: str = "Seed is low", body: str = "Please refill the seed in the birdfeeder"):
    tokens = fetch_device_tokens()
    if not tokens:
        raise HTTPException(status_code=400, detail="No device tokens registered")
    # print(tokens)
    # Send the notification to all registered devices
    for token in tokens:
        await send_push_notification(token, title, body)

    return {"message": "Push notification sent to all registered devices"}

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

# # Route is hit by device, pushes notification to front-end
# @app.get("/rt-notification-bird")
# async def push_rt_notif():
#     # push the notification to the front-end
#     uri = "ws://54.161.131.68:8000/ws"
#     async with websockets.connect(uri) as websocket:
#         message = json.dumps({
#             "action": "schedule_notification",
#             "title": "Bird arrived",
#             "body": "A bird has shown up at the birdfeeder!",
#             "delay": 1
#         })
#         print(f"Sending message: {message}")
#         await websocket.send(message)
#         print("Message sent, waiting for response...")
#         response = await websocket.recv()
#         print(f"Received response: {response}")

# @app.get("/rt-notification-seed")
# async def push_rt_notif():
#     # push the notification to the front-end
#     uri = "ws://54.161.131.68:8000/ws"
#     async with websockets.connect(uri) as websocket:
#         message = json.dumps({
#             "action": "schedule_notification",
#             "title": "Seed is low",
#             "body": "Please refill the seed in the birdfeeder",
#             "delay": 1
#         })
#         print(f"Sending message: {message}")
#         await websocket.send(message)
#         print("Message sent, waiting for response...")
#         response = await websocket.recv()
#         print(f"Received response: {response}")
    
@app.post("/video-clip")
async def push_video_clip_notif(data: VideoClipRequest):
    # push the video to the front-end
    await manager.broadcast(data.video_link)


# Initialize the S3 client
aws_access_key_id = os.environ['AWS_ACCESS_KEY_ID']
aws_secret_access_key = os.environ['AWS_SECRET_ACCESS_KEY']
BUCKET_NAME = "wingwatcher-videos"
THRESHOLD = timedelta(seconds=10)
PROCESSED_BIN_COUNT = 0
BIN_PROCESS_THRESHOLD = 10



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

@app.get("/get-last-connected")
async def fetch_last_connected_timestamp():
    """Fetch the list of device tokens stored in the S3 bucket."""
    try:
        response = s3.get_object(Bucket=BUCKET_NAME, Key=LAST_CONNECTED_FILE)
        token = json.loads(response['Body'].read().decode('utf-8'))
        return token
    except s3.exceptions.NoSuchKey:
        # If file doesn't exist, return an empty list
        return []
    except Exception as e:
        print(f"Error fetching last connected: {str(e)}")
        return []

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
        upload_to_s3(os.path.join("videos", os.path.basename(video_file)), video_bytes, 'video/mp4')

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
        video_filepath = os.path.join(temp_dir, file.filename + ".mp4")
        os.makedirs(os.path.dirname(video_filepath), exist_ok=True)
        background_tasks.add_task(process_bin_file, file, output_dir, video_filepath)
        
        # PROCESSED_BIN_COUNT += 1
        # if PROCESSED_BIN_COUNT >= BIN_PROCESS_THRESHOLD:
        #     background_tasks.add_task(batch_video_files)
        #     PROCESSED_BIN_COUNT = 0
    
        return {"filename": file.filename, "message": "Processing in background"}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/upload-image")
async def upload_file(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    try:
        # Read file contents
        file_contents = await file.read()
        if file_contents is None:
            print("File contents are None")
            raise HTTPException(status_code=400, detail="File contents are None")
        
        print(f"Received file: {file.filename} - {len(file_contents)} bytes.")
        
        # Add the upload task to the background
        background_tasks.add_task(upload_to_s3, "images/" + file.filename, file_contents, file.content_type or "image/png")

        return {"filename": file.filename, "bucket": BUCKET_NAME, "message": "Upload in progress"}
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

def extract_timestamp_from_key(key):
    """
    Extract timestamp from the S3 object key.
    Assumes the filename contains a timestamp in the format YYYYMMDD_HHMMSS.
    Adjust the regex pattern according to your filename structure.
    """
    match = re.search(r'(\d{8}_\d{6})', key)
    if match:
        return datetime.datetime.strptime(match.group(1), '%Y%m%d_%H%M%S')
    return None

def list_videos():
    response = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix="videos/")
    video_list = response.get('Contents', [])
    return video_list

def group_video_files(video_list, threshold):

    grouped_video_files = []
    current_group = []

    for video in video_list:
        timestamp = extract_timestamp_from_key(video['Key'])
        if not timestamp:
            continue

        if current_group:
            last_timestamp = extract_timestamp_from_key(current_group[-1]['Key'])
            if timestamp - last_timestamp <= threshold:
                current_group.append(video)
            else:
                grouped_video_files.append(current_group)
                current_group = [video]
        else:
            current_group.append(video)
    
    if current_group not in grouped_video_files:
        grouped_video_files.append(current_group)

    return grouped_video_files

def download_video(bucket, key, download_path):
    """Download a video from S3 to the specified local path."""
    s3.download_file(bucket, key, download_path)

def concatenate_videos(video_paths, output_path):
    """Concatenate multiple videos into a single video using ffmpeg."""
    with tempfile.NamedTemporaryFile('w', delete=False) as list_file:
        for path in video_paths:
            list_file.write(f"file '{path}'\n")
        list_file_path = list_file.name

    subprocess.run(['ffmpeg', '-f', 'concat', '-safe', '0', '-i', list_file_path,
                    '-c', 'copy', output_path], check=True)
    os.remove(list_file_path)

def upload_video(bucket, key, file_path):
    """Upload a video file to S3."""
    s3.upload_file(file_path, bucket, key)

def clean_up(files):
    """Remove temporary files."""
    for file in files:
        os.remove(file)

def delete_original_videos(bucket, keys):
    """Delete multiple objects from an S3 bucket."""
    objects = [{'Key': key} for key in keys]
    response = s3.delete_objects(Bucket=bucket, Delete={'Objects': objects})
    return response

def batch_video_files():
    videos = list_videos()
    videos = [v for v in videos if extract_timestamp_from_key(v['Key']) is not None]
    videos.sort(key=lambda v: extract_timestamp_from_key(v['Key']))
    grouped_vids = group_video_files(videos, THRESHOLD)

    for i, group in enumerate(grouped_vids):
        with tempfile.TemporaryDirectory() as temp_dir:
            video_paths = []
            original_keys = []
            if len(group) < 2:
                continue

            for video in group:
                video_key = video['Key']
                original_keys.append(video_key)
                download_path = os.path.join(temp_dir, os.path.basename(video_key))
                download_video(BUCKET_NAME, video_key, download_path)
                video_paths.append(download_path)

            output_filename = f"{extract_timestamp_from_key(group[0]['Key']).strftime('%Y%m%d_%H%M%S')}.mp4"
            output_path = os.path.join(temp_dir, output_filename)

            concatenate_videos(video_paths, output_path)

            upload_video(BUCKET_NAME, f"videos/{output_filename}", output_path)

            delete_original_videos(BUCKET_NAME, original_keys)

            clean_up(video_paths + [output_path])
    print("Video collation and concatenation completed")


if __name__ == "__main__":
    uvicorn.run(app=app, host=sys.argv[1], port=8000)
