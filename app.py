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
import uuid

# Load your API keys from the .env file
load_dotenv()

app = FastAPI()

# This makes the 'static' folder available to the browser
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- In-memory datastore for chat history ---
chat_histories = {}
# -------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def read_root():
    """Serves the main HTML page."""
    with open("templates/index.html", "r") as f:
        return f.read()

# --- Endpoint to get available voices ---
@app.get("/voices")
def get_voices():
    try:
        TTS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
        url = "https://api.elevenlabs.io/v1/voices"
        headers = {"xi-api-key": TTS_API_KEY}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": "Could not fetch voices."}

# This defines the structure for the text we receive for the TTS section
class SpeechRequest(BaseModel):
    text: str
    voice_id: str

@app.post("/generate-speech")
def generate_speech(request: SpeechRequest):
    try:
        TTS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{request.voice_id}"
        headers = {"Accept": "audio/mpeg", "Content-Type": "application/json", "xi-api-key": TTS_API_KEY}
        payload = {"text": request.text, "model_id": "eleven_multilingual_v2"}
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        audio_filename = "temp_tts.mp3"
        audio_filepath = os.path.join("static", audio_filename)
        with open(audio_filepath, "wb") as f: f.write(response.content)
        audio_url = f"/static/{audio_filename}?v={time.time()}"
        return {"audio_url": audio_url}
    except Exception as e:
        return {"error": "Failed to generate TTS audio."}

# --- Main Conversational Endpoint for Day 10 ---
@app.post("/agent/chat/{session_id}")
async def agent_chat(session_id: str, audio_file: UploadFile = File(...), voice_id: str = Query(...)):
    """
    The main conversational endpoint with chat history.
    """
    try:
        # 1. Transcribe the user's audio
        assemblyai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")
        transcriber = assemblyai.Transcriber()
        transcript = transcriber.transcribe(audio_file.file)

        if transcript.status == assemblyai.TranscriptStatus.error:
            return {"error": transcript.error}
        
        user_text = transcript.text
        if not user_text:
            return {"error": "Could not understand audio."}
        print(f"--- User said: '{user_text}' ---")

        # 2. Manage Chat History
        if session_id not in chat_histories:
            chat_histories[session_id] = []
        
        # 3. Get LLM response with history
        print("--- Getting LLM response ---")
        GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # The Gemini SDK's `start_chat` method automatically handles history
        chat = model.start_chat(history=chat_histories[session_id])
        llm_response = chat.send_message(user_text)
        llm_response_text = llm_response.text
        print(f"--- AI says: '{llm_response_text}' ---")
        
        # Update our history with the latest messages
        chat_histories[session_id] = chat.history

        # 4. Convert the LLM's text response to speech
        print(f"--- Generating AI speech with voice {voice_id} ---")
        TTS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {"Accept": "audio/mpeg", "Content-Type": "application/json", "xi-api-key": TTS_API_KEY}
        payload = {"text": llm_response_text, "model_id": "eleven_multilingual_v2"}
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()

        audio_filename = f"response_{session_id}.mp3"
        audio_filepath = os.path.join("static", audio_filename)
        with open(audio_filepath, "wb") as f: f.write(response.content)
        audio_url = f"/static/{audio_filename}?v={time.time()}"

        return {
            "user_transcription": user_text,
            "ai_response_audio_url": audio_url
        }

    except Exception as e:
        print(f"Error during agent chat: {e}")
        return {"error": "Failed to process the request."}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)
