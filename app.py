import os
import requests
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from dotenv import load_dotenv
from pydantic import BaseModel
import time
import shutil

# This line loads the MURF_API_KEY from your .env file
load_dotenv()

app = FastAPI()

# --- Create an 'uploads' directory if it doesn't exist ---
UPLOADS_DIR = "uploads"
os.makedirs(UPLOADS_DIR, exist_ok=True)
# -------------------------------------------------------------

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
def read_root():
    """Serves the main HTML page."""
    with open("templates/index.html", "r") as f:
        return f.read()

# This defines the structure for the text we receive
class SpeechRequest(BaseModel):
    text: str

# --- RE-ENABLING THE MOCK RESPONSE ---
@app.post("/generate-speech")
def generate_speech(request: SpeechRequest):
    """
    This endpoint returns a MOCK successful response for the TTS feature.
    """
    print("--- USING MOCK API RESPONSE ---")
    time.sleep(1) 
    return {"audio_url": "https://interactive-examples.mdn.mozilla.net/media/cc0-audio/t-rex-roar.mp3"}


# --- Endpoint for Day 5 ---
@app.post("/upload-audio")
async def upload_audio(audio_file: UploadFile = File(...)):
    """
    Receives an audio file from the client, saves it to the server,
    and returns details about the file.
    """
    # Define the path where the file will be saved
    file_path = os.path.join(UPLOADS_DIR, audio_file.filename)
    
    # Save the uploaded file to the server
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(audio_file.file, buffer)
        
    # Get file size
    file_size = os.path.getsize(file_path)
    
    # Return the file details as a JSON response
    return {
        "filename": audio_file.filename,
        "content_type": audio_file.content_type,
        "size_kb": round(file_size / 1024, 2)
    }
# ---------------------------------


if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
