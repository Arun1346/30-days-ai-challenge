import os
import requests
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from dotenv import load_dotenv
from pydantic import BaseModel
import time
import assemblyai # Import the new library

# This line loads your API keys from the .env file
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
    This endpoint returns a MOCK successful response for the TTS feature.
    """
    print("--- USING MOCK API RESPONSE ---")
    time.sleep(1) 
    return {"audio_url": "https://interactive-examples.mdn.mozilla.net/media/cc0-audio/t-rex-roar.mp3"}


# --- NEW ENDPOINT FOR DAY 6 ---
@app.post("/transcribe/file")
async def transcribe_file(audio_file: UploadFile = File(...)):
    """
    Receives an audio file, transcribes it using AssemblyAI,
    and returns the transcription text.
    """
    try:
        # Configure the AssemblyAI transcriber with your API key
        assemblyai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")
        transcriber = assemblyai.Transcriber()

        # The SDK can directly transcribe the binary data from the uploaded file
        # We don't need to save the file to disk first
        transcript = transcriber.transcribe(audio_file.file)

        # Check for transcription errors
        if transcript.status == assemblyai.TranscriptStatus.error:
            return {"error": transcript.error}

        # Return the transcribed text
        return {"transcription": transcript.text}

    except Exception as e:
        print(f"Error during transcription: {e}")
        return {"error": "Failed to transcribe audio."}
# ---------------------------------


if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
