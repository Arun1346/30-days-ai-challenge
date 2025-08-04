import os
import requests
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from dotenv import load_dotenv
from pydantic import BaseModel
import time

# This line loads the MURF_API_KEY from your .env file
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
    This endpoint returns a MOCK successful response.
    Use this to complete the Day 3 task while waiting for Murf Support.
    """
    print("--- USING MOCK API RESPONSE ---")
    # Simulate a short delay like a real API call
    time.sleep(1) 
    
    # --- FIXED: Using a real, playable MP3 file for the mock response ---
    return {"audio_url": "https://interactive-examples.mdn.mozilla.net/media/cc0-audio/t-rex-roar.mp3"}


if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
