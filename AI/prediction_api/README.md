# Gesture Prediction API

This folder runs the MediaPipe gesture model as an HTTP service. Run it on the
computer that has the model; the Raspberry Pi sends images to that computer.

## 1. Run the server on the PC

Open PowerShell on the PC that contains this project, then run:

```powershell
cd D:\AI_ALL\IOT\AI\prediction_api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

Keep this terminal open while using the API. By default, it uses
`..\models\gesture_recognizer.task` from this project. To use a different
model, set `GESTURE_MODEL_PATH` to its full path before starting Uvicorn.

Find the PC's LAN IPv4 address by running `ipconfig` and looking for the
active adapter's IPv4 address (for example, `192.168.1.100`). On the PC, open
`http://127.0.0.1:8000/health`; the response should contain
`"model_loaded": true`.

The PC and Raspberry Pi must be on a network that can reach each other. Allow
inbound TCP port 8000 in the PC firewall if the Pi cannot connect.

## 2. Call the API from Raspberry Pi

The Pi only needs to send an image; it does not need the AI model or the API
dependencies. On Raspberry Pi OS, install the HTTP client:

```bash
sudo apt update
sudo apt install -y python3-requests
```

For a Raspberry Pi camera, capture an image and send it to the PC (replace the
IP address with the PC's LAN IPv4 address):

```python
import subprocess
import requests

server_url = "http://192.168.1.100:8000"
image_path = "/tmp/hand.jpg"

subprocess.run(
    ["rpicam-still", "--nopreview", "--timeout", "1000", "--output", image_path],
    check=True,
)

with open(image_path, "rb") as image_file:
    response = requests.post(
        f"{server_url}/predict",
        data=image_file,
        headers={"Content-Type": "image/jpeg"},
        timeout=30,
    )
response.raise_for_status()
prediction = response.json()
print(prediction)
```

You can also skip the camera capture and set `image_path` to an existing
JPEG/PNG file. The API accepts images up to 10 MB. Example response:

```json
{
  "hand_count": 1,
  "predictions": [
    {
      "hand_index": 0,
      "gesture": "Open_Palm",
      "score": 0.98,
      "handedness": "Right"
    }
  ]
}
```

If no hand is detected, `hand_count` is `0` and `predictions` is an empty
array. Keep the service on a trusted network; this example API has no
authentication.
