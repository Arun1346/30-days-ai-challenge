# app.py
import os
from fastapi import (
    FastAPI, 
    File, 
    UploadFile, 
    Query, 
    HTTPException, 
    WebSocket, 
    WebSocketDisconnect
)
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
import logging
import uuid

# Import our service and schema modules
from schemas import AgentChatResponse, ErrorResponse
from services import stt, llm, tts

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

# --- Standard HTTP Endpoints ---

@app.get("/", response_class=HTMLResponse)
def read_root():
    """Serves the main HTML page."""
    with open("templates/index.html", "r") as f:
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

# The old /agent/chat endpoint is now effectively replaced by the WebSocket
# but we can leave it for now if we want to switch back for testing.

# --- UPDATED WEBSOCKET ENDPOINT FOR DAY 16 ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    This endpoint handles the streaming audio from the client.
    It receives audio chunks and writes them to a file.
    """
    await websocket.accept()
    logger.info("WebSocket connection established.")
    
    # Generate a unique filename for this recording session
    # The browser will likely send webm format
    output_filename = f"streamed_audio_{uuid.uuid4()}.webm"
    output_filepath = os.path.join("static", output_filename)
    
    try:
        # Open the file in binary write mode
        with open(output_filepath, "wb") as audio_file:
            logger.info(f"Saving incoming audio stream to {output_filepath}")
            while True:
                # Receive binary audio data from the client
                data = await websocket.receive_bytes()
                # Write the chunk to the file
                audio_file.write(data)
                
    except WebSocketDisconnect:
        logger.info(f"Client disconnected. Audio stream saved to {output_filepath}")
    except Exception as e:
        logger.error(f"An error occurred in the WebSocket: {e}")
    finally:
        # The 'with open' statement ensures the file is closed automatically
        logger.info("WebSocket connection closed.")
