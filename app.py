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
import google.generativeai as genai

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

# --- UPDATED ENDPOINT FOR DAY 9 ---
@app.post("/llm/query")
async def llm_query(audio_file: UploadFile = File(...), voice_id: str = Query(...)):
    """
    The full non-streaming pipeline:
    1. Transcribes audio to text.
    2. Sends text to an LLM to get a response.
    3. Converts the LLM's text response back to audio.
    """
    try:
        # Step 1: Transcribe the user's audio
        print("--- Transcribing audio ---")
        assemblyai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")
        transcriber = assemblyai.Transcriber()
        transcript = transcriber.transcribe(audio_file.file)

        if transcript.status == assemblyai.TranscriptStatus.error:
            return {"error": transcript.error}
        
        user_text = transcript.text
        if not user_text:
            return {"error": "Could not understand audio."}
        print(f"--- User said: '{user_text}' ---")

        # Step 2: Send the transcribed text to the Gemini LLM
        print("--- Getting LLM response ---")
        GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # --- FIX: Added a constraint to the prompt for a shorter response ---
        prompt = f"You are Aether, a friendly and helpful AI voice assistant. Answer the following user query in a conversational and informative way, but keep your response concise and under 30 words. User query: '{user_text}'"
        llm_response = model.generate_content(prompt)
        llm_response_text = llm_response.text
        print(f"--- AI says: '{llm_response_text}' ---")

        # Step 3: Convert the LLM's text response to speech using the Murf API
        print(f"--- Generating AI speech with voice {voice_id} ---")
        
        max_chars = 2999
        if len(llm_response_text) > max_chars:
            llm_response_text = llm_response_text[:max_chars]

        TTS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {"Accept": "audio/mpeg", "Content-Type": "application/json", "xi-api-key": TTS_API_KEY}
        payload = {"text": llm_response_text, "model_id": "eleven_multilingual_v2"}
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()

        audio_filename = "response.mp3"
        audio_filepath = os.path.join("static", audio_filename)
        with open(audio_filepath, "wb") as f:
            f.write(response.content)
        
        audio_url = f"/static/{audio_filename}?v={time.time()}"

        # Step 4: Return the final audio URL and the transcription
        return {
            "user_transcription": user_text,
            "ai_response_audio_url": audio_url
        }

    except Exception as e:
        print(f"Error during full pipeline: {e}")
        return {"error": "Failed to process the full request."}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)
