# this file mocks the IoT device and cloud video processing job
import requests
import sys

SERVER_ENDPOINT = f"http://{sys.argv[1]}:8000"

def test_push_rt_notif():
    response = requests.get(f"{SERVER_ENDPOINT}/rt-notification", timeout=9)
    print(response.json())

def test_push_video_clip_notif():
    response = requests.post(f"{SERVER_ENDPOINT}/video-clip", json={"video_link": "s3link"})
    print(response.json())

def test_upload_file(file_path: str):
    with open(file_path, 'rb') as file:
        files = {'file': (file_path, file)}
        
        response = requests.post(f"{SERVER_ENDPOINT}/upload", files=files)
        
        if response.status_code == 200:
            print("File uploaded successfully")
            print("Response:", response.json())
        else:
            print("Failed to upload file")
            print("Status code:", response.status_code)
            print("Response:", response.text)


if __name__ == "__main__":
    # print("testing GET request, rt notifaction")
    # test_push_rt_notif()
    # print("done testing http method")
#    test_push_video_clip_notif()
    test_upload_file("bird_test_image.png")