# this file mocks the IoT device and cloud video processing job
import requests

SERVER_ENDPOINT = "http://localhost:8000"

def test_push_rt_notif():
    response = requests.get(f"{SERVER_ENDPOINT}/rt-notification")
    print(response.json())

def test_push_video_clip_notif():
    response = requests.post(f"{SERVER_ENDPOINT}/video-clip", json={"video_link": "s3link"})
    print(response.json())

if __name__ == "__main__":
    test_push_rt_notif()
    test_push_video_clip_notif()