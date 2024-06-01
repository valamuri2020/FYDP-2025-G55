# to run the server: poetry run python3 main.py
# to test the server: curl localhost:8000/rt-notification
# curl --header "Content-Type: application/json" --request POST --data '{"video_link":"s3link"}' http://localhost:8000/video-clip

import os
import yaml
import requests
import fastapi
import pydantic
from dotenv import load_dotenv
import uvicorn

class RTNotificationTestInput(pydantic.BaseModel):
    message: str

# Load environment variables
class VideoClipRequest(pydantic.BaseModel):
    video_link: str

load_dotenv()

app = fastapi.FastAPI()

# Route is hit by device, pushes notification to front-end
# Mocking the front-end with rt-notification-test, to be removed later
@app.get("/rt-notification")
def push_rt_notif():
    # push the notification to the front-end
    requests.post("http://localhost:8000/rt-notification-test", json={"message": "Hello World"})
    # upload to s3 bucket
    
@app.post("/video-clip")
def push_video_clip_notif(data: VideoClipRequest):
    # push the video to the front-end
    print(data.video_link)
    # upload to s3 bucket


@app.post("/rt-notification-test")
def rt_notif_test(data: RTNotificationTestInput):
    print(data.message)

if __name__ == "__main__":
    uvicorn.run(app=app, host="127.0.0.1", port=8000)