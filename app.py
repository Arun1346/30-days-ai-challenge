import os
import requests
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from dotenv import load_dotenv
from pydantic import BaseModel
import time # We'll use this for the mock response

# Load the environment variables from the .env file
load_dotenv()

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
def read_root():
    """Serves the main HTML page."""
    with open("templates/index.html", "r") as f:
        return f.read()

# This defines the structure for the text we receive
class SpeechRequest(BaseModel):
    text: str

@app.post("/generate-speech")
def generate_speech(request: SpeechRequest):
    """
    The main endpoint for Day 2.
    Accepts text and returns a URL to the generated audio file from Murf AI.
    """
    # --- MOCK API FLAG ---
    # Set this to False when the real Murf API is working again
    USE_MOCK_API = True 
    # ---------------------

    if USE_MOCK_API:
        print("--- USING MOCK API RESPONSE ---")
        # Simulate a short delay like a real API call
        time.sleep(1) 
        # Return a fake, successful response
        return {"audio_url": "https://murfaistatus.com/mock-audio-file.mp3"}

    # --- REAL API CALL (will only run if USE_MOCK_API is False) ---
    print("--- ATTEMPTING REAL API CALL ---")
    API_URL = "https://api.murf.ai/v1/speech/generate"
    API_KEY = os.getenv("MURF_API_KEY")

    headers = {
        "Content-Type": "application/json",
        "x-api-key": API_KEY
    }

    payload = {
        "text": request.text,
        "voiceId": "en-US-NateNeural"
    }

    try:
        response = requests.post(API_URL, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        return data
    except requests.exceptions.RequestException as e:
        return {"error": f"API request failed: {e}"}


if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
