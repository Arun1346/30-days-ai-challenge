import os
import requests
from fastapi import FastAPI, File, UploadFile, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from dotenv import load_dotenv
from pydantic import BaseModel
import time
import assemblyai
import google.generativeai as genai # Import the new Gemini library

# Load your API keys from the .env file
load_dotenv()

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
def read_root():
    """Serves the main HTML page."""
    with open("templates/index.html", "r") as f:
        return f.read()

# --- Endpoint to get available voices ---
@app.get("/voices")
def get_voices():
    """Fetches the list of available voices from the TTS API."""
    try:
        TTS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
        url = "https://api.elevenlabs.io/v1/voices"
        headers = {"xi-api-key": TTS_API_KEY}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching voices: {e}")
        return {"error": "Could not fetch voices."}

# This defines the structure for the text we receive for the TTS section
class SpeechRequest(BaseModel):
    text: str
    voice_id: str

@app.post("/generate-speech")
def generate_speech(request: SpeechRequest):
    """Receives text and a voice_id from the UI and generates speech."""
    try:
        TTS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{request.voice_id}"
        headers = {"Accept": "audio/mpeg", "Content-Type": "application/json", "xi-api-key": TTS_API_KEY}
        payload = {"text": request.text, "model_id": "eleven_multilingual_v2", "voice_settings": { "stability": 0.5, "similarity_boost": 0.5 }}
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        audio_filename = "temp_tts.mp3"
        audio_filepath = os.path.join("static", audio_filename)
        with open(audio_filepath, "wb") as f:
            f.write(response.content)
        audio_url = f"/static/{audio_filename}?v={time.time()}"
        return {"audio_url": audio_url}
    except Exception as e:
        print(f"Error during TTS generation: {e}")
        return {"error": "Failed to generate TTS audio."}


@app.post("/tts/echo")
async def tts_echo(audio_file: UploadFile = File(...), voice_id: str = Query(...)):
    """Receives audio and a voice_id, transcribes it, generates speech, and returns the response."""
    try:
        # 1. Transcribe the user's audio
        assemblyai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")
        transcriber = assemblyai.Transcriber()
        transcript = transcriber.transcribe(audio_file.file)
        if transcript.status == assemblyai.TranscriptStatus.error: return {"error": transcript.error}
        transcribed_text = transcript.text
        if not transcribed_text: return {"error": "Could not understand audio."}
        
        # 2. Generate new audio from the transcribed text
        TTS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {"Accept": "audio/mpeg", "Content-Type": "application/json", "xi-api-key": TTS_API_KEY}
        payload = {"text": transcribed_text, "model_id": "eleven_multilingual_v2", "voice_settings": { "stability": 0.5, "similarity_boost": 0.5 }}
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        audio_filename = "temp_echo.mp3"
        audio_filepath = os.path.join("static", audio_filename)
        with open(audio_filepath, "wb") as f:
            f.write(response.content)
        audio_url = f"/static/{audio_filename}?v={time.time()}"
        return {"transcription": transcribed_text, "audio_url": audio_url}
    except Exception as e:
        print(f"Error during echo process: {e}")
        return {"error": "Failed to process audio echo."}

# --- ENDPOINT FOR DAY 8 ---
class LLMQueryRequest(BaseModel):
    text: str

@app.post("/llm/query")
def llm_query(request: LLMQueryRequest):
    """
    Accepts text, sends it to the Gemini LLM, and returns the response.
    """
    try:
        # Configure the Gemini API with  key
        GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
        genai.configure(api_key=GEMINI_API_KEY)

        # --- FIX: Use the latest, correct model name ---
        model = genai.GenerativeModel('gemini-1.5-flash')

        # Send the user's text to the model
        response = model.generate_content(request.text)

        # Return the AI's response text
        return {"response": response.text}

    except Exception as e:
        print(f"Error with Gemini API: {e}")
        return {"error": "Failed to get response from LLM."}
# ---------------------------------


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)
