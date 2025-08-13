import os
import requests
from fastapi import FastAPI, File, UploadFile, Query
from fastapi.responses import HTMLResponse, JSONResponse
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

# In-memory datastore for chat history
chat_histories = {}

@app.get("/", response_class=HTMLResponse)
def read_root():
    """Serves the main HTML page."""
    with open("templates/index.html", "r") as f:
        return f.read()

# Endpoint to get available voices
@app.get("/voices")
def get_voices():
    try:
        TTS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
        if not TTS_API_KEY:
            raise ValueError("ElevenLabs API key not found.")
        url = "https://api.elevenlabs.io/v1/voices"
        headers = {"xi-api-key": TTS_API_KEY}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching voices: {e}")
        return JSONResponse(status_code=500, content={"error": "Could not fetch voices."})

# Defines the structure for the text we receive for the TTS section
class SpeechRequest(BaseModel):
    text: str
    voice_id: str

@app.post("/generate-speech")
def generate_speech(request: SpeechRequest):
    try:
        TTS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
        if not TTS_API_KEY:
            raise ValueError("ElevenLabs API key not found.")
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
        print(f"Error during TTS generation: {e}")
        return JSONResponse(status_code=500, content={"error": "Failed to generate TTS audio."})

# --- UPDATED CONVERSATIONAL ENDPOINT WITH ERROR HANDLING ---
@app.post("/agent/chat/{session_id}")
async def agent_chat(session_id: str, audio_file: UploadFile = File(...), voice_id: str = Query(...)):
    """
    The main conversational endpoint with robust error handling.
    """
    fallback_audio_url = f"/static/error.mp3?v={time.time()}"
    user_text = "I heard you, but an error occurred." # Default text

    try:
        # Step 1: Transcribe the user's audio (STT)
        print("--- 1. Transcribing User Audio ---")
        assemblyai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")
        if not assemblyai.settings.api_key:
            raise ValueError("AssemblyAI API key not found.")
        
        transcriber = assemblyai.Transcriber()
        transcript = transcriber.transcribe(audio_file.file)

        if transcript.status == assemblyai.TranscriptStatus.error:
            raise Exception(f"STT Error: {transcript.error}")
        
        user_text = transcript.text
        if not user_text:
            # Use a silent audio response if user said nothing.
            return JSONResponse(status_code=200, content={"user_transcription": "[silence]", "ai_response_audio_url": None})
        print(f"--- User said: '{user_text}' ---")

        # Step 2: Get LLM response
        print("--- 2. Getting LLM Response ---")
        GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
        if not GEMINI_API_KEY:
            raise ValueError("Gemini API key not found.")
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        if session_id not in chat_histories:
            chat_histories[session_id] = []
        
        chat = model.start_chat(history=chat_histories[session_id])
        llm_response = chat.send_message(user_text)
        llm_response_text = llm_response.text
        print(f"--- AI says: '{llm_response_text}' ---")
        chat_histories[session_id] = chat.history

        # Step 3: Convert the LLM's text response to speech (TTS)
        print("--- 3. Generating AI Speech ---")
        TTS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
        if not TTS_API_KEY:
            raise ValueError("ElevenLabs API key not found.")
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
        # This block catches any failure in the try block
        print(f"--- ERROR IN AGENT CHAT PIPELINE: {e} ---")
        # On any failure, return the fallback audio and the error message
        return JSONResponse(
            status_code=500,
            content={
                "user_transcription": user_text,
                "ai_response_audio_url": fallback_audio_url,
                "error": str(e)
            }
        )

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)
