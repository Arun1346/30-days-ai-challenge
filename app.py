# app.py
import os
from fastapi import FastAPI, File, UploadFile, Query, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
import logging

# Import our new modules
from schemas import AgentChatResponse, ErrorResponse
from services import stt, llm, tts

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
def read_root():
    """Serves the main HTML page."""
    with open("templates/index.html", "r") as f:
        return f.read()

# --- NEW ENDPOINT TO SERVE THE WEBSOCKET TEST PAGE ---
@app.get("/test-ws", response_class=HTMLResponse)
def get_ws_test_page():
    """Serves a simple HTML page for testing the WebSocket."""
    with open("templates/websocket_test.html", "r") as f:
        return f.read()

@app.get("/voices")
def get_voices_endpoint():
    """
    Endpoint to get available voices.
    This function now transforms the Murf AI voice data into the format
    expected by the frontend JavaScript.
    """
    try:
        murf_voices = tts.get_voices()
        
        # Transform the data structure to match the frontend's expectation
        formatted_voices = []
        for voice in murf_voices:
            # Use the voice name if available, otherwise fall back to the voiceId
            voice_name = voice.get("name") or voice.get("voiceId")
            
            formatted_voices.append({
                "voice_id": voice.get("voiceId"),
                "name": voice_name,
                "labels": {
                    "gender": voice.get("gender")
                }
            })
            
        return {"voices": formatted_voices}
    except Exception as e:
        logger.error(f"Error fetching and formatting voices: {e}")
        raise HTTPException(status_code=500, detail="Could not fetch voices.")

@app.post("/agent/chat/{session_id}", response_model=AgentChatResponse)
async def agent_chat(session_id: str, audio_file: UploadFile = File(...), voice_id: str = Query(...)):
    """
    Main conversational endpoint, now refactored to use services.
    """
    logger.info(f"Received chat request for session: {session_id}")
    fallback_audio_url = f"/static/error.mp3"
    user_text = "I heard you, but an error occurred."

    try:
        # 1. Speech-to-Text
        user_text = stt.transcribe_audio(audio_file)
        if not user_text:
            logger.info("User was silent.")
            return JSONResponse(status_code=200, content={"user_transcription": "[silence]", "ai_response_audio_url": None})

        # 2. Language Model
        llm_response_text = llm.get_llm_response(session_id, user_text)

        # 3. Text-to-Speech
        audio_url = tts.generate_speech_audio(llm_response_text, voice_id, session_id)

        return AgentChatResponse(
            user_transcription=user_text,
            ai_response_text=llm_response_text,
            ai_response_audio_url=audio_url
        )

    except Exception as e:
        logger.error(f"Error in agent chat pipeline for session {session_id}: {e}", exc_info=True)
        # On any failure, return the fallback audio and the error message
        error_response = ErrorResponse(
            user_transcription=user_text,
            ai_response_audio_url=fallback_audio_url,
            error=str(e)
        )
        return JSONResponse(status_code=500, content=error_response.dict())

# --- NEW WEBSOCKET ENDPOINT FOR DAY 15 ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    This endpoint establishes a WebSocket connection and echoes back any message it receives.
    """
    await websocket.accept()
    logger.info("WebSocket connection established.")
    try:
        while True:
            # Wait for a message from the client
            data = await websocket.receive_text()
            logger.info(f"Received message via WebSocket: {data}")
            
            # Send a response back to the client
            await websocket.send_text(f"Server received: {data}")
            
    except WebSocketDisconnect:
        logger.info("Client disconnected from WebSocket.")
    except Exception as e:
        logger.error(f"An error occurred in the WebSocket: {e}")
